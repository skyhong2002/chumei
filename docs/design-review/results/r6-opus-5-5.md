# Round 6 blind review: opus-5-5

- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **C = baseline**, **B = new**, **A = reference**
- New set: `/tmp/cm-review/sets/new-r6`
- Mean of 12 scores: reference 7.25, new 7.62, baseline 6.04

Raw reviewer output below, unedited.

---

## 組 A
一句話總評：這組是成熟的商業活動平台加一個校方系統，視覺完整、有品牌感。但截圖幾乎都是有資料的狀態，看不出它們怎麼處理載入、空資料、錯誤這類邊界狀態。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | accupass-home desktop／mobile：首屏用大橫幅與分類入口說明「這裡找活動」，活動卡以封面圖、標題、日期為主；luma-taipei desktop：城市頁標題下直接是依日期分組的活動列，時間在最前面。nycu-life-events desktop 的層級較平，標題與日期份量相近 |
| 字體排印 | 7.5 | luma-discover／luma-taipei 兩種尺寸：英文介面字級階層乾淨，標題與輔助資訊對比明確；accupass-search mobile：中文卡片標題兩行截斷合理，但輔助資訊字級偏小；nycu-life-events mobile 的列表字級與行高偏擠 |
| 色彩 | 8 | accupass-home：品牌色與大量封面圖構成鮮明識別；luma-discover：淺色底配柔和漸層，一致而克制；nycu-life-events 主要靠校方預設樣式，品牌感較弱 |
| 間距與版面 | 8 | luma-taipei desktop：置中單欄，日期分組的留白節奏穩定；accupass-search desktop：多欄卡片網格對齊整齊；nycu-life-events desktop 左右留白多，桌面寬度利用一般 |
| 一致性 | 7.5 | 同一產品內（accupass-home 與 accupass-search、luma-discover 與 luma-taipei）卡片、圓角、按鈕都同一套；nycu-life-events 是另一個系統，元件風格較舊 |
| 資訊密度 | 7 | accupass-home mobile：首屏被橫幅與分類佔掉大半，往下捲才看到活動；luma-taipei mobile 每列含縮圖、時間、地點，密度適中；luma-discover 以城市或分類卡為主，可直接看到的活動少 |
| 導覽 | 7.5 | accupass-search desktop：頂部搜尋加篩選列清楚；luma 兩頁有上方導覽與城市切換；手機版多靠頂部漢堡選單，沒有底部常駐導覽 |
| 狀態與回饋 | 6 | 十張截圖都是有資料狀態，沒有載入中、空資料、錯誤、搜尋無結果的畫面可評，只能保守給分 |
| 響應式 | 7.5 | accupass-home mobile 與 luma-taipei mobile 都改成單欄重排，不是單純縮放；沒看到橫向溢出。nycu-life-events mobile 的表格式列表在窄寬下比較擠 |
| 文案 | 7.5 | luma、accupass 的按鈕與分類用詞自然；nycu-life-events 帶有校方系統用語，比較生硬 |
| 無障礙 | 6.5 | accupass-home：橫幅圖上的文字對比取決於圖片；多處灰色輔助字偏淡；從截圖看不到焦點樣式 |
| 動畫與轉場 | 6 | 靜態截圖看不到骨架畫面、對話框開啟或選單展開，線索不足，保守給分 |

要保留的優點：
- luma-taipei：依日期分組的活動列，時間在最前面，掃讀效率高。
- accupass-search：頂部搜尋加篩選，結果用卡片網格呈現，篩選條件一目了然。
- luma-discover：淺色、克制、有漸層點綴的品牌語彙，畫面乾淨。
- accupass-home：用封面圖建立的視覺吸引力和分類入口。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [全部截圖] [兩者] 沒有任何載入中、空資料、錯誤或無結果的畫面 —— 這些狀態最容易流失使用者，卻無從評估 —— 建議補截邊界狀態再比較。
2. [資訊密度] [accupass-home] [mobile] 首屏被橫幅與分類入口佔滿，活動卡要往下捲才出現 —— 手機使用者要花更多力氣才看到內容 —— 建議縮小橫幅，讓第一張活動卡進到首屏。
3. [無障礙] [accupass-home] [desktop] 橫幅圖上的疊字對比沒有保證，灰色輔助字偏淡 —— 弱視者或強光下難以閱讀 —— 建議加漸層遮罩，並提高輔助字的對比。
4. [一致性] [nycu-life-events] [兩者] 校方系統的元件與字級比較舊，和現代活動平台差距明顯 —— 降低信任感與易讀性 —— 建議統一卡片與字級的階層。
5. [導覽] [luma-discover、accupass-home] [mobile] 主要導覽收在頂部選單，沒有底部常駐入口 —— 單手操作時切換頁面成本較高 —— 建議提供常用頁的快速入口。

