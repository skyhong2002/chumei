# 2026-11-14 正式服務整併

Telegram 活動 `evt_b5dfcd621d7b` 的 404 源於雙機狀態分歧：
公開網域已切到 sky-server，但 sky-mini 的排程仍持續發布與發送通知。
sky-server 的發布驗證又因上游錯誤訊息包含「token」字樣而失敗，
網站因此停留於 2026-11-12 15:03 的版本。

## 現在的服務位置

* 程式：`/home/sky/Projects/chumei`。
* 部署來源：`/home/sky/Projects/chumei-deployment`。
* 正式設定與持久資料：`/srv/chumei`。
* 網站與動態服務由 Docker Compose 管理；網站由 nginx 讀取
  `/srv/chumei/published/current`，動態服務保留原有網域與路由。
* Pipeline、投稿處理、Web Push、Telegram 與備份使用 systemd timers。
* 宣傳檔案服務只在內部網路提供，不對外公開。
* 預覽容器讀取同一份 `/srv/chumei/site`。

sky-mini 的十個 `tw.observe.chumei.*` 服務、`com.chumei.promo-files`
與 `com.chumei.site-preview` 均已 bootout 並以 launchctl disable 停用，
避免重新登入或重開機後重啟第二個通知發送端。

## 資料處理

遷移前暫停兩端寫入並備份 server 狀態。合併兩端來源 inbox、抽取快取、
Telegram 已發送活動、Web Push 投遞紀錄與訂閱；Bot offset 採兩端較大值。
SQLite 保留 server 使用者狀態，補入 mini 缺少的資料列及登入 sessions，
衝突資料列採較新的 updated_at；完整性與外鍵檢查皆須通過。
VAPID 金鑰兩端一致，保留原訂閱身分。原始 mini 資料及 server 備份保存在
正式資料目錄下的遷移備份，限擁有者存取，不對外提供。
mini 的備份檔與舊日誌亦已保存到 server。

公開狀態資料現在將含憑證名稱的上游錯誤轉成固定認證錯誤訊息，
不再公開原始認證回應；輸出驗證的憑證檢查保持啟用。
容器透過 CHUMEI_CHROME_PATH 使用映像內的 Chromium。

不要直接執行舊 coordinator-cutover.sh 覆蓋目前資料；該腳本假設尚未切換，
不會合併切換後兩端已接受的資料。回復前須停止 server timers 與容器，
從現有 server 資料建立一致快照，避免還原成遷移前狀態。
