"""IG handle 驗證：topsearch 找 exact match，存在就順路存頭貼。

用法：.venv/bin/python scripts/verify_ig.py handle1 handle2 ...
輸出：每行 `handle<TAB>ok|miss<TAB>full_name`；ok 時頭貼存 site/assets/avatars/ig_<handle>.jpg
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from chumei_lib import save_avatar
from fetch_stories import load_session


def main():
    handles = [h.strip().lstrip("@") for h in sys.argv[1:] if h.strip()]
    if not handles:
        print("usage: verify_ig.py handle...", file=sys.stderr)
        return 1
    L = load_session()
    for u in handles:
        try:
            d = L.context.get_json("web/search/topsearch/", params={"query": u})
            hit = next((x["user"] for x in d.get("users", [])
                        if x["user"]["username"].lower() == u.lower()), None)
            if hit:
                if hit.get("profile_pic_url"):
                    save_avatar(f"ig_{u}", hit["profile_pic_url"], max_age_days=0)
                print(f"{u}\tok\t{hit.get('full_name', '')}")
            else:
                print(f"{u}\tmiss\t")
        except Exception as e:
            print(f"{u}\terr\t{str(e)[:60]}")
        time.sleep(3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
