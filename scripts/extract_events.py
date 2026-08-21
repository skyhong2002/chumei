"""LLM 活動抽取：inbox 貼文/公告 → 結構化 events。

- 文字＋最多兩張海報圖（base64）一起送 vision 模型。
- 快取鍵 (source_id, post_id, prompt_version)，存 state/extraction/<source_id>.json。
- 非活動貼文快取為空 events，不重複花錢。
"""

import argparse
import base64
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from chumei_lib import iter_inbox, load_env, now_iso, ROOT

PROMPT_VERSION = 2
EXTRACT_DIR = ROOT / "state" / "extraction"

SYSTEM_PROMPT = """你是「竹梅」（清大＋交大校園活動聚合站）的資料抽取引擎。輸入是一則校園社群貼文或公告（含海報圖片），你要判斷它是否在宣傳「有明確時間的實體或線上活動」，並抽出結構化欄位。

輸出 JSON 物件：{"is_event": bool, "events": [Event, ...], "recurrings": [Recurring, ...]}
Recurring＝**例行時段**（每週固定的社課/團練/讀書會）：{"title": "社課", "weekday": 1-7（一=1…日=7）, "time": "19:00" 或 null, "venue": 地點或 null, "note": 補充或 null}。
「每週二 19:00 社課」這類**週期性**資訊放 recurrings、不要放 events；但貼文若同時寫了特定日期的場次（如「第一堂 9/9」），該場次照樣輸出成 Event。
recurrings 門檻：原文必須**明確寫出**確切時間（幾點）和地點，缺一就不要輸出，禁止推算或猜測。沒有就輸出空陣列。
非活動（純心得、招募幹部無活動時間、商品販售、政令宣導、活動回顧/花絮）→ {"is_event": false, "events": []}。
一則貼文可含多場活動（例如社課系列、初選＋決賽）就輸出多個 Event，但同活動多場次若間隔規律可只留最近一場並在 description 註明。

Event 欄位：
- title: 活動名稱（精簡，不含 emoji 與 hashtag）
- summary: ≤60 字摘要
- description: 整理後的活動說明（保留報名方式、費用、對象等重點；不要逐字貼原文）
- start_at / end_at: ISO8601 含 +08:00。年份未寫時，依「貼文日期」推論最近的未來場次（活動宣傳都是預告未來）。只知日期不知時間 → all_day: true 且時間用 00:00。end_at 未知填 null。
- all_day: bool
- campus: 下列之一或 null（判斷不了就 null）：
  nthu-main（清大校本部：旺宏館、大禮堂、風雲樓、水木、蒙民偉樓、綜二、台達館、教育館、體育館、成功湖、小吃部、鴿子廣場）
  nthu-nanda（清大南大校區）
  nycu-guangfu（交大光復校區：浩然圖書館、活動中心、中正堂、工程幾館、科學一館、竹湖、女二餐、二餐、體育館、小木屋）
  nycu-boai（交大博愛校區）
  nycu-yangming（陽明校區）
  online（線上活動）
  other（校外或其他地點）
- venue: 具體地點文字（例：旺宏館 245 教室）；未知 null
- school: nthu | nycu | both | external（活動歸屬；兩校聯合＝both；主辦是來源帳號的學校但地點在他校時，以主辦學校為準）
- organizer: 主辦單位名稱（預設用來源帳號名稱，貼文有更精確主辦就用貼文的）
- organizer_type: official | department | club | external
- category: 演講|工作坊|表演|展覽|比賽|營隊|徵才|市集|運動|聚會|其他
- registration_required: true（需事先報名/填表/購票）| false（自由入場、免報名直接參加）| null（原文未註明）
- registration_url: 報名連結（linktr.ee、forms.gle 等；IG 貼文常寫「連結在 bio」，那樣就填 null）
- registration_deadline: ISO8601 或 null
- price: 費用文字（例：「免費」「200 元」）或 null
- confidence: 0–1，你對「這是活動＋欄位正確」的整體信心。海報字看不清、時間要猜的 → 調低。

規則：
- 已結束的活動（貼文日期看來是回顧）→ is_event: false。
- 「報名／徵才期間」的截止日**不是**活動日期。貼文若只寫報名時段、沒寫活動本身何時舉行 → is_event: false（或該場 start_at: null 且 confidence ≤ 0.4）。
- 「報名開始／開放報名」的時間不可填進 registration_deadline；只有明確的截止（「截止」「止」「額滿為止」不算日期）才填。
- **沒寫的欄位一律 null**：原文沒提費用就 price: null（不要自行填「免費」）；venue、時間同理，禁止腦補。
- registration_url 不可以填這則貼文自己的網址；「連結在 bio／主頁」就填 null。
- organizer 以原文寫的主辦單位為準；社團自營帳號可用帳號名；**絕不可**用公告分類或 feed 名稱（如「藝文活動」）。廠商廣告、純商品團購 → is_event: false。
- 同一貼文含多場次（分區茶會、兩場演出）→ 每場各輸出一個 Event；每日重複的攤位/展覽輸出一個 Event，start_at 用第一天、end_at 用最後一天並 all_day: true。**不可**把「每天 12:30-14:30」攤平成跨日連續區間。
- 多日活動的 end_at 填最後一天（含當天）。
- 全部用臺灣正體中文。輸出只能是 JSON，不要 markdown fence。"""


