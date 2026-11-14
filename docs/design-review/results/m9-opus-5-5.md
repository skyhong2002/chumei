# Round m9 blind review: opus-5-5

- Host: sky-mini
- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **B = baseline**, **A = new**, **C = reference**
- New set: `/Users/skyhong/cm-review/sets/new-m9`
- Mean of 12 scores: new 7.67, baseline 5.71, reference 7.12
- Note: First sky-mini round: baseline (main b5cf91d), new (fa10fa0, round 9 changes) and reference all re-shot on sky-mini (PingFang TC, Apple Color Emoji); not comparable with r1-r8.

Raw reviewer output below, unedited.

---

## 組 A
一句話總評：完成度最高的竹梅版本。錯誤、空資料、載入、登入後這幾種狀態都有說明和下一步，手機版的層級也清楚；剩下的主要是資訊密度、桌面窄欄和幾個文案細節。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | home mobile：頁首下方先有一句「清大與陽明交大的校園活動和社團貼文，自動彙整在這裡，每則都連回原文。看即將舉行的活動 →」，第一次來的人知道這是什麼網站。event-rich mobile：依序是標題、日期副標、時間／地點／主辦／類型／報名的定義列表、主要按鈕「報名／活動頁」，海報排在後面。org-rich desktop：右欄有「收錄活動 59 場／即將舉行 11 場／公開帳號 3 個／最近更新」四張統計卡，以及「收錄貼文（7 則）」。 |
| 字體排印 | 7.5 | event-rich mobile 的標題「校園急救實戰-從傷口照護到擬真演練！」用粗體大字，換行自然；日期是獨立一行副標。event-rich desktop 左欄「來自 NYCU LIFE 活動系統 的更多活動」很窄，「【全校運動會健康指南】賽前 4 訣竅要記牢…」折成三行。status desktop 統計卡裡「目標每 3 小時・正常 8・待抓 0…」的灰色小字很難讀。 |
| 色彩 | 7.5 | 「竹梅」用藍紫漸層字當品牌識別；學校有語意色（清大紫、交大／陽明交大藍、陽明另一色）；「需報名」用琥珀色、「免費」用藍色。錯誤卡在 home-error mobile 是暗紅底配粉色字，語意清楚。account-signed-in-light mobile、event-rich-light desktop 的淺色外觀都成立。深色模式是純黑底，層次主要靠細框線。 |
| 間距與版面 | 7.5 | account-signed-in desktop 用兩欄卡片格線，善用 1440 寬。submit desktop：表單和「最近的回報」左右分欄。events mobile 的列表左側有學校色條，縮圖、日期和標題對齊整齊。org-empty desktop：空狀態卡和三張「0 場」統計卡並排，資訊重複，桌面右側有大片空白。 |
| 一致性 | 8 | 空狀態一律是虛線框＋標題＋說明＋一個按鈕，home-empty、events-empty、stories-empty、org-empty、source-followed-empty 五處相同。錯誤卡一律是「X 暫時載入不了／伺服器暫時沒有回應…／詳細資訊／重新載入」，home-error、events-error、source-error、status-error 四處相同。主要按鈕是實心藍色膠囊（submit-signed-in「送出」、account-signed-in「儲存」）。例外：source mobile 的排序鈕「名稱⬍」是方塊狀的表情符號式圖示，和其他線條圖示不同套。 |
| 資訊密度 | 8 | calendar mobile 一屏約 10 筆，每筆是時間、標題和地點。source mobile 預設只露出學校膠囊、搜尋和「更多篩選」，第一屏就看得到名錄。home mobile 第一則貼文要在導言、限動和快捷膠囊之後（約 270 px）才出現，略晚。 |
| 導覽 | 8 | 手機底部有五個分頁（最新／活動／日曆／限動／更多），目前所在分頁會加粗。home-signed-in mobile 的「更多」選單列出 App 通知到登出共 10 項，還有外觀選項。登入後 mobile 頁首會出現「林」頭像（event-signed-in、submit-signed-in）。404 mobile 有搜尋框和「回到首頁／瀏覽所有活動」。source-search mobile 的副標寫著「搜尋「吉他」」，看得出目前條件。 |
| 狀態與回饋 | 8.5 | home-loading mobile：浮動膠囊「正在載入最新貼文…」，帶轉圈圖示。calendar-loading mobile：「正在載入最新活動資料…」橫幅。source-error mobile 說明「下方是稍早整理的完整名錄，篩選、排序與搜尋要等資料載入後才能使用」。source-followed-empty：「你還沒有追蹤任何單位」加上「瀏覽全部單位」。扣分處：events-no-results mobile 已搜尋「zzqxv」，但按鈕只有「看全部時間的活動」，沒有清除搜尋的選項。 |
| 響應式 | 8 | 手機和桌面各有適合的版面，不是單純縮放：桌面用側欄、手機用底部分頁；account-signed-in 桌面兩欄、手機一欄；events mobile 的時間膠囊橫向捲動，右緣露出半個「未…」當作還能捲的提示。沒有看到溢出。手機頁尾是精簡的兩行連結。 |
| 文案 | 8 | 用詞口語又精準，例如 org-empty「竹梅會持續整理它的公開帳號；有新活動時會列在這裡。如果你看到它的活動沒被收錄，可以把貼文連結回報給我們」，以及 404「連結是從竹梅點過來的？回報連結問題」。org-empty 把兩個 Facebook 區分成「Facebook nthucookingclub」和「Facebook 清大烹飪社」。status 頁仍有「快照」「抓取」這類系統用語。 |
| 無障礙 | 7 | 主要按鈕和膠囊高度足夠，手機約 40–44 CSS px；account-signed-in 的核取方塊放大成自訂樣式。學校語意除了顏色還有文字標籤（清大／交大）。深色模式的灰色次要文字（status 統計卡、events 列表的地點行）對比偏低。從截圖看不到焦點樣式。 |
| 動畫與轉場 | 6 | 只能從靜態線索推測：載入是轉圈膠囊和橫幅，沒有骨架；home-search-open 是全螢幕搜尋層，有分組結果；home-signed-in 是從底部升起的「更多」面板。沒有看到過場或骨架的設計，所以給保守分數。 |

