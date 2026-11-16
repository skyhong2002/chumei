# Round 7 blind review: opus-5-5

- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **C = baseline**, **B = new**, **A = reference**
- New set: `/tmp/cm-review/sets/new-r7`
- Mean of 12 scores: reference 7.12, new 7.75, baseline 6.0

Raw reviewer output below, unedited.

---

## 組 A
一句話總評：成熟的商業活動平台（Accupass、Luma）加上校方活動系統。視覺精緻、以圖片帶動瀏覽，但截圖裡沒有載入、空資料、錯誤等狀態，無法評估。另外，校方系統和兩個商業產品的完成度差很多。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | accupass-home desktop／mobile：頂部是主視覺輪播與分類入口，活動卡依序是封面、日期、標題，一眼看得出這是活動售票平台。luma-taipei desktop：活動依日期分組，時間在左、標題粗體，主次清楚。nycu-life-events desktop：列表欄位平均，標題和日期的權重差不多。 |
| 字體排印 | 7.5 | luma-discover／luma-taipei：英文介面的字級階層乾淨，行距寬鬆。accupass-search mobile：中文卡片標題兩行截斷，次要資訊字級偏小、偏灰。nycu-life-events：字級小、行長長，屬於傳統系統的排版。 |
| 色彩 | 8 | Accupass 有品牌色和大量圖片色彩。Luma 用淺色底和少量強調色，很克制。nycu-life-events 大多是預設灰階，沒有語意色。只有一種外觀，看不到深淺兩套是否都成立。 |
| 間距與版面 | 8 | accupass-home desktop：卡片格線整齊，有善用 1440 寬度。luma-discover desktop：留白充足，但內容欄窄，兩側空白多。nycu-life-events desktop：表單式排列，留白節奏不一。 |
| 一致性 | 7.5 | 兩個 Luma 頁面之間、兩個 Accupass 頁面之間的元件都一致。nycu-life-events 和前兩者是不同年代的設計語言。 |
| 資訊密度 | 7 | accupass-home mobile：輪播和廣告區塊占掉首屏，第一張活動卡偏下。luma-taipei mobile：每則活動一列，密度適中。 |
| 導覽 | 7.5 | Accupass 有頂部搜尋列和分類入口；accupass-search 有篩選。Luma 用城市、分類切換。手機上看不到底部導覽，主要靠漢堡選單和頁首。 |
| 狀態與回饋 | 5 | 截圖沒有任何載入、空資料、錯誤或登入前後狀態，找不到證據，給保守分數。 |
| 響應式 | 8 | accupass-home mobile 卡片改成單欄；luma-discover mobile 版面重排合理。nycu-life-events mobile 比較像桌面縮小，表格感重。 |
| 文案 | 7.5 | Accupass 用詞貼近消費情境（售票、報名）。Luma 簡潔。nycu-life-events 有系統欄位名稱直接外露。 |
| 無障礙 | 6.5 | accupass 卡片上的次要灰字、Luma 的淺灰說明字對比偏低。nycu-life-events 的小字和小點擊目標在 mobile 不易點。 |
| 動畫與轉場 | 5 | 只看得到 Accupass 的輪播指示點，沒有骨架或展開收合的線索，給保守分數。 |

