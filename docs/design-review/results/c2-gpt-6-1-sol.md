# Round c2 blind review: gpt-6-1-sol

- Host: sky-mini
- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **C = baseline**, **B = new**, **A = reference**
- New set: `/Users/skyhong/cm-review/sets/new-c2`
- Mean of 12 scores: reference 7.38, new 7.71, baseline 6.0
- Note: Council round 2 (sky-mini). New = 4dfc155 (c1 fixes). Reply taken verbatim from the Codex session rollout.

Raw reviewer output below, unedited.

---

## 組 A

一句話總評：品牌與活動卡片成熟、閱讀節奏清楚，但部分手機頁面讓主視覺與推薦內容占據太多空間，活動查找效率和次要文字對比仍有改善空間。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 7.5 | [luma-discover](/Users/skyhong/cm-review/rounds/c2/A/luma-discover_desktop.png)（desktop）以熱門活動、分類、精選日曆分段，目的清楚；[luma-taipei](/Users/skyhong/cm-review/rounds/c2/A/luma-taipei_mobile.png)（mobile）的城市主視覺與介紹占去接近一個視窗，實際活動較晚出現。 |
| 字體排印 | 8 | [nycu-life-events](/Users/skyhong/cm-review/rounds/c2/A/nycu-life-events_mobile.png)（mobile）的中文標題、日期與地點字級分明，長標題能自然換行；[accupass-search](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_desktop.png)（desktop）的日期與標籤較小、較淡。 |
| 色彩 | 8 | [accupass-home](/Users/skyhong/cm-review/rounds/c2/A/accupass-home_desktop.png)（desktop）的青藍導覽與選取底線建立品牌；[luma-discover](/Users/skyhong/cm-review/rounds/c2/A/luma-discover_desktop.png)（desktop）以彩色分類圖示建立辨識，白底內容保持清爽。 |
| 間距與版面 | 7.5 | [luma-discover](/Users/skyhong/cm-review/rounds/c2/A/luma-discover_desktop.png)（desktop）的雙欄活動、分類格線與區段留白整齊；[nycu-life-events](/Users/skyhong/cm-review/rounds/c2/A/nycu-life-events_desktop.png)（desktop）的未登入近期活動卡留白偏大。 |
| 一致性 | 8 | 各產品內部各自成立：[accupass-home](/Users/skyhong/cm-review/rounds/c2/A/accupass-home_desktop.png)與[accupass-search](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_desktop.png)（desktop）延續圖片、標題、日期、地點的卡片結構；Luma 的圓角、灰色輔助文字與小型縮圖也有一致語言。不同品牌之間未作一致性扣分。 |
| 資訊密度 | 6.5 | [accupass-search](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_mobile.png)（mobile）單張大海報卡占據大量高度；[luma-discover](/Users/skyhong/cm-review/rounds/c2/A/luma-discover_desktop.png)（desktop）則能以小縮圖活動列呈現較多選項。 |
| 導覽 | 7.5 | [nycu-life-events](/Users/skyhong/cm-review/rounds/c2/A/nycu-life-events_mobile.png)（mobile）保留已收藏、已報名與分類頁籤；[accupass-search](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_desktop.png)（desktop）目前條件主要只露出「講座」與漏斗圖示，其他篩選內容不易直接辨識。 |
| 狀態與回饋 | 7 | [luma-taipei](/Users/skyhong/cm-review/rounds/c2/A/luma-taipei_desktop.png)（desktop）以「即將額滿」「已售罄」「候補名單」文字區分活動狀態；[nycu-life-events](/Users/skyhong/cm-review/rounds/c2/A/nycu-life-events_mobile.png)（mobile）說明登入後可釘選及查看報名。提供的畫面不足以評斷載入與錯誤流程。 |
| 響應式 | 7.5 | [accupass-search](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_mobile.png)（mobile）改為單欄；[luma-discover](/Users/skyhong/cm-review/rounds/c2/A/luma-discover_mobile.png)（mobile）以卡片露出下一項提示橫向內容，但多個區段都需要橫向探索。 |
| 文案 | 8 | [nycu-life-events](/Users/skyhong/cm-review/rounds/c2/A/nycu-life-events_mobile.png)（mobile）的「登入後可釘選活動分類」直接說明用途；[luma-taipei](/Users/skyhong/cm-review/rounds/c2/A/luma-taipei_mobile.png)（mobile）的城市介紹較長，對立即找活動的幫助有限。 |
| 無障礙 | 6.5 | [accupass-search](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_desktop.png)（desktop）的日期、地點與統計文字視覺對比偏弱；[nycu-life-events](/Users/skyhong/cm-review/rounds/c2/A/nycu-life-events_mobile.png)（mobile）輪播控制有文字與較大的按鈕。未由截圖推論鍵盤或 ARIA 行為。 |
| 動畫與轉場 | 6.5 | [nycu-life-events](/Users/skyhong/cm-review/rounds/c2/A/nycu-life-events_mobile.png)（mobile）可見上一張、下一張、頁碼與「暫停輪播」，有使用者控制線索；其餘主要是靜態卡片，無法確認動畫速度、流暢度或減少動態效果設定，保守評分。 |

