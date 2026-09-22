# 網站原子發布與回復

`site/` 現在保留 Git 管理的 HTML 範本、JS、CSS、品牌資產，以及 fetcher 的可變快取。正式靜態網站改由 `published/current` 提供；這是指向已完成驗證之 release 的 symlink。**必須完成下列一次性 Caddy 切換，才會啟用正式站隔離。**

## 一次性啟用

先確認舊版 pipeline 沒有執行，再在正式 checkout 執行以下命令。這不會抓取社群、呼叫抽取模型、發送推播，也不會改寫既有 `site/` 範本：

```sh
.venv/bin/python scripts/publish_site.py --offline
CHUMEI_BUILD_DIR="$PWD/published/current" .venv/bin/python scripts/validate_outputs.py
```

離線模式使用現有海報、貼文圖、頭貼、來源截圖、地理編碼與 API 額度快取；缺圖沿用既有品牌 fallback，不會寫入失敗下載紀錄。如果需要的新資料尚未存在，驗證失敗會保留舊網站，不會切换 current。

確認 `published/current/index.html`、`data/events.json`、`api/events.json`、`api/status.json`、`feeds/all.ics` 都存在，再備份目前 Caddyfile，將靜態網站的 `root` 改為：

```caddyfile
root * /Users/skyhong/Projects/chumei/published/current
```

保留原有動態 API 反向代理。先執行 `caddy validate --config /實際路徑/Caddyfile`，成功後才執行 `caddy reload --config /實際路徑/Caddyfile`。不要把 `site/` 改為 symlink，也不要以 rsync 覆寫正式 release。

第一次切換後，重新啟動已載入舊路徑的常駐讀取服務：

```sh
launchctl kickstart -k "gui/$(id -u)/tw.observe.chumei.auth"
launchctl kickstart -k "gui/$(id -u)/tw.observe.chumei.mcp"
launchctl kickstart -k "gui/$(id -u)/tw.observe.chumei.bot-telegram"
launchctl kickstart -k "gui/$(id -u)/tw.observe.chumei.bot-line"
launchctl kickstart -k "gui/$(id -u)/tw.observe.chumei.push"
```

只對實際安裝的服務執行。這些是服務重啟，沒有執行 `publish_push.py` 或 Telegram 發送器。讀取服務保留未解析的 `published/current/...` 路徑，因此之後每次發布不必重新啟動；定時執行的投稿、Telegram、Push 程式下一次啟動即會讀取正式版本。首次發布尚無 `previous`，若首次啟用驗收失敗，還原 Caddy root 到原本 `site/`，原目錄仍完整保留。

## 日常操作

```sh
# 正常 pipeline：fetch → extract → isolated build/validate → atomic publish
.venv/bin/python scripts/run_pipeline.py

# 只重建與發布；--offline 不做建站期間的圖片/地理/額度網路請求
.venv/bin/python scripts/publish_site.py --offline

# 原子回復上一次成功發布；可重複執行，不會來回切換
.venv/bin/python scripts/publish_site.py --rollback

# 單獨清理舊 release，至少保留最新 3 個，以及 current/previous
.venv/bin/python scripts/publish_site.py --prune --keep 3
```

每次成功發布後會自動套用相同保留策略（預設最新 3 個，`current` 和 `previous` 永不刪除）；最壞會保留 5 個版本，避免持續累積每版約 629 MB 的快照。保留數量可用 `--keep` 調整。清理失敗只記錄警告，不會誤報已成功的發布失敗。人工備份、未完成 staging 不會自動刪除；程序被強制終止留下的 `.staging-*` 可在確認無 publisher 執行時手動清理。

`state/pipeline.lock` 阻止同時執行多輪 pipeline；`state/publish.lock` 保護發布、回復與清理。鎖由作業系統隨程序結束釋放，重複作業會以非零狀態退出。抽取失敗不會發布；部分 fetcher 失敗仍維持原先「記錄並使用其既有資料」的策略。

建站子程式只寫入 `CHUMEI_BUILD_DIR` 指定的私有 staging，依序完成地圖、主站、狀態頁和輸出驗證後，才使用同檔案系統的 `os.replace()` 一次更換 `current`。stage 使用真實檔案複本，不使用會污染正式檔案的 hardlink；歷史活動 URL 和圖片快取會保留，最新 repository 範本和 fetcher 輸出會覆蓋進新 stage。一般建站 CLI 仍可用於本機 `site/` 預覽，正式 Caddy 不再讀取該目錄。

每個 HTTP 檔案請求都會取得完整舊版或完整新版檔案；跨越切換時間的多次 HTTP 請求仍可能分屬前後版本，既有歷史頁面與圖片會保留。這不是跨多次 HTTP 請求的交易協定。

## 驗證

```sh
.venv/bin/python -m unittest discover -s tests -p test_publish_site.py -v
.venv/bin/python -m unittest discover -s tests -p test_run_pipeline.py -v
```

測試會對每個建站步驟、驗證步驟與 current 指標切換注入失敗，確認正式目錄逐檔不變；也涵蓋程序間鎖定、來源範本保留、舊 URL 快取、回復、release 清理保護和常駐讀取路徑。所有故障注入均在臨時目錄，不碰正式站。
