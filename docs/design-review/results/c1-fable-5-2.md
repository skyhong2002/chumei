# Round c1 blind review: fable-5-2

- Host: sky-mini
- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **C = baseline**, **B = new**, **A = reference**
- New set: `/Users/skyhong/cm-review/sets/new-c1`
- Mean of 12 scores: reference 6.96, new 7.29, baseline 6.21
- Note: Council round 1 (sky-mini). New = 0beec35 (m10 fixes). First Fable 5.2 attempt failed (gateway sent a 2.1.288 client header); rerun after the engines moved to a 2.1.325 default.

Raw reviewer output below, unedited.

---

## 評審結果（c1）

**先說明證據範圍：** 這一輪截圖共 186 張，超過單次工作階段能同時保留的影像量，工具把較早的影像移出，並拒絕我重開部分檔案。以下三類 B 組畫面我只在第一輪看過、沒留下可引用的細節，因此沒有拿來當證據：

- B 的活動列表全部狀態（`events*`）
- B 的首頁多數狀態（`home*`，只保留 `home-loading` 的觀察）
- B 的月曆與有資料的限動

B 在這些頁面上的分數是從其他頁面推得的，可信度較低；若這幾頁是本輪重點，建議另開一輪只送這些檔案。其餘引用的畫面都是我實際看過並記錄的。

## 組 A
一句話總評：三個成熟的活動產品（Accupass、Luma、NYCU EVENTS），以圖像與時間軸帶動瀏覽、完成度高，但只有淺色有資料的畫面，且 Accupass 有遮擋與跨頁不一致。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | `luma-taipei` desktop／mobile：依日期分組的時間軸，每張卡依序是時間、標題、主辦、地點、狀態標籤。`accupass-home` desktop：首屏被 400px 高的廣告輪播佔滿。 |
| 字體排印 | 7.5 | `luma-discover` desktop：標題、副標、灰色說明三級清楚。`accupass-search` desktop：日期是很小的淺灰字「2026.11.17 (Tue)」，mobile 卻是「(二)」，中英不一致。 |
| 色彩 | 7.5 | `luma-taipei`：「即將額滿」橘、「已售罄」紅、「候補名單」藍，語意明確。`nycu-life-events`：類型藍標籤一致。三者都只有淺色畫面，深色無從評。 |
| 間距與版面 | 7.5 | `nycu-life-events` desktop：右側「近期活動」面板約 550px 高，只有一行連結，其餘全空。`luma-discover` desktop：內容欄約 670px，1440 寬下兩側大片留白。 |
| 一致性 | 6.5 | `accupass-home` 是藍色頁首加地區、漢堡選單；`accupass-search` 換成白底、只有「主辦榜／登入｜註冊」，像兩個網站。Luma 兩頁一致。 |
| 資訊密度 | 7.5 | `accupass-search` desktop：三欄卡片，一屏約 6 張。`luma-taipei` desktop：一屏 3–4 場並附地圖與訂閱。 |
| 導覽 | 7 | `nycu-life-events` desktop：分頁「所有活動／依活動性質／依校區／依處室／已結束活動」清楚，mobile 斷成兩行，「已結束活動」孤立一行。`accupass-search`：沒有返回首頁以外的主導覽。 |
| 狀態與回饋 | 5 | 沒有載入、空、錯誤的截圖。可見線索只有 `nycu-life-events` 的「登入後可釘選活動分類。」與 Luma 的額滿／候補標籤，因此給保守分。 |
| 響應式 | 7.5 | `luma-taipei` mobile：主視覺改直幅、地圖收成按鈕，重新編排而非縮放。`accupass-home` mobile：橫向捲動列卡片被切、cookie 橫幅蓋住底部約 130px。 |
| 文案 | 7 | `luma-discover`：中文介面夾整段英文社群簡介。`accupass-home`：「每天一點新鮮事」區塊標題出現兩次。 |
| 無障礙 | 6.5 | `nycu-life-events`：輪播有「暫停輪播」與上下張按鈕（加分）。`accupass-search`：日期、標籤、瀏覽數都是淺灰小字。`luma-taipei` desktop：頁首時間文字疊在亮色雲上，幾乎看不清。 |
| 動畫與轉場 | 6 | 靜態線索只有輪播指示（`nycu-life-events` 的「2 / 5」、`accupass-home` 的圓點與箭頭）。沒有骨架或展開狀態，給保守分。 |