要保留的優點：

- Luma 探索頁的小縮圖活動列與清楚分段，兼顧掃讀與視覺吸引力。
- Luma 台北頁依日期排列的活動時間軸，以及有文字的額滿、售罄與候補狀態。
- NYCU LIFE 活動卡將日期、地點與校區獨立呈現，便於判斷是否適合參加。
- NYCU LIFE 輪播提供頁碼與「暫停輪播」控制。
- ACCUPASS 的分類選取底線與圖片卡片結構具有穩定辨識度。

最重要的五個問題（由嚴重到輕微）：

1. [資訊層級] [luma-taipei] [mobile] 城市主視覺、介紹與訂閱區高度約 770 CSS px，首張活動卡到約 880 CSS px 才出現 —— 使用者進站後難以立即判斷有哪些活動 —— 縮短手機主視覺，讓首筆活動與日期提早出現，城市介紹可收合。
2. [無障礙] [accupass-search、luma-taipei] [兩者] 日期、地點與主辦等決策資訊使用偏淡灰字，可見於 [accupass-search_desktop.png](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_desktop.png) 卡片下半部及 [luma-taipei_mobile.png](/Users/skyhong/cm-review/rounds/c2/A/luma-taipei_mobile.png) 活動列 —— 這些資訊需要穩定可讀，不能只靠粗黑標題吸引注意 —— 加深輔助文字，保留字重與字級的主次差異。
3. [間距與版面] [accupass-home] [兩者] [accupass-home_desktop.png](/Users/skyhong/cm-review/rounds/c2/A/accupass-home_desktop.png) 左下推廣浮層與右下 Cookie 告示同時覆蓋內容；手機 Cookie 告示也占用明顯高度 —— 多個浮層競爭注意力，壓縮活動瀏覽空間 —— 合併或延後推廣提示，讓 Cookie 說明更精簡並保留清楚關閉入口。
4. [導覽] [accupass-search] [兩者] 搜尋頁只明顯露出「講座」條件與漏斗入口，缺少醒目的結果總數及其他條件摘要 —— 使用者較難確認目前搜尋範圍 —— 在結果上方顯示總數、已選條件與清除入口，常用日期、地區條件可直接露出。
5. [資訊密度] [accupass-search] [mobile] [accupass-search_mobile.png](/Users/skyhong/cm-review/rounds/c2/A/accupass-search_mobile.png) 的大海報與卡片留白使一屏能比較的活動很少 —— 找活動需要反覆捲動 —— 提供較緊湊的列表模式，以小縮圖搭配標題、日期與地點。

## 組 B