## 組 B
一句話總評：整體成熟、一致，主要頁面的空資料、錯誤、未追蹤狀態都有說明和下一步。剩下的問題集中在桌面表格的小字、少數內部用語，以及登入狀態在手機首屏看不出差別。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | source desktop：H1「資料來源與機構名錄」、說明、篩選列、表格依序往下，主次清楚；source-search desktop 在 H1 下另起一行副標「搜尋「吉他」」，層級分明；org-rich mobile：單位名、學校與類型標籤、追蹤與外部連結、「即將舉行（11）」依序往下，日期在標題上方 |
| 字體排印 | 7.5 | org-rich mobile：日期用灰色小字、標題用大字，兩行標題斷行自然；source desktop：表格內的 ID、標籤、更新日期字級很小（約 11–12px），偏難讀；account-signed-in desktop：說明文字行長控制在卡片寬度內 |
| 色彩 | 7.5 | 「竹梅」漸層 logo 加上藍色主色貫穿全站；學校語意色一致（source：清大紫、陽明交大藍、交大與陽明琥珀）；source-light、account-signed-in-light 兩種尺寸的淺色外觀都成立；account-signed-in 的「永久刪除我的帳號」用紅色調和其他按鈕區隔 |
| 間距與版面 | 7.5 | account-signed-in desktop 用兩欄卡片（個人檔案、登入方式在左；訂閱、行事曆、回報在右），善用寬度；submit desktop 說明與「最近的回報」左右並排；但 not-found desktop 內容從約 x=510 開始，submit 約 310、org 約 280，各頁內容的左緣不一致 |
| 一致性 | 7.5 | 膠囊按鈕、虛線框空狀態卡（org-empty、source-followed-empty）、主色實心按鈕（submit-signed-in 的「送出」、account-signed-in 的「儲存」）全站一致；登入按鈕在 submit 是全寬堆疊，在 account desktop 則放在右欄，配置略有差異 |
| 資訊密度 | 8 | source mobile 每列一行名稱與學校、一行平台連結，右側是場數、更新時間與鈴鐺，緊湊而不擠；org-rich desktop 活動列一行一則；source desktop 平台連結欄只寫「IG FB Threads」，列高一致 |
| 導覽 | 8 | 桌面左側固定導覽，目前所在頁有粗體標示（source 的「資料來源」）；手機底部 5 格分頁加頂部搜尋；source mobile 把次要篩選收進「更多篩選」，學校 chip 橫向捲動且右緣露出半顆，暗示還能捲；org 頁底有「← 回資料來源名錄」 |
| 狀態與回饋 | 8.5 | source-error 兩種尺寸：紅底橫幅「名錄暫時載入不了」，說明正在顯示稍早的資料，附「重新載入」；source-followed-empty：「你還沒有追蹤任何單位」加做法說明和「瀏覽全部單位」；org-empty：「還沒有收錄到這個單位的活動」加「回報活動」；not-found：搜尋框加兩個去處；submit-signed-in 表單有欄位範例 |
| 響應式 | 8 | source mobile 把表格改成卡片列，不是縮放；account-signed-in mobile 把「登出」改成全寬按鈕放在標題下；submit mobile 把「最近的回報」移到表單下方；沒看到橫向溢出 |
| 文案 | 8 | 用詞自然，例如「看到活動，貼連結給竹梅」「連結外流了？換一組新的」；org-empty 的 Facebook 按鈕附帳號名（「Facebook nthucookingclub」），可以區分兩個帳號；但 source-error 露出「（代碼 500）」，account-signed-in 的刪除說明有「投入的優先點數、貢獻的抓取額度」等內部概念 |
| 無障礙 | 7 | 手機版的鈴鐺、chip、底部分頁點擊範圍足夠（source mobile 的鈴鐺約 52px）；account-signed-in 用自訂的大 checkbox；但 source desktop 的表格文字、chip 內的計數徽章對比與字級偏低 |
| 動畫與轉場 | 6 | 靜態截圖只能從載入骨架、搜尋對話框（home-loading、home-search-open）等狀態推測有對應呈現；看不到動態本身，保守給分 |

