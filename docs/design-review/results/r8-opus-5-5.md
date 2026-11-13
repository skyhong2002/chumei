# Round 8 blind review: opus-5-5

- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **A = baseline**, **C = new**, **B = reference**
- New set: `/tmp/cm-review/sets/new-r8`
- Mean of 12 scores: baseline 5.83, reference 7.67, new 7.46

Raw reviewer output below, unedited.

---

## 組 A
一句話總評：資料豐富，深色品牌色也成立，但錯誤與空資料狀態大多缺漏或壞掉，各頁版面寬度不一致，手機上也有標籤斷行、未登入感，整體還停在「能用但粗糙」。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6.5 | home desktop：頁首直接是限動圈和欄位，沒有任何一句說明網站是做什麼的。event-signed-in desktop/mobile：標題寫成「校園急救實戰-從傷口照護到擬真演練！｜2026 年 11 月 19 日」，日期和標題黏成同一行 H1；下方又有一段在「報名資」截斷的摘要，與內文重複。events mobile：日期、標題、地點的順序清楚。 |
| 字體排印 | 6.5 | events mobile：「需報名」「免費」膠囊被擠成兩行（「需報／名」「免／費」），變成大橢圓。source-search mobile：H1「資料來源與機構名錄｜搜尋「吉／他」」把引號內的詞從中間斷開。org-rich desktop：日期和標題都加底線，整欄底線密集，很難閱讀。 |
| 色彩 | 7 | 深色底配藍紫漸層字標，品牌一致。清大用紫、陽明交大用藍、交大／陽明校區用橘黃標籤，語意色有系統（source desktop）。source-light、account-signed-in-light desktop 淺色版成立。events mobile 的左側色條區分類型。 |
| 間距與版面 | 5.5 | home desktop：第三欄「陽明」被視窗右緣切掉（「陽明烘焙研…」截斷，圖片右半消失）。submit／account desktop：內容欄置中在 490–1210px，與其他頁從 280px 起排的左緣不一致。org-rich desktop：只用一欄約 540px，右側整片空著。 |
| 一致性 | 5.5 | 「追蹤」按鈕在 org-rich 叫「追蹤主辦」，在 source 叫「追蹤」，在 source-error 又叫「追蹤主辦」。not-found desktop：瀏覽器原生的小輸入框加灰色「搜尋」按鈕，與全站膠囊按鈕不同套。account-signed-in desktop：「永久刪除我的帳號」是外框按鈕，「儲存」也是外框按鈕，危險動作和一般動作看起來一樣。 |
| 資訊密度 | 6.5 | source desktop：連結欄把 IG／Threads 帳號完整列出，#512 一列高到四行，每列高度不一。source mobile：五組篩選全部展開，名錄要捲過約 950px 才出現第一筆。events mobile 列表的密度適中。 |
| 導覽 | 6.5 | 桌面左側欄、手機底部五格導覽清楚，目前頁有高亮。event-signed-in／submit-signed-in mobile：頁首沒有頭像，登入後的手機畫面看不出已經登入。source-search desktop：已經全部顯示 3 筆，下方仍有「顯示更多單位」。 |
| 狀態與回饋 | 4 | events-error desktop/mobile 和 events-loading 幾乎一樣，沒有任何錯誤說明或重試。source-error desktop：計數徽章變成空白方塊，「標籤」「平台」整列空白，沒有錯誤提示。status-error 只剩一行小字和空表格。source-followed-empty：只寫「沒有符合的單位。」，下面卻還有「顯示更多單位」。org-empty：只有一句「尚未從這個來源收錄到活動。」，沒有下一步。stories-empty 的文字斷行歪斜，也沒有下一步。 |
| 響應式 | 5.5 | home desktop 欄位溢出被切。events mobile 的膠囊斷行。mobile 頁尾把四組連結各自完整列出（org-empty mobile 頁尾約 900px 高）。source mobile 篩選全部展開，佔掉一屏多。 |
| 文案 | 6 | account-signed-in：刪除說明出現「Apify 貢獻憑證」「優先權重分配」等內部術語。submit desktop 有三顆按鈕「登入後回報連結／用清大帳號登入／用 Google 登入」，第一顆的用途不明，也沒寫陽明交大。org-empty 兩顆按鈕都只寫「Facebook」，無法區分。 |
| 無障礙 | 5.5 | account-signed-in desktop：「我同意公開個人頁」是很小的原生核取方塊，旁邊的說明是極小的灰字。not-found 的原生輸入框只有約 18px 高。source-error 只用空白徽章表示異常。source desktop 名錄字級約 11–12px，灰字對比偏低。 |
| 動畫與轉場 | 5 | home-loading／events-loading 有骨架，但 events-error 和骨架相同，看不出狀態有切換。home-search-open 有對話框遮罩。其他沒有足夠的動態線索，所以保守給分。 |

