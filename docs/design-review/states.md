# 設計評審截圖清單

每一輪都照這份清單截圖，ID 與 `tools/states.py` 一致。每個狀態截兩張：

| 尺寸 | 視窗 | 像素比 | 截圖高度 |
|---|---|---|---|
| `desktop` | 1440 × 900 | 1 | 從頁首或指定錨點起，最多 2700 px |
| `mobile` | 390 × 844（觸控） | 2 | 從頁首或指定錨點起，最多 1688 CSS px |

固定條件：

- 資料：`chumei.observe.tw` 公開 `/data/events.json`、`/data/posts.json` 與 `/api/status.json` 在 2026-11-12 15:03 的快照（3167 則活動、300 則貼文），由 `tools/prepare_fixture.py` 轉成隔離的 `state/nycu_life_activities.json` 與 `data/feeds/inbox/snapshot.jsonl`。圖片只下載一次並快取。
- 建置：`tools/build_preview.py` 把指定版本的 tracked 檔案複製到 `/tmp/cm-review/builds/<名稱>/src`，加入 fixture，以 `CHUMEI_BUILD_OFFLINE=1` 跑 `build_map_data.py`、`build_site.py`、`build_status_page.py`。建置程序的時鐘從 2026-11-12 15:30（Asia/Taipei）起算，非 loopback 連線一律封鎖，並以 nice／ionice 執行、load1 > 10 時等待。不讀寫 repo 的 `state/`、`data/feeds/`、`published/`。
- 限時動態：mock。五張本機畫的純色示意卡，四個虛構帳號，不含真實限動媒體。這次不改限動與 IG 圖片的呈現（#60、#65）。
- 登入：`tools/preview_server.py` 掛上該版本自己的帳號服務，資料庫在建置目錄內，種入一個虛構帳號（林小美，Google，追蹤 3 個單位、2 個「我會去」、1 筆回報）。OAuth 用假的 client ID，只為了讓登入按鈕出現，從不走真正的登入流程。
- 推播：`/push/*` 由預覽伺服器回固定值，不連推播服務。
- 瀏覽器：Chromium（Playwright），時鐘固定在 2026-11-12 15:30（Asia/Taipei），`zh-TW`，減少動態效果，停用 service worker；系統外觀為淺色。網站預設是深色（`data-theme="dark"`），所以主要狀態都是深色；`-light` 狀態在載入前把網站的外觀設定設為淺色（`localStorage.theme = "light"`，等同使用者在「更多 › 外觀」選淺色）。CJK 用系統的 Noto Sans CJK。一次只開一個瀏覽器，每個狀態前檢查 load1。

## 資料狀態怎麼做

`data` 欄攔截 `/data/*.json` 與 `/api/status.json`：

- `loading`：請求永遠不回應，等 1.5 秒後截圖。
- `error`：回 HTTP 500。
- `empty`：照常取回後把每個頂層陣列清空（活動、貼文、名錄、限動）。伺服器預先渲染的內容仍在 HTML 裡，由前端用空資料重繪。

## 頁面與狀態

