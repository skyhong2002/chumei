#!/usr/bin/env python3
"""Fetch announcements from NTHU RPage list pages into the chumei inbox."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

try:
    import requests
except ImportError as exc:  # Give a more useful error than a traceback in cron.
    raise SystemExit(
        "The 'requests' package is required. Install it with: "
        "python3 -m pip install requests"
    ) from exc


ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "data" / "sources" / "bulletin_sources.csv"
INBOX_PATH = ROOT / "data" / "feeds" / "inbox" / "rpage.jsonl"
SEEN_PATH = ROOT / "state" / "seen" / "rpage.json"
TAIPEI_TZ = timezone(timedelta(hours=8))
USER_AGENT = "chumei-rpage-crawler/1.0 (+https://github.com/)"
REQUEST_INTERVAL_SECONDS = 1.0
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "div", "dl", "dt", "dd",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p",
    "pre", "section", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
    "ul",
}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

_last_request_at: float | None = None


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    parent: "Node | None" = None
    children: list["Node | str"] = field(default_factory=list)

    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def iter_nodes(self) -> Iterable["Node"]:
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.iter_nodes()

    def text_content(self, *, exclude_site_chrome: bool = False) -> str:
        parts: list[str] = []

        def visit(value: Node | str) -> None:
            if isinstance(value, str):
                parts.append(value)
                return
            if value.tag in {"script", "style", "noscript", "template"}:
                return
            if exclude_site_chrome and value is not self and is_site_chrome(value):
                return
            if value.tag == "br":
                parts.append("\n")
                return
            is_block = value.tag in BLOCK_TAGS
            if is_block and parts and not parts[-1].endswith("\n"):
                parts.append("\n")
            for child in value.children:
                visit(child)
            if is_block:
                parts.append("\n")

        visit(self)
        return normalize_text("".join(parts))


class TreeParser(HTMLParser):
    """Small tolerant DOM builder; HTML is parsed structurally, not with regex."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(
            tag.lower(),
            {key.lower(): value or "" for key, value in attrs},
            self.stack[-1],
        )
        self.stack[-1].children.append(node)
        if node.tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(document: str) -> Node:
    parser = TreeParser()
    parser.feed(document)
    parser.close()
    return parser.root


