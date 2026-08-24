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
- **Web Push 推播**（PWA）：網站可安裝成 App（manifest + service worker），[/notify/](https://chumei.observe.tw/notify/) 可挑學校 × 類型 × 追蹤單位 × 關鍵字，新活動命中才通知；iOS 16.4+ 需先加入主畫面
- **追蹤（🔔）**：貼文、活動卡／列、活動詳情頁按鈴鐺即追蹤該單位，該單位的新活動一律通知（未開推播也會先記著）
- [Telegram 頻道](https://t.me/chumei_events)、RSS、ICS 行事曆訂閱（學校 × 類型／校區／主辦的組合訂閱）、JSON API
- **查詢 bot**：私訊 [@chumei_events_bot](https://t.me/chumei_events_bot) 一句話查活動（「這週末 清大」「熱舞社」…）；LINE 版共用同一核心（`bot_core.py`），待官方帳號金鑰後啟用
- **MCP server**（`https://chumei.observe.tw/mcp`，Streamable HTTP）：讓 Claude／ChatGPT 等 AI 助理直接搜活動、查名錄、組訂閱網址（接入方式見[訂閱頁](https://chumei.observe.tw/subscribe/)）

## 架構

```
data/sources/*.csv          人工維護的來源名冊（社團名冊、IG/FB/社群帳號、公告站、場地座標）
scripts/fetch_*.py          來源 adapters → 正規化 inbox JSONL（見 docs/SCHEMA.md）
                            bulletins / instagram / facebook / social(Threads·X) / stories / wp
scripts/extract_events.py   LLM 活動判別＋欄位抽取（vision，含快取；例行社課須明寫時間地點才收）
scripts/build_site.py       合併、跨來源去重、名錄歸戶、venue→座標 → 靜態站 + feeds + API
scripts/publish_telegram.py 新活動以「貼文」為單位推送（同貼文多活動合一則訊息）
scripts/push_server.py      Web Push 訂閱 API（Caddy 反代 /push/*；launchd 常駐）
scripts/auth_server.py      NYCU OAuth-only 帳號／Session API（Caddy 反代 /auth/*、/account*）
scripts/publish_push.py     Web Push 滴灌發布（偏好過濾；launchd 每 30 分鐘）
scripts/push_common.py      Web Push 共用層（訂閱儲存、偏好比對、VAPID、發送）
scripts/bot_core.py         查詢 bot 共用核心（一句話 → 解析時間/學校/類型/關鍵字 → 搜尋與排版）
scripts/bot_telegram.py     Telegram 私訊查詢（長輪詢，與頻道推播共用 bot token；launchd 常駐）
scripts/bot_line.py         LINE 官方帳號 webhook（只用免費 Reply API；Caddy 反代 /line/webhook）
scripts/mcp_server.py      MCP server（唯讀，資料源為 site/ 產物；launchd 常駐，Caddy 反代 /mcp）
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

## NYCU OAuth 帳號

在 NYCU OAuth 管理介面註冊 Authorization Code 應用程式，Callback URL 設為
`https://chumei.observe.tw/auth/nycu/callback`。正式機的 Client ID／Secret 存在 macOS
Keychain（service：`tw.observe.chumei.nycu-oauth-client-id` 與
`tw.observe.chumei.nycu-oauth-secret`）；開發環境也可改用 `.env`：

```sh
CHUMEI_NYCU_OAUTH_CLIENT_ID=
CHUMEI_NYCU_OAUTH_CLIENT_SECRET=
CHUMEI_AUTH_PUBLIC_BASE_URL=https://chumei.observe.tw
```

服務由 `deploy/tw.observe.chumei.auth.plist` 常駐在 `127.0.0.1:8324`。Caddy 需將
`/auth/*` 與 `/account*` 反代到該埠。帳號資料只包含 OAuth identity 與雜湊後的
Session token，以及使用者主動追蹤的單位關聯，存於被 Git 忽略的
`state/auth.sqlite3`；不保存學校密碼，也不公開個別帳號的追蹤名單。

## 資料回報與下架

資訊有誤、想上架活動、或主辦單位希望調整內容：開 [issue](../../issues) 或來信 chumei@observe.tw。轉載之海報與貼文皆附原始連結，主辦單位要求即下架。

## License

程式碼 [MIT](LICENSE)；活動內容版權屬各主辦單位。
