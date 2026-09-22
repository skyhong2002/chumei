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