一句話總評：網站用途、活動決策資訊與例外狀態交代完整，桌面與手機也有明確分工；主要摩擦集中在手機前置資訊過長、日曆零結果處理及少數長文字裁切。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8.5 | [home](/Users/skyhong/cm-review/rounds/c2/B/home_mobile.png)（mobile）直接說明彙整兩校活動、每則連回原文；[event-rich](/Users/skyhong/cm-review/rounds/c2/B/event-rich_mobile.png)（mobile）將標題、時間、地點、主辦與報名入口排在海報之前。 |
| 字體排印 | 8 | [event-rich](/Users/skyhong/cm-review/rounds/c2/B/event-rich_desktop.png)（desktop）的標題、日期與資訊表有明確字級區分，單日時間不重複完整日期；[event-rich-light](/Users/skyhong/cm-review/rounds/c2/B/event-rich-light_mobile.png)（mobile）的原始來源外連箭頭單獨換行，仍有細節可修。 |
| 色彩 | 8 | [events-light](/Users/skyhong/cm-review/rounds/c2/B/events-light_desktop.png)（desktop）在淺底保留學校色與報名狀態色；[home](/Users/skyhong/cm-review/rounds/c2/B/home_desktop.png)（desktop）深底使用藍、紫識別兩校，標籤同時有文字。 |
| 間距與版面 | 7.5 | [home](/Users/skyhong/cm-review/rounds/c2/B/home_desktop.png)（desktop）三欄能完整並列；[account-signed-in](/Users/skyhong/cm-review/rounds/c2/B/account-signed-in_desktop.png)（desktop）以雙欄分組設定，但右側空訂閱卡仍有較大留白。 |
| 一致性 | 8 | [submit-signed-in](/Users/skyhong/cm-review/rounds/c2/B/submit-signed-in_mobile.png)與[account-signed-in](/Users/skyhong/cm-review/rounds/c2/B/account-signed-in_mobile.png)（mobile）沿用圓角輸入框、藍色主按鈕與區塊邊框；[not-found](/Users/skyhong/cm-review/rounds/c2/B/not-found_mobile.png)（mobile）也延續同套搜尋與按鈕樣式。 |
| 資訊密度 | 7 | [events](/Users/skyhong/cm-review/rounds/c2/B/events_desktop.png)（desktop）四欄卡片便於比較；[events](/Users/skyhong/cm-review/rounds/c2/B/events_mobile.png)（mobile）標題、捷徑、說明與篩選占去約前 550 CSS px，首屏活動內容偏少。 |
| 導覽 | 8 | [home-signed-in](/Users/skyhong/cm-review/rounds/c2/B/home-signed-in_mobile.png)（mobile）有五個具文字的底部導覽與展開選單；[events-filtered](/Users/skyhong/cm-review/rounds/c2/B/events-filtered_mobile.png)（mobile）顯示可移除條件與全部清除，但日曆未延續同樣完整的清除方式。 |
| 狀態與回饋 | 8.5 | [source-error](/Users/skyhong/cm-review/rounds/c2/B/source-error_mobile.png)（mobile）清楚說明保留稍早名錄、哪些功能暫不可用並提供重載；[source-followed-empty](/Users/skyhong/cm-review/rounds/c2/B/source-followed-empty_mobile.png)（mobile）解釋尚未追蹤並提供「瀏覽全部單位」。日曆零結果仍較弱。 |
| 響應式 | 7.5 | [calendar](/Users/skyhong/cm-review/rounds/c2/B/calendar_mobile.png)（mobile）改用逐日議程，沒有硬塞月格；[source](/Users/skyhong/cm-review/rounds/c2/B/source_mobile.png)（mobile）將桌面表格改成列表並收合更多篩選，但單位頁的長地址仍被右緣裁切。 |
| 文案 | 8 | [event-sparse](/Users/skyhong/cm-review/rounds/c2/B/event-sparse_mobile.png)（mobile）以「場地尚未確認」與原公告提醒處理不完整資料；[submit](/Users/skyhong/cm-review/rounds/c2/B/submit_desktop.png)（desktop）用編號說明送出後處理方式。[status](/Users/skyhong/cm-review/rounds/c2/B/status_mobile.png)（mobile）仍露出 Apify 額度、後端等術語。 |
| 無障礙 | 7 | [home-search-open](/Users/skyhong/cm-review/rounds/c2/B/home-search-open_desktop.png)（desktop）可見搜尋框藍色焦點框與對話框遮罩；[events](/Users/skyhong/cm-review/rounds/c2/B/events_mobile.png)（mobile）的「我會去」「追蹤」附文字，但名錄與日曆仍有純圖示動作。未驗證實際鍵盤行為。 |
| 動畫與轉場 | 6.5 | [events-loading](/Users/skyhong/cm-review/rounds/c2/B/events-loading_mobile.png)（mobile）可見載入圖示、文字與篩選骨架；[home-search-open](/Users/skyhong/cm-review/rounds/c2/B/home-search-open_mobile.png)（mobile）有獨立搜尋畫面。日曆載入截圖與完成截圖採不同版型，存在版面切換疑慮；實際動態未測，保守評分。 |