要保留的優點：
- 深色預設搭配藍紫漸層字標「竹梅活動觀測站」，品牌辨識度高，淺色版也完整（source-light、account-signed-in-light）。
- 學校語意色有系統：清大紫、陽明交大藍、校區橘黃，名錄和活動列表都用同一套。
- events mobile 的活動列：縮圖、粗體日期時間、標題、地點，加上左側類型色條和「我會去」「追蹤」兩個圖示，結構清楚。
- 活動頁的資訊表（時間、地點、主辦、類型、報名、原始貼文）配上「報名／活動頁、加入 Google 日曆、在地圖上看、我會去、分享」整排動作，很實用。
- 帳號頁把隱私說明寫得很完整（預設不公開、匿名計數）。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [events-error, source-error, status-error] [兩者] 載入失敗時沒有錯誤訊息：events-error 和 loading 無法分辨，source-error 的徽章變空白、標籤列消失 —— 使用者會以為網站壞了或一直在載入，而且沒有重試的方法 —— 每個錯誤狀態都要有標題、原因、「重新載入」按鈕，並標示畫面上是不是舊資料。
2. [間距與版面] [home] [desktop] 第三欄超出視窗被切，首頁也沒有任何網站說明 —— 這是第一屏，看起來像排版壞掉，新使用者也不知道網站做什麼 —— 讓欄數配合可用寬度，切不下的改成明確的「新增一欄」控制項，頂端加一句價值說明，並附「看即將舉行的活動」連結。
3. [響應式／字體排印] [events] [mobile] 「需報名」「免費」膠囊斷成兩行的大橢圓，擠壓標題 —— 活動列表是最主要的使用情境 —— 膠囊設為不斷行，放不下時改到下一行，或縮成圖示。
4. [狀態與回饋／文案] [org-empty, source-followed-empty, stories-empty] [兩者] 空狀態只有一句話，沒有下一步；org-empty 的兩顆「Facebook」按鈕分不出來；追蹤 0 筆仍顯示「顯示更多單位」 —— 使用者卡住，也會誤以為是資料錯誤 —— 統一做空狀態卡片（說明加主要動作，例如「回報活動」「瀏覽全部單位」），同平台多個帳號要附帳號名稱。
5. [一致性／文案] [not-found, account-signed-in, org-rich] [兩者] 404 用瀏覽器原生輸入框；刪除帳號是外框按鈕，說明還外露「Apify 貢獻憑證」；org-rich 收錄貼文出現豆腐字「☐☐☐」 —— 這些細節破壞信任感 —— 404 套用全站元件，危險按鈕用實心紅色，說明改成白話，並補上字型或過濾無法顯示的字元。

