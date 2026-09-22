# 外部連結與推播出站限制

使用者投稿頁面、海報下載、建站海報快取、公告截圖共用 `scripts/safe_outbound.py`。只允許標準 80／443 port 的 HTTP(S)，拒絕 URL 帳密、非公開 IP、IPv6 transition address，以及任何包含非公開 IP 的 DNS 回答。每次重新導向均重新檢查 DNS，實際連線固定使用該次核准的 IP；TLS SNI、憑證驗證和 Host 保留原主機名稱，不讀取代理環境設定。

單次下載預設最多 8 MB、5 次轉址、25 秒期限；DNS、連線及單次讀取各限制 5 秒。期限在每次讀取前檢查，最後一次阻塞讀取可能額外花至多 5 秒。系統 DNS 呼叫本身不能取消，但最多 4 個解析工作，呼叫端等待有期限。只接收未壓縮 HTTP 回應，避免解壓縮炸彈。TLS 驗證失敗會停止抓取並走既有重試／人工複核流程。

截圖採用離線、關閉 JavaScript、封鎖 service worker 的瀏覽器 context。每個 document、stylesheet、image、font 請求皆由上述傳輸層取得，再注入瀏覽器；沒有 `route.continue_()` 或瀏覽器自行抓取。每頁最多 60 個請求、16 MB、30 秒的抓取預算。需執行 JavaScript 才能顯示的內容可能無法截圖，仍由既有人工複核機制處理。

Web Push 僅接受以下服務的 HTTPS endpoint，精確比對主機名稱：

- `fcm.googleapis.com`：Chrome／Edge 標準 FCM 推播。
- `updates.push.services.mozilla.com`：Firefox。
- `web.push.apple.com`：Safari。

其他 provider（例如舊版 Windows WNS endpoint）目前不接受；新增支援需明確審查 provider 範圍。實際發送也重新驗證既有訂閱，使用相同固定 IP 傳輸，禁止所有轉址，回應上限 64 KB，期限 15 秒。訂閱／測試 API 共用每個 endpoint 每分鐘一次、整個服務每分鐘 30 次的限制；目前部署為單個 uvicorn process，若改成多 worker，需換成共享限流儲存。JSON 輸入最多 16 KB。原有登入投稿每帳號每日 10 筆限制保留。

測試不使用真實 endpoint、密鑰、內網探測或推播。`test_safe_outbound.py` 覆蓋 DNS 混合回答、重新綁定、內網重新導向、回應大小、離線子資源、provider 與 API 限制；`test_push.py` 在暫存目錄產生測試金鑰，攔截加密 payload 後解密驗證。

設定中明確指定的本地 RSSHub 仍走既有內部服務連線；它不是投稿者可選擇的目的地。這些限制是應用程式層保護；維運仍可另搭配主機出站防火牆。
