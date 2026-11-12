# Browser data and performance budget

The build keeps `/data/events.json` and `/api/events.json` complete for server integrations. Browsers initially fetch `/data/events-index.json`: this month's events, all future events and older events that have not ended. The compact records retain presentation fields, summary and description so search and notification keyword previews preserve their meaning. Full event details remain available at the server-rendered `/event/{id}/` page.

`/data/events-archive.json` is fetched once on selecting All, loading an earlier calendar month, or opening global search. All preserves `time=all` in the URL. Archives are merged by ID, sorted and shared between callers; failed loads can be retried. Filters and historical hover previews work after loading. Current views retain SSR content if the initial fetch fails. The directory progressively displays 60 rows; its full SSR fallback remains available without JavaScript or if enhancement fails. MapLibre JS/CSS load only after pressing 顯示活動地圖.

`validate_outputs.py` requires both browser files, checks exact event coverage, duplicate IDs and archive metadata, and enforces the initial-index budget. Run the budget independently after building:

```sh
.venv/bin/python scripts/check_browser_budget.py /path/to/staged/site
```

Defaults are **1,500,000 decoded bytes and 300,000 gzip bytes**. A failed budget stops validation with measured sizes. Legitimate growth should first prompt reviewing the month window/field payload; a deliberate budget change can set positive byte counts in `CHUMEI_BROWSER_INDEX_MAX_BYTES` and `CHUMEI_BROWSER_INDEX_MAX_GZIP_BYTES` in the publishing environment. Zero/invalid values fail rather than disabling checks. Gzip here is a repeatable local estimate, not a claim about a particular proxy's compression.

## September 23 fixture measurements

Using the existing 2,838-event public snapshot without fetching or rebuilding production data:

| Asset | Decoded bytes | gzip bytes |
| --- | ---: | ---: |
| Previous full event bundle | 4,582,377 | 823,397 |
| Initial browser index (1,091 events) | 982,512 | 189,810 |
| Deferred archive (1,747 events) | 1,588,579 | 303,942 |
| Deferred MapLibre JS | 1,056,837 | 275,161 |

The initial event data is **78.6% smaller decoded / 76.9% smaller gzipped**. A current list/calendar/notification visit does not request the archive, and a list visit does not request MapLibre until the map is opened.

Local Chromium smoke used a cold cache, 390×844 viewport, 4× CPU slowdown and 150 ms / 1.6 Mbps network during initial loading. A sampled LCP was 632 ms; observed initial resource transfers were about 1.49 MB including images/fonts/styles from the existing SSR snapshot. This is one local fixture observation, not a before/after LCP claim or field Core Web Vitals result. Navigation retained 131 current list rows; All restored all 2,838 events with one archive request; searching 聯電 found 20 entries; map opt-in and earlier calendar loading worked. Directory enhancement showed 60 rows and expanded to 120. No uncaught browser errors occurred. Subsequent functional interactions used normal CPU/network speed, so their event timings are **not a throttled INP validation**.

For release verification, repeat cold-cache mobile measurements on the staged release with real generated SSR and collect LCP plus interaction latency for search, All, calendar navigation and directory expansion. Field INP requires representative real visits; it cannot be certified by this single smoke run.

## Homepage SSR and resilient loading (2026-11-12)

The homepage prerenders the desktop deck and the mobile column. Column filter menus are no longer repeated in the SSR markup: they did nothing without JS, and `app.js` (`colMenu()`) builds them from the same option lists once `posts.json` arrives. The platform badge and the four action icons of every SSR post now reference a single inline `<symbol>` sprite with `<use>`. The outer `<svg>` keeps its fill/stroke attributes, so rendering is unchanged. Client-rendered rows keep full inline SVG.

All feed, search and directory avatars carry intrinsic `width`/`height` and `decoding="async"`. Only the first `FEED_EAGER_ROWS` (3) rows of each column load eagerly, and the rest are `loading="lazy"`. The same constant exists in `build_site.py` and `app.js`. Post images keep their existing presentation and only gain `decoding="async"`. Story media is unchanged pending the school-version compliance work (#60, #65).

`window.chumeiFetchJSON` reads every `/data/*.json` file. It rejects non-2xx responses, aborts after 15 s (30 s for event data) and tags errors as `http`, `timeout`, `network` or `parse`. `.shared(url)` deduplicates concurrent requests and does not cache failures. Feed, directory and search failures show `window.chumeiLoadError` with a 重試 button. When SSR content exists it stays visible and the alert appears above it. Layout mode follows `matchMedia("(min-width: 700px)")` changes instead of a one-time `innerWidth` check.

Fixed fixture (72 posts with avatars, 58 with images, 18 events; same data built from `main` and this change, Chromium 151, cold cache):

| Homepage | Before | After |
| --- | ---: | ---: |
| `index.html` decoded bytes | 351,765 | 194,326 |
| `index.html` gzip -9 bytes | 18,734 | 15,243 |
| Inline SVG bytes | 211,596 | 63,904 |
| `<img>` with width/height | 54 / 120 | 120 / 120 |
| `<img loading="lazy">` | 54 / 120 | 108 / 120 |
| Requests until network idle, 1440×900 | 60 (49 images) | 56 (45 images) |
| Requests until network idle, 390×844 | 48 (37 images) | 33 (22 images) |

Before/after screenshots at 1440 and 390 in dark and light themes matched pixel for pixel, both after JS rendering and with `app.js` blocked (SSR only).
