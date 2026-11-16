# Round 1 blind review: opus-5-5

- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **A = baseline**, **B = new**, **C = reference**
- New set: `/tmp/cm-review/sets/new-r1`
- Mean of 12 scores: baseline 6.04, new 6.04, reference 6.96
- Note: A/A calibration: the new set is a byte-identical copy of the baseline (main b5cf91d; PR #70 was not merged by the 05:16 cutoff). The reviewer detected this by hashing the files. home-search-open desktop missed the dialog (capture clicked the mobile-only search button); fixed in states.py and re-shot for both sets from round 2.

Raw reviewer output below, unedited.

---

## 組 A
一句話總評：A 的每張截圖都和 B 位元組完全相同（88 組 MD5 全部一致），所以評分和 B 一樣。主體是深色、資訊豐富的校園活動彙整站，活動詳情與名錄做得扎實。最大的弱點是載入中、錯誤、空資料幾乎沒有專屬畫面，加上手機首屏被篩選器和海報佔滿，還有內部術語外露。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6.5 | event-rich desktop：海報在左，右側是校別、類型標籤與標題，下面依序是時間、地點、主辦、類型、報名、原始貼文的對照表，主次清楚。event-rich mobile：海報先佔掉約 620 CSS px，標題、時間都在第一屏之外。home desktop：一進來就是三欄貼文河道和示意限動圓圈，沒有任何一句話說明這是什麼網站。H1 寫成「校園急救實戰…演練！｜2026 年 11 月 19 日」，日期和下方時間列重複。 |
| 字體排印 | 7 | about、subscribe desktop：中文行長約 34–40 字，行高寬鬆，標點全形，看起來舒服。event-rich desktop：摘要截在「報名資」，沒有刪節號。org-rich desktop：收錄貼文列出現豆腐字「☒☒☒」。account-signed-in desktop：欄位標籤與說明約 12px，字偏小。events_mobile：「需報名」「免費」標籤被擠成兩行。 |
| 色彩 | 6.5 | 「竹梅」藍紫漸層 logo 和藍色主按鈕有辨識度。校別標籤有語意色：陽明交大是藍、清大是紫、交大是金（source desktop）。列表左側色條依學校區分（events-error desktop、calendar mobile）。home-light、events-light、event-rich-light、account-signed-in-light 都能成立。但整體大多是純黑底加白字，品牌色只有點綴。event-sparse 的「資料待確認」用棕底黃字，配上藍色連結，對比偏弱。 |
| 間距與版面 | 6 | org-rich desktop：內容欄大約只用了 1180 px 可用寬度中的 720 px，右側整片空白。event-sparse desktop 與 mobile：警示框貼著海報上緣，幾乎沒有間距。home desktop：第三欄「陽明」被右緣切掉，翻頁箭頭壓在圖上。event-rich desktop：「追蹤主辦」單獨掉到第二排。source desktop：連結欄 IG／FB／Threads 換行，造成列高忽高忽低。 |
| 一致性 | 6 | 卡片圓角、外框 pill 按鈕、側欄圖示整體是同一套。不一致的地方：not-found 兩者都用瀏覽器原生的白色 input 和按鈕；account-signed-in 的勾選框是原生樣式；submit-signed-in 的「送出」是外框按鈕，但其他頁的主要動作是實心藍；source 的按鈕寫「追蹤」，source-error 卻寫「追蹤主辦」；account 登入卡上有兩顆實心主按鈕並列。 |
| 資訊密度 | 7.5 | events-error desktop（列表內容和正常狀態一樣）：一屏約 25 筆，每筆有縮圖、時間、需報名／免費標籤、標題、地點與主辦。calendar mobile 一屏約 10 筆。source desktop 是表格，桌面上很有效率。反過來，event-rich 的摘要和下方內文是同一段文字重複出現。 |
| 導覽 | 7 | 桌面左側欄 9 個項目，手機底部 5 個分頁（最新、活動、日曆、限動、更多），目前位置會加粗（home-empty mobile 的「最新」）。home-search-open mobile 是全螢幕搜尋，結果分成「社團與單位」和「活動」兩組，很好用。缺點：頁尾又把整份導覽重複一次；source mobile 要捲過約 880 CSS px 的篩選器才看到第一筆結果。 |
| 狀態與回饋 | 4 | home-loading 與 home-error 的 mobile 截圖，和 home mobile 位元組完全相同；desktop 這兩張也彼此相同，都沒有骨架或錯誤訊息。events-loading 和 events-error 兩者完全相同，「排序」「時間」標籤後面沒有任何選項，也沒有錯誤說明。home-search-open desktop 和 home desktop 一模一樣，看不到搜尋對話框。source-error：數量徽章變成空的深色藥丸，「標籤」「平台」兩列沒有內容，但頁面沒有任何錯誤提示。status-error mobile：錯誤訊息只是頁面中段一行小字，上方還同時寫著「載入中…」。 |
| 響應式 | 6.5 | 手機版有重新排版：底部分頁、名錄由表格改成卡片、登入按鈕改成滿版，不是單純縮放。問題：events mobile 的篩選與地圖區塊把第一筆活動推到約 713 CSS px；「需報名」「免費」標籤變成兩行的橢圓；event-rich mobile 的海報佔掉第一屏。沒有看到橫向溢出。 |
| 文案 | 5.5 | 一般語氣自然，例如 submit 的「看到活動，貼連結給竹梅」。status-error 開頭整段是 quota、Apify、「權重」「加成」等內部術語。account-signed-in 的刪除說明提到「Apify 貢獻憑證、優先權重分配」。about 提到「Claude Code（Fable 5）」「Codex（5.6 Sol）」。org-empty 有兩顆同樣寫著「Facebook」的按鈕。source-search 的連結欄出現「FB FB」。空狀態只有一句「沒有符合的單位。」 |
| 無障礙 | 5.5 | 手機底部分頁與追蹤鈴鐺的點擊範圍夠大。問題：org-rich 與 event-sparse 的相關活動日期是灰色小字加底線，對比低；not-found 的原生輸入框很小；account-signed-in 的勾選框很小。學校只用色條區分（events），在 desktop 列表上沒有文字補充。截圖中看不到焦點樣式。 |
| 動畫與轉場 | 4.5 | 靜態截圖看不到動態。可見線索：home-search-open mobile 的搜尋框有藍色光暈；「展開全部（還有 9 個）」「更多篩選」暗示有展開收合。載入狀態沒有骨架（home-loading、events-loading 都直接顯示內容），calendar-loading 也看不出明確的轉場提示。線索不足，給保守分數。 |

要保留的優點：
- event-rich、event-sparse 的「時間／地點／主辦／類型／報名／原始貼文」對照表，加上「原始貼文 ↗」連回來源，可信度高。
- 校別語意色系統（清大紫、陽明交大藍、交大金），配合列表左側色條，掃讀很快。
- home-search-open mobile 的全螢幕搜尋，「社團與單位」和「活動」分組，日期欄靠左對齊。
- source desktop 的名錄表格：多維度篩選、每個選項附數量、欄位可排序，桌面效率高。
- event-sparse 的「資料待確認」區塊：主動說明哪些欄位缺漏，並提供更正方式。
- calendar mobile：依日期分組的時間軸列表，時間、標題、地點三層清楚。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [home-loading、home-error、events-loading、events-error、home-search-open、source-error] [兩者] 載入中和錯誤的畫面與正常狀態相同，或兩者彼此相同。desktop 上看不到搜尋對話框。source-error 只剩空白的數量徽章，沒有任何錯誤說明。—— 為什麼重要：使用者分不出資料是在載入、已經壞掉，還是本來就是這樣，可能拿舊資料做決定。—— 建議方向：每個資料區塊都要有骨架畫面；錯誤時顯示明確的橫幅，寫出原因、提供「重試」按鈕，並註明資料快照時間。
2. [響應式／資訊層級] [events、source、event-rich] [mobile] 篩選器佔掉第一屏約 700–880 CSS px；活動頁的海報先佔掉整個第一屏，標題、時間、地點都在折線以下；「需報名」「免費」標籤擠成兩行。—— 為什麼重要：多數使用者用手機，第一屏卻看不到任何活動或活動的關鍵資訊。—— 建議方向：手機上把篩選收進底部抽屜，只顯示目前條件的摘要；活動頁把標題和時間、地點移到海報上方，或縮小海報；標籤加上不換行並縮小字級。
3. [文案] [status-error、account-signed-in、about、org-empty、source-search] [兩者] quota、Apify、權重、加成、Fable 5／Codex 等內部用語外露；有重複的「Facebook」按鈕和「FB FB」；H1 後面附加日期。—— 為什麼重要：學生看不懂，也讓網站顯得像內部工具。—— 建議方向：把系統細節收進「進階說明」；重複的平台連結加上帳號名稱區分；H1 只放活動名稱。
4. [一致性] [not-found、account-signed-in、submit、submit-signed-in、source-error] [兩者] 404 頁用瀏覽器原生的 input 和按鈕；勾選框是原生樣式；「送出」是外框按鈕；登入卡有兩顆實心主按鈕並列；「永久刪除我的帳號」沒有危險色；「追蹤」和「追蹤主辦」標籤不一致。—— 為什麼重要：破壞品牌一致感，主要動作和危險動作也不夠醒目。—— 建議方向：統一表單元件；每張卡只放一個主要動作；破壞性操作改用紅色系。
5. [狀態與回饋／間距與版面] [home-empty、org-empty、source-followed-empty、org-rich] [兩者] 空狀態只有一行灰字，沒有下一步。沒有更多資料時仍顯示「顯示更多單位」。org-rich desktop 右側約 450 px 整片空白，收錄貼文出現豆腐字。—— 為什麼重要：使用者走到死路，桌面版看起來也像沒做完。—— 建議方向：空狀態要寫出原因並給一個行動（例如「去名錄追蹤單位」）；沒有更多資料就隱藏載入更多；單位頁在桌面加一欄，放簡介、統計或限動；字型補上 emoji 字型。

## 組 B
一句話總評：B 的每張截圖都和 A 位元組完全相同（88 組 MD5 全部一致），評分和 A 一樣。內容扎實、深淺兩種外觀都能用，但載入與錯誤狀態沒有專屬畫面，手機首屏效率低，內部術語外露。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6.5 | 和 A 相同：event-rich desktop 的對照表清楚；event-rich mobile 的海報先佔掉約 620 CSS px，標題在第一屏外；home desktop 沒有任何網站說明；H1 附加日期，和時間列重複。 |
| 字體排印 | 7 | about、subscribe desktop 行長、行高良好。event-rich 摘要截在「報名資」、沒有刪節號；org-rich 收錄貼文有豆腐字「☒☒☒」；events mobile 的標籤擠成兩行。 |
| 色彩 | 6.5 | 藍紫漸層 logo、校別語意色、列表色條都有；四組淺色畫面都成立。event-sparse 的棕底黃字配藍色連結，對比偏弱；整體以純黑白為主。 |
| 間距與版面 | 6 | org-rich desktop 右側大片空白；event-sparse 警示框緊貼海報；home desktop 第三欄被右緣切掉；source desktop 列高不一。 |
| 一致性 | 6 | not-found 用原生 input 和按鈕；account-signed-in 勾選框是原生樣式；「送出」是外框按鈕；「追蹤」和「追蹤主辦」不一致；登入卡有兩顆實心主按鈕。 |
| 資訊密度 | 7.5 | events desktop 一屏約 25 筆；calendar mobile 約 10 筆；source desktop 表格效率高。event-rich 摘要和內文重複。 |
| 導覽 | 7 | 桌面左側欄、手機 5 個底部分頁、目前位置會加粗；home-search-open mobile 的分組搜尋很好用。頁尾重複整份導覽；source mobile 要捲很久才到結果。 |
| 狀態與回饋 | 4 | home-loading 與 home-error 的 mobile 截圖和 home 完全相同；events-loading 等於 events-error；home-search-open desktop 看不到對話框；source-error 沒有錯誤提示；status-error 的錯誤訊息只是頁中一行小字。 |
| 響應式 | 6.5 | 手機確實有重新排版（底部分頁、名錄改成卡片）；但篩選和海報佔掉第一屏，標籤會換行。沒有看到橫向溢出。 |
| 文案 | 5.5 | status-error、account-signed-in、about 都有內部術語；org-empty 有兩顆「Facebook」；source-search 有「FB FB」；空狀態只有一句話。 |
| 無障礙 | 5.5 | 底部分頁點擊範圍足夠；日期灰色小字對比低；原生控制項很小；學校差異只靠色條；看不到焦點樣式。 |
| 動畫與轉場 | 4.5 | 可見線索只有搜尋框光暈和「展開全部」「更多篩選」；沒有骨架畫面；線索不足，給保守分數。 |

要保留的優點：
- 活動頁的關鍵欄位對照表，加上「原始貼文 ↗」連回來源。
- 清大紫、陽明交大藍、交大金的校別語意色，配合列表色條。
- 手機全螢幕搜尋，「社團與單位」和「活動」分組。
- 名錄表格的多維篩選、每個選項附數量、欄位可排序。
- event-sparse 的「資料待確認」主動揭露缺漏。
- calendar mobile 依日期分組的時間軸列表。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [home-loading、home-error、events-loading、events-error、home-search-open、source-error] [兩者] 載入中和錯誤沒有專屬畫面，desktop 上看不到搜尋對話框，source-error 沒有錯誤說明。—— 為什麼重要：使用者無法分辨資料是在載入、已經失效，還是正常。—— 建議方向：加入骨架畫面，以及寫明原因、可重試的錯誤橫幅。
2. [響應式／資訊層級] [events、source、event-rich] [mobile] 篩選器和海報佔掉第一屏，標籤會換行。—— 為什麼重要：主要使用者在手機上看不到內容。—— 建議方向：把篩選收進抽屜；活動頁把標題和時間、地點放在海報前面。
3. [文案] [status-error、account-signed-in、about、org-empty、source-search] [兩者] 內部術語外露、平台連結名稱重複、H1 附加日期。—— 為什麼重要：降低可讀性與信任感。—— 建議方向：改寫成使用者語言，系統細節收進進階說明。
4. [一致性] [not-found、account-signed-in、submit、submit-signed-in、source-error] [兩者] 原生控制項、主要按鈕樣式不一、刪除帳號沒有危險色。—— 為什麼重要：主次和風險訊號不清楚。—— 建議方向：統一表單元件，每張卡只放一個主要動作，破壞性操作用紅色。
5. [狀態與回饋／間距與版面] [home-empty、org-empty、source-followed-empty、org-rich] [兩者] 空狀態沒有下一步；沒有更多資料時仍顯示「顯示更多單位」；單位頁桌面右側空白；有豆腐字。—— 為什麼重要：使用者走到死路，頁面看起來沒做完。—— 建議方向：空狀態要有說明和行動；有條件地顯示載入更多；用好桌面寬度；補上 emoji 字型。

## 組 C
一句話總評：參考組由 Accupass、Luma、NYCU LIFE EVENTS 三個產品組成。視覺品質與元件一致性整體較成熟，但有廣告與 Cookie 遮擋內容、對比偏低，而且截圖裡看不到載入、錯誤狀態可供評估。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 7.5 | luma-taipei desktop：日期分組時間軸，卡片依序是時間、標題、主辦、地點、狀態標籤，層次清楚。nycu-life-events desktop：卡片有標題、日期、地點與校區標籤。luma-taipei mobile：主視覺照片佔掉約 770 CSS px，活動列表在第一屏外。accupass-home：首屏是大型商業輪播。 |
| 字體排印 | 7.5 | luma-discover 的中英混排、字重層級細緻。accupass 卡片標題兩行截斷並加刪節號。nycu-life-events 的標題行長合理。Accupass、Luma 的次要日期是很小的淺灰字。 |
| 色彩 | 8 | Accupass 品牌藍頂列；luma-discover 每個城市圖示有不同顏色；luma-taipei 的狀態標籤有語意色（即將額滿橘、已售罄紅、候補名單藍）。nycu-life-events 有深色模式切換鈕。 |
| 間距與版面 | 7.5 | accupass-search desktop 是 3 欄整齊網格。luma-discover desktop 的內容欄約 670 px，留白很大。nycu-life-events desktop：右側「近期活動」白卡大部分是空的；「Open House」卡沒有圖，留下大片空白。 |
| 一致性 | 7.5 | Accupass 各區塊的卡片樣式統一；nycu-life-events 卡片的標籤、愛心、「活動公告」按鈕位置固定；Luma 整體圓角和灰階一致。 |
| 資訊密度 | 7 | accupass-home 一屏約 6 張卡，中間穿插「每天一點新鮮事」行銷文章。luma-taipei 每張卡附參加者頭像與人數。nycu-life-events 只有 8 個活動，卡片偏高。 |
| 導覽 | 7 | accupass-home 有精選、學習、藝文、體驗分頁。nycu-life-events 有「所有活動／依活動性質／依校區／依處室／已結束」分頁、搜尋框與語言切換。nycu-life-events mobile 的「已結束活動」換到第二行，看起來像落單。Luma 頂列只有「探索活動」「登入」。 |
| 狀態與回饋 | 5.5 | 截圖裡看不到載入、錯誤或無結果狀態。nycu-life-events 有「登入後可釘選活動分類」「登入查看近期已報名活動」這類登入前提示。luma-taipei 有額滿、售罄等狀態標籤。可評估的狀態有限，給保守分數。 |
| 響應式 | 7 | accupass-home、luma-discover 的 mobile 改成可橫向滑動並露出下一張卡，是有意設計的手機排版。accupass-home 的 Cookie 橫幅在 mobile 底部蓋住約 170 CSS px；desktop 左下角的浮動推廣條也壓在卡片上。 |
| 文案 | 7.5 | 用詞自然，例如 luma-taipei「精彩活動盡在 台北」、nycu-life-events「暫停輪播」。accupass-search 的頁面只寫「探索」，沒有結果數。 |
| 無障礙 | 6.5 | nycu-life-events 輪播有「暫停輪播」與 2/5 頁碼，點擊範圍足夠。Luma、Accupass 的淺灰次要文字（日期、瀏覽數）在白底上對比偏低。 |
| 動畫與轉場 | 5 | 可見線索：Accupass 與 NYCU LIFE 的輪播頁碼點和左右箭頭、Luma 橫向卡片的截斷露出。沒有骨架或轉場畫面，線索不足，給保守分數。 |

要保留的優點：
- luma-taipei 的日期分組時間軸，加上狀態語意標籤（即將額滿、已售罄、候補名單）。
- nycu-life-events 輪播的「暫停輪播」與 2/5 頁碼。
- luma-discover 的類別格子：彩色圖示配活動數，掃讀快。
- accupass-search 卡片統一的「日期、標題、地點、標籤、瀏覽數」結構。
- nycu-life-events 頂列整合了搜尋、中英切換、深色模式和登入。

最重要的五個問題（由嚴重到輕微）：
1. [響應式] [accupass-home] [兩者] Cookie 橫幅和浮動推廣條蓋住卡片內容（mobile 底部約 170 CSS px，desktop 左下角）。—— 為什麼重要：直接擋住主要內容和可點擊區域。—— 建議方向：橫幅改成不遮擋的底部列，或第一次互動後就收合，推廣條不要壓在內容上。
2. [資訊層級] [luma-taipei] [mobile] 主視覺照片佔掉約 770 CSS px 的第一屏，活動列表在折線以下。—— 為什麼重要：手機使用者要先捲動才看得到任何活動。—— 建議方向：縮小主視覺高度，讓第一筆活動出現在第一屏內。
3. [間距與版面] [nycu-life-events] [兩者] 右側「已釘選／近期活動」卡大部分是空的；沒有海報的卡片留下大片空白；mobile 分頁換行，「已結束活動」單獨一行。—— 為什麼重要：浪費空間，看起來不完整。—— 建議方向：登入前縮小或收合側欄；沒有圖的卡改用替代版面；手機分頁改成可橫向捲動。
4. [無障礙] [luma-discover、accupass-search] [兩者] 日期、計數等淺灰小字在白底上對比偏低。—— 為什麼重要：日期是活動最關鍵的資訊。—— 建議方向：提高次要文字的對比，日期改用較深的顏色。
5. [資訊密度] [accupass-home] [兩者] 「每天一點新鮮事」行銷文章重複穿插在活動區塊之間。—— 為什麼重要：稀釋找活動的效率。—— 建議方向：把內容行銷集中到一個獨立區塊，或降低它的視覺權重。

```json
{"A": {"scores": {"資訊層級": 6.5, "字體排印": 7, "色彩": 6.5, "間距與版面": 6, "一致性": 6, "資訊密度": 7.5, "導覽": 7, "狀態與回饋": 4, "響應式": 6.5, "文案": 5.5, "無障礙": 5.5, "動畫與轉場": 4.5}, "issues": ["[狀態與回饋] home-loading/home-error/events-loading/events-error/home-search-open/source-error 兩者：載入與錯誤畫面與正常狀態或彼此相同、desktop 搜尋對話框不可見、source-error 無錯誤說明", "[響應式/資訊層級] events/source/event-rich mobile：篩選器與海報佔滿第一屏，標籤換行成兩行橢圓", "[文案] status-error/account-signed-in/about/org-empty/source-search：quota、Apify、權重等內部術語外露，重複 Facebook／FB FB，H1 附加日期", "[一致性] not-found/account-signed-in/submit/source-error：原生 input 與勾選框、主要按鈕樣式不一、刪除帳號無危險色、追蹤標籤不一致", "[狀態與回饋/版面] home-empty/org-empty/source-followed-empty/org-rich：空狀態無下一步、多餘的顯示更多單位、桌面右側空白、豆腐字"]}, "B": {"scores": {"資訊層級": 6.5, "字體排印": 7, "色彩": 6.5, "間距與版面": 6, "一致性": 6, "資訊密度": 7.5, "導覽": 7, "狀態與回饋": 4, "響應式": 6.5, "文案": 5.5, "無障礙": 5.5, "動畫與轉場": 4.5}, "issues": ["[狀態與回饋] home-loading/home-error/events-loading/events-error/home-search-open/source-error 兩者：載入與錯誤畫面與正常狀態或彼此相同、desktop 搜尋對話框不可見、source-error 無錯誤說明", "[響應式/資訊層級] events/source/event-rich mobile：篩選器與海報佔滿第一屏，標籤換行成兩行橢圓", "[文案] status-error/account-signed-in/about/org-empty/source-search：quota、Apify、權重等內部術語外露，重複 Facebook／FB FB，H1 附加日期", "[一致性] not-found/account-signed-in/submit/source-error：原生 input 與勾選框、主要按鈕樣式不一、刪除帳號無危險色、追蹤標籤不一致", "[狀態與回饋/版面] home-empty/org-empty/source-followed-empty/org-rich：空狀態無下一步、多餘的顯示更多單位、桌面右側空白、豆腐字"]}, "C": {"scores": {"資訊層級": 7.5, "字體排印": 7.5, "色彩": 8, "間距與版面": 7.5, "一致性": 7.5, "資訊密度": 7, "導覽": 7, "狀態與回饋": 5.5, "響應式": 7, "文案": 7.5, "無障礙": 6.5, "動畫與轉場": 5}, "issues": ["[響應式] accupass-home 兩者：Cookie 橫幅與浮動推廣條遮住卡片內容", "[資訊層級] luma-taipei mobile：主視覺佔約 770 CSS px，活動列表在第一屏外", "[間距與版面] nycu-life-events 兩者：右側卡片大部分空白、無圖卡片留白、手機分頁換行", "[無障礙] luma-discover/accupass-search：日期與計數等淺灰小字對比偏低", "[資訊密度] accupass-home：行銷文章區塊穿插在活動之間，稀釋找活動效率"]}}
```
