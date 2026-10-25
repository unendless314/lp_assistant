# 計算規格

> 狀態：初稿（2026-10-26）。
> 需求以 [`prd.md`](../prd.md) 為準；本文件補上 PRD 刻意不寫的公式、門檻與判定細節。PRD 已寫明的行為只引用編號，不重抄。

## 0. 範圍與邊界

**本文件管**：拿到輸入資料之後，怎麼算出每個數字、怎麼判定池子狀態、怎麼排序。全部是純函式：同樣的輸入必得同樣的輸出，不碰網路、資料庫與系統時鐘（「現在時間」由呼叫端傳入）。

**本文件不管**：輸入怎麼取得、怎麼存（見 [`sources.md`](sources.md)、[`data-model.md`](data-model.md)）；數字怎麼排版、上色以外的呈現（見 [`ui.md`](ui.md)）。

**條文編號**：`CALC-<主題>-<序號>`。編號永久不重用；條文廢止時保留編號並標示「已廢止」。

**單位慣例**：比率一律用小數（`0.0025` = 0.25%、`0.31` = 31%）；金額一律為美元；時間一律為 UTC。

---

## 1. 門檻總表

所有門檻集中於此，程式中以同名常數放在設定檔，可不改程式碼調整。「初始值」表示尚無實測依據，上線後依資料校準。

| 常數 | 值 | 用途 | 依據 |
|---|---|---|---|
| `APY_DAYS_PER_YEAR` | 365 | APY 年化 | 鏈上交易 24/7 |
| `SIGMA_TRADING_DAYS_PER_YEAR` | 252 | σ 年化 | 美股日 K 線；用 365 會高估 σ 約 20%（research 2026-10-24 §6） |
| `SIGMA_WINDOW_CALENDAR_DAYS` | 90 | σ 取樣窗口（約 63 個交易日） | PRD「約 3 個月」 |
| `SIGMA_MIN_BARS` | 30 | σ 最少樣本數 | 沿用參考專案 `MIN_ALIGNED_SAMPLES` |
| `SIGMA_MAX_AGE_DAYS` | 7 | σ 超過此天數未更新即「無法計算」 | PRD NFR |
| `MIN_TVL_USD` | 10,000 | 收錄下限 | 初始值；參考專案為 5,000，本專案另需顧及 V2 自我稀釋 |
| `FEE_RATE_MAX` | 0.05 | 費率合理上限 | 沿用參考專案 `MAX_SANE_FEE_RATE` |
| `MIN_HISTORY_DAYS` | 7 | 少於此天數為「資料不足」 | PRD F2 |
| `MEDIAN_SHORT_DAYS` | 7 | 排名用中位數窗口 | PRD F2 |
| `MEDIAN_LONG_DAYS` | 30 | 顯示用中位數窗口 | PRD F2 |
| `TREND_UP_RATIO` | 1.25 | 7 天 ÷ 30 天 ≥ 此值顯示 ↑ | 初始值 |
| `TREND_DOWN_RATIO` | 0.80 | 7 天 ÷ 30 天 ≤ 此值顯示 ↓ | 初始值；與 1.25 互為倒數，上下對稱 |
| `ANOMALY_MULTIPLE` | 5 | 高於同標的中位數此倍數為「異常」 | 沿用參考專案 `PEER_APY_OUTLIER_MULTIPLE` |
| `ANOMALY_MIN_PEERS` | 3 | 同標的至少此數量的其他池子才判定異常 | 沿用參考專案 `MIN_PEER_SAMPLE_SIZE` |
| `APY_CV_MAX` | 1.0 | 7 天日 APY 變異係數超過此值為「收益波動大」 | 初始值 |
| `FRESHNESS_DELAYED_HOURS` | 2 | 數據延遲起點 | PRD F6 |
| `FRESHNESS_STALE_HOURS` | 24 | 數據過期起點 | PRD F6 |
| `PIPELINE_BANNER_HOURS` | 2 | 排程未成功超過此時數顯示中斷橫幅 | PRD F6 |
| `LOSS_RATIO_GREEN_BELOW` | 0.25 | 損耗比綠色上限（不含） | PRD F2 |
| `LOSS_RATIO_RED_FROM` | 1.00 | 損耗比紅色下限（含） | PRD F2 |
| `DELIST_MISSING_DAYS`（PRD 中的 N） | 3 | 連續幾個有效更新日未出現即「官方已下架」 | 初始值；見 [`data-model.md`](data-model.md) DATA-REG-4 |
| `REPORTED_APY_LOG_RATIO` | 2.0 | 資料源 APY 與本站相差超過此倍數（任一方向）時寫入開發者紀錄 | 初始值 |
| `VOLUME_SYNC_MAX_LAG_DAYS` | 1 | `volume_synced_through` 落後昨日超過此天數即「數據過期」（CALC-DAY-4） | 正常情況下午夜到 `daily_close` 完成前會落後 1 天 |
| `PRICE_RESYNC_TOLERANCE` | 0.005 | 股價重疊日差異超過此比例即重抓整個窗口（[`sources.md`](sources.md) SRC-YF-6） | 初始值；拆股造成的差異為整數倍，遠大於此值 |