要保留的優點：
- source-error 的錯誤橫幅：說明原因，同時保留舊資料，並附「重新載入」。
- source-followed-empty 與 org-empty 的虛線空狀態卡：標題、原因、下一步按鈕都有。
- source mobile：次要篩選收進「更多篩選」，加上卡片式列表，名錄第一列就在首屏。
- account-signed-in desktop：兩欄卡片配置，加上全寬的刪除帳號區與紅色危險按鈕。
- org-empty 的外部連結按鈕附帳號名，兩個 Facebook 帳號分得開。
- 學校語意色（清大紫、陽明交大藍、交大與陽明琥珀）跨頁一致，深淺兩種外觀都成立。

最重要的五個問題（由嚴重到輕微）：
1. [無障礙] [source、source-light] [desktop] 表格的 ID、標籤、平台連結、更新日期約 11–12px，計數徽章對比偏低 —— 名錄是查找頁，小字會增加閱讀負擔 —— 建議把表格內文提高到 13–14px，提高灰字對比。
2. [狀態與回饋] [event-signed-in、subscribe-signed-in] [mobile] 這兩張登入後截圖和未登入版逐位元相同 —— 首屏看不出登入帶來的差異（「我會去」、個人訂閱） —— 建議在首屏呈現登入後的狀態或入口。
3. [文案] [account-signed-in、source-error] [兩者] 刪除說明出現「優先點數」「抓取額度」，錯誤橫幅露出「（代碼 500）」 —— 一般學生看不懂，削弱信任 —— 建議改成白話說明，代碼收進「詳細資訊」。
4. [間距與版面] [not-found、submit、org-rich] [desktop] 各頁內容的左緣不一（約 x=280、310、510） —— 換頁時視線會跳 —— 建議統一主欄的起點與最大寬度。
5. [間距與版面] [org-empty、source-search] [mobile] 內容很少的頁面，頁尾連結群組（與底部分頁重複）佔了半個螢幕以上 —— 重複導覽稀釋主要內容 —— 建議手機版頁尾精簡成一行。