要保留的優點：

- 首頁一句話說清楚網站服務範圍與原文可追溯性。
- 活動詳情手機版先呈現日期、地點、主辦與報名，再呈現海報。
- 活動詳情分開標示實際主辦與「收錄自」，資訊角色清楚。
- 錯誤提示保留舊內容，同時交代資料狀態、功能限制與重試入口。
- 搜尋無結果、未追蹤與 404 都有具體下一步。
- 桌面三欄河道、手機議程與名錄列表各自運用適合的版型。

最重要的五個問題（由嚴重到輕微）：

1. [響應式] [org-rich] [mobile] [org-rich_mobile.png](/Users/skyhong/cm-review/rounds/c2/B/org-rich_mobile.png) 第三筆《天官賜福》下方的長地址，在圖像約 y=1180、右緣被硬裁，未換行或顯示省略提示；更下方也有長地點相同情形 —— 地點是參加活動的重要資訊，裁切後無法完整閱讀 —— 允許地點換行，限制列寬並保留完整內容的查看方式。此處位於畫面中段，與截圖底部截斷無關。
2. [狀態與回饋] [calendar-filtered] [兩者] [calendar-filtered_mobile.png](/Users/skyhong/cm-review/rounds/c2/B/calendar-filtered_mobile.png) 連續列出五個零活動月份，未見直接清除條件按鈕；已選「藝文」也不在類型橫列的可見區域。[desktop](/Users/skyhong/cm-review/rounds/c2/B/calendar-filtered_desktop.png) 類型下拉框顯示空白，仍鋪出多個空月格 —— 使用者知道沒結果，卻不易修正原因 —— 顯示已選條件與一鍵清除，零結果先集中呈現說明及恢復入口。
3. [資訊密度] [events、source] [mobile] [events_mobile.png](/Users/skyhong/cm-review/rounds/c2/B/events_mobile.png) 的活動列表前置區約占 550 CSS px；[source_mobile.png](/Users/skyhong/cm-review/rounds/c2/B/source_mobile.png) 也先呈現長篇名錄說明再進入結果 —— 日常瀏覽時需要重複捲過相同內容 —— 縮短導讀，把完整說明收合，優先露出搜尋、目前條件與首筆結果。
4. [無障礙] [source、calendar] [mobile] [source_mobile.png](/Users/skyhong/cm-review/rounds/c2/B/source_mobile.png) 的追蹤只剩鈴鐺；[calendar_mobile.png](/Users/skyhong/cm-review/rounds/c2/B/calendar_mobile.png) 的票券圖示與數字沒有直接動作說明 —— 圖示可能被理解為通知、票券或統計，增加辨識成本 —— 延續活動列表的文字標籤，並區分動作、本人狀態與總人數。
5. [文案] [status] [兩者] [status_mobile.png](/Users/skyhong/cm-review/rounds/c2/B/status_mobile.png) 在來源列表之前呈現 Apify 餘額、配額與多項統計，搜尋提示也使用「後端」 —— 學生主要想確認來源是否正常更新，技術資訊提高理解成本 —— 先呈現正常／延遲／失敗、最近成功時間與來源搜尋，額度及抓取細節放入技術區。

## 組 C