---

## 2. 日的切分

- **CALC-DAY-1** 一個「日」為 UTC 00:00:00（含）到隔日 00:00:00（不含）。快照依其 UTC 時間戳歸日；外部日線依來源標示的 UTC 日期歸日（各來源的日期語意見 [`sources.md`](sources.md)）。
- **CALC-DAY-2** 只有**已結束**的 UTC 日會產生日 APY。當日（尚未結束）不參與任何中位數。
- **CALC-DAY-3** 「最近 7 天」指截至該池子的 `volume_synced_through`（CALC-DAY-4，含）往回 7 個 UTC 日；「最近 30 天」同理。
- **CALC-DAY-4** `volume_synced_through`：池子最後一個「在該日結束後，成功抓取過涵蓋該日的外部日線」的 UTC 日（[`data-model.md`](data-model.md) DATA-POOL-1）。窗口以它而非昨日為終點，因為午夜後到 `daily_close` 完成前，昨日的交易量尚未取得，不得當成 0，也不得讓窗口因缺日而無法計算。`昨日 − volume_synced_through` 超過 `VOLUME_SYNC_MAX_LAG_DAYS` 天時，池子為「數據過期」（`STALE_VOLUME`，§7.1）。

---

## 3. 波動率 σ

對應 PRD F2「波動率資料來源」與 F2-AC1、F2-AC2、F2-AC22。

- **CALC-VOL-1** 取樣窗口：計算日往前 `SIGMA_WINDOW_CALENDAR_DAYS` 個日曆日內（不含計算日當天）的所有日 K 線。少於 `SIGMA_MIN_BARS` 根時 σ 無法計算（原因代碼 `NC_SIGMA_INSUFFICIENT`）。
- **CALC-VOL-2** **穩定幣配對**使用股票本身的 Yang-Zhang 波動率，公式與參考專案 `yang_zhang_volatility()` 相同：

  ```
  σ²_YZ = σ²_overnight + k·σ²_open-close + (1 − k)·σ²_RS
  k     = 0.34 / (1.34 + (n + 1) / (n − 1))
  σ     = √(σ²_YZ × SIGMA_TRADING_DAYS_PER_YEAR)
  ```

  OHLC 任一值 ≤ 0 的 K 線剔除後再計算。Yang-Zhang 無法計算時（剔除後少於 3 根），退回收盤價對數報酬的樣本標準差（參考專案 `annualized_volatility()`）。唯一差別是年化天數改為 252。