## 組 C
一句話總評：框架和 B 相同，但多處狀態沒有對應畫面或直接壞掉：載入、錯誤、無追蹤看不出差別，404 用了瀏覽器原生控制項，名錄手機版篩選全部展開，桌面列高參差。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 7 | source-search desktop 把標題和搜尋詞串成「資料來源與機構名錄｜搜尋「吉他」」，mobile 斷成「…｜搜尋「吉 / 他」」；source mobile 的篩選全部展開，第一個單位落在約 1050 CSS px，首屏只有篩選、看不到單位 |
| 字體排印 | 6.5 | org-rich desktop 的「收錄貼文」出現多個 ☒ 缺字方框；org-rich mobile 的日期與標題全加底線，底線延伸到全形括號後的空白；source-search mobile 標題斷字不當 |
| 色彩 | 7 | 品牌漸層與學校語意色和 B 相同，source-light、account-signed-in-light 淺色外觀成立；但 submit、account 把兩顆登入按鈕都做成藍色實心（「使用陽明交大帳號登入」「使用清大 NTHU 帳號登入」），主色失去「唯一主要動作」的意義 |
| 間距與版面 | 6 | source desktop 平台連結欄顯示完整帳號，列高參差（#512 四行、多數一到兩行）；account-signed-in desktop 收成約 530px 寬的單欄，右側大片空白；submit desktop 卡片置中，和左側導覽之間空出很寬的間隙 |
| 一致性 | 5.5 | not-found 兩種尺寸用瀏覽器原生白底輸入框和灰色系統按鈕「搜尋」，和全站深色膠囊元件完全不同；account-signed-in 的 checkbox 是原生小方框；「送出」「儲存」是外框按鈕，「永久刪除」卻和一般按鈕同樣式；名錄的追蹤按鈕寫「追蹤主辦」，org-empty 也是「追蹤主辦」 |
| 資訊密度 | 6.5 | source mobile：篩選佔掉近兩個螢幕高度；source desktop：連結欄換行讓每屏能看到的列數變少；org-rich mobile 和 B 類似，一行日期一行標題 |
| 導覽 | 7 | 左側與底部導覽和 B 相同，目前位置有標示；但 source mobile 沒有「更多篩選」收合，篩選無法快速略過；source-search 只有 3 筆結果仍顯示「顯示更多單位」，誤導使用者以為還有更多 |
| 狀態與回饋 | 4.5 | home-loading、home-error 與 home 的 mobile 截圖逐位元相同，desktop 的 home-loading 與 home-error 也相同；events-loading 與 events-error 兩種尺寸都相同，至少一個狀態沒有對應畫面（請維護者看 1:1 原圖確認）；source-error 沒有任何錯誤訊息，篩選 chip 的計數變成空白方塊，「標籤」「平台」只剩標籤沒有選項；source-followed-empty 只有「沒有符合的單位。」，還附上沒有意義的「顯示更多單位」；org-empty 只有一行「尚未從這個來源收錄到活動。」，沒有下一步 |
| 響應式 | 6 | source mobile 篩選全部展開、沒有收合；submit-signed-in mobile 的連結欄位 placeholder 被截成「…例如 https://www.insta」；not-found mobile 的原生輸入框沒有配合觸控尺寸 |
| 文案 | 6 | account-signed-in 的刪除說明露出「工作階段、優先權重分配、Apify 貢獻憑證」等內部術語；org-empty 有兩顆都寫「Facebook」的按鈕，無法分辨；source-search 的連結欄出現「FB FB」重複字樣；名錄裡的「追蹤主辦」不符合單位清單的語境 |
| 無障礙 | 5.5 | not-found 的原生輸入框在深色底上是刺眼白底小字，點擊高度只有約 20px（desktop）；account-signed-in 的原生 checkbox 約 13px；org-rich desktop 的 ☒ 缺字讓輔助技術讀到無意義字元；「永久刪除我的帳號」沒有危險色，只靠文字傳達風險 |
| 動畫與轉場 | 5 | 載入狀態和資料或錯誤畫面相同，看不到骨架或任何過渡線索；其餘頁面也沒有可見的轉場線索，保守給分 |