要保留的優點：
- accupass-home：活動卡以封面圖、日期、標題組成，視覺記憶點強。
- luma-taipei：依日期分組的時間軸列表，時間欄固定在左側，掃讀效率高。
- luma-discover：用城市、分類作為發現入口，留白和字級階層克制。
- accupass-search：搜尋結果搭配篩選條件，找特定活動很直接。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [全部頁面] [兩者] 截圖看不到任何載入、空資料、錯誤狀態 —— 無法確認失敗時使用者是否知道下一步 —— 補齊各狀態的設計和截圖。
2. [一致性] [nycu-life-events] [兩者] 校方系統和商業平台的完成度落差大，字級小、灰階、表單式 —— 學生在校方系統的體驗明顯較差 —— 至少統一卡片、日期與地點的呈現。
3. [資訊密度] [accupass-home] [mobile] 首屏被輪播和推廣區塊占滿，活動列表被推到下方 —— 手機使用者要先滑過廣告才看到內容 —— 縮小主視覺，或把活動列表提前。
4. [無障礙] [luma-discover／accupass-search] [兩者] 次要資訊用淺灰小字，對比不足 —— 戶外手機閱讀困難 —— 提高次要文字對比到 4.5:1。
5. [響應式] [nycu-life-events] [mobile] 版面是桌面縮小，欄位擠壓、點擊目標小 —— 主要使用者用手機 —— 改成單欄卡片並放大點擊範圍。

## 組 B
一句話總評：各狀態都有說明和下一步，手機版也是另外設計的（收合篩選、精簡頁尾、登入後頁首頭像）。成熟度高，剩下的問題集中在小字對比、少數截斷和個別頁面的對齊。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | event-signed-in desktop：分類標籤、大標題、日期副標，再接時間、地點、主辦、類型、報名、原始貼文的定義列表，主要行動「報名／活動頁」用實心藍色，其餘是外框按鈕。org-rich desktop：左欄「即將舉行（11）」和「過往活動」、右欄「收錄貼文（7 則）」，主次明確。 |
| 字體排印 | 7.5 | event-signed-in mobile：標題「校園急救實戰-從傷口照護到擬真演練！」在兩行內自然斷開，日期另成一行。source desktop：表格內標籤和日期約 11px，偏小。submit desktop：說明文字行長約 520px，閱讀舒適。 |
| 色彩 | 7.5 | 「竹梅」字標用藍紫漸層；學校標籤清大是紫、陽明交大是藍、交大／陽明校區是橘，語意色一致（source desktop）。source-light 和 account-signed-in-light 的淺色外觀都成立；source-error 錯誤橫幅用暗紅底。整體仍以黑底白字為主，品牌色用得少。 |
| 間距與版面 | 8 | account-signed-in desktop：兩欄卡片平衡，刪除帳號卡橫跨全寬。org-rich desktop：兩欄善用寬度。not-found desktop：內容從 x≈510 開始，其他頁從 x≈280 對齊，左緣不一致。event-signed-in desktop：海報下方左欄留下大片空白。 |
| 一致性 | 8 | 膠囊按鈕、虛線框空狀態卡（org-empty、source-followed-empty）、單位頁和名錄的「追蹤」按鈕用詞都一致。submit 的三個登入按鈕是黑底外框，account 的登入按鈕同樣是外框，兩頁一致。 |
| 資訊密度 | 8 | org-rich mobile：日期一行、標題一行，每則約 85px，一屏可看 9 則。source mobile：每列有名稱、學校標籤、平台、場數、更新時間和鈴鐺按鈕，密而不亂。 |
| 導覽 | 8 | desktop 左側欄有圖示加文字，目前頁粗體高亮（source desktop 的「資料來源」）。mobile 底部有五個分頁，頁首有搜尋；登入後頁首顯示「林」頭像（event-signed-in mobile、account-signed-in mobile）。單位頁底部有「← 回資料來源名錄」。 |
| 狀態與回饋 | 8.5 | source-error desktop／mobile：「名錄暫時載入不了」，附原因、「重新載入」和「詳細資訊」，並保留舊資料。org-empty：虛線卡說明「還沒有收錄到這個單位的活動」，附「回報活動」按鈕。source-followed-empty：「你還沒有追蹤任何單位」，附「瀏覽全部單位」。submit-signed-in：「待處理」和「你回報的」標記。 |
| 響應式 | 8.5 | source mobile：桌面表格改成卡片列，篩選收成「學校」一列、搜尋和「更多篩選」。手機頁尾精簡成行內連結（org-empty mobile）。source mobile 的更新日期被截成「2026/1…」，學校篩選列「交大…」在右緣被裁切，看不出可以橫向捲動。 |
| 文案 | 8 | 「看到活動，貼連結給竹梅」「連結是從竹梅點過來的？回報連結問題，我們會修正。」很自然。account-signed-in 的刪除說明是使用者語言，沒有內部術語。「資料來源與機構名錄」略顯行政。 |
| 無障礙 | 7 | 主要文字對比足夠，mobile 鈴鐺按鈕約 52px。source desktop 表格裡的 ID、日期、標籤字很小，灰字對比偏低。account-signed-in desktop 的「永久刪除我的帳號」是暗紅底配紅字，對比偏弱。追蹤按鈕的狀態有文字，不只靠顏色。 |
| 動畫與轉場 | 6 | home-loading、events-loading、calendar-loading 有和最終版面對應的骨架。home-search-open 有對話框遮罩。看不到其他轉場，給中等偏保守的分數。 |

