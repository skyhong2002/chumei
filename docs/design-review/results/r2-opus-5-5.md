# Round 2 blind review: opus-5-5

- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **C = baseline**, **A = new**, **B = reference**
- New set: `/tmp/cm-review/sets/new-r2`
- Mean of 12 scores: new 7.08, reference 7.17, baseline 5.71

Raw reviewer output below, unedited.

---

## 組 A
一句話總評：資訊架構完整、品牌色與兩校語意色有系統，錯誤、空資料與登入前後的狀態都交代清楚、有下一步；剩下的問題主要是桌面字級偏小、資訊過密，還有首頁河道第三欄被裁切。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 7 | events_desktop：主標題「活動總覽」，下一行副標「排序：時間優先」；卡片依序是日期徽章（11月 12）、類型標籤、標題、時間｜地點、主辦，最重要的資訊排在前面。home_desktop 第一屏是限動圓圈加上三欄河道（交大／清大／陽明），沒有一句話說明網站在做什麼，新使用者得自己猜。 |
| 字體排印 | 6.5 | source-error_desktop 表格的標籤、ID、更新時間大約 10–11px，「#2」「今天」這類欄位在 1440 寬下很難讀。account-signed-in_desktop 卡片內的說明文字約 11px。手機版（submit_mobile、account_mobile）字級與行高舒適，中英混排（IG／FB／Threads）處理得好。 |
| 色彩 | 7.5 | 品牌字「竹梅」用藍到紫的漸層。學校標籤有固定語意色：清大紫、陽明交大藍、交大金。錯誤用深酒紅底的 banner（home-error_desktop、source-error_desktop）。account-signed-in-light_desktop 淺色外觀成立，「永久刪除我的帳號」用紅色系危險按鈕，「儲存」是實心藍色主按鈕，語意清楚。 |
| 間距與版面 | 6.5 | submit_desktop、account_desktop 的內容卡片固定約 720px 寬，左右各留下 250px 以上的黑色空白，1440 寬沒有善用。home-error_desktop 第三欄「陽明」在右緣被切掉，只露出「陽明烘焙研…」。events_desktop 四欄卡片的格線與對齊整齊。 |
| 一致性 | 7.5 | 登入按鈕在 account_desktop 與 submit_desktop 都是同一套全寬膠囊外框樣式（使用陽明交大／清大 NTHU／Google）。錯誤 banner 在 home-error、source-error、status-error 三頁同款（標題、錯誤代碼 500、右側「重新載入」）。404 的輸入框與按鈕也沿用站內膠囊樣式（not-found_desktop）。 |
| 資訊密度 | 6.5 | source-error_desktop 一屏約 30 列單位，連結欄同時列出 IG、FB、Threads 三行，造成列高不一、閱讀跳動。events_desktop 卡片下方「我會去／追蹤主辦」兩顆按鈕佔掉約 50px，每張卡都重複出現。 |
| 導覽 | 7.5 | 桌面是固定左側欄（最新、活動、日曆、限動、搜尋、App 通知、回報活動、資料來源、貢獻，底部是登入與更多），目前頁加粗。手機是底部五格分頁（最新、活動、日曆、限動、更多），頂部有搜尋圖示（submit_mobile）。缺點是「關於」「訂閱」「系統狀態」只能從頁尾或「更多」進入。 |
| 狀態與回饋 | 8 | home-empty_desktop 用虛線框寫出「目前還沒有貼文」、原因說明和「看即將舉行的活動」按鈕。home-error_desktop、source-error_mobile、status-error_desktop 都有錯誤標題、原因、錯誤代碼和「重新載入」。source-error 明確寫出「篩選、排序與搜尋要等資料載入後才能使用」，並把篩選列藏起來，不讓人點了沒反應。 |
| 響應式 | 7.5 | 手機不是單純縮放：source-error_mobile 的表格改成單位卡片列，「追蹤」變成右側 44px 圓形鈴鐺；account-signed-in_mobile 的「登出」改成全寬按鈕放在標題下。submit-signed-in_mobile 的連結輸入框 placeholder 被截斷成「https://www.insta」。 |
| 文案 | 8 | 404 寫「這個網址可能已移動、已移除，或輸入有誤…連結是從竹梅點過來的？回報連結問題」。status-error_desktop 的說明「某個單位的活動沒出現時，可以先在這裡確認它有沒有正常更新」貼近使用者的需求。account-signed-in_desktop 刪除帳號說明用「投入的優先點數、貢獻的抓取額度」這類使用者聽得懂的詞。 |
| 無障礙 | 6.5 | 鈴鐺按鈕與主要按鈕的點擊範圍足夠（source-error_mobile 圓鈕約 44px）。勾選框是自訂的大方框（account-signed-in_mobile）。但桌面大量 10–11px 灰字疊在黑底上（events_desktop 卡片的主辦單位、source 表格的更新時間），對比與字級都偏弱。學校只用顏色區分時，文字標籤仍在，算及格。 |
| 動畫與轉場 | 6 | home-loading、events-loading、calendar-loading 有骨架屏；home_desktop 河道右側有「›」箭頭，表示可以橫向捲動。靜態截圖看不到實際過場，保守評分。 |