要保留的優點：
- `luma-taipei` 的時間軸：日期節點加卡片，時間最先、狀態標籤有色有字。
- `luma-taipei` desktop 右欄：訂閱加小地圖，善用寬螢幕。
- `nycu-life-events` 的輪播控制：「暫停輪播」與頁碼。
- `luma-discover` 的「按類別瀏覽」：彩色圖示加場數，一眼可掃。
- `accupass-search` 卡片：圖、日期、標題、地點、標籤的順序固定。

最重要的五個問題（由嚴重到輕微）：
1. [間距與版面] `accupass-home` 兩者：cookie 說明與左下浮動促銷橫幅蓋在內容上，desktop 遮住最後一列卡片 —— 首訪就擋住主要內容 —— 改成不遮內容的底欄，促銷移入版面。
2. [一致性] `accupass-home` 對 `accupass-search` 兩者：頁首、導覽、標誌位置完全不同 —— 使用者會以為離站 —— 共用同一套頁首。
3. [間距與版面] `nycu-life-events` desktop：右側「已釘選／近期活動」登入前幾乎全空卻佔三分之一寬 —— 首屏浪費 —— 未登入時收合或改放熱門活動。
4. [無障礙] `accupass-search`、`accupass-home` 兩者：日期與標籤用淺灰小字，desktop 星期用英文 —— 日期是最重要的資訊卻最難讀 —— 加深、放大並統一中文。
5. [導覽] `nycu-life-events` mobile：分頁列換行，封面圖被裁掉文字（「HEALTH, BEGIN!」只剩一半） —— 小螢幕顯得粗糙 —— 分頁改橫向捲動，封面改完整顯示。

## 組 B
一句話總評：竹梅較成熟的一版：關鍵資訊先出現、空狀態與錯誤都有說明和下一步、登入按鈕與名錄列整齊，但寬螢幕利用與狀態頁的術語仍是明顯弱點。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 7.5 | `event-rich` desktop：H1 只放標題，下一行是「2026 年 11 月 19 日」，接著時間／地點／主辦表格。`event-sparse` mobile：標題與表格在海報之前。但六顆同權重的膠囊按鈕排成兩行。 |
| 字體排印 | 7.5 | `source-search` mobile：副標「搜尋「吉他」」獨立一行，日期縮成「9/25」，跨年才寫「2025/5/19」。`event-rich` desktop：時間寫成「2026/11/19（四）18:00 – 2026/11/19（四）21:00」，同日重複。 |
| 色彩 | 7.5 | `source` desktop：清大紫、陽明交大藍、交大琥珀的校別標籤成系統。`status-error` desktop：暗紅錯誤橫幅。`event-sparse` mobile：琥珀色「資料待確認」。主色只用在選取與主要動作。 |
| 間距與版面 | 7 | `account-signed-in` desktop：兩欄卡片對齊、底部滿寬的刪除卡。`subscribe` desktop：內容欄約 630px 靠左，右側約 40% 空白。`org-empty` desktop：空狀態卡 520px，右邊全空。 |
| 一致性 | 7.5 | `account` desktop 與 `submit` mobile：三顆登入按鈕同為外框膠囊、文案平行。`not-found` mobile：搜尋欄與按鈕都是站內樣式。`notify` mobile 仍用瀏覽器原生的「▶」展開標記。 |
| 資訊密度 | 7.5 | `source` desktop：每個單位一行，2700px 內約 33 列。`status` desktop：數字卡、額度、帳號池、表格全擠在一頁，過密。 |
| 導覽 | 7.5 | 桌面左側欄、手機底部五個分頁，`stories-empty` mobile 的「限動」有高亮。`source-search` mobile：篩選收成「學校」一列加「更多篩選」，結果在第一屏就出現；但學校列被右緣切掉（「交大…」）且無捲動提示。 |
| 狀態與回饋 | 8 | `org-empty`、`stories-empty`、`source-followed-empty`：虛線卡片加標題、原因、按鈕（「回報活動」「看即將舉行的活動」「瀏覽全部單位」）。`status-error` desktop：說明「活動與貼文頁面不受影響」並有「重新載入」。 |
| 響應式 | 7.5 | `source-search` mobile：桌面表格改成兩行列加 44px 鈴鐺按鈕，頁尾改成精簡的行內連結。`event-sparse` mobile：表格分隔線只到約 80% 寬，與下方滿寬區塊不齊。 |
| 文案 | 7 | `account-signed-in` desktop 刪除說明是白話（「刪除後無法復原。你的登入方式、追蹤的單位、「我會去」…」）。`status` desktop 仍滿是「Apify、Actor、pipeline、RSSHub、PRIMARY／GDGNTNU」。`source-followed-empty` mobile 留著「符合 0 個單位，已顯示 0 個」。 |
| 無障礙 | 7 | `org-empty` desktop：兩顆臉書按鈕各自標成「Facebook nthucookingclub」「Facebook 清大烹飪社」，可分辨。`source-search` mobile：鈴鐺按鈕夠大但沒有文字。`status` desktop：大量 11–12px 灰字。 |
| 動畫與轉場 | 6 | 線索有限：`home-loading` 有「正在載入最新貼文…」膠囊（會把欄位往下推），`notify` 有可展開區塊。看不到骨架或轉場，給保守分。 |