要保留的優點：
- 錯誤卡的寫法：說明「仍顯示稍早的資料」，再給「詳細資訊」和「重新載入」（home-error、events-error、source-error、status-error）。
- 虛線框空狀態，每個都帶一個對應的下一步按鈕（home-empty「看即將舉行的活動」、stories-empty、source-followed-empty「瀏覽全部單位」）。
- 活動頁先放標題和日期，接著是結構化資訊列表，再放主要按鈕，海報在後面（event-rich mobile）。
- 單位頁的統計卡和「收錄貼文」（org-rich desktop）。
- 帳號設定在桌面用兩欄卡片，整合了「我會去的活動行事曆」、Apple／Google 訂閱和刪除帳號（account-signed-in desktop）。
- 登入後手機頁首顯示頭像（event-signed-in、submit-signed-in mobile）。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [events-no-results] [兩者] 有搜尋字串「zzqxv」時，空狀態只給「看全部時間的活動」，沒有「清除搜尋」 —— 使用者最可能的下一步是改關鍵字，按鈕卻引導去改時間 —— 有搜尋字串時，主要按鈕改成「清除搜尋『zzqxv』」，時間放寬當次要按鈕。
2. [無障礙] [status、events、calendar（深色）] [兩者] 純黑底上的灰色次要文字（地點、統計卡細項）對比偏低，status desktop 的統計卡細項只有約 11px —— 多數人在手機上看，地點又是關鍵資訊 —— 提高次要文字亮度到 AA，地點行至少 13px。
3. [間距與版面] [event-rich、event-sparse] [desktop] 「更多活動」塞在海報下方的窄欄，標題折成三行；右欄的描述只有一段原始文字，網址 forms.gle 沒有做成連結 —— 桌面寬度沒用好，報名網址不能點 —— 「更多活動」移到主欄下方改成橫列；描述裡的網址自動轉成連結。
4. [一致性] [source、source-light、source-error] [mobile] 排序鈕的「⬍」圖示是方塊表情符號樣式，和全站的線條圖示不一致 —— 看起來像亂碼或預設樣式 —— 換成同一套線條排序圖示。
5. [資訊密度] [home] [mobile] 第一則貼文前有導言、限動列和快捷膠囊三層，約占首屏三分之一；org-empty desktop 的空狀態和三張 0 統計卡重複 —— 首屏效率低，資訊重複 —— 導言只在第一次造訪或未登入時顯示；空單位隱藏 0 的統計卡。