要保留的優點：
- 全站共用的錯誤 banner（home-error、source-error、status-error）：寫出原因與錯誤代碼，附「重新載入」，並說明哪些功能暫時不能用。
- 首頁空資料用虛線框說明，再加一顆 CTA「看即將舉行的活動」（home-empty_desktop）。
- 學校語意色標籤（清大紫／陽明交大藍／交大金）在活動卡、名錄、手機名錄列都一致。
- 手機名錄把表格改成卡片列，右側放圓形追蹤鈕，附追蹤數徽章（source-error_mobile）。
- 帳號頁的危險區塊：紅色「永久刪除我的帳號」按鈕，搭配輸入確認字串（account-signed-in_desktop／light）。
- 404 提供站內搜尋框、「回到首頁」「瀏覽所有活動」和回報連結（not-found_desktop／mobile）。

最重要的五個問題（由嚴重到輕微）：
1. [資訊層級] [home_desktop、home-error_desktop] [desktop] 首頁第一屏只有限動圓圈、三顆快捷標籤和多欄河道，沒有任何一句說明這是兩校活動彙整站，第三欄「陽明」還被右緣裁切 —— 第一次來的人看不懂網站用途，裁切的欄位也像壞掉 —— 在河道上方加一行副標與「看活動」入口；欄寬改成剛好排滿，或在右側加漸層遮罩。
2. [字體排印] [source-error_desktop、events_desktop、account-signed-in_desktop] [desktop] 表格標籤、更新時間、卡片主辦單位、表單說明大約 10–11px 灰字 —— 1440 寬的螢幕上難讀，也拉低對比 —— 桌面正文最小 13–14px，次要資訊最小 12px，並提高灰字明度。
3. [間距與版面] [submit_desktop、account_desktop、account-signed-in_desktop] [desktop] 單欄卡片只有約 720px 寬，左右留下大片空白，頁尾又重複整套導覽 —— 桌面寬度浪費，頁面顯得空 —— 改用兩欄（表單＋最近的回報或說明），或放寬內容區。
4. [資訊密度] [source-error_desktop] [desktop] 名錄的連結欄 IG／FB／Threads 換成多行，列高不一，例如 #512 佔了四行 —— 掃描困難 —— 改成平台小圖示一列排開，滑過再顯示帳號。
5. [響應式] [submit-signed-in_mobile] [mobile] 連結輸入框的 placeholder 被截成「https://www.insta」—— 使用者看不到完整範例格式 —— 縮短 placeholder（例如「貼上 IG／FB 貼文網址」），把範例移到欄位下方的說明文字。

