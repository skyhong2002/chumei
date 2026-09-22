# 2026-09-23 修正與部署紀錄

本次接續 [全面檢查](site-audit-2026-09-23.md)，將原本 16 項各自建立 issue、交由獨立 agent 修正並開 PR，依序合併。驗收追加 Telegram 圖片拒絕卡住佇列、首頁桌機溢出兩項，共 18 個 issue。使用者授權時限為 2 小時，自台北時間 03:01 起。

## Issue 與修正 PR

| 項目 | Issue | PR | 結果 |
| --- | --- | --- | --- |
| A01 | [#2](https://github.com/skyhong2002/chumei/issues/2) | [#19](https://github.com/skyhong2002/chumei/pull/19) | 共用安全出站、重新導向／DNS／推播限制 |
| A02 | [#3](https://github.com/skyhong2002/chumei/issues/3) | [#22](https://github.com/skyhong2002/chumei/pull/22) | 23 場進行中活動保留於一般與自訂 ICS |
| A03 | [#4](https://github.com/skyhong2002/chumei/issues/4) | [#24](https://github.com/skyhong2002/chumei/pull/24) | 海外時區修正、來源時區與不確定時間複核 |
| A04 | [#5](https://github.com/skyhong2002/chumei/issues/5) | [#20](https://github.com/skyhong2002/chumei/pull/20) | 隔離建站、先驗證、原子發布與回復 |
| A05 | [#6](https://github.com/skyhong2002/chumei/issues/6) | [#27](https://github.com/skyhong2002/chumei/pull/27) | 來源覆蓋、額度／錯誤分類與過期檢查 |
| A06 | [#7](https://github.com/skyhong2002/chumei/issues/7) | [#25](https://github.com/skyhong2002/chumei/pull/25) | 新帳號預設私人、公開範圍說明 |
| A07 | [#8](https://github.com/skyhong2002/chumei/issues/8) | [#26](https://github.com/skyhong2002/chumei/pull/26) | 頁面與資產真正 404 |
| A08 | [#9](https://github.com/skyhong2002/chumei/issues/9) | [#21](https://github.com/skyhong2002/chumei/pull/21) | 同名同時不同場地 SEO 可辨識 |
| A09 | [#10](https://github.com/skyhong2002/chumei/issues/10) | [#29](https://github.com/skyhong2002/chumei/pull/29) | 共用分類、別名及未知分類待審 |
| A10 | [#11](https://github.com/skyhong2002/chumei/issues/11) | [#33](https://github.com/skyhong2002/chumei/pull/33) | 資料品質清單、證據與缺漏標記 |
| A11 | [#12](https://github.com/skyhong2002/chumei/issues/12) | [#23](https://github.com/skyhong2002/chumei/pull/23) | 近期／歷史資料分拆、延後地圖、名錄漸進顯示 |
| A12 | [#13](https://github.com/skyhong2002/chumei/issues/13) | [#28](https://github.com/skyhong2002/chumei/pull/28) | 帳號刪除、隱私頁與還原刪除紀錄 |
| A13 | [#14](https://github.com/skyhong2002/chumei/issues/14) | [#32](https://github.com/skyhong2002/chumei/pull/32) | 跨平台 hash lock、乾淨環境 CI 與瀏覽器驗證 |
| A14 | [#15](https://github.com/skyhong2002/chumei/issues/15) | [#34](https://github.com/skyhong2002/chumei/pull/34) | 一致性備份、隔離還原、部署設定產生器 |
| A15 | [#16](https://github.com/skyhong2002/chumei/issues/16) | [#35](https://github.com/skyhong2002/chumei/pull/35) | 文字連結、焦點與對話框鍵盤操作 |
| A16 | [#17](https://github.com/skyhong2002/chumei/issues/17) | [#36](https://github.com/skyhong2002/chumei/pull/36) | 目前維運指南、歷史計畫標記及產品文案 |
| A17 | [#31](https://github.com/skyhong2002/chumei/issues/31) | [#37](https://github.com/skyhong2002/chumei/pull/37) | Telegram 圖片明確拒絕時退回文字，保留進度 |
| A18 | [#38](https://github.com/skyhong2002/chumei/issues/38) | [#39](https://github.com/skyhong2002/chumei/pull/39) | 首頁多欄溢出限定於橫向捲動容器 |

另外，PR #18 保留原有本機提交及檢查基準；PR #30 修正整合測試發現的單位頁日期型別衝突。該次建站失敗時，已發布版本保持完整，驗證了發布隔離機制。

## 驗收與正式環境

正式修正版於台北時間 **03:36:52** 發布；下列驗收記錄於 **2026-09-23T03:38:43+08:00**，在 2 小時時限內完成。另有[機器可讀證據摘要](site-remediation-2026-09-23-evidence.json)。

- 完整 Python／Node 套件共 **341 項測試通過**；SEO 使用完整正式產物檢查，非僅少量 fixture。
- 主分支已啟用保護：必須透過 PR，`verify` 通過且與最新 main 整合後才能合併；此規則也套用管理者。
- GitHub Ubuntu CI 使用 Python 3.14、Node 24、完整 hash lock 與正式機同版 Caddy 2.11.2；涵蓋離線產物、桌面／手機與故意破壞 JSON／canonical 的失敗攔截。
- 正式站桌面／手機共 34 次頁面檢查：回應碼、未捕捉 JS 錯誤、圖片與頁面寬度；訂閱／登入頁另執行 8 次明暗主題 WCAG axe 檢查。首頁追加 390／1024／1440／1920 寬度及第三欄、篩選器鍵盤驗證。
- 一般與自訂 ICS 各確認 **23 場進行中活動，遺漏 0 場**。兩筆海外活動時間已修正；交流會舊 ID 導向保留的活動。
- 正式離線建站產生 **2,838 場活動**、479 個單位頁及資料品質清單，發布前產物驗證通過。活動初始索引約 **982 KB 原始／190 KB gzip**，相較原先全量 4.58 MB，原始大小下降約 79%；未宣稱已通過實際使用者 Core Web Vitals。
- Caddy 已提供 `published/current`；不存在頁面／活動回 HTML 404，不存在 JS 回文字 404。帳號、Feed、Push 設定及 MCP initialize 仍正常。
- auth、MCP、LINE／Telegram Bot、Push 常駐服務已重新載入。沒有用真實訊息驗證推播或 Telegram 發送。
- 已啟用每小時本機備份至 `/Users/skyhong/Backups/chumei`，保留最近 168 份成功快照；第一份正式備份完成 checksum、SQLite 與隔離還原檢查。還原工具會重新套用最新刪除紀錄，不自動覆寫正式資料。
- 暫停的 pipeline／投稿排程已恢復，沒有額外觸發抓取或發送工作。
- 原有未提交的 HTML、頭貼與 geocode 變更保留；另保留部署前 patch、stash 與受限權限的資料／Caddy 備份。

## 尚未被本次程式修正消除的限制

- **上游額度與內容覆蓋**：狀態仍如實顯示 `degraded`；額度不足和已錯過的限動不會因修正監控而恢復。本次沒有購買額度、調高抓取預算或任意停用來源。
- **來源資料缺漏**：`/quality/` 提供待核對清單和來源證據入口，未把未知地點／報名網址猜成已確認。來源未提供的資訊仍須主辦或人工查證。
- **異地與密鑰復原**：本機定期備份已實際啟用；異地加密副本和 macOS Keychain 的離機保管尚未設定，不能保證整台主機／磁碟損失後完整復原。見 [備份還原](backup-recovery.md)。
- **真實身分與裝置**：OAuth 真實登入、Safari／iOS Web Push、外部服務最終投遞仍須實際身分／裝置驗收；模擬測試與公開健康回應不能取代它們。
- Telegram 圖片拒絕已有文字備援；網路回應不明時仍有平台缺乏冪等鍵造成的既有重複風險，見 [投遞說明](telegram-delivery.md)。

日常操作入口：[維運指南](operations.md)。本文件記錄本次檢查與部署當下狀態，不表示未來所有來源永遠健康。
