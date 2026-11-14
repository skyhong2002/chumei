# Round 4 blind review: opus-5-5

- Brief: `brief.md`, SHA-256 `e03dd013d96bdf99d0834f7accb89cb0dea2d8f0121c1e8e8d0531ec9e8cf90a`
- Mapping (revealed after the review): **B = baseline**, **C = new**, **A = reference**
- New set: `/tmp/cm-review/sets/new-r4`
- Mean of 12 scores: reference 6.75, baseline 6.29, new 7.38

Raw reviewer output below, unedited.

---

## 組 A
一句話總評：這組是參考網站（Accupass、Luma、陽明交大生活活動系統），品牌與商業活動平台的成熟度高，但三個產品水準落差大，校方系統明顯過時；這組沒有給錯誤、空資料等狀態，這幾項無法驗證。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 7.5 | accupass-home desktop：首屏大橫幅加分類入口，網站用途一看就懂；luma-discover／luma-taipei desktop：城市與活動卡片清楚，標題和時間排在最前面；nycu-life-events desktop：列表欄位多，標題與日期的主次比較弱。 |
| 字體排印 | 7 | luma 兩頁 desktop：英文字級與行高細緻；accupass-search mobile：卡片標題多行截斷，中文字級偏小；nycu-life-events mobile：內文偏小，行距緊。 |
| 色彩 | 7.5 | Accupass 有鮮明的品牌色，Luma 以留白配強調色；nycu-life-events 接近預設樣式，沒有語意色。三者都只看得到淺色外觀，無法評深色。 |
| 間距與版面 | 7.5 | luma-discover desktop：格線一致、留白節奏好；accupass-home desktop：區塊之間間距一致；nycu-life-events desktop：版面窄，桌面寬度沒有用到。 |
| 一致性 | 6.5 | 單一產品內部大致一致（Luma 的卡片和按鈕同一套），但 nycu-life-events 的表單元件與另兩站相比明顯是另一個年代。 |
| 資訊密度 | 7 | accupass-search desktop：一屏能看到多張帶圖卡片；luma-taipei mobile：每張卡片較高，一屏只放得下 3–4 則。 |
| 導覽 | 7 | accupass-search：搜尋與篩選在頂部；luma mobile：頂部導覽簡潔；nycu-life-events mobile：手機沒有底部導覽，切換頁面要回到頂部。 |
| 狀態與回饋 | 5 | 五張截圖都是有資料的狀態，看不到載入、空資料或錯誤，只能保守給分。 |
| 響應式 | 7.5 | accupass-home mobile 與 luma-discover mobile 都改成單欄卡片，不是單純縮放；nycu-life-events mobile 的表格內容擠壓。 |
| 文案 | 7 | Accupass 的行銷用語自然；nycu-life-events 有系統欄位名稱直接外露（例如報名狀態欄）。 |
| 無障礙 | 6.5 | Luma 有部分淺灰小字，對比偏低；Accupass 的圖卡標籤依賴顏色；nycu-life-events 的連結點擊範圍小。 |
| 動畫與轉場 | 5 | 靜態截圖只看得到 Accupass 的輪播圓點，沒有其他線索，給保守分數。 |

要保留的優點：
- Luma 城市頁的大留白卡片格線，加上清楚的時間標記
- Accupass 首屏用分類入口快速分流
- Accupass 搜尋頁把篩選條和結果放在同一屏
- 兩個商業站在手機上都改成單欄卡片，而不是直接縮小桌面版

最重要的五個問題（由嚴重到輕微）：
1. [響應式] [nycu-life-events] [mobile] 列表和表格欄位在手機上擠壓、字太小 —— 學生多用手機看 —— 手機上改成卡片列表
2. [一致性] [nycu-life-events] [兩者] 視覺語言過時，接近預設樣式 —— 降低信任感與可讀性 —— 建立元件與字級規範
3. [資訊密度] [luma-taipei] [mobile] 卡片過高，一屏只看得到少數活動 —— 不利快速瀏覽 —— 提供精簡列表模式
4. [無障礙] [luma-discover] [desktop] 淺灰輔助文字對比偏低 —— 小字不易閱讀 —— 提高次要文字對比
5. [文案] [accupass-search] [mobile] 卡片標題截斷，關鍵資訊被切掉 —— 使用者看不到完整名稱 —— 改成兩行截斷並保留日期與地點