| ID | 頁面 | 狀態 | 重現方式 |
|---|---|---|---|
| `home` | 首頁 `/` | 有資料（限動列、貼文河道） | — |
| `home-light` | 首頁 | 淺色 | 外觀設為淺色 |
| `home-loading` | 首頁 | 載入中 | `data=loading` |
| `home-error` | 首頁 | 載入錯誤 | `data=error` |
| `home-empty` | 首頁 | 空資料 | `data=empty` |
| `home-events-only` | 首頁 | 篩選：只看活動貼文 | `?kind=events` |
| `home-search-open` | 首頁 | 搜尋對話框，輸入「演講」 | 點可見的搜尋按鈕（手機 `.topbar-search`、桌面 `.nav-search`），只截視窗 |
| `home-signed-in` | 首頁 | 登入後，「更多」選單展開 | 模擬 session，點 `.nav-more > summary`，只截視窗 |
| `events` | 活動 `/events/` | 有資料 | — |
| `events-light` | 活動 | 淺色 | 外觀設為淺色 |
| `events-filtered` | 活動 | 陽明交大＋演講 | `?school=nycu&cat=演講` |
| `events-no-results` | 活動 | 搜尋無結果 | `?q=zzqxv` |
| `events-loading` | 活動 | 載入中 | `data=loading` |
| `events-error` | 活動 | 載入錯誤 | `data=error` |
| `events-empty` | 活動 | 空資料 | `data=empty` |
| `calendar` | 月曆 `/calendar/` | 有資料 | — |
| `calendar-filtered` | 月曆 | 清大＋藝文 | `?school=nthu&cat=藝文` |
| `calendar-loading` | 月曆 | 載入中 | `data=loading` |
| `stories` | 限動 `/stories/` | 有資料（示意卡，只看外框） | — |
| `stories-empty` | 限動 | 沒有限動 | `data=empty` |
| `subscribe` | 訂閱 `/subscribe/` | 登入前 | — |
| `subscribe-signed-in` | 訂閱 | 登入後 | 模擬 session |
| `notify` | App 通知 `/notify/` | 登入前 | — |
| `notify-signed-in` | App 通知 | 登入後 | 模擬 session |
| `status` | 系統狀態 `/status/` | 有資料 | — |
| `status-error` | 系統狀態 | 載入錯誤 | `data=error` |
| `about` | 關於 `/about/` | — | — |
| `event-rich` | 活動頁 `/event/evt_nyculife_qy2s4vs6j8p5/` | 資訊完整（海報、地點、報名、說明） | — |
| `event-rich-light` | 活動頁（同上） | 淺色 | 外觀設為淺色 |
| `event-sparse` | 活動頁 `/event/evt_9f1b235dfb82/` | 資訊很少（全天、無地點、無報名） | — |
| `event-signed-in` | 活動頁（資訊完整） | 登入後 | 模擬 session |
| `org-rich` | 單位頁 `/org/47/`（陽明交大藝文中心） | 活動多 | — |
| `org-empty` | 單位頁 `/org/306/`（清大烹飪社） | 沒有活動 | — |
| `source` | 名錄 `/source/` | 有資料 | — |
| `source-light` | 名錄 | 淺色 | 外觀設為淺色 |
| `source-search` | 名錄 | 搜尋「吉他」 | `?q=吉他` |
| `source-followed-empty` | 名錄 | 只看已追蹤，尚未追蹤 | `?follow=on` |
| `source-error` | 名錄 | 載入錯誤 | `data=error` |
| `submit` | 回報活動 `/submit/` | 登入前 | — |
| `submit-signed-in` | 回報活動 | 登入後，有一筆回報 | 模擬 session |
| `account` | 帳號 `/account/` | 登入前（登入選項） | — |
| `account-signed-in` | 帳號 | 登入後 | 模擬 session |
| `account-signed-in-light` | 帳號 | 登入後、淺色 | 模擬 session，外觀設為淺色 |
| `not-found` | 不存在的網址 `/no-such-page/` | 404 | — |

44 個狀態 × 2 尺寸 = 每組 88 張。

## 參考對手

第一輪截一次，之後每輪重用同一組檔案：

| ID | 網址 | 對應的竹梅頁面 |
|---|---|---|
| `accupass-home` | https://www.accupass.com/ | 首頁／探索 |
| `accupass-search` | https://www.accupass.com/search?q=講座 | 活動列表、篩選 |
| `luma-taipei` | https://luma.com/taipei | 活動列表、城市日曆 |
| `luma-discover` | https://luma.com/discover | 探索、分類 |
| `nycu-life-events` | https://events.life.nycu.edu.tw/ | 校園活動列表 |

## 重現

```bash
R=/tmp/cm-review PY=$R/venv/bin/python T=docs/design-review/tools
# 1. 公開資料快照與 fixture（每次 hill climb 只做一次）
for f in events posts sources stories; do curl -s https://chumei.observe.tw/data/$f.json > $R/data/$f.json; done
curl -s https://chumei.observe.tw/api/status.json > $R/data/status.json
$PY $T/prepare_fixture.py $R
# 2. 隔離建置（基準＝main，新版＝目前的 worktree）
$PY $T/build_preview.py main $R/builds/baseline
$PY $T/build_preview.py WORKTREE $R/builds/new
# 3. 預覽與截圖（一次一個瀏覽器）
CHUMEI_PREVIEW_NOW=2026-11-12T15:30:00+08:00 PYTHONPATH=$T/frozen $PY $T/preview_server.py $R/builds/new 8411 &
(cd $T && $PY capture.py site http://127.0.0.1:8411 $R/sets/new-r1 --session-file $R/builds/new/session.txt)
(cd $T && $PY capture.py references $R/sets/reference)
# 4. 組一輪盲測
python3 $T/make_round.py 1 $R/sets/new-r1
```
