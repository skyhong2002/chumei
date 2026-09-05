"""竹梅 pipeline orchestrator：fetch → extract → build → Telegram。

設計原則：單一來源掛掉不影響整輪；IG 每輪只跑一小批，帳號級排程與退避由 fetcher 保存。
launchd 每 3 小時呼叫一次即可。
"""

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from apify_pool import pool_status, recommended_interval_hours
from chumei_lib import read_sources_csv

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "bin" / "python"
STATE = ROOT / "state" / "pipeline.json"
IG_MIN_INTERVAL_H = 20  # Threads / X 單帳號重抓間隔；Instagram 已改為帳號級分批排程。
PIPELINE_INTERVAL_H = 3  # launchd 呼叫節奏，用來換算「每輪該抓幾個」的滾動批量。
BASE_IG_BATCH = 5
CONTRIBUTION_SLOTS_PER_ACCOUNT = 3
MAX_IG_BATCH = 30


def instagram_batch_size(status: dict) -> int:
    community_accounts = sum(
        (row.get("community") or str(row.get("label") or "").startswith("COMMUNITY-"))
        and row.get("available") and not row.get("exhausted")
        for row in status.get("accounts", [])
    )
    return min(
        MAX_IG_BATCH,
        BASE_IG_BATCH + community_accounts * CONTRIBUTION_SLOTS_PER_ACCOUNT,
    )


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
        # 登入者持續累積的來源權重採加權公平排程；仍套用 IG 冷卻與 Apify 額度保護。
        results["priority_fetch"] = run_step(
            "priority weight schedule", ["process_fetch_requests.py", "--max-requests", "2", "--buffer-seconds", "20"]
        )
        results["nycu_life"] = run_step("NYCU LIFE", ["fetch_nycu_life.py"])
        results["infonews"] = run_step("infonews", ["fetch_infonews.py", "--max-pages", "2"])
        results["nycu_open_data"] = run_step("NYCU Open Data", ["fetch_nycu_open_data.py"])
        results["rpage"] = run_step("rpage", ["fetch_rpage.py", "--max-pages", "2"])
        results["wp"] = run_step("wp", ["fetch_wp.py"])

        apify_status = pool_status(refresh=True)
        ig_batch = instagram_batch_size(apify_status)

        if not args.skip_ig:
            ig_args = ["fetch_instagram_public.py", "--limit", "5", "--max-accounts", str(ig_batch)]
            if args.force_ig:
                ig_args.append("--force")
            results["instagram"] = run_step("instagram", ig_args)
            state["last_ig_batch_run"] = time.time()
        else:
            print("instagram: skipped (--skip-ig)")

        # Threads / X 滾動：每輪抓一小批（帳號級排程），單帳號間隔仍 ~IG_MIN_INTERVAL_H
        if (ROOT / "scripts" / "fetch_social.py").exists():
            social_count = sum(
                row.get("active", "true").strip().lower() not in {"false", "link"}
                and row.get("platform") in {"threads", "x"}
                for row in read_sources_csv("social_accounts.csv")
            )
            social_batch = max(1, math.ceil(social_count * PIPELINE_INTERVAL_H / IG_MIN_INTERVAL_H))
            results["social"] = run_step("threads/x", ["fetch_social.py", "--limit", "5", "--sleep", "8",
                                                       "--max-accounts", str(social_batch),
                                                       "--account-interval-hours", str(IG_MIN_INTERVAL_H)])
            state["last_social_run"] = time.time()

        # FB 走 Apify 按結果計費；依額度配速決定單頁間隔，每輪滾動抓一小批。
        fb_script = ROOT / "scripts" / "fetch_facebook.py"
        fb_count = sum(
            row.get("active", "true").strip().lower() not in {"false", "link"}
            for row in read_sources_csv("fb_pages.csv")
        )
        fb_quota = apify_status
        fb_interval_h = recommended_interval_hours(fb_quota, source_count=fb_count)
        state["facebook_interval_hours"] = fb_interval_h
        if fb_script.exists() and not fb_quota.get("exhausted"):
            fb_batch = max(1, math.ceil(fb_count * PIPELINE_INTERVAL_H / fb_interval_h))
            results["facebook"] = run_step("facebook", ["fetch_facebook.py", "--limit", "5",
                                                       "--max-pages-per-run", str(fb_batch),
                                                       "--account-interval-hours", f"{fb_interval_h:g}"])
            state["last_fb_run"] = time.time()

        # 限時動態改走不使用本站 IG 帳號的 Actor；每輪掃活躍度最高的
        # 到期帳號，社群每貢獻一個可用帳號就增加三個處理槽位。
        if (ROOT / "scripts" / "fetch_stories_apify.py").exists():
            results["stories"] = run_step(
                "stories", ["fetch_stories_apify.py", "--max-accounts", str(ig_batch)]
            )

    results["extract"] = run_step("extract", ["extract_events.py"])
    results["map"] = run_step("map", ["build_map_data.py"])
    results["build"] = (results["map"] and run_step("build", ["build_site.py"])
                        and run_step("status", ["build_status_page.py"])
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