## 組 B
一句話總評：參考組裡的 Luma 與 NYCU Events 版面乾淨、層級分明；Accupass 色彩強但手機版很擠、cookie 橫幅擋住內容。三者的狀態覆蓋看不到太多。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | luma-taipei_desktop：hero「精彩活動盡在 台北」加上訂閱欄；下方時間軸依日期分組（明天 星期六、11月15日），每筆依序是時間、標題、主辦、地點、參加者頭像，主次極清楚。nycu-life-events_desktop：輪播卡最先列出日期 11/18（三）08:00 和地點光復校區。 |
| 字體排印 | 7.5 | luma-taipei_desktop 的標題字級與灰色輔助字層次分明，中英混排自然。accupass-home_mobile 卡片標題「伯樂星臻選・典藏饗宴」字重適中。nycu-life-events_desktop 卡片標題兩行截斷整齊，但 #分類 標籤偏小。 |
| 色彩 | 7.5 | Accupass 用品牌藍頂欄搭彩色海報（accupass-home_mobile）。Luma 是中性灰白底，狀態色小標「即將額滿」橘、「已售罄」紅、「候補名單」藍（luma-taipei_desktop）。NYCU Events 用藍色主色與校區藍色膠囊（nycu-life-events_desktop），偏預設樣式。 |
| 間距與版面 | 7.5 | luma-taipei_desktop 是主欄加右側欄（訂閱、地圖），留白節奏一致。nycu-life-events_desktop 四欄卡片格線整齊，但右上「已釘選／近期活動」卡大片留白。accupass-home_mobile 的橫向卡片超出右緣，露出半張。 |
| 一致性 | 7.5 | Luma 的事件卡、徽章、頭像堆疊統一。NYCU Events 每張卡都有同款「活動公告」灰按鈕與愛心。Accupass 不同區塊（本週主打推薦／每天一點新鮮事／熱門活動）的卡片尺寸各異。 |
| 資訊密度 | 7 | luma-taipei_desktop 一屏約 3 筆事件，偏鬆。nycu-life-events_desktop 一屏約 8 張卡，適中。accupass-home_mobile 被輪播與推薦內容佔據，真正的活動很少。 |
| 導覽 | 7 | nycu-life-events_desktop 有頂部搜尋、已收藏／已報名、分頁「所有活動／依活動性質／依校區」。accupass-home_mobile 有漢堡選單、地點、搜尋與類別分頁（精選、學習、藝文、體驗）。Luma 的頂部導覽只有「探索活動、登入」，很精簡。 |
| 狀態與回饋 | 6 | nycu-life-events_desktop 在登入前顯示「登入後可釘選活動分類」「登入查看近期已報名活動」。其餘截圖看不到載入、錯誤、空資料。 |
| 響應式 | 7 | accupass-home_mobile 是專門的手機版面，但底部 cookie 橫幅大約佔 15% 的畫面；Luma 與 NYCU 的手機版皆為單欄重排（luma-taipei_mobile、nycu-life-events_mobile）。 |
| 文案 | 7.5 | Luma 的「由 ninja 主辦」「臺北市光復里」簡潔。NYCU 的「暫停輪播」用語自然。Accupass 的推薦文案偏行銷。 |
| 無障礙 | 7 | Luma 灰色輔助字對比偏低（luma-taipei_desktop 的「由 … 主辦」）。NYCU 有「暫停輪播」控制鈕，對動態內容友善。Accupass 海報文字無替代說明可見，cookie 橫幅遮住內容。 |
| 動畫與轉場 | 6.5 | NYCU 輪播有「2/5」頁碼、左右箭頭與暫停鈕；Accupass 首頁輪播有圓點指示。其餘無線索，保守評分。 |

要保留的優點：
- Luma 依日期分組的時間軸列表：日期作群組標題，每筆時間在最上方（luma-taipei_desktop）。
- Luma 的小型狀態徽章（即將額滿／已售罄／候補名單）語意清楚。
- NYCU Events 的輪播附「暫停輪播」控制鈕（nycu-life-events_desktop）。
- NYCU Events 在登入前用簡短說明取代空白欄位（已釘選、近期活動）。
- Accupass 手機頂部的分類分頁（精選／學習／藝文／體驗），一鍵切換。

最重要的五個問題（由嚴重到輕微）：
1. [響應式] [accupass-home_mobile] [mobile] 底部 cookie 橫幅常駐，大約遮住 15% 的畫面 —— 首訪使用者第一屏就被擋住 —— 改成可收合的細條，或在首次互動後自動收起。
2. [資訊密度] [accupass-home_mobile] [mobile] 首屏被輪播與推薦文章佔據，真正的活動列表要捲兩屏以上才出現 —— 找活動的效率低 —— 把「近期活動」提前，縮小輪播。
3. [間距與版面] [nycu-life-events_desktop] [desktop] 右側「近期活動」卡只有一行連結，卻撐滿與輪播同高的空白 —— 版面失衡 —— 未登入時把側欄縮成一條提示。
4. [無障礙] [luma-taipei_desktop] [desktop] 主辦與地點的淺灰字對比偏低 —— 低視力或戶外難讀 —— 提高灰字明度至 4.5:1。
5. [一致性] [accupass-home_mobile] [mobile] 各推薦區塊卡片尺寸與比例都不同，橫向卡片在右緣露出半張 —— 視覺節奏凌亂 —— 統一卡片規格與露出提示。

