#!/usr/bin/env python3
"""Fetch NYCU unit announcements through the university's public Open Data API."""

from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import requests

from chumei_lib import (SeenState, TZ_TAIPEI, append_inbox, now_iso,
                        read_sources_csv)
from source_status import record_fetch


RAW_SOURCE = "nycu-open-data"
USER_AGENT = "ChumeiBot/1.0 (+https://chumei.observe.tw/)"


def _relaxed_ssl_context():
    # NYCU's chain omits Subject Key Identifier. Python 3.13+ strict mode
    # rejects it; disable only that strict flag while retaining CA/hostname
    # verification, matching the existing InfoNews collector.
    import ssl

    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


class _RelaxedAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = _relaxed_ssl_context()
        return super().init_poolmanager(*args, **kwargs)


class ListParser(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.current = None
        self.parts: list[str] = []
        self.entries: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a" or self.current is not None:
            return
        attrs = dict(attrs)
        href = html.unescape(attrs.get("href", "")).strip()
        absolute = urljoin(self.page_url, href)
        query = parse_qs(urlsplit(absolute).query)
        if "/app/data/view" not in urlsplit(absolute).path or not query.get("serno"):
            return
        self.current = {
            "post_id": query["serno"][0],
            "url": absolute,
            "title": attrs.get("title", "").strip(),
        }
        self.parts = []

    def handle_data(self, data):
        if self.current is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or self.current is None:
            return
        text = " ".join("".join(self.parts).split())
        if not self.current["title"]:
            self.current["title"] = re.sub(
                r"更新日期：\s*\d{3}[-/]\d{1,2}[-/]\d{1,2}.*?發布單位：\s*\S+",
                "",
                text,
            ).strip()
        match = re.search(r"更新日期：\s*(\d{3})[-/](\d{1,2})[-/](\d{1,2})", text)
        if match and self.current["title"]:
            year, month, day = map(int, match.groups())
            self.current["posted_at"] = datetime(
                year + 1911, month, day, tzinfo=TZ_TAIPEI
            ).isoformat(timespec="seconds")
            self.entries.append(self.current)
        self.current = None
        self.parts = []


class ContentParser(HTMLParser):
    BLOCKS = {"br", "div", "li", "ol", "p", "section", "table", "td", "tr", "ul"}

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.parts: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "img" and attrs.get("src"):
            value = urljoin(self.page_url, html.unescape(attrs["src"]).strip())
            if value not in self.images:
                self.images.append(value)

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    @property
    def text(self):
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def parse_list(document: str, page_url: str) -> list[dict[str, str]]:
    parser = ListParser(page_url)
    parser.feed(document)
    parser.close()
    return parser.entries


def parse_content(document: str, page_url: str) -> tuple[str, list[str]]:
    parser = ContentParser(page_url)
    parser.feed(document or "")
    parser.close()
    return parser.text, parser.images


def detail_api_url(detail_url: str) -> str:
    parts = urlsplit(detail_url)
    path = parts.path.replace("/app/data/view", "/app/openData/data/data")
    query = parse_qs(parts.query)
    query["type"] = ["json"]
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query, doseq=True), ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", help="comma-separated source_id values")
    parser.add_argument("--limit", type=int, help="maximum new items per source")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        parser.error("--limit cannot be negative")

    rows = [
        row for row in read_sources_csv("bulletin_sources.csv")
        if row.get("type", "").strip() == "nycu_open_data"
    ]
    if args.sources:
        wanted = {value.strip() for value in args.sources.split(",") if value.strip()}
        rows = [row for row in rows if row.get("source_id", "").strip() in wanted]

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,text/html"})
    session.mount("https://", _RelaxedAdapter())
    seen = SeenState(RAW_SOURCE)
    total = 0
    failures = 0
    for row in rows:
        source_id = row["source_id"].strip()
        fresh = []
        try:
            response = session.get(row["url"].strip(), timeout=30)
            response.raise_for_status()
            entries = parse_list(response.text, response.url)
            for entry in entries:
                if args.limit is not None and len(fresh) >= args.limit:
                    break
                if seen.has(source_id, entry["post_id"]):
                    continue
                detail = session.get(detail_api_url(entry["url"]), timeout=30)
                detail.raise_for_status()
                payload = detail.json()
                body, embedded_images = parse_content(
                    payload.get("detailContent") or payload.get("summary") or "",
                    entry["url"],
                )
                images = embedded_images + [
                    image["fileurl"] for image in payload.get("images") or []
                    if image.get("fileurl") and image["fileurl"] not in embedded_images
                ]
                fresh.append({
                    "source_id": source_id,
                    "source_name": row["name"].strip(),
                    "platform": "bulletin",
                    "raw_source": RAW_SOURCE,
                    "school": row.get("school") or "nycu",
                    "org_type": row.get("org_type") or "official",
                    "post_id": entry["post_id"],
                    "url": entry["url"],
                    "posted_at": entry["posted_at"],
                    "text": f"{entry['title']}\n\n{body}".strip(),
                    "images": images,
                    "fetched_at": now_iso(),
                })
                seen.add(source_id, entry["post_id"])
            written = append_inbox(RAW_SOURCE, fresh)
            seen.save()
            total += written
            record_fetch(f"bulletin:{source_id}", backend="NYCU Open Data",
                         ok=True, items=len(fresh))
            print(f"{source_id}: +{written}")
        except (requests.RequestException, ValueError, KeyError) as exc:
            failures += 1
            record_fetch(f"bulletin:{source_id}", backend="NYCU Open Data",
                         ok=False, error=exc)
            print(f"{source_id}: ERROR {str(exc)[:120]}", file=sys.stderr)

    print(f"nycu open data: {total} new items from {len(rows)} source(s)")
    return 0 if failures < max(1, len(rows)) else 1


if __name__ == "__main__":
    sys.exit(main())