- **CALC-VOL-3** **非穩定幣配對**使用相對波動率：取股票與報價資產**兩邊都有 K 線的日期**（依日期標籤對齊），計算 `ln(P_stock / P_quote)` 收盤價序列的對數報酬樣本標準差，再乘上 √252 年化。對齊後少於 `SIGMA_MIN_BARS` 個日期時無法計算。不做參考專案的「覆蓋率」檢查：對齊基準是美股交易日，週末與假日缺口是預期內的。
- **CALC-VOL-4** 報價資產的分類與價格序列：核心報價資產依 [`data-model.md`](data-model.md) DATA-POOL-3 表中的「類型」與「價格序列」欄（例：WBNB → `BNB-USD`）；另一邊是股票代幣（股票配股票）時，價格序列為該股票的美股代號，同樣用 CALC-VOL-3。
- **CALC-VOL-5** σ 的快取單位是「價格序列組合」：穩定幣配對以 `(股票代號)` 為鍵，非穩定幣配對以 `(股票代號, 報價序列)` 為鍵。因此同一檔股票的所有穩定幣配對池共用同一個 σ，與鏈、穩定幣種類無關（F2-AC1）。
- **CALC-VOL-6** 每個 σ 記錄最後一次**成功算出**的時間。現在時間減去該時間超過 `SIGMA_MAX_AGE_DAYS` 天時，使用該 σ 的池子為「無法計算」（`NC_SIGMA_STALE`）；未超過時沿用該 σ（F2-AC22）。
- **CALC-VOL-7** 美股代號轉成 Yahoo 格式：把 `.` 換成 `-`（例：`BRK.B` → `BRK-B`）。

---

## 4. APY

對應 PRD F2「APY 的定義」與 F2-AC4～F2-AC11、F2-AC23。

### 4.1 每日 APY

- **CALC-APY-1** 每個已結束的 UTC 日 `d`：

  ```
  daily_apy(d) = volume_usd(d) × fee_rate × lp_share ÷ denom_usd(d) × APY_DAYS_PER_YEAR
  ```

  - `volume_usd(d)`：該池子 `d` 日的美元交易量，取自外部日線（[`sources.md`](sources.md) SRC-GT-4）。
  - `fee_rate`：池子收取的費率，取 `d` 日最後一筆完整快照的鏈上值（CALC-APY-5）。
  - `lp_share`：LP 實得比例，取法同 `fee_rate`（CALC-APY-6）。
  - `denom_usd(d)`：全區間等價資金，見 CALC-APY-2、CALC-APY-3。
- **CALC-APY-2** **V2 池**：`denom_usd(d)` = `d` 日所有完整快照的 TVL 算術平均。
- **CALC-APY-3** **集中流動性池**：每筆快照先換算全區間等價資金，再取 `d` 日所有完整快照的算術平均。單筆換算：

  ```
  sqrt_p      = 鏈上 √P，換成實數（EVM：sqrtPriceX96 ÷ 2^96；Raydium、Orca：sqrt_price_x64 ÷ 2^64）
                其意義為 √(token1 原始單位 ÷ token0 原始單位)
  equiv_usd   = 2 × L × sqrt_p ÷ 10^(token1 精度) × token1 美元價格
  ```

  `token1 美元價格` 取同一筆快照中資料源給的代幣價格。資料源的價格以 base／quote 標示（[`sources.md`](sources.md) SRC-GT-3），一律**依代幣地址**對應到鏈上的 token0／token1，不得假設 base 即 token0。此換算已在 research 2026-10-24 §2 以價格交叉驗證（誤差 < 1%）。
- **CALC-APY-8** **分母為零**：單筆快照的 L = 0 是正常狀態（現價不在任何 LP 的區間內），照常計入平均。`denom_usd(d)` 平均後仍為 0 時，`d` 日沒有 `daily_apy`（原因 `NC_ZERO_DENOMINATOR`），不得計算成無限大。分母為負屬於「錯誤」（CALC-STATE 表）。
- **CALC-APY-4** **沒有完整快照的日子**（系統上線前的回補日，以及上線後斷線的日子）：交易量照常取自外部日線，分母、`fee_rate`、`lp_share` 改用**時間上最接近的完整快照**的值（距離相同時取較早者）；該日標記為「近似」。因此池子從外部日線的第一天起，每一天都有 `daily_apy`。上線前的回補日因此一律使用第一筆完整快照，與 PRD「以現值近似」一致。
  - 池子**從未有完整快照**時，所有日子都沒有 `daily_apy`；池子依 §7.1 為「數據過期」（或更前面的排除類狀態）。
  - 已彙整的日子（[`data-model.md`](data-model.md) DATA-STORE-3）直接使用彙整時已決定的分母、`fee_rate`、`lp_share` 與近似標記，不重新選取。最接近的完整快照只存在於已彙整的日子時（斷線超過約 60 天），以時間上最接近的已彙整日的已決定值代替。
