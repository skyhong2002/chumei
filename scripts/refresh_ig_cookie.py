"""IG cookie 續命：Chrome 撈 cookie → 更新 bamboo-rsshub IG_COOKIE → 重建容器 → 驗證 → 解除冷卻。

必須在自己的 Terminal 跑（解 Chrome cookie 要過 Keychain 互動授權，agent session 拿不到）：

    cd ~/Projects/chumei && .venv/bin/python scripts/refresh_ig_cookie.py

死亡簽名（SOP，2026-08-26 實測）：RSSHub IG route 全 503＋容器 log 出現
`web/fxcal/ig_sso_users/ redirect count exceeded`＝session 網頁端點被 IG 擋。
若本腳本回報 cookie 沒變或驗證仍失敗：先在 Chrome 登入 instagram.com（口琴社帳號）再重跑。
"""

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPS = Path.home() / "Documents" / "Bamboo Melody Club" / "ops" / "rsshub"
ENV_PATH = OPS / ".env"
TEST_URL = "http://127.0.0.1:1200/instagram/2/user/nthu_official?limit=2"
COOKIE_KEYS = ("sessionid", "csrftoken", "ds_user_id", "mid", "ig_did", "datr", "rur", "ig_nrcb", "wd")
SCHEDULE_FILES = (ROOT / "state" / "instagram_profile_schedule.json",
                  ROOT / "state" / "instagram_stories_schedule.json")


def main():
    import browser_cookie3
    import requests

    try:
        jar = browser_cookie3.chrome(domain_name="instagram.com")
    except Exception as e:
        sys.exit(f"讀不到 Chrome cookie（{e}）——要在自己的 Terminal 跑，Keychain 跳窗按允許。")
    cookies = {c.name: c.value for c in jar}
    if not cookies.get("sessionid"):
        sys.exit("Chrome 沒有 instagram.com 的 sessionid——先在 Chrome 登入 IG 再重跑。")

    new_cookie = "; ".join(f"{k}={cookies[k]}" for k in COOKIE_KEYS if cookies.get(k))
    env_text = ENV_PATH.read_text()
    m = re.search(r"^IG_COOKIE=(.*)$", env_text, flags=re.M)
    if not m:
        sys.exit(f"{ENV_PATH} 裡找不到 IG_COOKIE 行")
    old_sessionid = re.search(r"sessionid=([^;]*)", m.group(1))
    if old_sessionid and old_sessionid.group(1) == cookies["sessionid"]:
        sys.exit("Chrome 的 sessionid 跟現有設定一樣，代表這組 session 已被 IG 註銷：\n"
                 "在 Chrome 重新登入 instagram.com 之後再重跑本腳本。")

    backup = ENV_PATH.with_name(f".env.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(ENV_PATH, backup)
    ENV_PATH.write_text(env_text[:m.start(1)] + new_cookie + env_text[m.end(1):])
    print(f"IG_COOKIE 已更新（備份 {backup.name}），重建容器…")
    subprocess.run(["docker", "compose", "up", "-d"], cwd=OPS, check=True)

    for attempt in range(6):
        time.sleep(10)
        try:
            r = requests.get(TEST_URL, timeout=60)
        except requests.RequestException:
            continue
        if r.ok:
            print("驗證 OK：RSSHub IG route 恢復。")
            break
        print(f"  驗證中（{r.status_code}）…")
    else:
        sys.exit("換上新 cookie 後 IG route 仍失敗——可能 Chrome 這組 session 也失效了，\n"
                 "在 Chrome 重新登入 instagram.com 再重跑；還不行就查容器 log：docker logs bamboo-rsshub")

    for path in SCHEDULE_FILES:
        if path.exists():
            state = json.loads(path.read_text())
            state["global_cooldown_until"] = 0
            state["rate_limit_streak"] = 0
            path.write_text(json.dumps(state, ensure_ascii=False))
            print(f"已解除冷卻：{path.name}")
    print("完成。下一輪 pipeline（每 3h）會自動恢復抓 IG；要立刻補抓可跑：\n"
          "  .venv/bin/python scripts/fetch_instagram.py --limit 5")


if __name__ == "__main__":
    main()