## 組 B
一句話總評：和 A 同一套視覺，但多處退步：錯誤和載入狀態沒有任何提示（看起來像資料正常），手機篩選全展開占滿首屏，活動頁標題和日期併成一串、海報擋在資訊前面，404 和部分按鈕是瀏覽器預設樣式。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6.5 | home mobile 沒有導言，第一次來的人不知道這是什麼網站。event-rich mobile 先放整張海報，約 800 CSS px 高，標題、時間和地點全被推到首屏以下。event-rich desktop 在標題下面先放一段原始描述，而且在「報名資」處被截斷，描述在按鈕下方又完整出現一次。 |
| 字體排印 | 6 | 標題後面直接接狀態：「校園急救實戰-從傷口照護到擬真演練！｜2026 年 11 月 19 日」（event-rich）、「資料來源與機構名錄｜搜尋「吉他」」在 source-search mobile 斷成「吉／他」」。events mobile 的「需報名」「免費」膠囊折成兩行（「需報／名」「免／費」），時間「11/12（四）／19:00」也被擠到換行。 |
| 色彩 | 7 | 品牌漸層和學校語意色和 A 相同，淺色外觀也成立（source-light、account-signed-in-light）。但錯誤狀態完全沒有用到警示色（home-error、events-error、source-error），語意色系統少了一塊。 |
| 間距與版面 | 6 | home desktop 第三欄（陽明）被視窗右緣切掉，靠「>」箭頭橫捲，三欄寬度不平均。source mobile 的篩選全部展開（學校、狀態、類型、標籤、平台），名錄從約 760 CSS px 才開始。source desktop 的帳號 handle 折成兩行，每列高度不一。手機頁尾是四區完整網站地圖，約 400 CSS px，每頁都很長。 |
| 一致性 | 5.5 | not-found desktop／mobile：「搜尋活動 [原生輸入框] [原生灰色按鈕]」是瀏覽器預設樣式，和全站膠囊元件不同套。主要按鈕時而實心、時而外框：account-signed-in「儲存」、submit-signed-in「送出」是外框，notify「開啟推播」是實心。submit 和 account 的登入按鈕是兩個實心藍、一個外框，權重不明。org-rich 所有日期和標題都加了底線，其他列表沒有。 |
| 資訊密度 | 6 | source mobile 首屏只有篩選、沒有任何單位。org-rich desktop 只有單欄列表，沒有統計和最近貼文，右半邊空著。events mobile 的列表上方多了「活動地圖／顯示活動地圖」區塊，第一筆活動被推到約 650 CSS px。 |
| 導覽 | 6.5 | 底部分頁和更多選單與 A 相同（home-signed-in）。但登入後手機頁首沒有頭像（event-signed-in、submit-signed-in mobile），看不出已登入。篩選無法收合，在手機上要捲很久才能回到結果。 |
| 狀態與回饋 | 3.5 | home-error mobile：照常顯示舊貼文，完全沒有錯誤提示。events-error mobile：「排序」「時間」標籤後面是空白，沒有任何訊息。source-error：篩選膠囊的數字變成空灰塊，「標籤」「平台」整列空白，也沒說明。status-error desktop：同時出現「資料快照：載入中…」「讀取排程設定中…」和小字「狀態資料讀取失敗」，表格是空的，自相矛盾。home-loading、calendar-loading：沒有任何載入指示。home-empty 只有一行「沒有符合的貼文。」。source-followed-empty 顯示「沒有符合的單位。」，卻還有「顯示更多單位」按鈕。 |
| 響應式 | 6 | events／events-error mobile 的膠囊在窄寬度下變形成兩行圓塊。source-search mobile 的標題折斷。home desktop 的欄位被切掉。手機篩選沒有因應窄螢幕收合。 |
| 文案 | 5.5 | status desktop／mobile 的說明直接寫「quota」「Apify」「每日 quota 重複投入同一來源」「＋／－逐點收回」，內部營運用語外露。submit 的第一個登入按鈕寫「登入後回報連結」，看不出是用哪所學校的帳號。org-empty 有兩個都叫「Facebook」的按鈕，無法分辨。events 的「全部」膠囊數字是空灰塊（events mobile，連有資料時也一樣）。 |
| 無障礙 | 6 | account-signed-in mobile 的「我同意公開個人頁」是很小的原生核取方塊。404 的原生輸入框很小，桌面約 20 px 高。外框式主要按鈕的視覺權重弱。錯誤只靠內容消失或空白來表現，沒有文字或顏色提示，對輔助科技也不友善。 |
| 動畫與轉場 | 4 | 載入中狀態沒有任何骨架或指示（home-loading、calendar-loading），無法判斷是否正在更新。搜尋層和更多面板與 A 相同，但其他狀態切換沒有可見的過渡線索。 |