## 組 C
一句話總評：骨架與 A 相同，但多個狀態頁退化：錯誤不顯示、空資料只剩一行字、404 出現瀏覽器預設控件、系統狀態頁外露內部術語，主要動作還被弱化成外框按鈕。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6 | home_desktop 與 A 相同：沒有網站用途說明，第三欄被裁切。submit_desktop 的第一顆藍色按鈕寫「登入後回報連結」，看起來像動作，其實是登入方式的標題被做成按鈕，主次混亂。events_desktop 把「活動總覽｜排序：時間優先」塞進同一個 H1。 |
| 字體排印 | 6 | source-error_desktop 表格同樣大約 10–11px。not-found_desktop 的搜尋框是瀏覽器預設的小字輸入框，字級與站內不符。手機正文可讀（account_mobile）。 |
| 色彩 | 6.5 | 品牌漸層與學校語意色仍在。但危險動作「永久刪除我的帳號」只是中性外框按鈕（account-signed-in_desktop、account-signed-in-light_desktop），沒有危險色。「儲存」「送出」也改成外框（submit-signed-in_desktop），主按鈕色失去意義。 |
| 間距與版面 | 6 | 與 A 同樣單欄窄卡，大片空白（submit_desktop）。status-error_desktop 的「系統總覽」只剩一個空白圓角框，「狀態／平台」標籤後面沒有任何控制項，表頭下方大片空白。 |
| 一致性 | 5 | not-found_desktop／mobile 的搜尋框與「搜尋」按鈕是灰白預設樣式，連結改成底線文字，和全站膠囊按鈕不同。account_desktop 的登入按鈕為兩藍一外框的橫排，submit_desktop 卻是另一組文案與樣式。勾選框在 account-signed-in_mobile 是原生小方塊。 |
| 資訊密度 | 6 | source-error_desktop 篩選區有「標籤」「平台」兩列空白標籤，佔版面卻沒有內容。名錄連結欄同樣是多行。 |
| 導覽 | 7 | 左側欄、手機底部分頁與 A 相同。source-error_mobile 在錯誤狀態仍顯示整組篩選籤，可點卻沒有作用。 |
| 狀態與回饋 | 4 | home-error_desktop 完全沒有錯誤提示，畫面跟正常狀態一樣。events-error_mobile、source-error_desktop／mobile 也看不到錯誤 banner，events-error_mobile 的「排序」「時間」後面空白。home-empty_desktop 只寫「沒有符合的貼文。」，沒有原因也沒有下一步。status-error_desktop 同時出現「資料快照：載入中…」與「狀態資料讀取失敗」，訊息互相矛盾。 |
| 響應式 | 6 | events-error_mobile 的「需報名」「免費」膠囊在窄欄被斷成兩行（「需報／名」「免／費」），變成橢圓塊。account-signed-in_mobile 的勾選框只有約 12px，點擊困難。 |
| 文案 | 5 | status-error_desktop 外露「quota」「Apify」「加權」「12 小時到 14 天」等內部排程細節。account-signed-in_desktop 刪除說明寫「工作階段、優先權重分配、Apify 貢獻憑證」，屬於系統術語。submit_desktop 用「登入後回報連結」當按鈕文字。 |
| 無障礙 | 5.5 | 原生小勾選框（account-signed-in_mobile 約 12px）。404 的預設搜尋框高度約 20px（not-found_desktop），點擊範圍過小。主要動作改成細外框，對比降低（submit-signed-in_mobile 的「送出」）。 |
| 動畫與轉場 | 5.5 | 有載入骨架（home-loading、events-loading），但錯誤狀態沒有任何切換回饋。status-error_desktop 卡在「載入中…」，使用者無法分辨是在載入還是已經失敗。 |