def normalize_text(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ").replace("\u3000", " ")
    lines: list[str] = []
    previous_blank = True
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
            previous_blank = False
        elif not previous_blank:
            lines.append("")
            previous_blank = True
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


SITE_CHROME_CLASSES = {
    "breadcrumb", "copyright", "footer", "header", "menu", "navbar",
    "navigation", "navmenu", "selfhead", "selffoot", "sitemap",
}
SITE_CHROME_MODULE_CLASSES = {
    "module-footer", "module-header", "module-menu", "module-nav",
    "module-path", "module-search",
}
SITE_CHROME_LINES = {
    "english", "menu", "回首頁", "回首頁 home", "搜尋", "漢堡鈕選單",
    "網站導覽",
}


def is_site_chrome(node: Node) -> bool:
    """Identify navigation/header/footer nodes that cannot be article content."""
    if node.tag in {"aside", "footer", "header", "nav"}:
        return True
    role = node.attrs.get("role", "").lower()
    if role in {"banner", "contentinfo", "navigation", "search"}:
        return True
    classes = {name.lower() for name in node.classes()}
    if classes & (SITE_CHROME_CLASSES | SITE_CHROME_MODULE_CLASSES):
        return True
    identifiers = " ".join(classes | {node.attrs.get("id", "").lower()})
    return any(
        marker in identifiers
        for marker in ("breadcrumb", "copyright", "navmenu", "site-footer", "site-header")
    )


def clean_article_text(value: str) -> str:
    """Remove isolated RPage chrome labels left in otherwise valid article HTML."""
    cleaned: list[str] = []
    for line in normalize_text(value).splitlines():
        comparable = re.sub(r"\s+", " ", line).strip().lower()
        if comparable in SITE_CHROME_LINES or comparable.startswith("copyright ©"):
            continue
        cleaned.append(line)
    return normalize_text("\n".join(cleaned))


def detail_url_parts(url: str) -> tuple[str, str] | None:
    """Return (RPage route type, content id) for /p/406-... and /p/450-...."""
    path = unquote(urlsplit(url).path)
    filename = path.rsplit("/", 1)[-1]
    if filename.endswith(".php"):
        filename = filename[:-4]
    pieces = filename.split("-", 2)
    if len(pieces) != 3 or pieces[0] not in {"406", "450"}:
        return None
    post_id = pieces[2].split(",", 1)[0].strip()
    if not post_id or not all(char.isalnum() or char in "_" for char in post_id):
        return None
    return pieces[0], post_id


def find_date_text(entry_node: Node) -> str:
    for node in entry_node.iter_nodes():
        classes = {name.lower() for name in node.classes()}
        if "mdate" in classes or "date" in classes or any("date" in name for name in classes):
            text = node.text_content()
            if text:
                return text
    return entry_node.text_content()


def parse_posted_at(value: str) -> str:
    match = re.search(
        r"(?<!\d)(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})日?"
        r"(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        value,
    )
    if not match:
        raise ValueError(f"unrecognized announcement date: {value!r}")
    year, month, day = (int(match.group(index)) for index in range(1, 4))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    second = int(match.group(6) or 0)
    return datetime(year, month, day, hour, minute, second, tzinfo=TAIPEI_TZ).isoformat(
        timespec="seconds"
    )


def _request(session: requests.Session, url: str) -> requests.Response:
    global _last_request_at
    if _last_request_at is not None:
        delay = REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
    try:
        response = session.get(url, timeout=30, allow_redirects=True)
    finally:
        _last_request_at = time.monotonic()
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type and not response.content.lstrip().startswith(b"<"):
        raise ValueError(f"non-HTML response ({content_type or 'unknown content type'})")
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
        response.encoding = response.apparent_encoding or "utf-8"
    return response


def fetch_list_page(session: requests.Session, url: str) -> str:
    return _request(session, url).text


def parse_list_page(document: str, base_url: str) -> list[dict[str, str]]:
    root = parse_html(document)
    entries: list[dict[str, str]] = []
    page_ids: set[str] = set()
    for anchor in (node for node in root.iter_nodes() if node.tag == "a"):
        href = anchor.attrs.get("href", "").strip()
        absolute_url = urljoin(base_url, href)
        parts = detail_url_parts(absolute_url)
        if not parts:
            continue
        _, post_id = parts
        if post_id in page_ids:
            continue
        title = anchor.text_content()
        if not title:
            print(f"warning: skipping RPage item {post_id}: empty title", file=sys.stderr)
            continue
        container = anchor
        for _ in range(5):
            if container.parent is None:
                break
            container = container.parent
            if "mtitle" in container.classes() or "mbox" in container.classes():
                break
        posted_at: str | None = None
        date_error: Exception | None = None
        date_container: Node | None = container
        # Some themes put the date beside .mtitle or one/two wrappers above it.
        for _ in range(5):
            if date_container is None:
                break
            try:
                posted_at = parse_posted_at(find_date_text(date_container))
                break
            except (TypeError, ValueError) as exc:
                date_error = exc
                date_container = date_container.parent
        if posted_at is None:
            print(f"warning: skipping RPage item {post_id}: {date_error}", file=sys.stderr)
            continue
        entries.append(
            {"post_id": post_id, "url": absolute_url, "title": title, "posted_at": posted_at}
        )
        page_ids.add(post_id)
    return entries


def fetch_detail(session: requests.Session, url: str) -> tuple[str, str]:
    response = _request(session, url)
    return response.text, response.url


def image_source(node: Node) -> str:
    for name in ("src", "data-src", "data-original", "data-lazy-src"):
        value = node.attrs.get(name, "").strip()
        if value:
            return value
    srcset = node.attrs.get("srcset", "").strip()
    if srcset:
        return srcset.split(",", 1)[0].strip().split(" ", 1)[0]
    return ""


def _image_dimension(node: Node, name: str) -> int | None:
    match = re.match(r"\s*(\d+)", node.attrs.get(name, ""))
    return int(match.group(1)) if match else None


def is_site_chrome_image(node: Node, source: str) -> bool:
    """Reject obvious theme assets while preserving article photos and posters."""
    path = unquote(urlsplit(source).path).lower()
    basename = path.rsplit("/", 1)[-1]
    if path.endswith(".svg") or "/plugin/mobile/title/" in path:
        return True
    if re.search(r"(?:^|[-_])(logo|icon\d*|spacer|blank|loading|bullet)(?:[-_.(]|$)", basename):
        return True
    width = _image_dimension(node, "width")
    height = _image_dimension(node, "height")
    if width is not None and height is not None and width <= 64 and height <= 64:
        return True
    return any(is_site_chrome(ancestor) for ancestor in _node_ancestors(node))


def _node_ancestors(node: Node) -> Iterable[Node]:
    current = node.parent
    while current is not None:
        yield current
        current = current.parent


def best_nonempty_by_class(root: Node, class_name: str) -> Node | None:
    candidates = [
        node
        for node in root.iter_nodes()
        if class_name in node.classes()
        and node.text_content(exclude_site_chrome=True)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda node: len(node.text_content(exclude_site_chrome=True)))


def parse_detail(document: str, base_url: str) -> tuple[str, list[str]]:
    root = parse_html(document)
    content: Node | None = None

    # RPage themes reuse .meditor for the header menu, article editor, and
    # footer.  The stable detail boundary is .module-detail; within it,
    # .mpgdetail is the actual body across the observed site variants.
    detail_modules = [
        node for node in root.iter_nodes() if "module-detail" in node.classes()
    ]
    for detail_module in detail_modules:
        for class_name in ("mpgdetail", "mcont", "meditor"):
            candidate = best_nonempty_by_class(detail_module, class_name)
            if candidate is not None:
                content = candidate
                break
        if content is None and detail_module.text_content(exclude_site_chrome=True):
            content = detail_module
        if content is not None:
            break

    # Older RPage layouts may omit .module-detail but still retain the
    # article-specific .mpgdetail wrapper.  Never fall back to a global
    # .meditor: it is commonly the navigation editor.
    if content is None:
        content = best_nonempty_by_class(root, "mpgdetail")
    if content is None:
        for tag in ("article", "main"):
            candidates = [
                node
                for node in root.iter_nodes()
                if node.tag == tag and node.text_content(exclude_site_chrome=True)
            ]
            candidate = max(
                candidates,
                key=lambda node: len(node.text_content(exclude_site_chrome=True)),
                default=None,
            )
            if candidate is not None:
                content = candidate
                break
    if content is None:
        raise ValueError("could not find RPage detail content")

    body = clean_article_text(content.text_content(exclude_site_chrome=True))
    if not body:
        raise ValueError("RPage detail content was empty")
    images: list[str] = []
    seen_images: set[str] = set()
    for node in content.iter_nodes():
        if node.tag != "img":
            continue
        source = image_source(node)
        if (
            not source
            or source.lower().startswith(("data:", "javascript:"))
            or is_site_chrome_image(node, source)
        ):
            continue
        absolute_url = urljoin(base_url, source)
        if absolute_url not in seen_images:
            images.append(absolute_url)
            seen_images.add(absolute_url)
    return body, images


def load_seen(path: Path | None = None) -> dict[str, str]:
    path = path or SEEN_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load seen state {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"seen state must be a JSON object: {path}")
    return {str(key): str(value) for key, value in data.items()}


def save_seen(seen: dict[str, str], path: Path | None = None) -> None:
    path = path or SEEN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_existing_inbox_keys(path: Path | None = None) -> set[str]:
    path = path or INBOX_PATH
    keys: set[str] = set()
    if not path.exists():
        return keys
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                keys.add(f"{item['source_id']}|{item['post_id']}")
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                print(
                    f"warning: ignoring invalid existing inbox line {line_number}: {exc}",
                    file=sys.stderr,
                )
    return keys


def list_page_url(url: str, page_offset: int) -> str:
    if page_offset == 0:
        return url
    parts = urlsplit(url)
    path = parts.path
    stem, separator, extension = path.rpartition(".php")
    dash = stem.rfind("-")
    if not separator or dash < 0 or not stem[dash + 1 :].isdigit():
        if page_offset == 1:
            print(
                f"warning: cannot infer RPage pagination URL from {url}; using first page only",
                file=sys.stderr,
            )
        return ""
    page_number = int(stem[dash + 1 :]) + page_offset
    new_path = f"{stem[:dash + 1]}{page_number}.php{extension}"
    return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))