- **CALC-APY-5** `fee_rate` 一律使用鏈上讀取值（F2-AC7）。池名費率只用於比對，不一致時寫入開發者紀錄。費率讀取方式依 DEX 而定，見 [`sources.md`](sources.md) §4。
- **CALC-APY-6** `lp_share` 的取得方式見 [`sources.md`](sources.md) §4。若同一池子的 token0、token1 方向抽成比例不同，取兩者平均並寫入開發者紀錄。
- **CALC-APY-7** 「池子平均 APY」（只用於顯示，F6-AC8）：與 CALC-APY-1 相同，但分母一律用當日 TVL 平均（CALC-APY-2 的算法），排名與狀態判定都不使用它。V2 池的池子平均 APY 恆等於全區間 APY。顯示值取其 7 天中位數（CALC-AGG-1 的算法），使兩個數字的時間窗口一致，比值即反映集中程度。

### 4.2 中位數與歷史天數

- **CALC-AGG-1** `apy_7d` = 最近 7 個 UTC 日（CALC-DAY-3）的 `daily_apy` 中位數。窗口內每一天都必須有 `daily_apy`（實測或近似皆可），否則不計算：缺日是因為歷史不足時為「資料不足」，因為分母為零（CALC-APY-8）時為「無法計算」。
- **CALC-AGG-2** `apy_30d` = 最近 30 個 UTC 日的 `daily_apy` 中位數（偶數個時取中間兩個的平均）。窗口內有任何一天沒有 `daily_apy` 時為缺值，顯示「—」（F2-AC10）。
- **CALC-AGG-3** `history_days` = 池子從外部日線的第一個日期到 `volume_synced_through`（CALC-DAY-4）的天數（含回補）。日線中間缺少的日期視為交易量 0（外部日線對沒有成交的日子不回傳 K 線，見 SRC-GT-4）。`history_days < MIN_HISTORY_DAYS` 為「資料不足」，此時 `apy_7d` 與其衍生值（淨收益、損耗比、容錯空間、池子平均 APY）都不計算，不以不足 7 天的資料硬算。
- **CALC-AGG-4** **近似標記 `≈`**：`apy_7d` 的窗口內有任何一天標記為近似（CALC-APY-4）時，`apy_7d` 帶近似標記；`apy_30d` 同理。由 `apy_7d` 衍生的淨收益、損耗比沿用 `apy_7d` 的標記（F2-AC11）。
- **CALC-AGG-5** **趨勢箭頭**：`apy_30d` 有值且大於 0 時，令 `r = apy_7d ÷ apy_30d`；`r ≥ TREND_UP_RATIO` 為 ↑，`r ≤ TREND_DOWN_RATIO` 為 ↓，其餘不顯示（F6-AC9）。

---

## 5. 無常損失、淨收益與損耗比

對應 PRD F2「手續費損耗比」與 F2-AC14～F2-AC16。

