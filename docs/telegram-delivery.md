# Telegram 發送失敗與恢復

`scripts/publish_telegram.py` 會先嘗試以圖片和 HTML 說明發送活動。
Telegram 明確回覆 HTTP API 錯誤碼 `400`，且說明屬於下列圖片內容拒絕時，
才將同一段說明改用純文字訊息發送：

- `Bad Request: failed to get HTTP URL content`
- `Bad Request: wrong type of the web page content`
- `Bad Request: PHOTO_INVALID_DIMENSIONS`
- `Bad Request: IMAGE_PROCESS_FAILED`

文字保留原本 HTML、連結和靜音設定，關閉連結預覽；不重新排版或拆分活動。
原本圖片說明已限制於 1,024 個 UTF-16 單位，因此也符合文字訊息限制。
只有成功回覆的文字訊息 ID 才會寫入既有進度紀錄；被拒絕的圖片不占用一個段落。
後續段落失敗時，下次執行依已寫入的段落數接續，已確認送達的文字不會重送。

發送 API 每次只嘗試一次。逾時、網路中斷、無法解析回覆、權限錯誤、限流、
其他 `400` 和伺服器錯誤都不會觸發文字備援，也不會在同一次呼叫自動重試。
它們保留原有失敗退出行為，未確認送達的段落不會寫入進度。

Telegram 發送 API 沒有本地使用的冪等鍵。網路結果不明時，訊息仍可能已送達，
下一次排程重試尚未確認的段落也可能重複；需要暫停發送排程，核對頻道與
`state/telegram.json` 的訊息 ID 後再恢復。這個修正處理明確圖片拒絕，
不宣稱能讓網路結果不明的發送達到 exactly-once。

驗證只使用模擬 API：

```sh
.venv/bin/python -m unittest discover -s tests -p test_publish_telegram.py -q
```

不需要對正式頻道發送測試訊息；程式部署後，已安裝的定時工作會在正常排程使用修正。
