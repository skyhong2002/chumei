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
- **我要去（✓）**：登入後可標記要參加哪些活動，人數公開顯示在活動卡／列／詳情頁；[/events/](https://chumei.observe.tw/events/) 可切「熱門」排序，看大家都往哪裡去
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
scripts/auth_server.py      OAuth 帳號／Session API（NYCU＋Google；Caddy 反代 /auth/*、/account*）
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

Instagram 抓取有兩個後端（`CHUMEI_IG_BACKEND` 或 `fetch_instagram.py --backend`）：`rsshub`（本機 RSSHub 網頁端點）與 `instaloader`（同一組 IG cookie 走 app 端點 `feed/user/<id>`，user id 快取在 `state/ig_userids.json`）；預設 `auto` 先走 RSSHub、共享 route 失敗時該輪開啟 circuit breaker，改走 instaloader。

IG 採持久化分批排程：launchd 每 3 小時觸發時，一般貼文最多跑 4 批、每批 10 個帳號，帳號間隨機等待 25–45 秒、批次間緩衝 5–8 分鐘；約 24 小時輪完名冊，同帳號成功後至少 24 小時才再排入。限時動態每輪只查 48 個帳號，約 21 小時輪完名冊；抓到後在網站顯示 48 小時，讓已消失的 IG 限動多保留一天。遇到 401／429 會立即停止該批並以 12–72 小時指數退避，狀態分別保存在 `state/instagram_profile_schedule.json` 與 `state/instagram_stories_schedule.json`。`--dry-run` 只印貼文，不寫入 inbox、seen-state 或排程狀態。

首次正常執行會把現有近期活動記為 baseline，不會洗版。此後每輪 pipeline 最多推送 10 則貼文；22:00–07:59 自動靜音。

## OAuth 帳號（NYCU＋Google）

在 NYCU OAuth 管理介面註冊 Authorization Code 應用程式，Callback URL 設為
`https://chumei.observe.tw/auth/nycu/callback`。正式機的 Client ID／Secret 存在 macOS
Keychain（service：`tw.observe.chumei.nycu-oauth-client-id` 與
`tw.observe.chumei.nycu-oauth-secret`）；開發環境也可改用 `.env`：

```sh
CHUMEI_NYCU_OAUTH_CLIENT_ID=
CHUMEI_NYCU_OAUTH_CLIENT_SECRET=
CHUMEI_AUTH_PUBLIC_BASE_URL=https://chumei.observe.tw
```

Google 登入開放任何 Google 帳號（給清大朋友與校友用）：在 GCP Console 建 OAuth 2.0
Client（Web application），Callback URL 設為
`https://chumei.observe.tw/auth/google/callback`。正式機的 Client ID／Secret 存在
Keychain（service：`tw.observe.chumei.google-oauth-client-id` 與
`tw.observe.chumei.google-oauth-secret`）；開發環境也可用 `.env` 的
`CHUMEI_GOOGLE_OAUTH_CLIENT_ID` 與 `CHUMEI_GOOGLE_OAUTH_CLIENT_SECRET`。

兩種登入可在帳號頁互相綁定（`/auth/{provider}/start?link=1` → callback 走綁定分
支）。若要綁定的身分已有自己的帳號，會把對方的追蹤、參加標記、回報與 session 全部
併入目前帳號再刪除對方；`POST /auth/unlink` 可解除綁定，但至少要留一種登入方式。

帳號分成兩頁：**公開個人頁 `/@handle`**（名稱、代號、追蹤的單位、要去的活動；可在設定關閉公開）與
**帳號設定 `/account/`**（個人檔案、登入方式綁定、行事曆訂閱、我的回報、登出）。未登入時 `/account/` 是登入頁。
Caddy 的 auth matcher 包含 `/@*`。

帳號還提供：
- **名稱與代號**：`POST /auth/profile`（display_name、handle、public）；handle 小寫英數底線 3–20 字、全站唯一，
  首次登入從 Email 自動產生（撞名加數字），舊帳號在服務啟動時補齊。
- **私密行事曆**：`GET /auth/calendar/{token}.ics` 輸出該帳號「我要去」的活動（token 在帳號頁，
  `POST /auth/calendar/rotate` 換新）。
- **推播綁帳號**：`push_server` 用 session cookie 解析 `state/auth.sqlite3`，把訂閱記上 `user_id`。
  綁定後發送時追蹤單位以帳號現況為準（跨裝置同步）、mode／rules 儲存時同步到同帳號其他裝置，
  `publish_push` 會在「我要去」的活動前一天推提醒（每帳號每場一次，記在 `state/push/publish.json` 的 `reminders`）。
- **只看追蹤**：首頁河道欄、活動列表、日曆與限動牆都有「追蹤」篩選；登入且有追蹤的人第一次進首頁會自動多一欄「追蹤」河道。

服務由 `deploy/tw.observe.chumei.auth.plist` 常駐在 `127.0.0.1:8324`。Caddy 需將
`/auth/*` 與 `/account*` 反代到該埠。帳號資料只包含 OAuth identity 與雜湊後的
Session token，以及使用者主動追蹤的單位關聯，存於被 Git 忽略的
`state/auth.sqlite3`；不保存學校密碼，也不公開個別帳號的追蹤名單。

## 連結回報（登入投稿）

登入者在 `/account/` 貼活動連結（`POST /auth/submissions`，每人每日 10 筆、同連結去重），
`scripts/process_submissions.py` 由 `deploy/tw.observe.chumei.submissions.plist` 每 15 分鐘審核一輪：

1. 帳號主頁比對追蹤名錄（已追蹤→已收錄；未追蹤→寫 `state/submissions/source_suggestions.jsonl` 等人工加入）。
2. 單篇內容先比對 inbox／`events.json`，已收錄就直接對回活動頁。
3. 其餘抓內容（IG 走 instaloader，其他抓 og tags＋正文，文字太少就截圖）交 Codex 依
   `scripts/submission_schema.json` 判讀：新活動→寫 `data/feeds/inbox/user_submission.jsonl` 走既有抽取／建站／去重；
   對上既有活動→回連結；不相關→不收錄；信心不足→`state/submissions/manual_review.jsonl` 人工確認。

狀態會回寫到 `submissions` 表（與帳號同一個 sqlite），使用者在帳號頁看得到進度。

## 資料回報與下架

活動想上架、資訊有誤、主辦單位希望調整或下架：登入後在帳號頁回報連結（見上節），或來信 chumei@observe.tw。
GitHub [issue](../../issues) 只處理程式問題。轉載之海報與貼文皆附原始連結，主辦單位要求即下架。

## License

程式碼 [MIT](LICENSE)；活動內容版權屬各主辦單位。