## 組 B
一句話總評：竹梅的完整功能都在，深色品牌也成立，但多個錯誤和空狀態只有一行字或完全沒有說明，帳號、回報等頁面在桌面上沒有用到寬度，404 還露出瀏覽器原生的輸入框。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 6.5 | event-signed-in desktop：標題寫成「校園急救實戰-從傷口照護到擬真演練！｜2026 年 11 月 19 日」，把日期塞進 H1；標題下的摘要截在「報名資」，下方又把同一段描述完整重複一次。event-signed-in mobile：首屏全是海報，標題和時間要往下捲才看得到。 |
| 字體排印 | 7 | org-rich desktop：日期用小字加底線，和標題的字級差太大；event-rich mobile：內文 17px 左右、行高舒適；org-rich desktop：收錄貼文出現「▯▯▯」缺字。 |
| 色彩 | 6.5 | 竹梅的漸層字標、清大紫、陽明交大藍、交大黃三種學校語意色成立（source desktop）；source-light 淺色外觀可用。但 account-signed-in desktop 的「永久刪除我的帳號」是普通外框按鈕，沒有危險色。 |
| 間距與版面 | 6 | account-signed-in desktop：內容是約 530px 的窄欄，右側大片空白；submit desktop：表單卡片置中，沒有用到寬度；org-rich desktop：列表只佔約 540px 的窄欄。 |
| 一致性 | 6 | source-error desktop 的按鈕是「追蹤主辦」，同頁其他狀態是「追蹤」；not-found desktop 的搜尋框和按鈕是瀏覽器原生樣式，和其他頁的圓角輸入框不同；submit-signed-in 的「送出」是外框按鈕，account 的主按鈕卻是實心藍。 |
| 資訊密度 | 7 | source desktop：表格一屏可見約 30 個單位，密度好；但 source mobile 的篩選標籤佔滿近一屏，要捲很遠才看得到名錄。 |
| 導覽 | 7 | 桌面左側欄位齊全；手機底部有 5 個入口（最新、活動、日曆、限動、更多）；org 頁有「← 回資料來源名錄」；source mobile 的排序做成 pill 列，好用。 |
| 狀態與回饋 | 5 | events-error：沒有任何錯誤提示；source-error desktop／mobile：篩選標籤只剩空白的數字槽，「標籤」「平台」整排空白，沒有錯誤說明，也沒有重試；org-empty：只有「尚未從這個來源收錄到活動。」一行；source-followed-empty：只有「沒有符合的單位。」，下面還留著「顯示更多單位」按鈕；stories-empty：只有一行窄字。 |
| 響應式 | 6.5 | 手機都改成單欄、有底部導覽，但 source mobile 的篩選沒有收合，佔掉約 900px 高；source-followed-empty mobile 的標題「資料來源與機構名錄｜單位：已追蹤單位」斷成兩行。 |
| 文案 | 7 | 整體用詞自然；account-signed-in 的刪除說明出現「Apify 貢獻憑證」，是內部術語外露；org-empty 有兩個都叫「Facebook」的按鈕，分不出差別。 |
| 無障礙 | 6 | account-signed-in desktop 的核取方塊是約 10px 的原生樣式；org-rich desktop 的日期連結字小、灰；source desktop 的追蹤按鈕上的數字徽章很小。 |
| 動畫與轉場 | 5 | 只有 *-loading 與 home-search-open 這類間接線索；source-error 的空白數字槽看起來像載入卡住，沒有視覺說明。 |

要保留的優點：
- 單位名錄的表格欄位齊全（ID、名稱、標籤、連結、更新、收錄、追蹤），可以排序，學校語意色清楚
- 活動頁的「時間／地點／主辦／類型／報名／原始貼文」定義列表，每一列都連回原始來源
- 手機底部 5 個入口的導覽，加上單位頁的「← 回資料來源名錄」
- 漸層「竹梅」字標，加上深色外觀的品牌識別
- 回報頁公開處理狀態（待處理、你回報的）

