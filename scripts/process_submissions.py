"""連結回報審核：登入者貼的連結 → 判讀 → 進 inbox 走既有抽取管線。

每一筆 pending：
1. 先用程式比對：已在 inbox／events 裡的貼文直接回「已收錄」。帳號主頁比對名錄，
   已追蹤的回「已收錄」；沒追蹤的抓最近貼文交給 Codex 審，過了就直接寫進 registry CSV
   （站長不用再確認一次），下一輪抓取就開始收錄。
2. 抓頁面內容（IG 貼文走 instaloader，其餘 og tags＋正文；文字太少就截圖）。
3. Codex 判讀：相關嗎？新活動、對上既有活動、還是不收。信心不足留人工。
4. new_event → append data/feeds/inbox/user_submission.jsonl，接著只對這個來源跑
   extract_events；抽到活動就「已收錄，等待上線」，等下次 build 後對回 events.json 換成「已上線」。

launchd 每 15 分鐘跑一輪（tw.observe.chumei.submissions）；也可手動 `--dry-run` 看判讀結果。
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests

from chumei_lib import ROOT, TZ_TAIPEI, append_inbox, iter_inbox, load_env, now_iso, read_sources_csv
from submissions import MAX_ATTEMPTS, SubmissionStore, classify_url, normalize_url

SOURCE_ID = "user_submission"
EVENTS_JSON = ROOT / "site" / "api" / "events.json"
STATE_DIR = ROOT / "state" / "submissions"
MANUAL_REVIEW = STATE_DIR / "manual_review.jsonl"
EXTRACT_CACHE = ROOT / "state" / "extraction" / f"{SOURCE_ID}.json"
SCHEMA = ROOT / "scripts" / "submission_schema.json"
SOURCE_SCHEMA = ROOT / "scripts" / "source_schema.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36 chumei.observe.tw"
MIN_TEXT_FOR_NO_SCREENSHOT = 120
CONFIDENCE_FLOOR = 0.6
# classify_url 用 twitter，registry CSV 用 x
CSV_TO_KIND = {"x": "twitter"}
KIND_TO_CSV = {"instagram": "instagram", "facebook": "facebook", "threads": "threads", "twitter": "x"}
# 各平台的 registry 檔；沒列到的走 social_accounts.csv（第一欄多一個 platform）
REGISTRY_FILES = {"instagram": "ig_accounts.csv", "facebook": "fb_pages.csv"}

TRIAGE_PROMPT = """你是「竹梅活動觀測站」（清大＋陽明交大校園活動聚合站）的收件審核員。有使用者回報了一個連結，附上抓到的頁面內容（可能還有截圖或海報）。請判斷這個連結該怎麼處理。

判斷標準：
- relevant：內容是否為「清大或陽明交大的學生／單位會參加的公開活動資訊」（演講、社課、表演、比賽、營隊、市集、徵才…）。純商業廣告、與兩校無關的活動、個人動態、抱怨文、已結束活動的回顧 → relevant: false。
- action：
  - "attach_to_existing"：候選活動清單裡已經有同一場活動（同名或明顯同一場、日期相同或相近）→ 填 matched_event_id。
  - "new_event"：相關、且候選清單裡沒有 → 交給下游抽取欄位（你不用抽時間地點）。
  - "reject"：不相關、抓不到有意義的內容、或只是帳號主頁而非單篇內容。
- organizer：主辦單位名稱（依內容判斷；不確定填 null）。
- school：主辦歸屬 nthu／nycu／both／external（校外單位辦給兩校學生的填 external）。
- org_type：official（校方）／department（系所）／club（社團）／external。
- posted_at：內容裡看得出的發文／公告日期（ISO8601，含 +08:00），看不出填 null。
- reason：一句話給回報者看的理由（臺灣正體中文，≤60 字，不要提到「候選清單」這類內部詞）。
- confidence：0–1，對整體判斷的信心；內容零碎、看不清、要猜的 → 調低。
輸出只能是 JSON。"""

SOURCE_PROMPT = """你是「竹梅活動觀測站」（清大＋陽明交大校園活動聚合站）的來源審核員。有使用者回報了一個社群帳號主頁，希望竹梅長期追蹤它的貼文。附上帳號的顯示名稱與最近幾則貼文。請判斷要不要收進追蹤清單。

