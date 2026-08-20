# 竹梅 chumei — 開發計畫（2026-08-21 深夜衝刺）

清大＋交大校園活動聚合站。名稱「竹梅」＝竹（交大，凌竹銘）＋梅（清大，梅貽琦），倒過來致敬梅竹賽。

## 架構

```
data/sources/*.csv          ← 人工維護的來源清單（IG 帳號、公告站、FB 專頁）
scripts/fetch_*.py          ← 各來源 adapter，統一輸出 inbox JSONL（docs/SCHEMA.md）
data/feeds/inbox/*.jsonl    ← 正規化貼文/公告 inbox（不進 git）
scripts/extract_events.py   ← LLM（文字＋海報圖 vision）判別活動＋抽欄位，快取於 state/
scripts/build_site.py       ← 合併、去重、override、產出 site/data + site/api + site/feeds + 詳情頁
site/                       ← 靜態站（Caddy file_server 直接服務）
state/                      ← 抓取 seen-state、LLM 快取（不進 git）
```

- IG 抓取走本機 RSSHub：`http://127.0.0.1:1200/instagram/2/user/<username>`（bamboo-rsshub 容器，已配 IG cookie）。節制：每帳號 limit 5、整輪攤平、一天一輪。
- FB 走 Apify（token 在 .env `APIFY_TOKEN`），參考 `~/Documents/Harmonica-in-Taiwan/scripts/apify_facebook_fetcher.py`。
- LLM 走 OpenAI-compatible relay（.env `CHUMEI_LLM_*`，值抄自 harmonica）。
- 官方活動直接吃 NYCU LIFE 公開 API：`https://events.life.nycu.edu.tw/api/activities`。

## 資料來源

| 來源 | Adapter | 狀態 |
|---|---|---|
| 交大 infonews 公告系統（演講/藝文/其他活動） | fetch_infonews.py | 派工 Codex |
| 清大 RPage 各單位站（藝文/學務/課指組…） | fetch_rpage.py | 派工 Codex |
| 清交社團 IG（帳號清單 data/sources/ig_accounts.csv） | fetch_instagram.py | 我寫；清單由研究 agent 產 |
| NYCU LIFE 官方活動 API | fetch_nycu_life.py | 我寫（小） |
| FB 專頁（Apify） | fetch_facebook.py | 深夜補 |

## 前端

靜態站，設計系統採 nycu-life-ui-skill（tokens.css 已 vendor 進 site/assets/）但品牌是竹梅自己的：
梅（清大＝紫）＋竹（交大＝藍 #0045F2 系）。頁面：首頁河道＋篩選（校區/類型/主辦）、
日曆檢視、活動詳情（SEO 靜態頁）、feeds 說明頁、關於/投稿。地圖資訊仿 events.life.nycu.edu.tw
的 campus+venue 模型：nthu-main / nthu-nanda / nycu-guangfu / nycu-boai / nycu-yangming / online / other。

## 進度記錄（隨時更新，供 context reset 後接續）

- [x] 全部 fetcher 完成並實測：infonews（TLS strict 修正）、rpage（8 站 95 筆）、IG（RSSHub）、NYCU LIFE API
- [x] extract_events.py：vision 抽取、429 backoff、Pillow 縮圖、快取；build_site.py：去重、海報快取、RSS/ICS/詳情頁/sitemap
- [x] 前端上線：https://chumei.observe.tw （Caddy vhost 用預設 ACME，不能用 tls_cloudflare —— token 只有 elvismao.com zone）
- [x] launchd 每 3h：tw.observe.chumei.pipeline（IG 一天一輪，run_pipeline.py 控制）
- [x] GitHub 公開：github.com/skyhong2002/chumei ＋ 投稿/回報 issue 模板
- [x] Codex 視覺驗證一輪，修了日曆欄寬/深色對比/placeholder/海報裁切
- [x] IG 80 帳號回填完成（74 成功/363 篇；5 個壞 handle 已標 inactive）
- [x] 幻覺審計（34 場抽驗）→ prompt v2 ＋ 程式後驗（日期範圍、星期比對、自我指涉連結）＋ 二階段去重
      → 全量重抽驗證：年份錯誤、報名截止誤判、亂填免費、重複活動全數修復
- [x] RPage 正文擷取修復（選單→文章本體，Codex）；回抓 42 筆較舊公告
- [x] 最終視覺驗收（Codex，正式站）：手機篩選收合、深色日曆、去重 —— 三項全過
- [x] 2026-08-21 夜間衝刺完成：https://chumei.observe.tw 上線，214 場活動（23 場即將登場）
- [ ] 之後再說：FB/Apify fetcher、站內投稿表單（先用 GitHub issue）、IG 深度回填（limit>5）
