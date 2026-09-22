# 可重現的本機與 CI 檢查

支援 Python 3.14、Node.js 24 LTS。`requirements.in` 列直接依賴，`requirements.txt` 固定直接及間接依賴與 SHA-256；安裝必須啟用 hash 驗證。這份 lock 也包含現有 Instagram、瀏覽器 cookie 與字型工具的執行依賴。

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/ci_check.py
```

Linux 需使用 `playwright install --with-deps chromium`。Caddy 路由測試另需安裝 Caddy；GitHub Actions 會安裝，因此不會略過。CI 的 `verify` job 應設為主分支保護的必要檢查；workflow 本身不部署，也不變更 repository 分支保護設定。

檢查器將 Git 追蹤的目前內容複製至暫存目錄（新檔案先 `git add`），只注入合成活動與貼文，執行真正的離線原子建站、完整 Python/Node 測試、產物 SEO、桌面及手機 Chromium smoke test。Python 子程序封鎖非 loopback 網路，瀏覽器只准存取暫存 HTTP server；不讀本機 `.env`、帳號 DB 或正式事件，不執行抓取／推播。離開時移除暫存資料。測試也刻意破壞 JSON 與 canonical，確認產物驗證會失敗。SEO 重複、缺少 canonical 或預覽資料會讓完整測試失敗。

更新依賴時使用 `uv`，並將 lock 與通過的測試一同提交：

```sh
uv pip compile requirements.in --python-version 3.14 --generate-hashes --output-file requirements.txt --upgrade
```

更新後應重新建立乾淨虛擬環境執行以上安裝與檢查。Playwright 的 browser revision 隨 lock 內套件版本固定；Node/Caddy/Python 的 patch 與作業系統安全更新由 CI runner 提供，並非 bit-for-bit 系統映像。