要保留的優點：
- source-error：錯誤橫幅加「重新載入」，下面照樣列出稍早整理的名錄，失敗時仍可用。
- org-empty、source-followed-empty：虛線空狀態卡，各帶一個明確的下一步按鈕。
- source mobile：手機名錄改成卡片列，篩選收合成「更多篩選」，鈴鐺按鈕點擊範圍大。
- event-signed-in：定義列表式的活動資訊，加上一個實心主要按鈕、其餘外框按鈕的行動列。
- 登入後 mobile 頁首顯示頭像（event-signed-in、account-signed-in、submit-signed-in），一看就知道登入狀態。
- 手機頁尾精簡成兩行行內連結，不和底部導覽重複堆疊。

最重要的五個問題（由嚴重到輕微）：
1. [響應式] [source、source-light、source-error] [mobile] 單位卡右側的更新日期被截成「2026/1…」「2026/9…」 —— 日期截斷後就沒有資訊價值 —— 手機上改用相對時間或短格式（10/8），或把日期移到第二行。
2. [無障礙] [source、source-light] [desktop] 表格的 ID、標籤、更新日期約 11px，灰字對比偏低 —— 長表格掃讀吃力，低視力使用者看不清 —— 次要欄位至少 13px，灰階對比提高到 4.5:1。
3. [導覽] [source、source-followed-empty] [mobile] 學校篩選列在右緣直接裁掉「交大…」，沒有漸層或箭頭提示 —— 使用者不知道還有校區選項 —— 加邊緣漸隱或「更多」提示，或改成換行。
4. [間距與版面] [not-found] [desktop] 404 內容從 x≈510 開始，其他頁從 x≈280 開始；event-signed-in desktop 海報下方留大片空白 —— 頁與頁之間左緣跳動，降低整體感 —— 404 對齊主內容欄，活動頁讓左欄海報跟著捲動，或把相關活動放到左欄下方。
5. [無障礙] [account-signed-in] [desktop] 「永久刪除我的帳號」暗紅底配紅字，對比弱 —— 危險操作的按鈕本身要清楚可辨 —— 提高文字和底色的對比，維持危險色的語意。

