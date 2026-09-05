# 資料契約

所有 fetcher 輸出、LLM 抽取、站台資料共用這兩個 schema。改欄位要同步改這份文件。

## 1. Inbox item（正規化貼文/公告）— JSONL，一行一筆

寫到 `data/feeds/inbox/<raw_source>.jsonl`（append；由 fetcher 自己用 state 去重，同一筆不要重複寫入）。

```json
{
  "source_id": "ig_nthu_sa",
  "source_name": "清大學生會",
  "platform": "instagram | facebook | bulletin | youtube | api",
  "raw_source": "rsshub | infonews | rpage | apify | nycu-life-api",
  "school": "nthu | nycu | both | external",
  "org_type": "official | department | club | external",
  "post_id": "C8xYz...",
  "url": "https://...",
  "posted_at": "2026-08-20T12:00:00+08:00",
  "text": "貼文全文或公告標題＋內文",
  "images": ["https://..."],
  "image_url": "https://...",
  "fetched_at": "2026-08-21T03:00:00+08:00"
}
```

- 去重鍵：`(source_id, post_id)`。fetcher 的 seen-state 放 `state/seen/<raw_source>.json`。
- `posted_at`/`fetched_at` 一律 ISO8601 含時區。公告沒有時間就用當天 00:00+08:00。
- 公告類（bulletin）的 `text` = 標題 + "\n\n" + 內文純文字（去 HTML）；有附圖放 `images`。
- 欄位可缺：`images`、`image_url` 可為空陣列/null。其他欄位必填。

## 2. Event（抽取後的活動）

建站時另附 `schedule_kind`（`period` / `scheduled`）：跨日且為全天或至少 24 小時的活動歸入期間活動；單晚跨午夜仍保留於定時議程。期間以起訖日期與所選日期範圍相交判斷，跨月每月列一次。

人工核對同場後，在 `data/sources/event_merges.csv` 指定 `event_id` → `canonical_id`，更正欄位仍寫 `event_overrides.csv`。保留主活動 ID，合併來源於 `alt_posts` / `alt_sources`，舊 ID 記錄於 `merged_event_ids`；舊頁導向主活動。此表只收錄已核對的同場宣傳，不以名稱相近推定同場。每筆直接指向最終主活動，不串接合併鏈。

`extract_events.py` 產出，`build_site.py` 合併。

```json
{
  "id": "evt_<sha1(source_id+post_id)[:12]>",
  "title": "○○社迎新茶會",
  "summary": "一句話摘要（≤60字）",
  "description": "整理過的活動說明（保留原文重點，非逐字）",
  "start_at": "2026-09-10T19:00:00+08:00",
  "end_at": null,
  "all_day": false,
  "campus": "nthu-main | nthu-nanda | nycu-guangfu | nycu-boai | nycu-yangming | online | other | null",
  "venue": "旺宏館 245 教室",
  "school": "nthu | nycu | both | external",
  "organizer": "清大口琴社",
  "organizer_type": "official | department | club | external",
  "category": "演講 | 工作坊 | 表演 | 展覽 | 比賽 | 營隊 | 徵才 | 市集 | 運動 | 聚會 | 其他",
  "registration_url": null,
  "registration_deadline": null,
  "price": null,
  "source": {"platform": "instagram", "url": "https://...", "source_id": "ig_x", "post_id": "..."},
  "poster_image": "https://...",
  "extraction": {"model": "...", "confidence": 0.0, "needs_review": false, "prompt_version": 1},
  "status": "published | review | rejected"
}
```

- LLM 快取鍵：`(source_id, post_id, prompt_version)`，存 `state/extraction/<source_id>.json`。
- 一篇貼文可以抽出多個 events（例如社課系列）；也可能是 0 個（非活動貼文 → 記錄為 rejected 供統計）。
- `confidence < 0.7` 或缺 `start_at` → `needs_review: true`、`status: "review"`。

## 3. 來源清單 CSV

`data/sources/ig_accounts.csv`：
`username,name,school,org_type,category_hint,active,notes`

`data/sources/bulletin_sources.csv`：
`source_id,name,type,school,org_type,url,extra`
（type = infonews_category | rpage_list；extra 放 adapter 需要的參數，如 infonews 的 SuperType 或 RPage 分類路徑）

`data/sources/event_overrides.csv`（人工校正，build 時後蓋前）：
`event_id,field,value,note`