## 組 B
一句話總評：參考組由 Accupass、Luma、陽明交大生活網三個成熟產品組成。前兩者視覺精緻、以圖片為主、層級明確；校方網站較傳統。截圖只有有資料的狀態，評不到錯誤與空狀態。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8.5 | accupass-home desktop：大型主視覺輪播、分類入口和活動卡依序排列，一眼看得出是售票與活動平台。luma-discover desktop：「探索」標題、熱門活動、城市分類，主次清楚。活動卡都先給圖片、日期、標題。 |
| 字體排印 | 8 | luma-discover／luma-taipei：字級階層少而清楚，留白大，中英混排自然。accupass-search mobile：卡片標題兩行截斷整齊。nycu-life-events 的字級偏小、偏傳統。 |
| 色彩 | 8 | Accupass 品牌色用在按鈕和標記，其餘交給活動圖片。Luma 是近乎單色的極簡配色，靠城市和活動圖片上色。nycu-life-events 是校方藍白，有識別但偏制式。 |
| 間距與版面 | 8.5 | luma-discover desktop：格線一致，城市格與活動列對齊，留白節奏穩定。accupass-home desktop：卡片格線整齊，寬度用得好。mobile 都改成單欄卡片，沒有溢出。 |
| 一致性 | 8 | 同一產品內的卡片、按鈕、圓角一致（accupass-home 與 accupass-search 的卡片相同）。三個產品之間風格差異大，nycu-life-events 明顯較舊。 |
| 資訊密度 | 7.5 | accupass-search desktop 一屏約 6–9 張卡，密度適中。luma-taipei 列表較疏，一屏的活動數偏少。nycu-life-events 的列表較擠。 |
| 導覽 | 8 | Accupass 頁首有搜尋框和分類。Luma 有城市切換和「探索」入口。mobile 都有漢堡選單或頂部搜尋，但沒有底部導覽，切換主要頁面要多一步。 |
| 狀態與回饋 | 6 | 截圖只有有資料的狀態，看不到載入、錯誤、空結果；accupass-search 只看得到結果數量。依說明保守給分。 |
| 響應式 | 8 | 三站的 mobile 都是重新排版（單欄卡片、收合選單），不是單純縮放，沒看到橫向溢出。nycu-life-events mobile 的表格式列表偏擠。 |
| 文案 | 8 | Accupass、Luma 的文案短、偏行銷、語氣一致。nycu-life-events 是公文式標題，但用詞精準。 |
| 無障礙 | 7 | Luma 的灰色次要文字對比偏低。Accupass 的圖片上疊字有時不易讀。點擊目標在 mobile 大多夠大。 |
| 動畫與轉場 | 6.5 | accupass-home 有輪播指示點，暗示會切換。其他沒有動態線索，所以保守給分。 |

要保留的優點：
- luma-discover：克制的單色介面，讓活動圖片成為主角，留白與格線節奏穩定。
- accupass-home：主視覺、分類入口、活動卡的首頁層級清楚。
- accupass-search：結果卡固定呈現圖片、日期、標題、地點，掃讀效率高。
- luma-taipei：用城市當作瀏覽入口，對在地活動很直覺。
- nycu-life-events：校方來源的權威感，對竹梅是重要的參考對照。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [全部] [兩者] 截圖裡看不到任何載入、空結果、錯誤狀態 —— 無法確認這些產品在失敗時是否友善 —— 參考時只取版面與層級，不要當作狀態設計的依據。
2. [一致性] [nycu-life-events] [兩者] 校方網站風格明顯比其他兩個舊，字級小、列表擠 —— 與商業平台的落差大 —— 作為資訊來源的參考即可，不宜模仿它的視覺。
3. [導覽] [accupass-home, luma-discover] [mobile] 手機沒有底部導覽，要靠頂部選單切換 —— 經常使用的人切換成本較高 —— 竹梅的底部導覽在這點上較好。
4. [無障礙] [luma-discover, luma-taipei] [兩者] 次要灰字對比偏低 —— 戶外或低亮度時難讀 —— 次要文字至少要達 4.5:1。
5. [資訊密度] [luma-taipei] [desktop] 留白大，一屏活動數少 —— 對想快速掃過大量校園活動的人效率較低 —— 竹梅應保留較高的密度。