- **CALC-IL-1** 預估無常損失（全區間、一年）：`il = σ² ÷ 8`。`σ ≥ √8`（約 283%）時公式失效（參考專案 MODEL.md §3.2），池子為「無法計算」（`NC_SIGMA_OUT_OF_RANGE`），不夾成 100%。
- **CALC-IL-2** `σ ≤ 0` 視為資料異常（30 根以上 K 線完全沒有波動不符合現實），池子為「無法計算」（`NC_SIGMA_DEGENERATE`）。因此後續公式中的 σ 恆為正數，`headroom` 不會是無限大。
- **CALC-NET-1** 淨收益：`net_yield = apy_7d − il`。
- **CALC-NET-2** 損益平衡波動率：`σ* = √(8 × apy_7d)`（`apy_7d > 0` 時）。
- **CALC-NET-3** `vol_ratio = σ ÷ σ*`。`apy_7d ≤ 0` 時 `vol_ratio` 為 +∞。
- **CALC-NET-4** `fee_loss_ratio = vol_ratio²`，等價於 `il ÷ apy_7d`；`apy_7d ≤ 0` 時為 +∞。**顯示一律使用 `fee_loss_ratio`，不得使用 `vol_ratio`**（PRD F2，F2-AC14）。
- **CALC-NET-5** 容錯空間（白話說明的後半句）：`headroom = σ* ÷ σ − 1`，意義為「σ 再大多少比例就開始虧損」。`fee_loss_ratio ≥ 1` 時沒有容錯空間，說明文字改用另一句（見 [`ui.md`](ui.md)）。

### 範例（測試向量）

| 編號 | 輸入 | 預期輸出 |
|---|---|---|
| E1 | V2 池；某日交易量 500,000；費率 0.0025；`lp_share` 0.68；當日三筆快照 TVL 1,000,000／1,200,000／800,000 | `denom` = 1,000,000；`daily_apy` = 0.31025 |
| E2 | 集中流動性池；token0、token1 精度皆 18；`sqrtPriceX96` = 20 × 2^96 = `1584563250285286751870879006720`；`L` = 5×10²²；token1 價格 1.00；交易量 200,000；費率 0.0025；`lp_share` 0.68 | `equiv_usd` = 2,000,000；`daily_apy` = 0.06205 |
| E3 | 7 天 `daily_apy` = 0.020、0.030、0.025、0.300、0.028、0.027、0.031 | `apy_7d` = 0.028（單日暴衝不影響，F2-AC9） |
| E4 | `apy_7d` = 0.031；σ = 0.38 | `il` = 0.01805；`net_yield` = 0.01295；`vol_ratio` ≈ 0.7631；`fee_loss_ratio` ≈ 0.5823（顯示 58%，不是 76%）；`headroom` ≈ 0.3105 |
| E5 | `apy_7d` = 0.012；σ = 0.38 | `net_yield` = −0.00605；`fee_loss_ratio` ≈ 1.5042（紅色） |
| E6 | `apy_7d` = 0.025；`apy_30d` = 0.015 | `r` ≈ 1.667，顯示 ↑ |
| E7 | E3 的 7 天資料 | 變異係數 ≈ 1.569 > 1.0，標示「收益波動大」 |
| E8 | 7 天 `daily_apy` = 0.020、0.030、0.025、0.035、0.028、0.027、0.031 | 變異係數 ≈ 0.170，不標示 |

---

## 6. 收錄條件

- **CALC-INC-1** **TVL 下限**：池子「最近一個已結束 UTC 日的 TVL 平均」低於 `MIN_TVL_USD` 時不收錄，不出現在任何卡片（F2-AC3）。尚無已結束日的完整快照時，用最新一筆完整快照的 TVL。以日平均判斷，避免池子在門檻附近每 30 分鐘進出一次。
- **CALC-INC-2** TVL 下限用**實際 TVL**，不用全區間等價資金（F2-AC3）。
- **CALC-INC-3** 報價資產分級（F5）、V4／Infinity 排除（F2-AC13）與 DEX 白名單（F2-AC27）是收錄的前置條件，判定規則見 [`data-model.md`](data-model.md) DATA-POOL-2、DATA-POOL-5、DATA-POOL-6。

---

## 7. 池子狀態判定

狀態的定義、顯示與是否參與排名以 PRD F2「池子狀態一覽」為準。本節只補判定條件。所有判定以「計算時間 `now`」為基準。

### 7.1 排除類

依 PRD 狀態表由上而下的順序判定；同時符合多種時，第一個符合者為主要狀態，其餘列為次要狀態（F2-AC19）。

