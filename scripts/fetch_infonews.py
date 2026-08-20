"""Fetch NYCU campus announcements from infonews.nycu.edu.tw."""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from chumei_lib import (
    TZ_TAIPEI,
    SeenState,
    append_inbox,
    now_iso,
    read_sources_csv,
)

try:
    import requests
except ImportError:  # requests is optional; urllib is sufficient.
    requests = None

NETWORK_ERRORS = (HTTPError, URLError, OSError)
if requests is not None:
    NETWORK_ERRORS += (requests.RequestException,)


RAW_SOURCE = "infonews"
USER_AGENT = "ChumeiBot/1.0 (+https://infonews.nycu.edu.tw/)"
DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
CHARSET_RE = re.compile(
    br"<meta\s+[^>]*(?:charset\s*=\s*['\"]?\s*([\w-]+)|"
    br"content\s*=\s*['\"][^'\"]*charset\s*=\s*([\w-]+))",
    re.IGNORECASE,
)


def clean_text(parts: Iterable[str]) -> str:
    """Normalize HTML-derived text while retaining paragraph breaks."""
    text = "".join(parts).replace("\r", "\n").replace("\xa0", " ")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
        elif lines and lines[-1] != "":
            lines.append("")
    return "\n".join(lines).strip()


def decode_html(data: bytes, content_type: str = "") -> str:
    """Decode the response using HTTP/meta charset, then safe site fallbacks."""
    candidates = []
    match = re.search(r"charset\s*=\s*([\w-]+)", content_type, re.I)
    if match:
        candidates.append(match.group(1))
    meta = CHARSET_RE.search(data[:4096])
    if meta:
        charset = next((part for part in meta.groups() if part), b"")
        if charset:
            candidates.append(charset.decode("ascii", "ignore"))
    candidates.extend(("utf-8", "cp950", "big5"))

    tried = set()
    for charset in candidates:
        charset = charset.lower()
        if not charset or charset in tried:
            continue
        tried.add(charset)
        try:
            return data.decode(charset)
        except (LookupError, UnicodeDecodeError):
            pass
    return data.decode("utf-8", "replace")


def _relaxed_ssl_context():
    # infonews.nycu.edu.tw 的憑證缺 Subject Key Identifier，Python 3.13+ 預設的
    # VERIFY_X509_STRICT 會拒絕。放寬 strict flag、保留完整鏈驗證。
    import ssl

    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


if requests is not None:
    class _RelaxedAdapter(requests.adapters.HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = _relaxed_ssl_context()
            return super().init_poolmanager(*args, **kwargs)


class HttpClient:
    def __init__(self, delay: float = 1.0, timeout: float = 30.0):
        self.delay = delay
        self.timeout = timeout
        self.last_request_at = 0.0
        self.session = requests.Session() if requests is not None else None
        if self.session is not None:
            self.session.headers.update({"User-Agent": USER_AGENT})
            self.session.mount("https://", _RelaxedAdapter())

    def get_text(self, url: str) -> str:
        elapsed = time.monotonic() - self.last_request_at
        if self.last_request_at and elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_at = time.monotonic()

        if self.session is not None:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return decode_html(response.content, response.headers.get("Content-Type", ""))

        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=self.timeout, context=_relaxed_ssl_context()) as response:
            return decode_html(response.read(), response.headers.get("Content-Type", ""))


class ListParser(HTMLParser):
    """Parse the site's three-row announcement records."""

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.entries = []
        self.current = None
        self.in_detail_link = False
        self.in_style4 = False
        self.style4_parts = []

    def _finish_current(self):
        if self.current and self.current.get("post_id") and self.current.get("title"):
            self.entries.append(self.current)
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "action=detail" in attrs.get("href", ""):
            self._finish_current()
            href = urljoin(self.page_url, attrs["href"])
            post_id = parse_qs(urlparse(href).query).get("id", [""])[0].strip()
            self.current = {
                "post_id": post_id,
                "title": attrs.get("title", "").strip(),
                "url": href,
                "date": "",
            }
            self.in_detail_link = True
        elif tag == "td" and "style4" in attrs.get("class", "").split():
            self.in_style4 = True
            self.style4_parts = []

    def handle_endtag(self, tag):
        if tag == "a":
            self.in_detail_link = False
        elif tag == "td" and self.in_style4:
            value = clean_text(self.style4_parts)
            if self.current and not self.current["date"] and DATE_RE.search(value):
                self.current["date"] = DATE_RE.search(value).group(0)
            self.in_style4 = False
            self.style4_parts = []

    def handle_data(self, data):
        if self.in_detail_link and self.current and not self.current["title"]:
            self.current["title"] += data
        if self.in_style4:
            self.style4_parts.append(data)

    def close(self):
        super().close()
        if self.current:
            self.current["title"] = self.current["title"].strip()
        self._finish_current()