判斷標準：
- relevant：這個帳號是否會持續發布「清大或陽明交大的學生看得到、去得了的公開活動資訊」（系所、系學會、社團、學生自治組織、校方單位、校園媒體，以及辦活動給兩校學生的校外單位）。個人帳號、與兩校無關的商家或粉專、只發迷因且從不預告活動 → relevant: false。貼文量少但明顯是兩校的正式單位 → 仍然可以收。
- name：這個單位對外的正式名稱（臺灣正體中文）。顯示名稱含花字、口號或表情符號時整理成乾淨的單位名。
- school：nthu／nycu／both／external。跨兩校的填 both；校外單位填 external。
- org_type：official（校方單位）／department（系所）／club（社團、系學會、學生自治、學生自媒體）／external（校外單位或商家）。
- category_hint：二到五個字的分類提示（例如 學術性、運動、校園媒體、系學會、校園商家）；判斷不出填 null。
- reason：一句話給回報者看的理由（臺灣正體中文，≤60 字）。
- confidence：0–1。抓不到貼文、看不出跟兩校的關係、要用猜的 → 調低。
輸出只能是 JSON。"""


# ---------- 索引：既有 inbox／events／名錄 ----------

def _ig_shortcode(url):
    m = re.search(r"instagram\.com/(?:p|reel|reels|tv)/([\w-]+)", url or "")
    return m.group(1) if m else None


def load_events_index():
    if not EVENTS_JSON.exists():
        return {"by_id": {}, "by_source": {}, "by_url": {}, "events": [], "generated_at": ""}
    data = json.loads(EVENTS_JSON.read_text())
    events = data.get("events", [])
    by_id, by_source, by_url = {}, {}, {}
    for e in events:
        by_id[e["id"]] = e
        src = e.get("source") or {}
        by_source.setdefault((src.get("source_id"), src.get("post_id")), []).append(e["id"])
        nu = normalize_url(src.get("url"))
        if nu:
            by_url.setdefault(nu, []).append(e["id"])
    return {"by_id": by_id, "by_source": by_source, "by_url": by_url, "events": events,
            "generated_at": data.get("generated_at", "")}


def load_inbox_index():
    by_url, by_shortcode = {}, {}
    for it in iter_inbox():
        key = (it["source_id"], it["post_id"])
        nu = normalize_url(it.get("url"))
        if nu:
            by_url.setdefault(nu, key)
        sc = _ig_shortcode(it.get("url"))
        if sc:
            by_shortcode.setdefault(sc, key)
    return by_url, by_shortcode


def load_tracked_handles():
    from fetch_facebook import page_slug

    handles = {"instagram": set(), "facebook": set(), "threads": set(), "twitter": set()}
    for r in read_sources_csv("ig_accounts.csv"):
        handles["instagram"].add(r["username"].strip().lstrip("@").lower())
    for r in read_sources_csv("fb_pages.csv"):
        handles["facebook"].add(page_slug(r["page"]))
    # registry 的 x 對應 classify_url 的 twitter，不對齊的話已追蹤的 X 帳號會被判成沒收錄
    for r in read_sources_csv("social_accounts.csv"):
        platform = r["platform"].strip().lower()
        handles.setdefault(CSV_TO_KIND.get(platform, platform), set()).add(
            r["username"].strip().lstrip("@").lower())
    return handles


def load_org_index():
    """source_id → 名錄 id（site/data/sources.json 的 sids），帳號類回報用來回單位頁連結。"""
    path = ROOT / "site" / "data" / "sources.json"
    if not path.exists():
        return {}
    out = {}
    for entry in json.loads(path.read_text()).get("entries", []):
        for sid in entry.get("sids") or []:
            out.setdefault(sid, entry["id"])
    return out


def source_id_for(info):
    prefix = {"instagram": "ig", "facebook": "fb", "threads": "threads", "twitter": "twitter"}.get(info["platform"])
    return f"{prefix}_{info['handle']}" if prefix and info.get("handle") else None


def org_url(orgs, info):
    org_id = orgs.get(source_id_for(info) or "")
    return f"/org/{org_id}/" if org_id else None


def event_url(event_id):
    return f"/event/{event_id}/"


# ---------- 抓內容 ----------

def _strip_tags(s):
    s = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s)
    s = re.sub(r"[ \t　]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _meta(html, prop):
    for attr in ("property", "name"):
        m = re.search(rf'<meta[^>]+{attr}=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)["\']', html, re.I)
        if not m:
            m = re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+{attr}=["\']{re.escape(prop)}["\']', html, re.I)
        if m:
            return html_lib.unescape(m.group(1)).strip()
    return ""


def _http_get(url):
    headers = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"}
    try:
        return requests.get(url, timeout=25, headers=headers, allow_redirects=True)
    except requests.exceptions.SSLError:
        # 兩校不少站的憑證缺 Subject Key Identifier（同 fetch_infonews），放寬 strict flag 再試
        from fetch_infonews import _RelaxedAdapter
        session = requests.Session()
        session.mount("https://", _RelaxedAdapter())
        return session.get(url, timeout=25, headers=headers, allow_redirects=True)


def fetch_generic(url):
    r = _http_get(url)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if not ctype.startswith("text/html"):
        return {"title": urlsplit(url).path.rsplit("/", 1)[-1], "text": "", "images": [],
                "posted_at": None, "final_url": r.url, "note": f"非 HTML（{ctype.split(';')[0]}）"}
    page = r.text
    title = _meta(page, "og:title") or _strip_tags(re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I).group(1)
                                                   if re.search(r"<title", page, re.I) else "")
    desc = _meta(page, "og:description") or _meta(page, "description")
    body_html = re.search(r"<body[^>]*>(.*)</body>", page, re.S | re.I)
    body = _strip_tags(body_html.group(1) if body_html else page)
    text = "\n".join(x for x in (desc, body) if x)
    images = [u for u in (_meta(page, "og:image"),) if u.startswith("http")]
    posted = _meta(page, "article:published_time") or None
    return {"title": title, "text": text[:6000], "images": images, "posted_at": posted,
            "final_url": r.url, "note": None}


def fetch_instagram_post(shortcode):
    from fetch_stories import load_session
    import instaloader
    L = load_session()
    post = instaloader.Post.from_shortcode(L.context, shortcode)
    images = []
    if post.typename == "GraphSidecar":
        images = [n.display_url for n in post.get_sidecar_nodes()][:4]
    else:
        images = [post.url]
    return {
        "title": f"@{post.owner_username}",
        "text": post.caption or "（純圖片貼文，內容見海報）",
        "images": images,
        "posted_at": post.date_utc.replace(tzinfo=None).isoformat(timespec="seconds") + "+00:00",
        "final_url": f"https://www.instagram.com/p/{shortcode}/",
        "handle": post.owner_username,
        "note": None,
    }


def screenshot(url, dest_dir):
    """文字抓不到時整頁截圖給模型看；沒 Chrome／playwright 就跳過。"""
    try:
        from playwright.sync_api import sync_playwright
        from render_source_covers import _chrome_path
    except ImportError:
        return None
    chrome = _chrome_path()
    if not chrome:
        return None
    out = Path(dest_dir) / "page.jpg"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chrome, headless=True)
            ctx = browser.new_context(viewport={"width": 1000, "height": 1400}, locale="zh-TW",
                                      user_agent=UA, ignore_https_errors=True)
            page = ctx.new_page()
            page.set_default_navigation_timeout(30_000)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out), type="jpeg", quality=80, full_page=False)
            ctx.close()
            browser.close()
        return str(out)
    except Exception as exc:  # noqa: BLE001
        print(f"  screenshot fail {url}: {str(exc)[:120]}", file=sys.stderr)
        return None


def fetch_content(url, info):
    if info["kind"] == "ig_post":
        try:
            return fetch_instagram_post(info["post_id"])
        except Exception as exc:  # noqa: BLE001
            print(f"  instaloader fail {url}: {str(exc)[:120]}", file=sys.stderr)
    return fetch_generic(url)


# ---------- Codex 判讀 ----------

def _bigrams(s):
    s = re.sub(r"[\W_]+", "", (s or "").lower())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s} if s else set()


def candidate_events(index, content, limit=12):
    """依標題／正文 bigram 重疊挑候選；只看最近與未來的活動。"""
    cutoff = (datetime.now(TZ_TAIPEI) - timedelta(days=14)).isoformat()
    probe = _bigrams((content.get("title") or "") + " " + (content.get("text") or "")[:400])
    scored = []
    for e in index["events"]:
        if (e.get("start_at") or "") < cutoff:
            continue
        grams = _bigrams(e.get("title", "")) | _bigrams(e.get("organizer", ""))
        if not grams:
            continue
        overlap = len(grams & probe) / len(grams)
        if overlap >= 0.3:
            scored.append((overlap, e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def triage_with_codex(env, url, info, content, candidates, image_paths):
    cand_lines = "\n".join(
        f"- {e['id']}｜{(e.get('start_at') or '')[:10]}｜{e['title']}｜{e.get('organizer') or ''}"
        for e in candidates
    ) or "（沒有相近的既有活動）"
    user = (
        f"回報的連結：{url}\n連結類型：{info['kind']}\n"
        f"頁面標題：{content.get('title') or ''}\n"
        f"頁面日期：{content.get('posted_at') or '未知'}\n"
        f"{('備註：' + content['note']) if content.get('note') else ''}\n\n"
        f"頁面內容：\n{(content.get('text') or '（抓不到文字）')[:6000]}\n\n"
        f"候選的既有活動：\n{cand_lines}"
    )
    with tempfile.TemporaryDirectory(prefix="chumei-sub-") as td:
        cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
               "--output-schema", str(SCHEMA), "-o", f"{td}/out.json"]
        model = env.get("CHUMEI_CODEX_MODEL")
        if model:
            cmd += ["-m", model]
        for p in image_paths[:3]:
            cmd += ["-i", p]
        # prompt 走 stdin：-i 是變長參數會吞掉 positional prompt
        r = subprocess.run(cmd, cwd=td, capture_output=True, text=True, timeout=420,
                           input=TRIAGE_PROMPT + "\n\n---\n" + user)
        if r.returncode != 0:
            raise RuntimeError(f"codex exec rc={r.returncode}: {r.stderr[-200:]}")
        return json.loads(Path(f"{td}/out.json").read_text())


# ---------- 帳號主頁：自動審核並收進追蹤名單 ----------

RSSHUB_ACCOUNT_ROUTES = {"instagram": "/instagram/2/user/{u}", "threads": "/threads/{u}",
                         "twitter": "/twitter/user/{u}"}


def _rss_preview(text, limit=8):
    """RSS → (頻道標題, 最近貼文摘要)。只取判讀要看的欄位，不去耦合各 fetcher 的解析器。"""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.S)
    m = re.search(r"<title>(.*?)</title>", text, re.S)
    title = _strip_tags(html_lib.unescape(m.group(1))) if m else ""
    posts = []
    for item in list(re.finditer(r"<item>(.*?)</item>", text, re.S))[:limit]:
        body = item.group(1)
        when = re.search(r"<pubDate>(.*?)</pubDate>", body, re.S)
        desc = re.search(r"<description>(.*?)</description>", body, re.S)
        txt = _strip_tags(html_lib.unescape(desc.group(1))) if desc else ""
        if txt:
            posts.append(f"{when.group(1)[:16] if when else ''}｜{txt[:240]}")
    return title, posts


class AccountNotFound(Exception):
    """RSSHub 明確回報查無此帳號——跟「路由暫時壞掉」是兩回事。"""


def fetch_account_preview(url, info, env):
    """回傳 (顯示名稱, 最近貼文摘要)。

    IG／Threads／X 走本地 RSSHub：那正是之後排程抓這個帳號會走的路。只有 RSSHub 明講
    NotFoundError 才算帳號不存在；其他失敗（IG 登入流程整條掛掉時每個帳號都會 503）
    一律往外拋讓上層重試——把暫時性故障當成「這個帳號不能收」會冤枉掉正常的投稿。
    FB 沒有免費路由，退回頁面 og tags。
    """
    from fetch_instagram import rsshub_error
    route = RSSHUB_ACCOUNT_ROUTES.get(info["platform"])
    if route:
        base = env.get("CHUMEI_RSSHUB_BASE", "http://127.0.0.1:1200")
        resp = requests.get(base + route.format(u=info["handle"]), params={"limit": 8},
                            timeout=(10, 60))
        if resp.status_code == 200 and b"<rss" in resp.content[:200]:
            return _rss_preview(resp.text)
        error = rsshub_error(resp)
        if error and "NotFoundError" in str(error):
            raise AccountNotFound(str(error))
        raise error or RuntimeError(f"RSSHub 沒回傳 RSS（HTTP {resp.status_code}）")
    page = fetch_generic(url)
    body = (page.get("text") or "")[:1500]
    return (page.get("title") or ""), ([body] if body else [])


def review_source_with_codex(env, url, info, name, posts, note):
    listing = "\n".join(f"- {p}" for p in posts[:8]) or "（抓不到貼文）"
    user = (
        f"回報的帳號：{url}\n平台：{info['platform']}\n帳號代號：@{info['handle']}\n"
        f"顯示名稱：{name or '（抓不到）'}\n"
        f"{('回報者備註：' + note) if note else ''}\n\n最近的貼文：\n{listing[:6000]}"
    )
    with tempfile.TemporaryDirectory(prefix="chumei-src-") as td:
        cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
               "--output-schema", str(SOURCE_SCHEMA), "-o", f"{td}/out.json"]
        model = env.get("CHUMEI_CODEX_MODEL")
        if model:
            cmd += ["-m", model]
        r = subprocess.run(cmd, cwd=td, capture_output=True, text=True, timeout=420,
                           input=SOURCE_PROMPT + "\n\n---\n" + user)
        if r.returncode != 0:
            raise RuntimeError(f"codex exec rc={r.returncode}: {r.stderr[-200:]}")
        return json.loads(Path(f"{td}/out.json").read_text())


def add_tracked_source(info, verdict, sub_id):
    """通過審核的帳號寫進對應的 registry CSV；回傳檔名。"""
    platform = KIND_TO_CSV[info["platform"]]
    reason = (verdict.get("reason") or "").strip()
    note = (f"{now_iso()[:10]} 使用者回報 {sub_id}：自動審核通過"
            + (f"（{reason}）" if reason else ""))
    tail = [verdict["name"], verdict["school"], verdict["org_type"],
            verdict.get("category_hint") or "", "true", note]
    fname = REGISTRY_FILES.get(platform)
    row = [info["handle"]] + tail if fname else [platform, info["handle"]] + tail
    fname = fname or "social_accounts.csv"
    with (ROOT / "data" / "sources" / fname).open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    return fname


def review_account(sub, url, info, ctx, finish, dry_run):
    """帳號主頁不進人工佇列：審過就直接進追蹤名單，下一輪抓取開始收錄。"""
    env = ctx["env"]
    try:
        name, posts = fetch_account_preview(url, info, env)
    except AccountNotFound:
        return finish("rejected", "找不到這個帳號，可能已改名、刪除或設為不公開。")
    if not name and not posts:
        return finish("rejected", "抓不到這個帳號的公開內容，沒辦法判斷。")
    verdict = review_source_with_codex(env, url, info, name, posts, sub.get("note"))
    verdict_json = json.dumps(verdict, ensure_ascii=False)
    reason = (verdict.get("reason") or "").strip() or "系統判讀完成。"
    conf = float(verdict.get("confidence") or 0)
    print(f"  source relevant={verdict.get('relevant')} conf={conf:.2f} :: {reason}")
    if conf < CONFIDENCE_FLOOR:
        if not dry_run:
            _append_jsonl(MANUAL_REVIEW, {"ts": now_iso(), "submission": sub["id"], "url": url,
                                          "verdict": verdict, "note": sub.get("note") or ""})
        return finish("manual", "系統不太確定這個帳號，已交給站長人工確認。", verdict=verdict_json)
    if not verdict.get("relevant"):
        return finish("rejected", reason, verdict=verdict_json)
    # 單位頁通常要等下次建站才會有；先試著對，沒有的話 settle_source_added 之後補
    link = org_url(ctx["orgs"], info)
    if dry_run:
        return finish("source_added", reason, verdict=verdict_json, event_url=link)
    fname = add_tracked_source(info, verdict, sub["id"])
    ctx["handles"].setdefault(info["platform"], set()).add(info["handle"])
    print(f"  + {fname}: {info['platform']} @{info['handle']} → {verdict['name']}")
    return finish("source_added",
                  f"已加入追蹤清單（{verdict['name']}），之後的新貼文會自動收錄。",
                  verdict=verdict_json, event_url=link)


# ---------- 落地 ----------

def _append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _valid_iso(value):
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except (TypeError, ValueError):
        return False


def write_inbox_item(sub, url, info, content, verdict):
    posted = verdict.get("posted_at") if _valid_iso(verdict.get("posted_at")) else None
    posted = posted or (content.get("posted_at") if _valid_iso(content.get("posted_at")) else None) or now_iso()
    text = content.get("text") or ""
    if content.get("title") and content["title"] not in text[:200]:
        text = f"{content['title']}\n\n{text}"
    if sub.get("note"):
        text += f"\n\n（回報者備註：{sub['note']}）"
    item = {
        "source_id": SOURCE_ID,
        "source_name": verdict.get("organizer") or content.get("handle") or content.get("title") or "使用者回報",
        "platform": info["platform"],
        "raw_source": SOURCE_ID,
        "school": verdict.get("school") or "both",
        "org_type": verdict.get("org_type") or "club",
        "post_id": sub["id"],
        "url": url,
        "posted_at": posted,
        "text": text[:8000],
        "fetched_at": now_iso(),
        "images": [u for u in (content.get("images") or []) if u.startswith("http")][:4],
    }
    append_inbox(SOURCE_ID, [item])


def run_extract():
    py = ROOT / ".venv" / "bin" / "python"
    py = py if py.exists() else Path(sys.executable)
    r = subprocess.run([str(py), str(ROOT / "scripts" / "extract_events.py"), "--source", SOURCE_ID],
                       timeout=1800, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  extract failed: {r.stderr[-300:]}", file=sys.stderr)
    return r.returncode == 0


def extracted_events_for(sub_id):
    if not EXTRACT_CACHE.exists():
        return None
    rec = json.loads(EXTRACT_CACHE.read_text()).get(sub_id)
    if not rec or "error" in rec:
        return None
    return rec.get("events", [])


# ---------- 主流程 ----------

def process_one(store, sub, ctx, dry_run=False):
    url = normalize_url(sub["url"]) or sub["url"]
    info = classify_url(url)
    index, (inbox_by_url, inbox_by_sc), handles, env = ctx["events"], ctx["inbox"], ctx["handles"], ctx["env"]

    def finish(status, reason, **kw):
        print(f"  {sub['id']} → {status}: {reason}")
        if not dry_run:
            store.update(sub["id"], status, reason, **kw)

    if info["kind"] == "chumei":
        return finish("rejected", "這已經是竹梅站內的頁面。")
    if info["kind"] == "fb_group":
        return finish("manual", "Facebook 社團內容需要登入才看得到，已交給站長人工處理。")

    # 帳號主頁：比對名錄，不進 LLM
    if info["kind"] in ("ig_profile", "fb_page", "threads_profile", "x_profile"):
        tracked = handles.get(info["platform"], set())
        if info["handle"] in tracked:
            return finish("existing", "這個帳號已經在竹梅的追蹤清單裡，新貼文會自動收錄。",
                          event_url=org_url(ctx["orgs"], info))
        try:
            return review_account(sub, url, info, ctx, finish, dry_run)
        except Exception as exc:  # noqa: BLE001
            if sub["attempts"] + 1 < MAX_ATTEMPTS:
                return finish("pending", f"暫時讀不到這個帳號（{str(exc)[:80]}），稍後重試。",
                              bump_attempts=True)
            # 一直讀不到多半是抓取管線的問題，不是這個帳號的錯：交給站長，不要默默丟掉
            if not dry_run:
                _append_jsonl(MANUAL_REVIEW, {"ts": now_iso(), "submission": sub["id"], "url": url,
                                              "error": str(exc)[:200], "note": sub.get("note") or ""})
            return finish("manual", "一直讀不到這個帳號的內容，已交給站長確認。", bump_attempts=True)

    # 單篇內容：已在 inbox／events 裡就直接對回
    key = inbox_by_url.get(url) or (inbox_by_sc.get(info["post_id"]) if info["kind"] == "ig_post" else None)
    if key:
        ids = index["by_source"].get(key) or []
        if ids:
            return finish("existing", "這則內容已經收錄在竹梅。", event_url=event_url(ids[0]))
        if key[0] == SOURCE_ID:
            pass  # 前一次回報寫進 inbox 但還沒建站，往下走正常流程會再次 dedupe
        else:
            return finish("not_event", "這則內容竹梅之前已經看過，但沒有辨識出有明確時間的活動。",
                          event_url=f"/org/{ctx['orgs'][key[0]]}/" if key[0] in ctx["orgs"] else None)

    # 抓內容 → Codex 判讀
    try:
        content = fetch_content(url, info)
    except Exception as exc:  # noqa: BLE001
        return finish("pending" if sub["attempts"] + 1 < MAX_ATTEMPTS else "error",
                      f"無法讀取這個連結（{str(exc)[:80]}）。", bump_attempts=True)

    with tempfile.TemporaryDirectory(prefix="chumei-subimg-") as td:
        images = []
        from extract_events import fetch_image_file
        for i, u in enumerate((content.get("images") or [])[:2]):
            p = fetch_image_file(u, td, i)
            if p:
                images.append(p)
        if len(content.get("text") or "") < MIN_TEXT_FOR_NO_SCREENSHOT and info["kind"] != "ig_post":
            shot = screenshot(url, td)
            if shot:
                images.append(shot)
                content["note"] = (content.get("note") or "") + "（文字很少，附整頁截圖）"
        candidates = candidate_events(index, content)
        try:
            verdict = triage_with_codex(env, url, info, content, candidates, images)
        except Exception as exc:  # noqa: BLE001
            return finish("pending" if sub["attempts"] + 1 < MAX_ATTEMPTS else "error",
                          f"判讀時發生錯誤（{str(exc)[:80]}）。", bump_attempts=True)

    verdict_json = json.dumps(verdict, ensure_ascii=False)
    reason = (verdict.get("reason") or "").strip() or "系統判讀完成。"
    conf = float(verdict.get("confidence") or 0)
    action = verdict.get("action")
    print(f"  verdict {action} conf={conf:.2f} match={verdict.get('matched_event_id')} :: {reason}")

    if action == "attach_to_existing" and verdict.get("matched_event_id") in index["by_id"]:
        if conf < CONFIDENCE_FLOOR:
            action = "manual"
        else:
            return finish("existing", reason, event_url=event_url(verdict["matched_event_id"]), verdict=verdict_json)
    if action == "reject" or not verdict.get("relevant"):
        if conf < CONFIDENCE_FLOOR:
            action = "manual"
        else:
            return finish("rejected", reason, verdict=verdict_json)
    if action == "manual" or conf < CONFIDENCE_FLOOR:
        if not dry_run:
            _append_jsonl(MANUAL_REVIEW, {"ts": now_iso(), "submission": sub["id"], "url": url,
                                          "verdict": verdict, "note": sub.get("note") or ""})
        return finish("manual", "系統不太確定，已交給站長人工確認。", verdict=verdict_json)

    # new_event（或 attach 但 id 對不上）→ 進 inbox
    if dry_run:
        return finish("accepted", reason, verdict=verdict_json)
    if not inbox_by_url.get(url):
        write_inbox_item(sub, url, info, content, verdict)
        inbox_by_url[url] = (SOURCE_ID, sub["id"])
    store.update(sub["id"], "accepted", reason,
                 verdict=json.dumps({**verdict, "accepted_at": now_iso()}, ensure_ascii=False))
    ctx["needs_extract"] = True


def settle_accepted(store, index):
    """抽取後：0 場→未辨識；建站後：對回 events.json → 已上線。"""
    for sub in store.list_by_status(["accepted"], limit=200):
        events = extracted_events_for(sub["id"])
        if events is None:
            continue
        if not events:
            store.update(sub["id"], "not_event", "系統讀過這則內容，但沒有辨識出有明確時間的活動。")
            continue
        url = normalize_url(sub["url"]) or sub["url"]
        ids = index["by_source"].get((SOURCE_ID, sub["id"])) or index["by_url"].get(url) or []
        if ids:
            store.update(sub["id"], "published", f"已上線：{events[0]['title']}", event_url=event_url(ids[0]))
            continue
        try:
            accepted_at = json.loads(sub.get("verdict") or "{}").get("accepted_at") or ""
        except ValueError:
            accepted_at = ""
        if accepted_at and index["generated_at"] > accepted_at:
            # 建站已跑過卻找不到：多半被去重合併進既有活動，或抽取結果進了 review
            if events[0].get("status") == "published":
                store.update(sub["id"], "existing", "已辨識出活動並與既有內容合併。")
            else:
                store.update(sub["id"], "manual", "已辨識出活動，但資訊需要站長確認後才上線。")
        else:
            reason = f"已辨識出活動「{events[0]['title']}」，下次建站後上線。"
            if sub.get("reason") != reason:
                store.update(sub["id"], "accepted", reason)


def settle_source_added(store, orgs):
    """建站後：新加入追蹤的帳號有了單位頁，把 /org/{id} 連結補上。"""
    for sub in store.list_by_status(["source_added"], limit=200):
        if sub.get("event_url"):
            continue
        info = classify_url(normalize_url(sub["url"]) or sub["url"])
        link = org_url(orgs, info)
        if link:
            store.update(sub["id"], "source_added", sub.get("reason") or "", event_url=link)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="只判讀、不寫入任何狀態")
    ap.add_argument("--id", help="只處理這一筆 submission id（忽略狀態）")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    env = load_env()
    db = Path(env.get("CHUMEI_AUTH_DATABASE", ROOT / "state" / "auth.sqlite3"))
    store = SubmissionStore(db)
    if args.id:
        todo = [store.get(args.id)] if store.get(args.id) else []
    else:
        todo = store.list_by_status(["pending"], limit=args.limit)
    ctx = {"events": load_events_index(), "inbox": load_inbox_index(), "handles": load_tracked_handles(),
           "orgs": load_org_index(), "env": env, "needs_extract": False}
    print(f"{len(todo)} submissions to process")
    for sub in todo:
        print(f"- {sub['id']} {sub['url']}")
        if not args.dry_run:
            store.update(sub["id"], "processing", "")
        try:
            process_one(store, sub, ctx, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"  {sub['id']} crashed: {exc!r}", file=sys.stderr)
            if not args.dry_run:
                store.update(sub["id"], "pending" if sub["attempts"] + 1 < MAX_ATTEMPTS else "error",
                             "處理時發生錯誤，稍後會再試。", bump_attempts=True)
    if args.dry_run:
        return 0
    if ctx["needs_extract"]:
        run_extract()
    settle_accepted(store, ctx["events"])
    settle_source_added(store, ctx["orgs"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
