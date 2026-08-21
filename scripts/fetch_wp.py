"""WordPress REST API fetcher：bulletin_sources.csv 內 type=wp_api 的站（如交大藝文中心）。

GET <url>/wp-json/wp/v2/posts → inbox JSONL。結構化、免爬 HTML。
"""

import argparse
import html
import re
import sys
import time

import requests

from chumei_lib import SeenState, append_inbox, now_iso, read_sources_csv

RAW_SOURCE = "wp"


def strip_html(s):
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(s)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-page", type=int, default=20)
    ap.add_argument("--pages", type=int, default=1)
    args = ap.parse_args()

    rows = [r for r in read_sources_csv("bulletin_sources.csv") if r.get("type") == "wp_api"]
    seen = SeenState(RAW_SOURCE)
    total = 0
    for row in rows:
        base = row["url"].rstrip("/")
        fresh = []
        for page in range(1, args.pages + 1):
            try:
                resp = requests.get(f"{base}/wp-json/wp/v2/posts",
                                    params={"per_page": args.per_page, "page": page},
                                    timeout=30, headers={"User-Agent": "chumei.observe.tw"})
                resp.raise_for_status()
                posts = resp.json()
            except Exception as e:
                print(f"{row['source_id']}: page {page} ERROR {str(e)[:100]}", file=sys.stderr)
                break
            if not posts:
                break
            for p in posts:
                pid = str(p["id"])
                if seen.has(row["source_id"], pid):
                    continue
                content = p.get("content", {}).get("rendered", "")
                images = [html.unescape(u) for u in re.findall(r'<img[^>]+src="([^"]+)"', content)]
                title = strip_html(p.get("title", {}).get("rendered", ""))
                date = p.get("date", "")
                posted_at = date + "+08:00" if date and "+" not in date and "Z" not in date else (date or now_iso())
                fresh.append({
                    "source_id": row["source_id"],
                    "source_name": row["name"],
                    "platform": "bulletin",
                    "raw_source": RAW_SOURCE,
                    "school": row.get("school") or "other",
                    "org_type": row.get("org_type") or "official",
                    "post_id": pid,
                    "url": p.get("link"),
                    "posted_at": posted_at,
                    "text": title + "\n\n" + strip_html(content)[:5000],
                    "images": images,
                    "fetched_at": now_iso(),
                })
                seen.add(row["source_id"], pid)
            time.sleep(1)
        n = append_inbox(RAW_SOURCE, fresh)
        seen.save()
        total += n
        print(f"{row['source_id']}: +{n}")
    print(f"wp: {total} new items from {len(rows)} site(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