| 狀態 | 判定條件 | 原因代碼（系統內部） |
|---|---|---|
| 官方已下架 | 池子內任一登記表代幣狀態為「官方已下架」 | `TOKEN_DELISTED` |
| 暫停交易 | 池子內任一登記表代幣狀態為「暫停交易」 | `TOKEN_HALTED` |
| 錯誤 | 鏈上讀到的 `fee_rate` 不在 `(0, FEE_RATE_MAX]`；`lp_share` 不在 `(0, 1]`；L 為負或無法解碼；√P ≤ 0 或無法解碼；TVL 或交易量為負 | `ERR_FEE_OUT_OF_RANGE`、`ERR_LP_SHARE_OUT_OF_RANGE`、`ERR_LIQUIDITY_DECODE`、`ERR_NEGATIVE_VALUE` |
| 無法計算 | DEX 沒有對應的 L 讀取方式；費率無法取得（含動態費率池）；`lp_share` 讀取方式未知或尚待查證；標的沒有 Yahoo 股價；σ 樣本不足、過期、為零或超出公式範圍；7 天窗口內有分母為零的日子 | `NC_NO_LIQUIDITY_READER`、`NC_NO_FEE_RATE`、`NC_NO_LP_SHARE`、`NC_NO_PRICE_SOURCE`、`NC_SIGMA_INSUFFICIENT`、`NC_SIGMA_STALE`、`NC_SIGMA_DEGENERATE`、`NC_SIGMA_OUT_OF_RANGE`、`NC_ZERO_DENOMINATOR` |
| 數據過期 | `now − last_complete_snapshot_at > FRESHNESS_STALE_HOURS`；池子從未有完整快照（`last_complete_snapshot_at` 為空）；或交易量同步落後（CALC-DAY-4） | `STALE`、`STALE_NEVER_COMPLETE`、`STALE_VOLUME` |
| 資料不足 | `history_days < MIN_HISTORY_DAYS` | `INSUFFICIENT_HISTORY` |

- **CALC-STATE-1** 「讀不到」分兩種，處理不同：**結構性讀不到**（DEX 不支援、費率是動態的、編碼未知）為「無法計算」；**暫時讀不到**（網路錯誤、逾時、RPC 限流）不改變狀態，只是那一次快照不完整，由新鮮度反映（CALC-STATE-4）。讀到了但值不合理為「錯誤」（F2-AC24）。
- **CALC-STATE-2** 「錯誤」與「無法計算」共用相同的使用者顯示，但原因代碼必須寫入輸出資料的開發者欄位與紀錄（F2-AC20）。
- **CALC-STATE-3** 「完整快照」依池子實際需要的欄位定義，新鮮度（數據延遲、數據過期）一律以最後一筆完整快照的時間 `last_complete_snapshot_at` 判定：
  - 所有池子：TVL、24 小時交易量、兩個代幣的美元價格都已取得（展示 TVL、交易量所需）。
  - 所屬 DEX 的計算狀態為 `支援`（[`sources.md`](sources.md) §4）時另需：集中流動性池的 L 與 √P；`fee_rate` 與 `lp_share` 已有值（可沿用上一筆，因其很少變動）。

  因此已啟用但不能計算的池子（例如讀不到 L 的 DEX），只要 TVL 與交易量照常更新，就有正確的新鮮度，不會因為缺少它本來就讀不到的欄位而永遠沒有完整快照。

### 7.2 提示類

提示類不影響排名（F2-AC18），可同時帶多個。

- **CALC-STATE-4** **數據延遲**：`FRESHNESS_DELAYED_HOURS ≤ now − last_complete_snapshot_at ≤ FRESHNESS_STALE_HOURS`（F2-AC21）。
- **CALC-STATE-5** **異常**：對池子所在的每張股票卡片，取該卡片上**其他**不屬於排除類的池子為同儕。同儕數 ≥ `ANOMALY_MIN_PEERS`、同儕 `apy_7d` 中位數 > 0，且本池 `apy_7d` > 同儕中位數 × `ANOMALY_MULTIPLE` 時標示。股票配股票的池子在任一張卡片上符合即標示，兩張卡片顯示相同（F3-AC2）。只標示偏高，不標示偏低：偏低的池子本來就排在後面，不會誤導（F2-AC25）。
- **CALC-STATE-6** **收益波動大**：`apy_7d` 窗口內 7 個 `daily_apy` 的樣本標準差 ÷ 平均值 > `APY_CV_MAX` 時標示；平均值 ≤ 0 時不標示（F2-AC26）。

