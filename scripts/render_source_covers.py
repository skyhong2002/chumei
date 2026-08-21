"""缺圖活動的原始公告頁截圖。

只針對已知公開的校方公告網域，並依原始 URL 快取為 WebP。
有原始海報時不會使用截圖；渲染失敗由建站器退回竹梅示意封面。
"""

import hashlib
import os
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from chumei_lib import ROOT, load_env


OUTPUT_DIR = ROOT / "site" / "assets" / "source-screenshots"
DOMAIN_SELECTORS = {
    "infonews.nycu.edu.tw": "#changeWidh",
}


def _chrome_path():
    env = load_env()
    configured = env.get("CHUMEI_CHROME_PATH")
    candidates = [
        configured,
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    return next((path for path in candidates if path and Path(path).is_file()), None)


def _allowed_source(url):
    parsed = urlparse(url or "")
    return parsed.scheme == "https" and parsed.hostname in DOMAIN_SELECTORS


def _screenshot_path(url):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return OUTPUT_DIR / f"{digest}.webp"


def cached_source_cover(url):
    """已有可用快取時回傳站內路徑，否則回傳 None。"""
    if not _allowed_source(url):
        return None
    destination = _screenshot_path(url)
    if destination.exists() and destination.stat().st_size > 2_000:
        return "/assets/source-screenshots/" + destination.name
    return None


def _save_element_cover(page, selector, destination):
    from PIL import Image

    element = page.locator(selector).first
    element.wait_for(state="visible", timeout=12_000)
    box = element.bounding_box()
    if not box or box["width"] < 320 or box["height"] < 180:
        raise RuntimeError("announcement body is too small")

    png = element.screenshot(type="png", animations="disabled", timeout=20_000)
    import io
    image = Image.open(io.BytesIO(png)).convert("RGB")
    # 內文可能很長；卡片只保留最前面且不放大低解析圖。
    crop_h = min(image.height, max(630, round(image.width * 0.75)))
    image = image.crop((0, 0, image.width, crop_h))
    image.thumbnail((1200, 900))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "WEBP", quality=82, method=6)


def attach_source_screenshots(events, limit=20):
    """替缺圖的未來活動附上原始公告截圖，回傳新產生截圖數。"""
    pending = {}
    today = date.today().isoformat()
    for event in events:
        if event.get("poster_image") or event.get("start_at", "")[:10] < today:
            continue
        url = (event.get("source") or {}).get("url")
        if _allowed_source(url):
            pending.setdefault(url, []).append(event)

    if not pending:
        return 0

    uncached = {}
    for url, grouped_events in pending.items():
        cover = cached_source_cover(url)
        if cover:
            for event in grouped_events:
                event["cover_image"] = cover
                event["image_kind"] = "source_screenshot"
        else:
            uncached[url] = grouped_events
    if not uncached or limit <= 0:
        return 0

    chrome = _chrome_path()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("source screenshots: playwright unavailable; using branded fallbacks", file=sys.stderr)
        return 0
    if not chrome:
        print("source screenshots: Chrome/Chromium unavailable; using branded fallbacks", file=sys.stderr)
        return 0

    produced = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=chrome,
            headless=True,
            args=["--disable-background-networking", "--disable-component-update"],
        )
        context = browser.new_context(
            viewport={"width": 1200, "height": 900},
            device_scale_factor=1,
            ignore_https_errors=True,
            locale="zh-TW",
        )
        page = context.new_page()
        page.set_default_navigation_timeout(30_000)

        for url, grouped_events in list(uncached.items())[:limit]:
            destination = _screenshot_path(url)
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(900)
                page.add_style_tag(content="header, nav, .cookie, .cookie-banner { display:none !important; }")
                _save_element_cover(page, DOMAIN_SELECTORS[urlparse(url).hostname], destination)
                produced += 1
            except Exception as exc:
                print(f"  source screenshot fail {url}: {str(exc)[:120]}", file=sys.stderr)
                continue
            cover = "/assets/source-screenshots/" + destination.name
            for event in grouped_events:
                event["cover_image"] = cover
                event["image_kind"] = "source_screenshot"

        context.close()
        browser.close()
    return produced


if __name__ == "__main__":
    from build_site import apply_overrides, cache_posters, dedupe, load_events

    rows = dedupe(apply_overrides(load_events()))
    rows = [event for event in rows if event.get("start_at")]
    cache_posters(rows)
    created = attach_source_screenshots(rows, limit=int(os.environ.get("CHUMEI_SCREENSHOT_LIMIT", "20")))
    attached = sum(event.get("image_kind") == "source_screenshot" for event in rows)
    print(f"source screenshots: {created} created, {attached} events attached")