要保留的優點：
- 虛線空狀態卡的固定結構（標題、原因、一顆按鈕），用在 `org-empty`、`stories-empty`、`source-followed-empty`。
- `status-error` 的錯誤橫幅：講明影響範圍、給重試、把壞掉的表格收起來。
- `source` 名錄單行列與短日期，`source-search` mobile 的收合篩選。
- `event-rich` 的順序：標題、日期、事實表、動作、說明，內文連結可點。
- `account-signed-in` desktop 的兩欄卡片，主要動作藍色、刪除紅色。
- `not-found` 的搜尋欄、兩顆按鈕與「回報連結問題」。

最重要的五個問題（由嚴重到輕微）：
1. [文案] `status` 兩者：整頁是維運儀表板用語（Apify 額度美元數、帳號池代號、Actor、pipeline） —— 學生只想知道某社團有沒有在更新 —— 預設只給白話摘要與來源表，額度與帳號池收進「進階」。
2. [間距與版面] `subscribe`、`org-empty` desktop：內容只佔約 520–630px 靠左，右側大片空白 —— 1440 寬顯得沒排完 —— 訂閱頁改兩欄，空狀態卡撐滿內容欄。
3. [字體排印] `status` desktop 表格第一列：狀態膠囊「帳號無法取得」看起來壓到右欄「嘗試 2026/11/10」的第一個字 —— 文字重疊（請對 1:1 原圖確認） —— 加寬狀態欄或讓膠囊換行。
4. [文案] `event-sparse` mobile、`event-rich` desktop：「沒有可用定位；有場地者需核對地址或補入場館表」是維護者語言；同日時間重複寫日期；說明結尾殘留「主辦」二字 —— 活動頁是最常被分享的頁面 —— 改寫提示、同日只寫一次日期、清掉摘要尾字。
5. [資訊層級] `event-rich` desktop、`org-rich` mobile：六顆等重按鈕且「追蹤主辦」獨落第二行；「即將舉行（11）」第一筆是 2026/10/27，早於同頁其他日期，列內也沒有地點 —— 主要動作不明、時間感混亂 —— 留一顆主按鈕，其餘降階；長期展覽標「進行中至…」並補地點。