---

## 8. 選取與排序

所有排序在主鍵相同或缺值時，依本節的次要鍵決定順序，確保同樣資料重複產生時結果完全相同（F6-AC23）。缺值一律排在有值之後。

- **CALC-RANK-1** **可排名池子**：已收錄（§6）且沒有任何排除類狀態的池子。
- **CALC-RANK-2** **卡片的最佳淨收益**：該卡片可排名池子中 `net_yield` 最高者。平手時依序比較：池子 24h 交易量（高者優先）、`pool_id` 字典序（小者優先）。
- **CALC-RANK-3** **卡片的 24h 交易量**：卡片上所有已收錄池子（含排除類）的最新快照 24h 交易量總和（F6-AC6）。
- **CALC-RANK-4** **卡片分類**：至少一個可排名池子為情況 A；有已收錄池子但全部為排除類為情況 B；沒有已收錄池子為情況 C（PRD F6）。
- **CALC-RANK-5** **市場收益排行**：情況 A 依最佳淨收益由高到低，平手依卡片 24h 交易量（高者優先）、`stock_id` 字典序；接著是情況 B，依卡片 24h 交易量由高到低，平手依 `stock_id`。情況 C 不列入（F6-AC1、F6-AC3、F6-AC4）。
- **CALC-RANK-6** **情況 B 的主要原因**：統計卡片上每個池子的**主要**狀態，取池子數最多者；數量相同時取 PRD 狀態表中較前者（F6-AC3）。
- **CALC-RANK-7** **我的關注**：預設依卡片 24h 交易量由高到低，平手依 `stock_id`。切換為淨收益排序時，規則同 CALC-RANK-5，但情況 C 也列入並排在最後（依 `stock_id`）（F6-AC22）。
- **CALC-RANK-8** **費率階梯分組與預設池子**：同一條鏈、同一個 DEX、同一組代幣地址（不分先後）的池子為同一組。預設顯示的池子：組內可排名池子中 `net_yield` 最高者，平手依 24h 交易量、`pool_id`；組內沒有可排名池子時取 24h 交易量最高者，平手依 `pool_id`（F3-AC1）。
- **CALC-RANK-9** 排序一律使用未四捨五入的原始值。

---

## 9. 顯示數值與分級

- **CALC-DISP-1** APY、淨收益顯示到小數點後一位百分比；損耗比顯示到整數百分比。四捨五入採「遠離零」方向，且不顯示 `-0.0%`（四捨五入後為零即顯示 `0.0%`）。
- **CALC-DISP-2** 損耗比顏色依**四捨五入後的整數百分比**判定，讓顯示的數字與顏色一致：`< 25%` 綠色，`25%～99%` 黃色，`≥ 100%` 紅色（F2-AC15）。例：原始值 0.2496 顯示 25%，為黃色。
- **CALC-DISP-3** `fee_loss_ratio` 為 +∞ 或 ≥ 10 時顯示 `> 999%`，紅色。
- **CALC-DISP-4** 淨收益為負時以紅色顯示實際數值（F6-AC2）；顏色依四捨五入後的值判定。
- **CALC-DISP-5** 「池子平均 APY」只在集中流動性池顯示（F6-AC8）。

---

## 10. 對照檢查（只寫開發者紀錄）

- **CALC-CHK-1** 資料源報的 APY（例如 DefiLlama `apyBase`）只與本站的**池子平均 APY**（CALC-APY-7）比較，相差超過 `REPORTED_APY_LOG_RATIO` 倍（任一方向）時寫入開發者紀錄。不參與任何排名、不顯示給使用者（F2-AC12）。
- **CALC-CHK-2** 池名費率與鏈上費率不一致時寫入開發者紀錄（F2-AC7）。