一句話總評：品牌色、主要導覽與功能架構清楚，但錯誤回饋、手機資訊排列及內容密度有明顯摩擦，部分頁面仍呈現技術工具而非活動服務的閱讀順序。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6 | [home](/Users/skyhong/cm-review/rounds/c2/C/home_mobile.png)（mobile）直接進入限動、捷徑與貼文，缺少醒目的用途說明；[event-rich](/Users/skyhong/cm-review/rounds/c2/C/event-rich_mobile.png)（mobile）先放完整海報，標題、資訊表與報名入口在後。 |
| 字體排印 | 6.5 | [events-filtered](/Users/skyhong/cm-review/rounds/c2/C/events-filtered_mobile.png)（mobile）把類型、學校與排序合併進大標題，形成冗長兩行；[events](/Users/skyhong/cm-review/rounds/c2/C/events_mobile.png)（mobile）部分「需報名」「免費」標籤被擠成直向多行。 |
| 色彩 | 8 | [events-light](/Users/skyhong/cm-review/rounds/c2/C/events-light_desktop.png)（desktop）的淺底、深色文字、校別標籤與藍色選取狀態成立；[home](/Users/skyhong/cm-review/rounds/c2/C/home_desktop.png)（desktop）也維持藍紫品牌與學校語意色。 |
| 間距與版面 | 6 | [home](/Users/skyhong/cm-review/rounds/c2/C/home_desktop.png)（desktop）欄寬較大，第三欄只露出右側窄片，需要橫向探索；[org-rich](/Users/skyhong/cm-review/rounds/c2/C/org-rich_desktop.png)（desktop）主要內容集中單列，右方留白較多。 |
| 一致性 | 6.5 | [account-signed-in](/Users/skyhong/cm-review/rounds/c2/C/account-signed-in_desktop.png)（desktop）沿用圓角區塊與輸入框，但儲存使用藍框；[not-found](/Users/skyhong/cm-review/rounds/c2/C/not-found_desktop.png)（desktop）搜尋欄與按鈕呈現原生白底小控制項，與其他頁差異明顯。 |
| 資訊密度 | 5.5 | [source-search](/Users/skyhong/cm-review/rounds/c2/C/source-search_mobile.png)（mobile）即使只有三筆結果，仍先展開學校、狀態、類型、標籤、平台全部篩選；[status](/Users/skyhong/cm-review/rounds/c2/C/status_mobile.png)（mobile）大量高度用於額度與帳號池資訊。 |
| 導覽 | 6.5 | [home-signed-in](/Users/skyhong/cm-review/rounds/c2/C/home-signed-in_mobile.png)（mobile）底部五項導覽有圖示與文字，更多選單提供其他入口；[events-filtered](/Users/skyhong/cm-review/rounds/c2/C/events-filtered_mobile.png)（mobile）的展開篩選與獨立地圖區將結果推得很後，未見直接清除全部條件的入口。 |
| 狀態與回饋 | 4 | [source-error](/Users/skyhong/cm-review/rounds/c2/C/source-error_mobile.png)（mobile）只見空白計數塊與舊名錄，沒有清楚錯誤提示或重試；[source-followed-empty](/Users/skyhong/cm-review/rounds/c2/C/source-followed-empty_mobile.png)（mobile）顯示泛用「沒有符合的單位」及「顯示更多單位」，未說明尚未追蹤。 |
| 響應式 | 5.5 | [calendar](/Users/skyhong/cm-review/rounds/c2/C/calendar_mobile.png)（mobile）採逐日議程是合理調整；但[events](/Users/skyhong/cm-review/rounds/c2/C/events_mobile.png)（mobile）的縮圖、日期、標籤與兩個操作欄同列競爭寬度，造成標籤與時間異常換行。 |
| 文案 | 6 | [submit](/Users/skyhong/cm-review/rounds/c2/C/submit_mobile.png)（mobile）能說明可回報哪些連結，但說明偏長；[event-sparse](/Users/skyhong/cm-review/rounds/c2/C/event-sparse_mobile.png)（mobile）使用「補入場館表」，[status](/Users/skyhong/cm-review/rounds/c2/C/status_mobile.png)（mobile）露出權重、冷卻與抓取帳號池等內部概念。 |
| 無障礙 | 6 | [home-search-open](/Users/skyhong/cm-review/rounds/c2/C/home-search-open_desktop.png)（desktop）有可見焦點框；[events](/Users/skyhong/cm-review/rounds/c2/C/events_mobile.png)（mobile）的票券與鈴鐺缺少動作文字，[not-found](/Users/skyhong/cm-review/rounds/c2/C/not-found_mobile.png)（mobile）的搜尋控制項也明顯較小。未由畫面推論鍵盤或 ARIA 支援。 |
| 動畫與轉場 | 5.5 | [home-search-open](/Users/skyhong/cm-review/rounds/c2/C/home-search-open_mobile.png)（mobile）與更多選單提供開啟狀態線索；[events-loading](/Users/skyhong/cm-review/rounds/c2/C/events-loading_mobile.png)（mobile）只見局部空缺與舊結果，沒有清楚載入文字或圖示。無法確認實際動畫品質，保守評分。 |