最重要的五個問題（由嚴重到輕微）：
1. [狀態與回饋] [source-error、events-error] [兩者] 載入失敗時沒有錯誤說明，也沒有重新載入，篩選標籤變成空白槽 —— 使用者會以為網站壞了或資料是 0 —— 加上錯誤橫幅、重新載入按鈕，並說明下方是舊資料
2. [狀態與回饋] [org-empty、source-followed-empty、stories-empty] [兩者] 空狀態只有一行字，沒有下一步；已追蹤為空時還顯示「顯示更多單位」 —— 使用者不知道能做什麼 —— 加上說明和行動按鈕（例如回報活動、瀏覽全部單位）
3. [一致性] [not-found] [兩者] 404 的搜尋框和按鈕是瀏覽器原生樣式 —— 看起來像壞掉的頁面 —— 改用全站的輸入框與按鈕元件
4. [間距與版面] [account-signed-in、submit、org-rich] [desktop] 窄欄置中，1440 寬的畫面大半留白 —— 帳號頁要捲很長 —— 改成雙欄，或把側欄資訊並排
5. [資訊層級] [event-signed-in] [兩者] H1 塞進日期，摘要截斷後又重複一次，手機首屏只有海報 —— 時間地點太晚才看到 —— 把日期改成副標題、移除重複摘要，手機先放標題和資訊

## 組 C
一句話總評：同一套竹梅介面，錯誤、空狀態、404 和帳號頁都補上了說明、下一步與雙欄版面，完成度明顯較高；剩下的問題是名錄連結截斷、手機上連結疊行，以及貼文缺字。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 7.5 | event-signed-in desktop：H1 只放標題，「2026 年 11 月 19 日」改成副標題，資訊列表緊接在後，沒有重複摘要；event-signed-in mobile：標題、資訊和操作按鈕放在海報之前；source-search 的「搜尋「吉他」」改成獨立副標。 |
| 字體排印 | 7.5 | 標題、副標、內文分層清楚（source-followed-empty 的主標題加副標）；org-rich desktop 的收錄貼文仍出現「▯▯▯」缺字；org-rich desktop 的日期字級依然偏小。 |
| 色彩 | 7 | 學校語意色一致；source-error 用深紅錯誤橫幅；account-signed-in-light 的「永久刪除我的帳號」是紅底紅字，有危險色；淺色外觀（source-light、account-signed-in-light）成立。品牌色以外的強調色仍偏少。 |
| 間距與版面 | 7.5 | account-signed-in desktop：雙欄卡片，用到了寬度；submit desktop：說明與「最近的回報」並排；org-rich desktop：活動列表加右側收錄貼文的雙欄。account-signed-in desktop 右欄底部有留白，左右欄高度不平衡。 |
| 一致性 | 7.5 | 追蹤按鈕統一叫「追蹤」；空狀態都用虛線外框卡片加按鈕（org-empty、source-followed-empty）；404 改用全站的膠囊輸入框與按鈕。submit 未登入時，三個登入按鈕都是深色外框，和 account 頁的樣式一致。 |
| 資訊密度 | 7.5 | source desktop：連結欄壓成「IG FB Threads」，每列等高，一屏約 40 列；source mobile：篩選收合成「更多篩選」，名錄在首屏就出現。 |
| 導覽 | 7.5 | 手機底部導覽與桌面左側欄同上一組；source mobile 的學校篩選改成橫向捲動，右側露出一半「交大」暗示還有更多；空狀態按鈕提供明確的去向。 |
| 狀態與回饋 | 8 | source-error：「名錄暫時載入不了」加錯誤代碼 500，說明下方是稍早整理的資料，附「重新載入」；org-empty：說明竹梅會持續整理，附「回報活動」；source-followed-empty：「你還沒有追蹤任何單位」加「瀏覽全部單位」；not-found：搜尋、回首頁、瀏覽活動、回報連結問題。stories-empty 仍只有一行窄字。 |
| 響應式 | 7.5 | 手機的篩選收合、雙欄改單欄都合理；但 source-search mobile 的「清大吉他社」連結疊成 3 行，日期垂直置中造成對齊鬆散；source mobile 的部分列也因 Threads 帳號換行而變高。 |
| 文案 | 8 | 空狀態與錯誤文案具體、有語氣（例如「連結是從竹梅點過來的？回報連結問題，我們會修正。」）；account 刪除說明改成「貢獻的抓取額度」，拿掉了 Apify；org-empty 的 Facebook 按鈕附上帳號名稱，可以分辨。 |
| 無障礙 | 7 | account-signed-in 的核取方塊放大到約 20px；source desktop 的連結截斷成「IG @nth…」「I·」「F」，螢幕閱讀器和肉眼都難以辨識；追蹤按鈕上的數字徽章仍然很小。 |
| 動畫與轉場 | 6 | 錯誤橫幅、虛線空狀態卡片、「更多篩選」收合按鈕，都是可見的狀態切換線索，但靜態截圖看不到實際轉場，給保守分數。 |

