"""頭貼回填：RSSHub/graph 沒帶到的單位，用其他管道補。

- IG：instaloader session（同 fetch_stories）打 topsearch，拿 profile_pic_url。
- FB：slug 尾端有數字粉專 ID 的（如 -ym-tennis-100316179065253），改用數字 ID 打 graph。
- website：抓首頁 og:image 或 apple-touch-icon / favicon。
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from chumei_lib import AVATAR_DIR, ROOT, save_avatar


def missing_sids():
    d = json.loads((ROOT / "site" / "data" / "sources.json").read_text())
    out = []
    for e in d["entries"]:
        if not e.get("links") or e.get("avatar"):
            continue
        out.extend(e.get("sids", []))
    return [s for s in out if not (AVATAR_DIR / f"{s}.jpg").exists()]


def backfill_ig(usernames):
    if not usernames:
        return
    from fetch_stories import load_session
    L = load_session()
    for u in usernames:
        try:
            d = L.context.get_json("web/search/topsearch/", params={"query": u})
            hit = next((x["user"] for x in d.get("users", [])
                        if x["user"]["username"].lower() == u.lower()), None)
            pic = hit and (hit.get("profile_pic_url"))
            ok = pic and save_avatar(f"ig_{u}", pic, max_age_days=0)
            print(f"  ig {u}: {'ok' if ok else 'no pic'}")
        except Exception as e:
            print(f"  ig {u}: FAIL {str(e)[:80]}", file=sys.stderr)
        time.sleep(3)


def backfill_fb(slugs):
    for slug in slugs:
        m = re.search(r"(\d{9,})$", slug)
        target = m.group(1) if m else slug
        ok = save_avatar(f"fb_{slug}", f"https://graph.facebook.com/{target}/picture?type=large", max_age_days=0)
        print(f"  fb {slug} (via {target}): {'ok' if ok else 'fail'}")
        time.sleep(1)


def backfill_web(hosts):
    for host in hosts:
        try:
            r = requests.get(f"https://{host}/", timeout=20,
                             headers={"User-Agent": "Mozilla/5.0 (chumei.observe.tw)"})
            html = r.text
            cand = (re.search(r'property="og:image"\s+content="([^"]+)"', html)
                    or re.search(r'content="([^"]+)"\s+property="og:image"', html)
                    or re.search(r'rel="apple-touch-icon[^"]*"\s+href="([^"]+)"', html)
                    or re.search(r'rel="(?:shortcut )?icon"\s+href="([^"]+)"', html))
            if not cand:
                print(f"  web {host}: no icon found")
                continue
            from urllib.parse import urljoin
            ok = save_avatar(f"web_{host}", urljoin(f"https://{host}/", cand.group(1)), max_age_days=0)
            print(f"  web {host}: {'ok' if ok else 'fail'}")
        except Exception as e:
            print(f"  web {host}: FAIL {str(e)[:80]}", file=sys.stderr)


def main():
    sids = missing_sids()
    igs = [s[3:] for s in sids if s.startswith("ig_")]
    fbs = [s[3:] for s in sids if s.startswith("fb_")]
    webs = [s[4:] for s in sids if s.startswith("web_")]
    print(f"missing: ig={len(igs)} fb={len(fbs)} web={len(webs)}")
    backfill_fb(fbs)
    backfill_web(webs)
    backfill_ig(igs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
