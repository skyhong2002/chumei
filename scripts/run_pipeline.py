"""竹梅 pipeline orchestrator：fetch → extract → build → Telegram。

設計原則：單一來源掛掉不影響整輪；IG 一天最多跑一輪（cookie 額度是共用資源）。
launchd 每 3 小時呼叫一次即可。
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "bin" / "python"
STATE = ROOT / "state" / "pipeline.json"
IG_MIN_INTERVAL_H = 20


def run_step(name, args):
    print(f"=== {name} ===", flush=True)
    t0 = time.time()
    try:
        r = subprocess.run([str(PY), str(ROOT / "scripts" / args[0]), *args[1:]], timeout=7200)
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
        print(f"{name}: TIMEOUT", file=sys.stderr)
    print(f"=== {name}: {'ok' if ok else 'FAILED'} ({time.time()-t0:.0f}s) ===", flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ig", action="store_true")
    ap.add_argument("--force-ig", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true")
    args = ap.parse_args()

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    results = {}

    if not args.skip_fetch:
        results["nycu_life"] = run_step("NYCU LIFE", ["fetch_nycu_life.py"])
        results["infonews"] = run_step("infonews", ["fetch_infonews.py", "--max-pages", "2"])
        results["rpage"] = run_step("rpage", ["fetch_rpage.py", "--max-pages", "2"])
        results["wp"] = run_step("wp", ["fetch_wp.py"])

        last_ig = state.get("last_ig_run", 0)
        due = (time.time() - last_ig) > IG_MIN_INTERVAL_H * 3600
        if args.force_ig or (due and not args.skip_ig):
            results["instagram"] = run_step("instagram", ["fetch_instagram.py", "--limit", "5", "--sleep", "8"])
            state["last_ig_run"] = time.time()
        else:
            print(f"instagram: skipped (last run {(time.time()-last_ig)/3600:.1f}h ago)")

        # Threads / X 同樣走 RSSHub，跟 IG 一樣一天一輪
        last_social = state.get("last_social_run", 0)
        if (ROOT / "scripts" / "fetch_social.py").exists() and (time.time() - last_social) > IG_MIN_INTERVAL_H * 3600:
            results["social"] = run_step("threads/x", ["fetch_social.py", "--limit", "5", "--sleep", "8"])
            state["last_social_run"] = time.time()

        # FB 走 Apify 按結果計費；免費層每月 $5，一週一輪剛好打平（160h 門檻容忍排程抖動）
        FB_MIN_INTERVAL_H = 160
        fb_script = ROOT / "scripts" / "fetch_facebook.py"
        last_fb = state.get("last_fb_run", 0)
        if fb_script.exists() and (time.time() - last_fb) > FB_MIN_INTERVAL_H * 3600:
            results["facebook"] = run_step("facebook", ["fetch_facebook.py", "--limit", "5"])
            state["last_fb_run"] = time.time()

        # 限時動態 24h 就消失，每輪都抓（批量查詢，額度便宜）
        if (ROOT / "scripts" / "fetch_stories.py").exists():
            results["stories"] = run_step("stories", ["fetch_stories.py"])

    results["extract"] = run_step("extract", ["extract_events.py"])
    results["map"] = run_step("map", ["build_map_data.py"])
    results["build"] = (results["map"] and run_step("build", ["build_site.py"])
                        and run_step("validate", ["validate_outputs.py"]))
    # Telegram 改由獨立 launchd job（tw.observe.chumei.telegram，每 30 分鐘、
    # 每次最多 2 則）滴灌發送，與抓取節奏解耦，避免一輪攢一堆一次炸出。

    state["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["last_results"] = results
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))

    # fetcher 局部失敗只記錄；公開輸出與通知投遞需成功。
    return 0 if results.get("build") and results.get("telegram", True) else 1


if __name__ == "__main__":
    sys.exit(main())