要保留的優點：
- source-error 的錯誤橫幅：原因加錯誤代碼，說明還能用的舊資料，附重新載入
- 虛線外框空狀態卡片加行動按鈕（org-empty、source-followed-empty）
- 帳號設定與回報頁的桌面雙欄版面，刪除按鈕用危險色
- 手機名錄的「更多篩選」收合加上橫向捲動的學校篩選，名錄在首屏就出現
- 活動頁標題與日期分層，手機先給資訊與操作，再放海報
- 404 提供搜尋、回首頁、瀏覽活動、回報問題四種出路

最重要的五個問題（由嚴重到輕微）：
1. [無障礙] [source、source-error、source-search] [desktop] 連結欄截斷成「IG @nth… IG @nt… F」「I· FB nctu… FB nctu…」 —— 平台與帳號無法辨識，看起來像壞掉 —— 多帳號時改成平台圖示加數量，或把完整帳號放進 tooltip／展開
2. [字體排印] [org-rich] [desktop] 收錄貼文標題出現「▯▯▯」缺字（emoji 沒有字型） —— 看起來像亂碼 —— 加上 emoji 字型後備，或過濾掉無法顯示的字元
3. [響應式] [source-search、source] [mobile] 多個連結逐行疊放，列高暴增、日期對齊鬆散 —— 名錄掃讀節奏被打斷 —— 手機上連結改成單行內聯，多出的收進「+2」
4. [狀態與回饋] [stories-empty] [兩者] 沒有限動時只有一行窄字，沒有下一步 —— 和其他頁空狀態的品質不一致 —— 套用虛線空狀態卡片，引導去活動頁或追蹤單位
5. [間距與版面] [account-signed-in] [desktop] 左右欄高度不平衡，右欄下方大片留白 —— 版面重心偏左 —— 依內容高度重新分配卡片，或改用瀑布流排列

```json
{"A": {"scores": {"資訊層級": 7.5, "字體排印": 7, "色彩": 7.5, "間距與版面": 7.5, "一致性": 6.5, "資訊密度": 7, "導覽": 7, "狀態與回饋": 5, "響應式": 7.5, "文案": 7, "無障礙": 6.5, "動畫與轉場": 5}, "issues": ["nycu-life-events mobile 列表／表格欄位擠壓、字太小", "nycu-life-events 視覺語言過時、接近預設樣式", "luma-taipei mobile 卡片過高，一屏只有少數活動", "luma-discover 淺灰輔助文字對比偏低", "accupass-search mobile 卡片標題截斷"]}, "B": {"scores": {"資訊層級": 6.5, "字體排印": 7, "色彩": 6.5, "間距與版面": 6, "一致性": 6, "資訊密度": 7, "導覽": 7, "狀態與回饋": 5, "響應式": 6.5, "文案": 7, "無障礙": 6, "動畫與轉場": 5}, "issues": ["source-error／events-error 無錯誤說明與重試，篩選標籤變空白槽", "org-empty／source-followed-empty／stories-empty 空狀態只有一行字、無下一步", "not-found 使用瀏覽器原生輸入框與按鈕", "account-signed-in／submit／org-rich 桌面窄欄、大片留白", "event-signed-in H1 塞日期、摘要截斷且重複，手機首屏只有海報"]}, "C": {"scores": {"資訊層級": 7.5, "字體排印": 7.5, "色彩": 7, "間距與版面": 7.5, "一致性": 7.5, "資訊密度": 7.5, "導覽": 7.5, "狀態與回饋": 8, "響應式": 7.5, "文案": 8, "無障礙": 7, "動畫與轉場": 6}, "issues": ["source 桌面連結欄截斷成「IG @nth… I· F」難以辨識", "org-rich 收錄貼文出現 ▯▯▯ 缺字", "source-search／source mobile 連結逐行疊放使列高暴增", "stories-empty 空狀態仍只有一行字", "account-signed-in 桌面左右欄高度不平衡"]}}
```