## 組 C
一句話總評：和 A 是同一套產品，但把首頁說明、欄寬、空狀態、錯誤狀態、404、單位頁雙欄、手機篩選收合都補齊了，整體成熟一大截；剩下的是日期斷行、少數截斷與留白分配等細節。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | home desktop：頂端一句「清大與陽明交大的校園活動和社團貼文，自動彙整在這裡，每則都連回原文。看即將舉行的活動 →」，新使用者馬上懂。event-signed-in desktop/mobile：H1 只有活動名稱，日期「2026 年 11 月 19 日」另成副標，並刪掉重複的截斷摘要，資訊表緊接在標題下。source-search：H1 加上「搜尋「吉他」」副標。 |
| 字體排印 | 7.5 | 標題和副標的層級清楚（events mobile「活動總覽／排序：時間優先」）。events mobile：日期「11/12（四）」在有兩個膠囊的列會斷成兩行（孫運璿講座、韓語社列），「進行中・至 11/12／（四）」也斷行。org-rich desktop：活動列改成無底線，好讀很多。 |
| 色彩 | 7.5 | 延續 A 的品牌與學校語意色。source-error 用暗紅底橫幅表示錯誤。account-signed-in 的「永久刪除我的帳號」改成實心紅色，「儲存」是實心藍色，語意明確。淺色版成立（source-light、account-signed-in-light）。 |
| 間距與版面 | 7.5 | home desktop：三欄剛好放下，右側是「新增一欄」控制項。org-rich desktop：左欄活動、右欄收錄貼文。account-signed-in desktop 兩欄卡片，submit desktop 改成「說明＋表單｜最近的回報」兩欄，左緣都對齊 280px。缺點是 event-signed-in desktop 海報下方約 500px 空白，org-rich 右欄只用到上方約 450px。 |
| 一致性 | 7.5 | 空狀態統一成虛線框卡片（org-empty、source-followed-empty）。404 的輸入框和按鈕套用全站膠囊樣式。登入按鈕三顆同款（account、submit）。追蹤按鈕統一叫「追蹤」。 |
| 資訊密度 | 7.5 | source desktop：連結欄縮成「IG FB Threads」，每列等高，同一屏可見的單位比 A 多。source mobile：篩選收成「學校」橫向捲動加「更多篩選」，第一筆單位約在 570px 就出現。 |
| 導覽 | 7.5 | event-signed-in／submit-signed-in mobile 頁首有「林」頭像，看得出已登入。org-empty 空狀態直接附「回報活動」。source-followed-empty 附「瀏覽全部單位」。404 有「回到首頁」「瀏覽所有活動」和搜尋。手機的篩選列用右緣半截項目（「交大…」）暗示可以橫捲。 |
| 狀態與回饋 | 8 | source-error desktop/mobile：「名錄暫時載入不了／伺服器暫時沒有回應。下方是稍早整理的完整名錄…」，附「重新載入」與「詳細資訊」。source-followed-empty：「你還沒有追蹤任何單位」，附說明和動作。org-empty：「還沒有收錄到這個單位的活動」，附回報入口。submit-signed-in 的回報列有「待處理／你回報的」。 |
| 響應式 | 7.5 | 手機頁尾改成單行流式連結，比 A 短很多（org-empty mobile）。手機篩選收合。account 手機登出是全寬按鈕。events mobile 日期斷行；source mobile 長名稱截斷成「陽明交大學務處-課外…」。 |
| 文案 | 8 | 刪除帳號說明改成白話：「你在「系統狀態」和「貢獻」頁做過的設定都會一併刪除」，不再出現 Apify。submit 未登入時寫「登入後回報連結」，下面列三種登入方式（含陽明交大）。org-empty 的兩顆按鈕是「Facebook nthucookingclub／Facebook 清大烹飪社」。404 寫「連結是從竹梅點過來的？回報連結問題，我們會修正。」 |
| 無障礙 | 7 | account-signed-in 的核取方塊放大了。404 和登入按鈕的高度約 44px 以上。source desktop 的連結欄 #512 寫成「G FB 官網 Threads X」，「IG」的 I 被切掉。「FB²」「IG²」用上標表示第二個帳號，螢幕閱讀器和一般使用者都不易理解。名錄字級仍偏小。 |
| 動畫與轉場 | 6 | home-loading／events-loading 有骨架。錯誤狀態和載入能清楚區分。home-search-open 有對話框遮罩。「更多篩選」暗示會展開收合。沒有實際動態可看，所以保守給分。 |

要保留的優點：
- home desktop 的一句話價值說明加「看即將舉行的活動 →」，以及剛好放進三欄的欄寬和「新增一欄」控制項。
- 統一的虛線空狀態卡片（標題、說明、主要動作），用在 org-empty、source-followed-empty。
- source-error 的錯誤橫幅：說明原因、告知下方是舊資料、附「重新載入」。
- source mobile 收合篩選（學校橫捲加「更多篩選」），名錄馬上可見。
- event 頁 H1 只放活動名稱、日期另成副標，並刪掉重複的截斷摘要。
- 帳號頁兩欄卡片和實心紅色刪除按鈕，危險動作一眼可辨。