## 組 C
一句話總評：骨架和 B 相同，但大量狀態沒有設計：錯誤時不顯示訊息、空狀態只有一行字、404 用原生表單，還有缺字方塊和全列底線。另外有內部術語外露，手機篩選也全部攤開，整體摩擦明顯。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6.5 | event-signed-in desktop：標題後接「｜2026 年 11 月 19 日」，標題和日期黏在同一個大字級裡。標題下先出現被截斷的描述（結尾是「報名資」），定義列表後又重複一次完整描述。event-signed-in mobile：海報放最前面，標題和時間地點被推到約 680px 以下。 |
| 字體排印 | 6.5 | org-rich desktop／mobile：每個日期和標題都加底線，一整頁都是線，難讀。org-rich desktop 的收錄貼文出現缺字方塊（「工作坊花絮來啦！！⊠⊠⊠」）。source-search mobile：標題「搜尋「吉他」」在引號中間斷行（「吉／他」」）。 |
| 色彩 | 7 | 學校語意色和 B 相同（source desktop）。source-light、account-signed-in-light 的淺色外觀可用。source-error 的篩選計數徽章變成空白深色方塊，看起來像壞掉。account-signed-in desktop 的刪除按鈕沒有危險色。 |
| 間距與版面 | 6 | account-signed-in desktop：單欄約 530px 寬置中，左右都留大片空白，字級偏小。submit desktop：卡片從 x≈490 開始，和其他頁 x≈280 不對齊。source desktop：連結欄把帳號拆成兩行，列高忽高忽低（#512 交大日本文化研究社占四行）。 |
| 一致性 | 5.5 | source desktop 的按鈕寫「追蹤」，source-error 和 org-empty 寫「追蹤主辦」。not-found 用瀏覽器原生的白色輸入框和灰色按鈕，和全站膠囊樣式完全不同。submit 把說明標籤「登入後回報連結」做成實心藍色按鈕。 |
| 資訊密度 | 6.5 | source mobile、source-light mobile：篩選全部攤開，占了 1000px 以上，第一筆單位要捲過一整屏才看到。event-signed-in mobile：描述重複兩次，平白拉長頁面。 |
| 導覽 | 7 | 側欄和底部導覽和 B 相同。event-signed-in mobile、account-signed-in mobile 登入後頁首沒有頭像，看不出已登入。手機頁尾是完整的兩欄網站地圖（org-empty mobile），和底部導覽功能重複。 |
| 狀態與回饋 | 4 | events-error：沒有錯誤訊息。status-error：只剩空骨架。source-error desktop／mobile：沒有任何錯誤提示，篩選計數變成空白方塊，「標籤」「平台」兩列沒有內容。org-empty：只有一行「尚未從這個來源收錄到活動。」，沒有下一步。source-followed-empty：「沒有符合的單位。」加一個沒有意義的「顯示更多單位」按鈕。 |
| 響應式 | 6.5 | 手機卡片列可用（source mobile）。篩選沒有收合。not-found mobile 的原生輸入框很小。submit-signed-in mobile 的 placeholder 被截成「https://www.insta」。 |
| 文案 | 6 | account-signed-in 的刪除說明外露「工作階段、優先權重分配、Apify 貢獻憑證」等內部術語。org-empty 的「尚未從這個來源收錄到活動」偏系統口吻。org-empty 的兩個按鈕都只寫「Facebook」，分不出是哪個帳號。 |
| 無障礙 | 5.5 | not-found desktop 的原生輸入框和按鈕約 20px 高，點擊範圍小。全列底線降低辨識度。org-rich 有缺字方塊。account-signed-in 的核取方塊是未加樣式的小方塊。 |
| 動畫與轉場 | 5 | events-loading、calendar-loading 有骨架。status-error 的骨架在失敗後沒有消失，可能讓人誤以為一直在載入。其他看不到線索，給保守分數。 |