要保留的優點：
- source mobile／desktop 的列表直接顯示帳號 handle（「IG @nthu_jad」「Threads @nthu_mubao」），比只寫「IG FB」好辨識。
- 學校篩選在手機上折行完整顯示，不靠橫捲（source mobile「交大校區 187、陽明校區 54」）。
- notify、subscribe、about、calendar 的內容和結構完整，與 A 一致。
- event-sparse 的「資料待確認」琥珀色警示框，以及 org-rich 全部可點的連結列。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [home-error、events-error、source-error、status-error] [兩者] 載入失敗時沒有任何錯誤訊息，只剩空白標籤、空灰塊或舊資料 —— 使用者會以為資料就是這樣，或以為網站壞了卻沒有重試方式 —— 加回統一的錯誤卡：說明、顯示稍早的資料、重新載入按鈕。
2. [資訊層級] [event-rich、event-sparse、event-signed-in] [兩者] 手機海報放在最上面，把標題、時間、地點推到首屏外；標題串上「｜日期」；描述截斷後又重複一次 —— 活動頁最重要的時間地點被延後，閱讀重複 —— 標題和日期分開，資訊列表和主要按鈕放在海報前，描述只出現一次。
3. [間距與版面] [source、source-followed-empty、source-search] [mobile] 五組篩選全部展開，結果要到約 760 CSS px 才出現；0 筆時還顯示「顯示更多單位」 —— 手機主要使用情境被篩選牆擋住 —— 只保留學校和搜尋，其餘收進「更多篩選」；0 筆時隱藏「顯示更多」，改成有引導的空狀態。
4. [一致性] [not-found、account-signed-in、submit-signed-in] [兩者] 404 用原生輸入框和按鈕；「儲存」「送出」變成外框按鈕；登入按鈕時而實心、時而外框 —— 看起來像沒上樣式，主要動作權重混亂 —— 統一用膠囊輸入框和實心主要按鈕。
5. [文案] [status、status-error、submit、org-empty] [兩者] 「quota」「Apify」等內部術語外露；「登入後回報連結」按鈕沒有說明帳號來源；兩個同名的「Facebook」按鈕 —— 一般學生看不懂，也點不準 —— status 改寫成使用者語言（多久更新一次、為什麼會延遲）；按鈕標出學校，帳號按鈕加上名稱或 handle。