## 組 C
一句話總評：竹梅較粗糙的一版：骨架與配色相同，但標題塞進排序與日期、手機篩選牆把結果擠出首屏、空與錯誤狀態只有一行字，還有未套樣式的原生表單與標錯字的登入按鈕。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6.5 | `events` 兩者：H1 是「活動總覽｜排序：時間優先」。`event-rich` desktop：H1 接「｜2026 年 11 月 19 日」斷成兩行，下面的摘要在「報名資」被截斷，全文又在下方重複。`event-sparse` mobile：海報排在標題之前。 |
| 字體排印 | 6.5 | `events` mobile：「需報名」「免費」被擠成兩行直排的膠囊，日期與時間拆成兩行。`org-rich` mobile：日期與標題全部加底線。`stories-empty` mobile：空狀態句子斷成兩行且第二行縮排。 |
| 色彩 | 7 | 與 B 同一套深色加藍紫。`account-signed-in-light` 兩者：淺色成立。`account` desktop：兩顆藍色主按鈕加一顆外框，主色失去「唯一主要動作」的意義。 |
| 間距與版面 | 6 | `source` desktop：帳號代號讓列高 1–4 行不等。`subscribe`、`account` desktop：內容置中，其他頁靠左。`event-rich` desktop：海報下方左欄整段空白。 |
| 一致性 | 6 | `not-found` mobile：白底的瀏覽器原生輸入框與灰按鈕，和全站深色膠囊元件不合。`submit` mobile 三顆登入按鈕樣式與文案各不相同。 |
| 資訊密度 | 6.5 | `source-search` mobile：五組篩選約 25 顆標籤全展開，三筆結果要捲過一整屏才出現。`events` desktop：四欄卡片資訊完整，但卡片下半常有空白。 |
| 導覽 | 7 | 左側欄與底部分頁同 B。`calendar` mobile：「‹ 載入上個月／回到今天」加逐日議程，清楚。名錄與活動頁的篩選在手機上過重。 |
| 狀態與回饋 | 5 | `status-error` desktop：「資料快照：載入中…」卡住、空框、「讀取排程設定中…」、一行小灰字「狀態資料讀取失敗」，沒有重試。`home-empty`：只有「沒有符合的貼文。」。`source-followed-empty` mobile：0 筆卻還有「顯示更多單位」。`home-loading`：看不到載入提示。 |
| 響應式 | 6.5 | `home` mobile：限動列、三顆篩選、單欄貼文，合理。`events` mobile 標籤擠壓；`not-found`、`stories-empty` mobile 頁尾展開成四組連結，比主內容還長。`home` desktop：第三欄「陽明」被右緣切掉。 |
| 文案 | 6 | `submit` mobile：第一顆登入按鈕寫「登入後回報連結」，看不出是哪種登入。`status-error` desktop 前言滿是「quota、Apify、公開端點冷卻」。`account-signed-in-light` 刪除說明有「工作階段、優先權重分配、Apify 貢獻憑證」。 |
| 無障礙 | 6.5 | `home` 兩者：貼文下方三個圖示按鈕沒有文字。`org-empty` desktop：兩顆按鈕都只寫「Facebook」，無法分辨。`status` desktop 小灰字多。列表底線有助辨識連結（加分）。 |
| 動畫與轉場 | 5 | `home-loading` 無提示，`status-error` 的載入文字不會結束，可見線索偏負面。只有原生展開標記，給保守分。 |