最重要的五個問題（由嚴重到輕微）：
1. [字體排印／響應式] [events] [mobile] 有兩個膠囊的活動列，日期「11/12（四）」斷成兩行，「進行中・至 11/12（四）」也斷行 —— 日期是列表最重要的掃讀資訊，斷行破壞對齊 —— 日期設為不斷行，膠囊移到標題下一行，或在窄寬度時縮小。
2. [無障礙／一致性] [source] [desktop] 連結欄 #512 顯示「G FB 官網 Threads X」，「IG」被切掉；「FB²」「IG²」的上標語意不明 —— 會被看成錯字或註腳 —— 給連結欄足夠寬度或允許換行，第二個帳號改用「FB（另一帳號）」或 tooltip 說明。
3. [間距與版面] [event-signed-in, event-rich] [desktop] 左欄海報下方約 500px 空白，右欄內容很長 —— 寬螢幕上看起來頭重腳輕 —— 讓海報固定在捲動視窗內（sticky），或把「更多活動」移到左欄海報下方。
4. [間距與版面] [org-rich] [desktop] 右欄「收錄貼文」只有 7 列，下方大片空白；貼文標題截斷時 emoji 也被切 —— 雙欄不平衡 —— 讓右欄 sticky，或加上單位簡介、統計補滿，截斷時避開 emoji。
5. [資訊密度] [source] [mobile] 單位名稱截斷成「陽明交大學務處-課外…」，更新時間只到「2025/5」沒有日 —— 名錄是查找工具，名稱和日期都應完整 —— 名稱允許換成兩行，日期統一用「YYYY/M/D」或相對時間。

```json
{"A": {"scores": {"資訊層級": 6.5, "字體排印": 6.5, "色彩": 7, "間距與版面": 5.5, "一致性": 5.5, "資訊密度": 6.5, "導覽": 6.5, "狀態與回饋": 4, "響應式": 5.5, "文案": 6, "無障礙": 5.5, "動畫與轉場": 5}, "issues": ["events-error、source-error、status-error 缺少錯誤訊息與重試，events-error 與載入中無法分辨，source-error 徽章空白", "home desktop 第三欄超出視窗被切，且首頁沒有任何網站說明", "events mobile「需報名」「免費」膠囊斷成兩行大橢圓", "org-empty、source-followed-empty、stories-empty 空狀態沒有下一步，兩顆「Facebook」按鈕無法區分，0 筆仍顯示「顯示更多單位」", "404 用原生輸入框、刪除帳號是外框按鈕且外露「Apify 貢獻憑證」、org-rich 出現豆腐字"]}, "B": {"scores": {"資訊層級": 8.5, "字體排印": 8, "色彩": 8, "間距與版面": 8.5, "一致性": 8, "資訊密度": 7.5, "導覽": 8, "狀態與回饋": 6, "響應式": 8, "文案": 8, "無障礙": 7, "動畫與轉場": 6.5}, "issues": ["截圖只有有資料的狀態，無法評估載入、空結果與錯誤", "nycu-life-events 風格老舊、字級小、列表擠，與其他兩個產品落差大", "手機沒有底部導覽，切換主要頁面成本較高", "Luma 次要灰字對比偏低", "luma-taipei 留白大，一屏活動數少"]}, "C": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 7.5, "間距與版面": 7.5, "一致性": 7.5, "資訊密度": 7.5, "導覽": 7.5, "狀態與回饋": 8, "響應式": 7.5, "文案": 8, "無障礙": 7, "動畫與轉場": 6}, "issues": ["events mobile 有兩個膠囊的列，日期「11/12（四）」斷成兩行", "source desktop 連結欄 #512「IG」被切成「G」，FB²／IG² 上標語意不明", "event 頁 desktop 海報下方約 500px 空白，左右欄不平衡", "org-rich desktop 右欄收錄貼文下方大片空白，截斷時切到 emoji", "source mobile 單位名稱截斷，更新日期只到「2025/5」"]}}
```