要保留的優點：
- source mobile：名錄改成卡片列，鈴鐺按鈕大、好點。
- 學校語意色（清大紫、陽明交大藍、校區橘）在名錄、單位頁、活動頁一致。
- source desktop 連結欄直接顯示 IG 帳號（@nthu_jad），辨識度高。
- event-signed-in desktop：定義列表加一個實心主要按鈕的行動列。
- account-signed-in-light：淺色外觀的卡片、輸入框、連結色都成立。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [events-error、status-error、source-error] [兩者] 載入失敗時沒有任何錯誤訊息或重試按鈕；source-error 的篩選計數變成空白方塊，「標籤」「平台」列沒有內容 —— 使用者會以為網站壞了或資料就是這樣 —— 加錯誤橫幅、原因說明和「重新載入」，並保留舊資料。
2. [一致性] [not-found] [兩者] 404 用瀏覽器原生的白色輸入框和灰色按鈕，連結用「・」串在一起 —— 和全站設計語言斷裂，在深色底下特別刺眼 —— 改用全站的膠囊搜尋框和按鈕。
3. [資訊層級] [event-rich、event-signed-in] [兩者] 標題和日期以「｜」黏成一個大標題，描述被截斷後又完整重複一次；mobile 版海報放最前，資訊被推到一屏以下 —— 活動頁最重要的時間地點變得不明顯 —— 日期改成獨立副標，刪除重複描述，mobile 先放資訊再放海報。
4. [字體排印] [org-rich] [兩者] 每個日期和標題都加底線，收錄貼文出現缺字方塊 —— 整頁底線造成閱讀疲勞，缺字方塊讓內容看起來壞掉 —— 列表連結只在 hover／focus 時加底線，並處理 emoji 或缺字的字型後備。
5. [文案] [account-signed-in、account-signed-in-light] [兩者] 刪除帳號說明外露「工作階段、優先權重分配、Apify 貢獻憑證」，刪除按鈕也沒有危險色 —— 內部術語讓使用者不安，危險操作又不夠醒目 —— 改寫成使用者看得懂的資料項目，按鈕改用危險色。

```json
{"A": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 8, "間距與版面": 8, "一致性": 7.5, "資訊密度": 7, "導覽": 7.5, "狀態與回饋": 5, "響應式": 8, "文案": 7.5, "無障礙": 6.5, "動畫與轉場": 5}, "issues": ["[狀態與回饋] 全部頁面 兩者：截圖看不到載入、空資料、錯誤狀態，無法評估失敗時的下一步", "[一致性] nycu-life-events 兩者：校方系統和商業平台完成度落差大，小字、灰階、表單式", "[資訊密度] accupass-home mobile：首屏被輪播和推廣區塊占滿，活動列表被往下推", "[無障礙] luma-discover/accupass-search 兩者：次要資訊淺灰小字，對比不足", "[響應式] nycu-life-events mobile：桌面縮小版，欄位擠壓、點擊目標小"]}, "B": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 7.5, "間距與版面": 8, "一致性": 8, "資訊密度": 8, "導覽": 8, "狀態與回饋": 8.5, "響應式": 8.5, "文案": 8, "無障礙": 7, "動畫與轉場": 6}, "issues": ["[響應式] source/source-light/source-error mobile：單位卡更新日期被截成「2026/1…」", "[無障礙] source desktop：表格 ID、標籤、日期約 11px，灰字對比偏低", "[導覽] source mobile：學校篩選列右緣裁掉「交大…」，沒有可橫向捲動的提示", "[間距與版面] not-found desktop 內容左緣 x≈510，和其他頁 x≈280 不一致；event-signed-in desktop 海報下方大片空白", "[無障礙] account-signed-in desktop：「永久刪除我的帳號」暗紅底紅字，對比弱"]}, "C": {"scores": {"資訊層級": 6.5, "字體排印": 6.5, "色彩": 7, "間距與版面": 6, "一致性": 5.5, "資訊密度": 6.5, "導覽": 7, "狀態與回饋": 4, "響應式": 6.5, "文案": 6, "無障礙": 5.5, "動畫與轉場": 5}, "issues": ["[狀態與回饋] events-error/status-error/source-error 兩者：沒有錯誤訊息或重試，篩選計數變空白方塊、標籤與平台列沒有內容", "[一致性] not-found 兩者：原生白色輸入框和灰色按鈕，和全站樣式斷裂", "[資訊層級] event-rich/event-signed-in 兩者：標題與日期以「｜」黏在一起，描述截斷後又重複一次，mobile 海報在最前", "[字體排印] org-rich 兩者：所有日期與標題都加底線，收錄貼文出現缺字方塊", "[文案] account-signed-in 兩者：刪除說明外露「工作階段、優先權重分配、Apify 貢獻憑證」，刪除按鈕沒有危險色"]}}
```
