"""竹梅 pipeline orchestrator：fetch → extract → build。

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

        last_ig = state.get("last_ig_run", 0)
        due = (time.time() - last_ig) > IG_MIN_INTERVAL_H * 3600
        if args.force_ig or (due and not args.skip_ig):
            results["instagram"] = run_step("instagram", ["fetch_instagram.py", "--limit", "5", "--sleep", "8"])
            state["last_ig_run"] = time.time()
        else:
            print(f"instagram: skipped (last run {(time.time()-last_ig)/3600:.1f}h ago)")

        # FB 走 Apify 按結果計費，一天一輪就好
        fb_script = ROOT / "scripts" / "fetch_facebook.py"
        last_fb = state.get("last_fb_run", 0)
        if fb_script.exists() and (time.time() - last_fb) > IG_MIN_INTERVAL_H * 3600:
            results["facebook"] = run_step("facebook", ["fetch_facebook.py", "--limit", "5"])
            state["last_fb_run"] = time.time()

    results["extract"] = run_step("extract", ["extract_events.py"])
    results["build"] = run_step("build", ["build_site.py"]) and run_step("validate", ["validate_outputs.py"])

    state["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["last_results"] = results
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))

    # build 成功就算整輪成功；fetcher 局部失敗只記錄
    return 0 if results.get("build") else 1


if __name__ == "__main__":
    sys.exit(main())