## 組 C
一句話總評：參考組（Accupass、Luma、NYCU Life Events）是成熟的商業和校方產品。視覺識別、卡片格線和活動資訊結構都很穩；缺點是彈出層遮蓋內容、部分頁面空白過多，而且截圖裡看不到它們的錯誤或空狀態。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | luma-taipei desktop：依日期分組（「明天 星期六」），每張卡依序是時間、標題、主辦、地點、狀態（即將額滿／候補名單／已售罄）。accupass-search：每張卡是圖、日期、標題、地點、標籤、瀏覽數。accupass-home 首屏被大型 Banner 輪播占掉，活動卡要往下捲才看到。 |
| 字體排印 | 8 | Luma 的標題和灰色次要資訊字級對比清楚，中英混排自然（「[Cleanup 0.24]三校迎風｜野海同行」）。Accupass 的長標題用兩行省略號。NYCU Life 卡片標題兩行，日期和地點有圖示。 |
| 色彩 | 8 | Accupass 是明確的品牌藍頂欄；Luma 用柔和漸層加城市照片 hero；NYCU Life 是藍色主色加「光復校區／陽明校區」的淡藍標籤。三者都是淺色；NYCU Life 有深色模式切換，但截圖沒有呈現。 |
| 間距與版面 | 7.5 | accupass-search desktop 三欄卡片格線整齊；luma-discover 的類別格是 3×4。nycu-life-events desktop 右側「已釘選／近期活動」卡下方有大片空白（約 450 px）；第二排的「Open House」卡沒有圖，和其他卡高度不一致。 |
| 一致性 | 7.5 | 各自站內一致：Luma 的卡片、「追蹤」小鈕和圓角統一；Accupass 卡片的 meta 列統一。但 nycu-life 卡片的「活動公告」灰色按鈕和膠囊標籤樣式混用。 |
| 資訊密度 | 7.5 | luma-taipei 一屏約 4–5 場，資訊精簡。accupass-home 的 Banner 和「每天一點新鮮事」等行銷區塊稀釋了活動密度。nycu-life mobile 一張卡占大半屏，因為有 QR 海報大圖。 |
| 導覽 | 7.5 | Accupass 有「精選／學習／藝文／體驗」分頁；NYCU Life 有「所有活動／依活動性質／依校區／依處室／已結束活動」分頁和搜尋列；Luma 有地區分頁（亞洲與太平洋…）。但 nycu-life mobile 的分頁折行，「已結束活動」單獨落在第二行；Luma 手機沒有底部導覽。 |
| 狀態與回饋 | 5 | 截圖只看得到有資料的狀態，看不到載入、錯誤或空資料。nycu-life 未登入時有「登入後可釘選活動分類。」「登入查看近期已報名活動」，算有提示；Luma 有「即將額滿／已售罄」的即時狀態。證據不足，給保守分數。 |
| 響應式 | 7.5 | luma-discover mobile 的「熱門活動」和類別用橫向捲動，右緣露出半張卡當提示；accupass-home mobile 的推薦卡也橫捲。但 accupass-home mobile 底部的 Cookie 橫幅遮住約 1/8 畫面；desktop 的 Cookie 視窗和「最全面的活動整合服務」浮動廣告同時蓋住最後一排卡片。 |
| 文案 | 7.5 | Luma「精彩活動盡在 台北」「探索附近的熱門活動、按類別瀏覽…」很自然；NYCU Life「本週精選」「暫停輪播」清楚。Accupass 有「每天一點新鮮事」這類行銷用語，以及「主辦榜」，對找活動幫助有限。 |
| 無障礙 | 6.5 | nycu-life 的輪播有「‹ 2/5 › 暫停輪播」控制，是好的做法。Luma 的灰色次要字（「由 ninja 主辦」、地點）在淺灰底上對比低；Accupass 的日期灰字很小（約 11px）；Accupass 的 Banner 只靠圖片傳達資訊。 |
| 動畫與轉場 | 5 | 可見線索只有輪播的分頁點和箭頭（accupass-home、nycu-life「2/5」），Luma 的 hero 照片有景深漸層。看不到載入骨架或狀態過渡，給保守分數。 |

要保留的優點：
- Luma 依日期分組的時間軸列表，加上「即將額滿／候補名單／已售罄」狀態膠囊（luma-taipei）。
- NYCU Life 輪播的「暫停輪播」和「2/5」控制（nycu-life-events desktop）。
- Luma 類別格：圖示＋名稱＋場次數（luma-discover desktop）。
- Accupass 卡片 meta 結構統一：日期、標題、地點、標籤、瀏覽數（accupass-search）。
- NYCU Life 的校區標籤和分頁（依校區／依處室）切分清楚。

