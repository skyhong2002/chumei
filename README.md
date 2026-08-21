# 竹梅 chumei

**[chumei.observe.tw](https://chumei.observe.tw/)** — 清大 × 交大校園活動觀測站。

「竹梅」取自梅竹賽的梅（清華，梅貽琦）與竹（交大，凌竹銘），倒過來唸——因為我們把兩校的活動放在同一邊。

自動彙整公開活動資訊：

- 陽明交大校園公告系統（演講課程、藝文體育、其他活動）
- 清華大學各單位 RPage 公告（課指組、藝文中心、體育室…）
- [NYCU LIFE](https://events.life.nycu.edu.tw/) 官方活動 API
- 兩校學生社團的公開 Instagram 貼文（經自架 RSSHub）

活動欄位（時間、地點、報名連結）由 LLM 從貼文文字與海報圖擷取，低信心結果標示「待確認」。輸出：網站、[Telegram 頻道](https://t.me/chumei_events)、RSS、ICS 行事曆訂閱、JSON API。

## 架構

```
data/sources/*.csv          人工維護的來源清單（IG 帳號、公告站）
scripts/fetch_*.py          來源 adapters → 正規化 inbox JSONL（見 docs/SCHEMA.md）
scripts/extract_events.py   LLM 活動判別＋欄位抽取（vision，含快取）
scripts/build_site.py       合併、跨來源去重、海報快取 → 靜態站 + feeds + API
scripts/publish_telegram.py 新活動 → Telegram 頻道（首次執行只建立 baseline）
scripts/run_pipeline.py     orchestrator（launchd 每 3 小時執行）
site/                       靜態輸出（Caddy file_server）
```

## 開發

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # 填 CHUMEI_LLM_API_KEY 等
.venv/bin/python scripts/run_pipeline.py
python3 -m http.server -d site 8899
```

Telegram publisher 由 `CHUMEI_TELEGRAM_ENABLED=true` 啟用。Token 與頻道 ID 只放在被 Git 忽略的 `.env`；可先執行：

```sh
.venv/bin/python scripts/publish_telegram.py --check
.venv/bin/python scripts/publish_telegram.py --dry-run
```

首次正常執行會把現有近期活動記為 baseline，不會洗版。此後每輪 pipeline 最多推送 10 筆新活動；22:00–07:59 自動靜音。

## 資料回報與下架

資訊有誤、想上架活動、或主辦單位希望調整內容：開 [issue](../../issues) 或來信 chumei@observe.tw。轉載之海報與貼文皆附原始連結，主辦單位要求即下架。

## License

程式碼 MIT；活動內容版權屬各主辦單位。
