"""把 data/sources/found/batch_*_found.csv 合併進正式 registry（可重複執行）。

- instagram → ig_accounts.csv、facebook → fb_pages.csv、threads/x → social_accounts.csv
- 去重鍵：IG/threads/x 用 username（不分大小寫）；FB 用 page_slug。
- 只 append，不動既有列。
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "sources"
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_facebook import page_slug  # noqa: E402


def load(fname):
    p = SRC / fname
    return list(csv.DictReader(p.open(encoding="utf-8-sig"))) if p.exists() else []


def main():
    ig = load("ig_accounts.csv")
    fb = load("fb_pages.csv")
    social = load("social_accounts.csv")
    seen = {
        "instagram": {r["username"].strip().lstrip("@").lower() for r in ig},
        "facebook": {page_slug(r["page"]).lower() for r in fb},
        "threads": {r["username"].strip().lstrip("@").lower() for r in social if r["platform"] == "threads"},
        "x": {r["username"].strip().lstrip("@").lower() for r in social if r["platform"] == "x"},
    }

    add = {"instagram": [], "facebook": [], "threads": [], "x": []}
    n_dup = n_bad = 0
    for f in sorted((SRC / "found").glob("batch_*_found.csv")):
        for r in csv.DictReader(f.open(encoding="utf-8-sig")):
            plat = (r.get("platform") or "").strip().lower()
            u = (r.get("username") or "").strip().lstrip("@")
            if plat not in add or not u or not (r.get("name") or "").strip():
                n_bad += 1
                continue
            key = (page_slug(u) if plat == "facebook" else u).lower()
            if key in seen[plat]:
                n_dup += 1
                continue
            seen[plat].add(key)
            add[plat].append(r)

    def append(fname, rows, mapper, fieldnames):
        if not rows:
            return
        p = SRC / fname
        with p.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            for r in rows:
                w.writerow(mapper(r))

    append("ig_accounts.csv", add["instagram"],
           lambda r: {"username": r["username"].strip().lstrip("@"), "name": r["name"],
                      "school": r["school"], "org_type": r["org_type"],
                      "category_hint": r.get("category_hint", ""), "active": "true",
                      "notes": r.get("notes", "")},
           ["username", "name", "school", "org_type", "category_hint", "active", "notes"])
    append("fb_pages.csv", add["facebook"],
           lambda r: {"page": r["username"].strip(), "name": r["name"], "school": r["school"],
                      "org_type": r["org_type"], "category_hint": r.get("category_hint", ""),
                      "active": "true", "notes": r.get("notes", "")},
           ["page", "name", "school", "org_type", "category_hint", "active", "notes"])
    for plat in ("threads", "x"):
        append("social_accounts.csv", add[plat],
               lambda r, p=plat: {"platform": p, "username": r["username"].strip().lstrip("@"),
                                  "name": r["name"], "school": r["school"], "org_type": r["org_type"],
                                  "category_hint": r.get("category_hint", ""), "active": "true",
                                  "notes": r.get("notes", "")},
               ["platform", "username", "name", "school", "org_type", "category_hint", "active", "notes"])

    print(f"merged: ig+{len(add['instagram'])} fb+{len(add['facebook'])} "
          f"threads+{len(add['threads'])} x+{len(add['x'])} | dup {n_dup} | bad {n_bad}")
    # 新增名單供回填
    print("NEW_IG:" + ",".join(r["username"].strip().lstrip("@") for r in add["instagram"]))
    print("NEW_FB:" + ",".join(r["username"].strip() for r in add["facebook"]))
    print("NEW_SOCIAL:" + ",".join(r["username"].strip().lstrip("@") for r in add["threads"] + add["x"]))


if __name__ == "__main__":
    main()
