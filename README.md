# 竹梅 chumei

**[chumei.observe.tw](https://chumei.observe.tw/)** — 清大 × 陽明交大校園活動觀測站。

「竹梅」取自梅竹賽的梅（清華，梅貽琦）與竹（交大，凌竹銘），倒過來唸——都有梅竹了，怎麼能沒有竹梅呢？

自動彙整兩校的公開活動資訊：

- 校園公告系統：陽明交大公告（演講課程、藝文體育…）、清大各單位 RPage、WordPress 站（如交大藝文中心）、[NYCU LIFE](https://events.life.nycu.edu.tw/) 官方活動 API
- 學生社團與校方單位的公開社群貼文：Instagram、Facebook、Threads、X（帳號名冊見 `data/sources/`，以兩校 114 學年度官方社團名冊為底）
- Instagram 限時動態（24 小時輪播牆）

活動欄位（時間、地點、報名資訊、例行社課時段）由 LLM 從貼文文字與海報圖擷取，經程式後驗與跨來源去重，低信心結果標示「待確認」。

產出：

- **貼文河道**（首頁）＋**活動總覽**（地圖／列表／日曆檢視，地圖含校園建築定位）
- **機構名錄** [/source/](https://chumei.observe.tw/source/)：470+ 單位，每單位有專頁（活動、收錄貼文、例行時段）
- [Telegram 頻道](https://t.me/chumei_events)、RSS、ICS 行事曆訂閱（學校 × 類型／校區／主辦的組合訂閱）、JSON API

## 架構

```
data/sources/*.csv          人工維護的來源名冊（社團名冊、IG/FB/社群帳號、公告站、場地座標）
scripts/fetch_*.py          來源 adapters → 正規化 inbox JSONL（見 docs/SCHEMA.md）
                            bulletins / instagram / facebook / social(Threads·X) / stories / wp
scripts/extract_events.py   LLM 活動判別＋欄位抽取（vision，含快取；例行社課須明寫時間地點才收）
scripts/build_site.py       合併、跨來源去重、名錄歸戶、venue→座標 → 靜態站 + feeds + API
scripts/publish_telegram.py 新活動以「貼文」為單位推送（同貼文多活動合一則訊息）
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

首次正常執行會把現有近期活動記為 baseline，不會洗版。此後每輪 pipeline 最多推送 10 則貼文；22:00–07:59 自動靜音。

## 資料回報與下架

資訊有誤、想上架活動、或主辦單位希望調整內容：開 [issue](../../issues) 或來信 chumei@observe.tw。轉載之海報與貼文皆附原始連結，主辦單位要求即下架。

## License

程式碼 [MIT](LICENSE)；活動內容版權屬各主辦單位。