WEEKDAY_RE = None  # lazily compiled in check_start_at


def check_start_at(ev, item):
    """程式後驗：日期範圍＋星期一致性。回傳 None（通過）或 review 原因字串。"""
    import re
    from datetime import datetime, timedelta
    st = ev.get("start_at")
    if not st:
        return "no start_at"
    try:
        d = datetime.fromisoformat(st)
        posted = datetime.fromisoformat(item["posted_at"])
    except ValueError:
        return "unparseable date"
    if d.tzinfo is None or posted.tzinfo is None:
        return "date missing timezone"
    if not (posted - timedelta(days=60) <= d <= posted + timedelta(days=365)):
        return f"start_at 距貼文日 {(d - posted).days} 天，超出合理範圍"
    # 原文若有「M/D（三）」式星期標記，驗證星期是否吻合（抓年份推論錯誤）
    zh = "一二三四五六日天"
    for m in re.finditer(r"(\d{1,2})\s*[/月]\s*(\d{1,2})[日號]?\s*[（(]\s*[週周]?([一二三四五六日天])\s*[)）]", item["text"]):
        mo, day, wd = int(m.group(1)), int(m.group(2)), m.group(3)
        if (mo, day) == (d.month, d.day):
            expect = min(zh.index(wd), 6)
            if d.weekday() != expect:
                return f"{mo}/{day} 原文標（{wd}）但抽出日期是週{zh[d.weekday()]}，年份可能推錯"
    return None


def _load_cache(source_id):
    path = EXTRACT_DIR / f"{source_id}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _save_cache(source_id, cache, lock):
    with lock:
        EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
        path = EXTRACT_DIR / f"{source_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
        tmp.replace(path)


def fetch_image_b64(url, max_bytes=8_000_000):
    """下載並縮到 1024px JPEG 再 base64 — 控制 vision token 用量。"""
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (chumei.observe.tw fetcher)"})
        r.raise_for_status()
        if len(r.content) > max_bytes or not r.headers.get("content-type", "").startswith("image/"):
            return None
        try:
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            im.thumbnail((1024, 1024))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
            data, ctype = buf.getvalue(), "image/jpeg"
        except Exception:
            ctype = r.headers["content-type"].split(";")[0]
            if ctype not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                return None  # SVG 等 OpenAI 不支援的格式
            data = r.content
        return f"data:{ctype};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return None


def user_prompt(item, retry_note=None):
    return (
        f"來源：{item['source_name']}（{item['school']}／{item['org_type']}／{item['platform']}）\n"
        f"貼文日期：{item['posted_at']}\n貼文連結：{item['url']}\n\n貼文內容：\n{item['text'][:6000]}"
        + (f"\n\n（上次輸出無法解析，這次{retry_note}）" if retry_note else "")
    )


