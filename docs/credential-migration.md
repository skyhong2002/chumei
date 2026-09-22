# 停用 Keychain 與一次性憑證遷移

2026-09-23 起網站的登入、訂閱簽章與 Apify 貢獻加密設定只讀取 `.env`、`.env.apify` 及程序環境變數，不再呼叫 macOS `security` 或讀取 Chrome 金鑰。這是憑證存放位置的遷移，不是輪替金鑰；既有登入、私密訂閱網址與貢獻 token 應維持可用。Web Push VAPID 私鑰仍在受保護的 `state/push/`，由推播狀態備份保留，不在這次遷移範圍。歷史稽核文件中的 Keychain 待辦反映當時狀態，目前操作以本頁為準。

## 部署前：只匯出本站需要的值

先保留受限權限的目前環境檔備份。由主機操作者在本機一次性取得以下舊 Keychain services 的有效值；account 為 `chumei`。不要匯出整個系統 Keychain，不要動 Chrome 或其他網站項目，不把輸出貼到終端記錄、issue 或 PR。

| 舊 service | 新 `.env` 設定 |
| --- | --- |
| `tw.observe.chumei.nycu-oauth-client-id` | `CHUMEI_NYCU_OAUTH_CLIENT_ID` |
| `tw.observe.chumei.nycu-oauth-secret` | `CHUMEI_NYCU_OAUTH_CLIENT_SECRET` |
| `tw.observe.chumei.google-oauth-client-id` | `CHUMEI_GOOGLE_OAUTH_CLIENT_ID` |
| `tw.observe.chumei.google-oauth-secret` | `CHUMEI_GOOGLE_OAUTH_CLIENT_SECRET` |
| `tw.observe.chumei.feed-signing-key` | `CHUMEI_FEED_SIGNING_KEY` |
| `tw.observe.chumei.apify-contribution-key` | `CHUMEI_APIFY_CONTRIBUTION_KEY` |

不是每個 service 都一定存在。舊程式對每個設定先讀非空環境值，再查對應 Keychain 項目。不要用已過期的 Keychain 值覆蓋原本有效的環境設定。遷移時先用舊程式在實際服務設定下求出下列兩個**最終生效值**，再將它們固定到獨立的環境設定：

- `AuthConfig.from_env().feed_signing_key` → `CHUMEI_FEED_SIGNING_KEY`。舊站未設獨立值時，這是 `sha256("chumei-saved-feed-v1\0" + NYCU client secret)` 的十六進位字串。
- `apify_contributions.encryption_secret()` → `CHUMEI_APIFY_CONTRIBUTION_KEY`。舊站未設獨立值時，這是 NYCU client secret 本身；不要誤填成內部衍生的 Fernet key，否則會再次衍生而無法解密舊資料。

只在程序記憶體內比較遷移前後有效值及驗證結果，操作記錄僅留下通過／失敗，不記錄秘密或其雜湊。兩值固定後，日後輪替 OAuth secret 不會連帶更換訂閱或貢獻資料的金鑰。新程式仍保留相同的 OAuth 衍生 fallback，供未使用獨立值的部署相容使用。

環境檔格式是每行純 `KEY=value`，不加引號、`export` 或跨行值。先以 `0600` 權限寫入暫存檔再原子替換，確認檔案擁有者是服務帳號，父目錄不允許其他使用者改寫。`.env.apify` 覆蓋 `.env` 同名項目，程序中的 `CHUMEI_*` 又會覆蓋檔案；因此必須同時確認 launchd 服務有無舊環境覆蓋值。程序環境專有的秘密不會自動納入檔案備份。

## 更新與驗收

1. 完成憑證檔遷移後再部署新程式，重新啟動讀取設定的常駐服務；不啟動通知發送工作。
2. 在不輸出內容的條件下驗證設定值一致、原訂閱 token 簽章可驗、既有貢獻 token 可解密；再檢查帳號 health 與登入供應商設定。
3. 立即建立並驗證一份新的私密備份，確認其中包含遷移後的環境檔，並在隔離還原目錄驗證。迁移前的舊備份可能沒有這些值，不能單獨作為恢復依據。
4. 舊 Keychain 項目保持原樣、停止使用，無須刪除。此次變更也不會移除任何 Chrome 或其他應用程式的 Keychain 項目。

`refresh_ig_cookie.py` 是無目前 caller 的舊 RSSHub 操作工具，已退役：呼叫只會顯示停用提示後結束，不再讀 Chrome、改外部 RSSHub 設定或重啟容器。現行 IG 抓取使用 Apify，額度與來源檢查見 [來源健康文件](source-health.md)。

## 保管與還原

本機備份已包含 `.env`、`.env.apify`，目錄 `0700`、檔案 `0600`；金鑰不再另外依賴 Keychain 匯出才能還原。備份含可直接使用的秘密與個人資料，異地複本必須加密。異地目的地、加密金鑰與主機完全故障演練仍是獨立待辦，詳見 [備份與還原](backup-recovery.md)。