def is_nthu_rpage_host(hostname: str | None) -> bool:
    hostname = (hostname or "").lower().rstrip(".")
    return hostname == "site.nthu.edu.tw" or hostname.endswith(".site.nthu.edu.tw")


def warning(source_id: str, post_id: str | None, message: object) -> None:
    item = f"/{post_id}" if post_id else ""
    print(f"warning: {source_id}{item}: {message}", file=sys.stderr)


def append_items(items: list[dict[str, object]], path: Path | None = None) -> int:
    path = path or INBOX_PATH
    if not items:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
    return len(items)


def read_rpage_sources(path: Path | None = None) -> list[dict[str, str]]:
    path = path or SOURCES_PATH
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])
    required = {"source_id", "name", "type", "school", "org_type", "url", "extra"}
    missing = sorted(required - fieldnames)
    if missing:
        raise RuntimeError(f"source CSV is missing columns {missing}: {path}")
    return [row for row in rows if row.get("type", "").strip() == "rpage_list"]


def now_iso() -> str:
    return datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="maximum list pages per source (default: 2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="stop after this many new items total across all sources",
    )
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be zero or greater")
    return args


def main() -> int:
    args = parse_args()
    rows = read_rpage_sources()
    seen = load_seen()
    for key in load_existing_inbox_keys():
        seen.setdefault(key, "recovered-from-inbox")

    session = requests.Session()
    session.headers.update(
        {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    collected: list[dict[str, object]] = []
    scheduled: set[str] = set()
    list_pages_fetched = 0

    for row in rows:
        source_id = row.get("source_id", "").strip()
        source_name = row.get("name", "").strip()
        source_url = row.get("url", "").strip()
        if not source_id or not source_name or not source_url:
            warning(source_id or "unknown-source", None, "missing source_id, name, or url")
            continue
        if not is_nthu_rpage_host(urlsplit(source_url).hostname):
            warning(source_id, None, f"not an NTHU RPage host: {source_url}")
            continue

        stop = False
        for page_offset in range(args.max_pages):
            if args.limit is not None and len(collected) >= args.limit:
                stop = True
                break
            page_url = list_page_url(source_url, page_offset)
            if not page_url:
                break
            try:
                entries = parse_list_page(fetch_list_page(session, page_url), page_url)
                list_pages_fetched += 1
            except (requests.RequestException, ValueError) as exc:
                warning(source_id, None, f"list page {page_offset + 1} failed: {exc}")
                break
            if not entries:
                warning(source_id, None, f"list page {page_offset + 1} contained no detail links")
                break

            for entry in entries:
                if args.limit is not None and len(collected) >= args.limit:
                    stop = True
                    break
                key = f"{source_id}|{entry['post_id']}"
                if key in seen or key in scheduled:
                    continue
                try:
                    detail_html, final_url = fetch_detail(session, entry["url"])
                    if not is_nthu_rpage_host(urlsplit(final_url).hostname):
                        raise ValueError(f"detail redirects outside NTHU RPage to {final_url}")
                    body, images = parse_detail(detail_html, final_url)
                except (requests.RequestException, ValueError) as exc:
                    warning(source_id, entry["post_id"], exc)
                    continue

                fetched_at = now_iso()
                collected.append(
                    {
                        "source_id": source_id,
                        "source_name": source_name,
                        "platform": "bulletin",
                        "raw_source": "rpage",
                        "school": "nthu",
                        "org_type": "official",
                        "post_id": entry["post_id"],
                        "url": entry["url"],
                        "posted_at": entry["posted_at"],
                        "text": f"{entry['title']}\n\n{body}",
                        "images": images,
                        "fetched_at": fetched_at,
                    }
                )
                scheduled.add(key)
                seen[key] = fetched_at
            if stop:
                break
        if stop:
            break

    written = append_items(collected)
    save_seen(seen)
    print(f"rpage: {written} new items from {len(rows)} source(s)")
    return 0 if not rows or args.limit == 0 or list_pages_fetched else 1


if __name__ == "__main__":
    sys.exit(main())