def fetch_image_file(url, dest_dir, idx, max_bytes=8_000_000):
    """下載並縮圖成 jpg 檔（給 codex exec -i 用）。回傳路徑或 None。"""
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (chumei.observe.tw fetcher)"})
        r.raise_for_status()
        if len(r.content) > max_bytes or not r.headers.get("content-type", "").startswith("image/"):
            return None
        import io
        from pathlib import Path
        from PIL import Image
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((1024, 1024))
        path = Path(dest_dir) / f"img{idx}.jpg"
        im.save(path, "JPEG", quality=80)
        return str(path)
    except Exception:
        return None


def call_llm_codex(env, item, retry_note=None):
    """走 Codex CLI（訂閱制），--output-schema 強制結構化輸出。"""
    import subprocess
    import tempfile
    schema = str(ROOT / "scripts" / "extract_schema.json")
    with tempfile.TemporaryDirectory(prefix="chumei-ext-") as td:
        cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
               "--output-schema", schema, "-o", f"{td}/out.json"]
        model = env.get("CHUMEI_CODEX_MODEL")
        if model:
            cmd += ["-m", model]
        for idx, img_url in enumerate((item.get("images") or [])[:2]):
            p = fetch_image_file(img_url, td, idx)
            if p:
                cmd += ["-i", p]
        # prompt 走 stdin：-i 是變長參數，positional prompt 會被它吞掉
        prompt = SYSTEM_PROMPT + "\n\n---\n" + user_prompt(item, retry_note)
        r = subprocess.run(cmd, cwd=td, capture_output=True, text=True,
                           timeout=420, input=prompt)
        if r.returncode != 0:
            raise RuntimeError(f"codex exec rc={r.returncode}: {r.stderr[-200:]}")
        with open(f"{td}/out.json") as f:
            return f.read()