要保留的優點：

- 深淺外觀都保留藍紫品牌、學校文字標籤與狀態色。
- 桌面側欄及手機五項底部導覽，讓主要功能有穩定入口。
- 手機日曆採逐日議程，比縮小桌面月格適合閱讀。
- 限動頁的比例外框、單位名稱、時間標示與追蹤篩選清楚；評價僅針對外框與操作，不涉及示意圖片內容。
- 通知設定以不同範圍選項及預覽數量說明訂閱內容。
- 帳號設定明確呈現個人頁目前不公開，以及公開後會顯示哪些資料。

最重要的五個問題（由嚴重到輕微）：

1. [狀態與回饋] [home-error、events-error、source-error、status-error] [兩者] 多個錯誤狀態仍主要呈現舊內容或空白控制項，缺少明確錯誤與重試；[status-error_mobile.png](/Users/skyhong/cm-review/rounds/c2/C/status-error_mobile.png) 還同時顯示「載入中」與讀取失敗 —— 使用者無法可靠判斷資料是否最新、是否仍在等待 —— 統一提供錯誤標題、舊資料說明、受影響功能與重試入口，失敗後停止顯示等待文案。
2. [響應式] [events、events-filtered] [mobile] [events_mobile.png](/Users/skyhong/cm-review/rounds/c2/C/events_mobile.png) 第五筆「2026 孫運璿科技講座」上方，約圖像 y=2250–2340 的「需報名」「免費」被擠成多行直排，日期時間也拆開；篩選頁第二筆亦相同 —— 掃讀活動條件變慢，列表列高不穩 —— 將日期與狀態分列，讓標籤整顆換行，操作移到獨立區域。這是列內寬度擠壓，與底部截圖截斷無關。
3. [資訊層級] [event-rich、event-rich-light] [mobile] [event-rich_mobile.png](/Users/skyhong/cm-review/rounds/c2/C/event-rich_mobile.png) 先呈現大海報，再接標題、摘要與資訊表，報名入口約到 1250 CSS px 後才出現；「主辦」列使用 NYCU LIFE 活動系統，也未清楚區分收錄來源與實際主辦 —— 參加決策資訊與責任單位不夠直接 —— 先放整理後的時間、地點、實際主辦與報名，另列「收錄自」，海報與原文放後。
4. [資訊密度] [source、events-filtered、status] [mobile] [source_mobile.png](/Users/skyhong/cm-review/rounds/c2/C/source_mobile.png) 與篩選後活動頁先展開大量條件；[status_mobile.png](/Users/skyhong/cm-review/rounds/c2/C/status_mobile.png) 則先呈現長篇額度、帳號池與技術儀表板 —— 找單位、找活動、確認更新三種任務都要先捲過大量前置資訊 —— 預設收合進階篩選和技術細節，優先呈現目前條件、結果及一般使用者需要的更新狀態。
5. [狀態與回饋] [source-followed-empty、events-no-results、stories-empty] [兩者] [source-followed-empty_mobile.png](/Users/skyhong/cm-review/rounds/c2/C/source-followed-empty_mobile.png) 在零追蹤時仍提供「顯示更多單位」；搜尋無結果與限動空狀態也主要只有泛用文字 —— 使用者難以分辨是尚未建立資料、條件太窄，還是稍後才有內容 —— 依原因分別提供「瀏覽全部單位」「清除搜尋／篩選」「瀏覽活動」等具體下一步。