要保留的優點：
- `calendar` mobile 的逐日議程：時間、標題、地點，左緣校別色條，右側「我會去」。
- `events` desktop 卡片：日期角標、校別／類型／報名／費用標籤、兩顆動作。
- `home` 的限動列與來源標示（單位 › 校別、相對時間、「新收錄」、平台圖示）。
- 左側欄與手機底部分頁的導覽骨架。
- `account-signed-in-light`：淺色外觀完整可用。

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] `status-error` desktop：失敗後停在「載入中…」，空框與空表頭仍在，沒有重試 —— 使用者分不清是壞了還是在等 —— 改成明確的錯誤橫幅加重試，收起空表格。
2. [文案] `submit` mobile、`account` desktop：登入按鈕標成「登入後回報連結」，三顆按鈕兩藍一框 —— 不知道會用哪個帳號登入 —— 三顆同樣式，文案統一為「用○○帳號登入」。
3. [響應式] `source-search`、`source-followed-empty`、`events` mobile：篩選全展開佔滿首屏，活動列的標籤被擠成兩行直排 —— 手機是主要裝置，結果與標籤都看不好 —— 篩選預設收合，標籤不換行或移到標題下方。
4. [資訊層級] `events`、`event-rich`、`source-search` 兩者：H1 接上排序、日期、搜尋條件；活動頁摘要截斷後又重複全文 —— 標題變長、斷行、重點模糊 —— 條件改放副標，摘要與全文擇一。
5. [狀態與回饋] `home-empty`、`org-empty`、`stories-empty`、`not-found` 兩者：空狀態只有一行字、沒有下一步，404 用未套樣式的原生輸入框 —— 像沒做完 —— 套用統一的空狀態卡與站內表單樣式。

```json
{"A": {"scores": {"資訊層級": 8, "字體排印": 7.5, "色彩": 7.5, "間距與版面": 7.5, "一致性": 6.5, "資訊密度": 7.5, "導覽": 7, "狀態與回饋": 5, "響應式": 7.5, "文案": 7, "無障礙": 6.5, "動畫與轉場": 6}, "issues": ["[間距與版面] accupass-home 兩者：cookie 說明與浮動促銷橫幅遮住內容", "[一致性] accupass-home 對 accupass-search：頁首與導覽完全不同，像兩個網站", "[間距與版面] nycu-life-events desktop：右側「已釘選／近期活動」登入前幾乎全空卻佔三分之一寬", "[無障礙] accupass-search／home：日期與標籤是淺灰小字，desktop 星期用英文", "[導覽] nycu-life-events mobile：分頁列換行、封面圖裁掉文字"]}, "B": {"scores": {"資訊層級": 7.5, "字體排印": 7.5, "色彩": 7.5, "間距與版面": 7, "一致性": 7.5, "資訊密度": 7.5, "導覽": 7.5, "狀態與回饋": 8, "響應式": 7.5, "文案": 7, "無障礙": 7, "動畫與轉場": 6}, "issues": ["[文案] status 兩者：整頁是維運儀表板用語（Apify 額度、帳號池代號、Actor、pipeline）", "[間距與版面] subscribe／org-empty desktop：內容只佔 520–630px 靠左，右側大片空白", "[字體排印] status desktop 表格第一列：狀態膠囊疑似壓到右欄文字（需對 1:1 原圖確認）", "[文案] event-sparse mobile／event-rich desktop：待確認提示是維護者語言、同日時間重複日期、說明結尾殘留「主辦」", "[資訊層級] event-rich desktop／org-rich mobile：六顆等重按鈕；「即將舉行」第一筆日期早於其他且列內無地點"]}, "C": {"scores": {"資訊層級": 6.5, "字體排印": 6.5, "色彩": 7, "間距與版面": 6, "一致性": 6, "資訊密度": 6.5, "導覽": 7, "狀態與回饋": 5, "響應式": 6.5, "文案": 6, "無障礙": 6.5, "動畫與轉場": 5}, "issues": ["[狀態與回饋] status-error desktop：失敗後停在「載入中…」、空表頭仍在、沒有重試", "[文案] submit mobile／account desktop：登入按鈕標成「登入後回報連結」，三顆按鈕樣式不一", "[響應式] source-search／source-followed-empty／events mobile：篩選全展開佔滿首屏，標籤被擠成兩行直排", "[資訊層級] events／event-rich／source-search：H1 接上排序、日期、搜尋條件；活動頁摘要截斷又重複", "[狀態與回饋] home-empty／org-empty／stories-empty／not-found：空狀態只有一行字，404 用未套樣式的原生輸入框"]}}
```