要保留的優點：
- 左側欄加手機底部五格分頁的導覽架構（submit_mobile、account_mobile）。
- 學校語意色標籤與活動卡片格線（events_desktop）。
- account_desktop 登入按鈕橫排，主次分明（兩校登入用藍色實心，Google 用外框）。
- 帳號頁把私密訂閱連結做成帶「複製連結」的區塊，附「連結外流了？換一組新的」（account-signed-in_desktop）。
- 手機名錄的卡片列與圓形追蹤鈕（source-error_mobile）。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [home-error、events-error、source-error] [兩者] 資料載入失敗時畫面與正常狀態幾乎相同，沒有錯誤提示也沒有重新載入 —— 使用者會誤以為看到的是最新資料，或以為篩選壞了 —— 加回統一的錯誤 banner（原因、錯誤代碼、重新載入），並停用無效的篩選。
2. [文案] [status-error_desktop、account-signed-in_desktop] [desktop] 外露 quota、Apify、加權、工作階段、優先權重分配等內部術語，狀態頁還同時顯示「載入中…」與「讀取失敗」—— 一般學生看不懂，也無法判斷狀態 —— 改寫成使用者語言，失敗時只顯示一種明確狀態。
3. [一致性] [not-found_desktop、not-found_mobile] [兩者] 404 的搜尋框和按鈕是瀏覽器預設樣式（灰白小框），動作改成底線連結 —— 看起來像壞掉的頁面 —— 套用站內的膠囊輸入框與按鈕。
4. [色彩] [account-signed-in_desktop、submit-signed-in_desktop／mobile] [兩者] 「儲存」「送出」改成外框，「永久刪除我的帳號」用中性樣式 —— 主要動作不突出，危險動作沒有警示 —— 主要動作用實心品牌藍，危險動作用紅色系。
5. [狀態與回饋] [home-empty_desktop] [desktop] 空資料只寫「沒有符合的貼文。」，沒有原因也沒有下一步 —— 使用者不知道是篩選太嚴還是沒資料 —— 說明原因，並提供「清除篩選」或「看即將舉行的活動」。

```json
{"A": {"scores": {"資訊層級": 7, "字體排印": 6.5, "色彩": 7.5, "間距與版面": 6.5, "一致性": 7.5, "資訊密度": 6.5, "導覽": 7.5, "狀態與回饋": 8, "響應式": 7.5, "文案": 8, "無障礙": 6.5, "動畫與轉場": 6}, "issues": ["[資訊層級] home_desktop 首屏沒有網站用途說明，第三欄被右緣裁切", "[字體排印] source/events/account 桌面大量 10–11px 灰字", "[間距與版面] submit/account 桌面單欄窄卡留下大片空白", "[資訊密度] 名錄連結欄 IG/FB/Threads 多行造成列高不一", "[響應式] submit-signed-in_mobile 連結輸入框 placeholder 被截斷"]}, "B": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 7.5, "間距與版面": 7.5, "一致性": 7.5, "資訊密度": 7, "導覽": 7, "狀態與回饋": 6, "響應式": 7, "文案": 7.5, "無障礙": 7, "動畫與轉場": 6.5}, "issues": ["[響應式] accupass-home_mobile cookie 橫幅常駐遮住內容", "[資訊密度] accupass-home_mobile 首屏被輪播與推薦佔據", "[間距與版面] nycu-life-events_desktop 側欄大片留白", "[無障礙] luma-taipei_desktop 淺灰輔助字對比偏低", "[一致性] accupass-home_mobile 各區塊卡片規格不一"]}, "C": {"scores": {"資訊層級": 6, "字體排印": 6, "色彩": 6.5, "間距與版面": 6, "一致性": 5, "資訊密度": 6, "導覽": 7, "狀態與回饋": 4, "響應式": 6, "文案": 5, "無障礙": 5.5, "動畫與轉場": 5.5}, "issues": ["[狀態與回饋] home/events/source 錯誤狀態不顯示錯誤與重新載入", "[文案] status-error 與帳號刪除外露 quota、Apify、權重等內部術語，且載入中與失敗矛盾", "[一致性] 404 使用瀏覽器預設輸入框與按鈕", "[色彩] 儲存／送出改為外框、刪除帳號無危險色", "[狀態與回饋] home-empty 只顯示一行字，沒有原因與下一步"]}}
```