class DetailParser(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "div", "dl", "dt",
        "dd", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5",
        "h6", "header", "hr", "li", "main", "ol", "p", "pre", "section",
        "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
    }
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.active_depth = 0
        self.parts = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.active_depth == 0 and attrs.get("id") == "changeWidh":
            self.active_depth = 1
            return
        if not self.active_depth:
            return
        if tag in self.BLOCK_TAGS or tag == "br":
            self.parts.append("\n")
        if tag == "img" and attrs.get("src"):
            image_url = urljoin(self.page_url, attrs["src"].strip())
            if urlparse(image_url).scheme in {"http", "https"} and image_url not in self.images:
                self.images.append(image_url)
        if tag not in self.VOID_TAGS:
            self.active_depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.active_depth and tag not in self.VOID_TAGS:
            self.active_depth -= 1

    def handle_endtag(self, tag):
        if not self.active_depth:
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag not in self.VOID_TAGS:
            self.active_depth -= 1

    def handle_data(self, data):
        if self.active_depth:
            self.parts.append(data)

    @property
    def text(self):
        return clean_text(self.parts)


def parse_list(html_text: str, page_url: str):
    parser = ListParser(page_url)
    parser.feed(html_text)
    parser.close()
    return parser.entries


def parse_detail(html_text: str, page_url: str):
    parser = DetailParser(page_url)
    parser.feed(html_text)
    parser.close()
    return parser.text, parser.images


def posted_at(date_text: str) -> str:
    match = DATE_RE.search(date_text or "")
    if match:
        year, month, day = map(int, match.groups())
        return datetime(year, month, day, tzinfo=TZ_TAIPEI).isoformat(timespec="seconds")
    now = datetime.now(TZ_TAIPEI)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def super_type_from_row(row) -> str:
    values = parse_qs(row.get("extra", ""), keep_blank_values=True)
    value = values.get("SuperType", [""])[0].strip()
    if not value:
        raise ValueError(f"missing SuperType in extra={row.get('extra')!r}")
    return value


def list_url(base_url: str, super_type: str, page: int) -> str:
    query = urlencode({
        "SuperType": super_type,
        "action": "more",
        "pagekey": page,
        "categoryid": "all",
    })
    return urljoin(base_url, "index.php") + "?" + query


def main():
    parser = argparse.ArgumentParser(description="Fetch NYCU InfoNews announcements")
    parser.add_argument("--max-pages", type=int, default=2, help="maximum list pages per source (default: 2)")
    parser.add_argument("--limit", type=int, default=None, help="maximum new items per source (default: unlimited)")
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit cannot be negative")

    rows = [row for row in read_sources_csv("bulletin_sources.csv") if row.get("type", "").strip() == "infonews_category"]
    seen = SeenState(RAW_SOURCE)
    client = HttpClient(delay=1.0)
    total_new = 0
    failures = 0

    for index, row in enumerate(rows, 1):
        source_id = row["source_id"].strip()
        source_name = row["name"].strip()
        fresh = []
        pending_post_ids = set()
        try:
            super_type = super_type_from_row(row)
            stop = args.limit == 0
            for page in range(1, args.max_pages + 1):
                if stop:
                    break
                page_url = list_url(row["url"].strip(), super_type, page)
                entries = parse_list(client.get_text(page_url), page_url)
                if not entries:
                    break
                for entry in entries:
                    if seen.has(source_id, entry["post_id"]) or entry["post_id"] in pending_post_ids:
                        continue
                    body, images = parse_detail(client.get_text(entry["url"]), entry["url"])
                    if not body:
                        print(f"warning: empty body for {source_id}/{entry['post_id']}", file=sys.stderr)
                        continue
                    fresh.append({
                        "source_id": source_id,
                        "source_name": source_name,
                        "platform": "bulletin",
                        "raw_source": RAW_SOURCE,
                        "school": "nycu",
                        "org_type": "official",
                        "post_id": entry["post_id"],
                        "url": entry["url"],
                        "posted_at": posted_at(entry["date"]),
                        "text": entry["title"] + "\n\n" + body,
                        "images": images,
                        "image_url": images[0] if images else None,
                        "fetched_at": now_iso(),
                    })
                    pending_post_ids.add(entry["post_id"])
                    if args.limit is not None and len(fresh) >= args.limit:
                        stop = True
                        break

            written = append_inbox(RAW_SOURCE, fresh)
            for item in fresh:
                seen.add(source_id, item["post_id"])
            seen.save()
            total_new += written
            print(f"[{index}/{len(rows)}] {source_id}: +{written}")
        except NETWORK_ERRORS + (ValueError,) as exc:
            failures += 1
            print(f"[{index}/{len(rows)}] {source_id}: ERROR {exc}", file=sys.stderr)

    print(f"done: {total_new} new items, {failures} failures / {len(rows)} sources")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