```json
{
  "A": {
    "scores": {
      "資訊層級": 7.5,
      "字體排印": 8,
      "色彩": 8,
      "間距與版面": 7.5,
      "一致性": 8,
      "資訊密度": 6.5,
      "導覽": 7.5,
      "狀態與回饋": 7,
      "響應式": 7.5,
      "文案": 8,
      "無障礙": 6.5,
      "動畫與轉場": 6.5
    },
    "issues": [
      "[資訊層級][luma-taipei][mobile] 城市主視覺與介紹占據接近一屏，首張活動卡過晚出現；縮短主視覺並提早呈現活動。",
      "[無障礙][accupass-search、luma-taipei][兩者] 日期、地點與主辦文字偏淡；加深決策資訊的文字對比。",
      "[間距與版面][accupass-home][兩者] Cookie 與推廣浮層占用或覆蓋活動內容；精簡並減少同時出現的浮層。",
      "[導覽][accupass-search][兩者] 結果總數及條件摘要不夠醒目；顯示總數、已選條件與清除入口。",
      "[資訊密度][accupass-search][mobile] 大海報卡讓一屏可比較活動過少；提供小縮圖列表模式。"
    ]
  },
  "B": {
    "scores": {
      "資訊層級": 8.5,
      "字體排印": 8,
      "色彩": 8,
      "間距與版面": 7.5,
      "一致性": 8,
      "資訊密度": 7,
      "導覽": 8,
      "狀態與回饋": 8.5,
      "響應式": 7.5,
      "文案": 8,
      "無障礙": 7,
      "動畫與轉場": 6.5
    },
    "issues": [
      "[響應式][org-rich][mobile] org-rich_mobile.png 第三筆活動地址約 y=1180 在右緣硬裁；允許地點換行並提供完整閱讀方式。",
      "[狀態與回饋][calendar-filtered][兩者] 零結果仍鋪出多個空月份，手機缺少直接清除入口且選取類型不在可見範圍，桌面類型欄空白；集中顯示空狀態與清除條件。",
      "[資訊密度][events、source][mobile] 導讀、捷徑與篩選占去過多前置高度；縮短並收合重複說明，提早露出結果。",
      "[無障礙][source、calendar][mobile] 鈴鐺、票券與數字缺少直接動作說明；補上文字並區分動作、本人狀態與總人數。",
      "[文案][status][兩者] 來源更新查詢前呈現過多額度與後端術語；先呈現來源健康及更新時間，技術細節收合。"
    ]
  },
  "C": {
    "scores": {
      "資訊層級": 6,
      "字體排印": 6.5,
      "色彩": 8,
      "間距與版面": 6,
      "一致性": 6.5,
      "資訊密度": 5.5,
      "導覽": 6.5,
      "狀態與回饋": 4,
      "響應式": 5.5,
      "文案": 6,
      "無障礙": 6,
      "動畫與轉場": 5.5
    },
    "issues": [
      "[狀態與回饋][home-error、events-error、source-error、status-error][兩者] 錯誤提示與重試不足，部分畫面同時顯示載入中與失敗；統一錯誤、舊資料與恢復提示。",
      "[響應式][events、events-filtered][mobile] events_mobile.png 第五筆活動約 y=2250–2340 的狀態標籤被擠成直排，時間也拆行；重排日期、標籤與操作區。",
      "[資訊層級][event-rich、event-rich-light][mobile] 大海報與重複摘要延後報名入口，主辦與收錄來源角色不清；先呈現決策資訊與報名，另列收錄來源。",
      "[資訊密度][source、events-filtered、status][mobile] 全展開篩選及技術儀表板將核心結果推得過後；預設收合進階內容並優先顯示結果。",
      "[狀態與回饋][source-followed-empty、events-no-results、stories-empty][兩者] 空狀態缺少情境說明與有效下一步，零追蹤仍顯示更多單位；依原因提供瀏覽、清除或替代入口。"
    ]
  }
}
```