要保留的優點：
- 品牌漸層 logo、學校語意色、左側導覽加手機底部 5 格分頁的骨架，和另一版共用，品質穩定。
- source desktop 的五列篩選（學校、狀態、類型、標籤、平台），每個選項附計數，一眼看出資料分布。
- org-rich mobile：日期在上、標題在下，「即將舉行」與「過往活動」分段清楚。
- submit 與 account 未登入頁：說明登入能做什麼，並附隱私說明連結。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [home-loading、home-error、events-loading、events-error、source-error] [兩者] 載入與錯誤截圖和資料畫面或彼此相同；source-error 沒有錯誤訊息，篩選計數變成空白方塊 —— 使用者分不出資料是載入中、失敗，還是本來就這樣 —— 建議每個狀態有獨立畫面：骨架、錯誤原因、重新載入按鈕，並保留稍早的資料。
2. [一致性] [not-found] [兩者] 404 用瀏覽器原生白底輸入框和灰色系統按鈕 —— 迷路的使用者最需要被引導，這頁卻看起來像壞掉 —— 建議改用全站的膠囊輸入框與按鈕，「回到首頁」「瀏覽所有活動」做成按鈕。
3. [狀態與回饋] [source-followed-empty、source-search、org-empty] [兩者] 空結果只有一句「沒有符合的單位。」或「尚未從這個來源收錄到活動。」，還在 0 筆或已全部顯示時出現「顯示更多單位」 —— 沒有下一步，按鈕也會誤導 —— 建議用空狀態卡說明原因並附 CTA，結果已全部顯示時隱藏「顯示更多」。
4. [間距與版面] [source] [兩者] desktop 連結欄顯示完整帳號，列高在一到四行之間參差；mobile 篩選全展開，首屏看不到任何單位 —— 名錄的掃讀效率大幅下降 —— 建議連結欄只顯示平台縮寫（帳號放 tooltip 或詳情頁），手機版把次要篩選收進「更多篩選」。
5. [文案] [account-signed-in、org-rich、org-empty、source-search] [兩者] 刪除說明有「Apify 貢獻憑證」等內部術語，收錄貼文有 ☒ 缺字，兩顆按鈕都只寫「Facebook」，標題斷成「吉 / 他」 —— 系統細節外露、內容無法辨識 —— 建議改寫成白話、過濾無法顯示的字元、外部連結附帳號名、標題與搜尋詞分兩行。

```json
{"A": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 8, "間距與版面": 8, "一致性": 7.5, "資訊密度": 7, "導覽": 7.5, "狀態與回饋": 6, "響應式": 7.5, "文案": 7.5, "無障礙": 6.5, "動畫與轉場": 6}, "issues": ["[狀態與回饋] 全部截圖 兩者：只有資料狀態，看不到載入、空資料、錯誤與無結果畫面", "[資訊密度] accupass-home mobile：首屏被橫幅與分類佔滿，活動卡要往下捲才出現", "[無障礙] accupass-home desktop：橫幅圖上的疊字與灰色輔助字對比不足", "[一致性] nycu-life-events 兩者：校方系統元件與字級較舊、較擠", "[導覽] luma-discover、accupass-home mobile：主要導覽收在頂部選單，沒有底部常駐入口"]}, "B": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 7.5, "間距與版面": 7.5, "一致性": 7.5, "資訊密度": 8, "導覽": 8, "狀態與回饋": 8.5, "響應式": 8, "文案": 8, "無障礙": 7, "動畫與轉場": 6}, "issues": ["[無障礙] source、source-light desktop：表格文字約 11–12px，計數徽章對比偏低", "[狀態與回饋] event-signed-in、subscribe-signed-in mobile：與未登入截圖逐位元相同，首屏看不出登入差異", "[文案] account-signed-in、source-error：『優先點數』『抓取額度』『（代碼 500）』等內部用語外露", "[間距與版面] not-found、submit、org-rich desktop：各頁主欄左緣不一（約 280、310、510px）", "[間距與版面] org-empty、source-search mobile：頁尾連結群組與底部分頁重複，佔掉半個螢幕以上"]}, "C": {"scores": {"資訊層級": 7, "字體排印": 6.5, "色彩": 7, "間距與版面": 6, "一致性": 5.5, "資訊密度": 6.5, "導覽": 7, "狀態與回饋": 4.5, "響應式": 6, "文案": 6, "無障礙": 5.5, "動畫與轉場": 5}, "issues": ["[狀態與回饋] home-loading、home-error、events-loading、events-error、source-error：載入與錯誤畫面相同或無錯誤訊息，篩選計數變成空白方塊", "[一致性] not-found 兩者：使用瀏覽器原生輸入框與系統按鈕，和全站元件不一致", "[狀態與回饋] source-followed-empty、source-search、org-empty：空結果沒有下一步，還出現誤導的『顯示更多單位』", "[間距與版面] source 兩者：desktop 連結欄換行使列高參差，mobile 篩選全展開，首屏看不到單位", "[文案] account-signed-in、org-rich、org-empty、source-search：『Apify 貢獻憑證』術語、☒ 缺字、兩顆同名『Facebook』按鈕、標題斷成『吉／他』"]}}
```