def call_llm(env, item, retry_note=None):
    if env.get("CHUMEI_LLM_BACKEND") == "codex":
        return call_llm_codex(env, item, retry_note)
    content = [{"type": "text", "text": user_prompt(item, retry_note)}]
    for img_url in (item.get("images") or [])[:2]:
        b64 = fetch_image_b64(img_url)
        if b64:
            content.append({"type": "image_url", "image_url": {"url": b64}})
    payload = {
        "model": env.get("CHUMEI_LLM_MODEL", "gpt-5.4-mini"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    for attempt in range(5):
        resp = requests.post(
            f"{env['CHUMEI_LLM_BASE_URL']}/chat/completions",
            headers={"Authorization": f"Bearer {env['CHUMEI_LLM_API_KEY']}"},
            json=payload, timeout=180,
        )
        if resp.status_code in (429, 500, 502, 503) and attempt < 4:
            import random
            time.sleep(min(120, 8 * (2 ** attempt)) + random.uniform(0, 4))
            continue
        if resp.status_code == 400:
            raise RuntimeError(f"400: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError("rate-limited after retries")


def model_name(env):
    if env.get("CHUMEI_LLM_BACKEND") == "codex":
        return "codex/" + (env.get("CHUMEI_CODEX_MODEL") or "default")
    return env.get("CHUMEI_LLM_MODEL")


def process_item(env, item, lock, caches):
    source_id, post_id = item["source_id"], item["post_id"]
    raw = None
    try:
        raw = call_llm(env, item)
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(call_llm(env, item, retry_note="請輸出合法 JSON"))
        except Exception as e:
            return source_id, post_id, {"error": f"{e} raw={str(raw)[:200]}", "prompt_version": PROMPT_VERSION, "ts": now_iso()}
    except Exception as e:
        return source_id, post_id, {"error": str(e)[:300], "prompt_version": PROMPT_VERSION, "ts": now_iso()}

    events = []
    for i, ev in enumerate(parsed.get("events") or []):
        conf = float(ev.get("confidence") or 0.5)
        if ev.get("registration_url") and ev["registration_url"].rstrip("/") == (item.get("url") or "").rstrip("/"):
            ev["registration_url"] = None  # 禁止自我指涉的報名連結
        review_reason = check_start_at(ev, item)
        needs_review = conf < 0.7 or review_reason is not None
        events.append({
            "id": "evt_" + hashlib.sha1(f"{source_id}|{post_id}|{i}".encode()).hexdigest()[:12],
            "title": ev.get("title") or "(未命名活動)",
            "summary": ev.get("summary") or "",
            "description": ev.get("description") or "",
            "start_at": ev.get("start_at"),
            "end_at": ev.get("end_at"),
            "all_day": bool(ev.get("all_day")),
            "campus": ev.get("campus"),
            "venue": ev.get("venue"),
            "school": ev.get("school") or item["school"],
            "organizer": ev.get("organizer") or item["source_name"],
            "organizer_type": ev.get("organizer_type") or item["org_type"],
            "category": ev.get("category") or "其他",
            "registration_required": ev.get("registration_required"),
            "registration_url": ev.get("registration_url"),
            "registration_deadline": ev.get("registration_deadline"),
            "price": ev.get("price"),
            "source": {"platform": item["platform"], "url": item["url"], "source_id": source_id, "post_id": post_id},
            "poster_image": item.get("image_url"),
            "extraction": {
                "model": model_name(env), "confidence": conf,
                "needs_review": needs_review, "prompt_version": PROMPT_VERSION,
                **({"review_reason": review_reason} if review_reason else {}),
            },
            "status": "review" if needs_review else "published",
        })
    recurrings = []
    for rc in (parsed.get("recurrings") or []):
        try:
            wd = int(rc.get("weekday"))
        except (TypeError, ValueError):
            continue
        # 使用者要求：確切時間＋地點都有才算，不能推算
        if 1 <= wd <= 7 and rc.get("title") and rc.get("time") and rc.get("venue"):
            recurrings.append({"title": rc["title"], "weekday": wd, "time": rc.get("time"),
                               "venue": rc.get("venue"), "note": rc.get("note"),
                               "source": {"platform": item["platform"], "url": item["url"],
                                          "source_id": source_id, "post_id": post_id}})
    return source_id, post_id, {
        "prompt_version": PROMPT_VERSION, "ts": now_iso(),
        "model": model_name(env), "events": events, "recurrings": recurrings,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="這一輪最多處理幾筆（0=全部）")
    ap.add_argument("--source", help="只處理這個 source_id")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--retry-errors", action="store_true", help="重跑之前出錯的項目")
    args = ap.parse_args()

    env = load_env()
    if not env.get("CHUMEI_LLM_API_KEY"):
        print("missing CHUMEI_LLM_API_KEY", file=sys.stderr)
        return 1

    caches, todo = {}, []
    for item in iter_inbox():
        if item["raw_source"] == "nycu-life-api":
            continue
        if args.source and item["source_id"] != args.source:
            continue
        sid = item["source_id"]
        if sid not in caches:
            caches[sid] = _load_cache(sid)
        hit = caches[sid].get(item["post_id"])
        if hit and hit.get("prompt_version") == PROMPT_VERSION:
            if "error" not in hit or not args.retry_errors:
                continue
        todo.append(item)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} items to extract")

    lock = threading.Lock()
    n_events = n_err = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process_item, env, it, lock, caches) for it in todo]
        for i, fut in enumerate(as_completed(futures)):
            sid, pid, result = fut.result()
            caches[sid][pid] = result
            _save_cache(sid, caches[sid], lock)
            if "error" in result:
                n_err += 1
                print(f"  [{i+1}/{len(todo)}] {sid}/{pid}: ERROR {result['error'][:100]}", file=sys.stderr)
            else:
                k = len(result["events"])
                n_events += k
                if k:
                    print(f"  [{i+1}/{len(todo)}] {sid}/{pid}: {k} event(s) — {result['events'][0]['title']}")
    print(f"done: {n_events} events extracted, {n_err} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