最重要的五個問題（由嚴重到輕微）：
1. [響應式] [accupass-home] [兩者] Cookie 橫幅和浮動推廣同時蓋住內容，手機底部約 1/8 被遮 —— 第一次造訪就擋住活動卡 —— 合併成單一、較矮的通知，並且不和浮動廣告同時出現。
2. [資訊層級] [accupass-home] [兩者] 大型 Banner 輪播和行銷區塊排在活動之前，首屏幾乎沒有可操作的活動資訊 —— 找活動的效率低 —— 縮小 hero，把「近期活動」提到首屏。
3. [間距與版面] [nycu-life-events] [desktop] 右側側欄下方大片空白，無圖卡片高度不一 —— 版面失衡、桌面寬度浪費 —— 側欄放近期活動或篩選，無圖卡給替代縮圖。
4. [無障礙] [luma-taipei、accupass-search] [兩者] 灰色次要文字對比低、字很小 —— 主辦和地點是關鍵資訊 —— 提高次要文字對比和字級。
5. [導覽] [nycu-life-events] [mobile] 分頁折行，「已結束活動」單獨一行，看起來像不同層級 —— 位置感混亂 —— 改成橫向捲動的分頁，或收進下拉選單。

```json
{"A": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 7.5, "間距與版面": 7.5, "一致性": 8, "資訊密度": 8, "導覽": 8, "狀態與回饋": 8.5, "響應式": 8, "文案": 8, "無障礙": 7, "動畫與轉場": 6}, "issues": ["[狀態與回饋] events-no-results 兩者：有搜尋字串時空狀態只給『看全部時間的活動』，缺少『清除搜尋』", "[無障礙] status/events/calendar 深色 兩者：純黑底上灰色次要文字對比偏低，status 統計卡細項過小", "[間距與版面] event-rich/event-sparse desktop：『更多活動』塞在海報下窄欄折三行；描述中的報名網址沒有做成連結", "[一致性] source 系列 mobile：排序鈕『⬍』是方塊表情符號樣式，和全站線條圖示不一致", "[資訊密度] home mobile 首則貼文前有導言、限動、快捷膠囊三層；org-empty desktop 空狀態與 0 統計卡重複"]}, "B": {"scores": {"資訊層級": 6.5, "字體排印": 6, "色彩": 7, "間距與版面": 6, "一致性": 5.5, "資訊密度": 6, "導覽": 6.5, "狀態與回饋": 3.5, "響應式": 6, "文案": 5.5, "無障礙": 6, "動畫與轉場": 4}, "issues": ["[狀態與回饋] home-error/events-error/source-error/status-error 兩者：載入失敗時沒有錯誤訊息，只剩空白標籤、空灰塊或舊資料；home-loading、calendar-loading 也沒有載入指示", "[資訊層級] event-rich/event-sparse/event-signed-in 兩者：手機海報置頂推走時間地點；標題串上『｜日期』；描述截斷後又重複一次", "[間距與版面] source 系列 mobile：五組篩選全部展開，結果約 760px 才出現；0 筆時仍顯示『顯示更多單位』", "[一致性] not-found/account-signed-in/submit-signed-in 兩者：404 用原生輸入框和按鈕，儲存與送出變外框按鈕，登入按鈕權重混亂", "[文案] status/submit/org-empty 兩者：quota、Apify 等內部術語外露；『登入後回報連結』按鈕不明確；兩個同名 Facebook 按鈕"]}, "C": {"scores": {"資訊層級": 8, "字體排印": 8, "色彩": 8, "間距與版面": 7.5, "一致性": 7.5, "資訊密度": 7.5, "導覽": 7.5, "狀態與回饋": 5, "響應式": 7.5, "文案": 7.5, "無障礙": 6.5, "動畫與轉場": 5}, "issues": ["[響應式] accupass-home 兩者：Cookie 橫幅和浮動推廣同時遮住內容", "[資訊層級] accupass-home 兩者：大型 Banner 和行銷區塊排在活動之前，首屏缺少可操作的活動", "[間距與版面] nycu-life-events desktop：右側側欄大片空白，無圖卡片高度不一", "[無障礙] luma-taipei/accupass-search 兩者：灰色次要文字對比低、字太小", "[導覽] nycu-life-events mobile：分頁折行，『已結束活動』單獨一行"]}}
```
