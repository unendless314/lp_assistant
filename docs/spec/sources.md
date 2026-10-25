# 外部資料來源契約

> 狀態：初稿（2026-10-26）。外部 API 隨時可能改版；實測紀錄見 [`research/`](../research/)，本文件只寫系統依賴的部分。
> 需求以 [`prd.md`](../prd.md) 為準。

## 0. 範圍與邊界

**本文件管**：每個外部來源的端點、必要欄位、正規化規則、完整性檢查，以及失敗時對外回報什麼。每個來源由一個轉接模組負責，只做「抓取 → 驗證 → 轉成內部模型」，不做任何判斷與計算。

**本文件不管**：資料抓下來之後怎麼存、怎麼組成登記表（[`data-model.md`](data-model.md)）；怎麼用來計算（[`calc.md`](calc.md)）；多久抓一次（[`../architecture.md`](../architecture.md)）。

**條文編號**：`SRC-<來源>-<序號>`。編號永久不重用。

### 共通原則

- **SRC-ALL-1** 必要欄位缺少時視為「資料無法取得」，不得以 0 或空字串代替。
- **SRC-ALL-2** 所有請求帶 `User-Agent`（Robinhood 公開 RPC 對沒有 `User-Agent` 的請求回 HTTP 403）。
- **SRC-ALL-3** 所有外部請求經由同一個 HTTP 客戶端：逾時、重試（指數退避，遇 HTTP 429 依 `Retry-After` 或至少等 15 秒）、每個來源各自的限速。
- **SRC-ALL-4** 每次外部回應的原始內容以 gzip 存檔 30 天，解析邏輯修正後可重新處理（[`data-model.md`](data-model.md) DATA-STORE-6）。
- **SRC-ALL-5** 地址正規化：EVM 地址一律轉小寫；Solana 地址保持原樣（區分大小寫），並去除 `svm:` 之類的前綴。
- **SRC-ALL-6** 轉接模組回報三種結果之一：`ok`（附資料）、`invalid`（回應收到但未通過完整性檢查，附原因）、`failed`（網路錯誤、逾時、HTTP 錯誤）。上層依此決定是否計入登記表更新（DATA-REG-3）。

---

## 1. 代幣官方清單

三個來源都轉成同一個內部模型 `OfficialToken`：

| 欄位 | 說明 |
|---|---|
| `issuer` | `bstock`／`xstocks`／`robinhood` |
| `chain` | `bsc`／`solana`／`robinhood` |
| `address` | 合約地址（正規化後） |
| `address_role` | `primary`／`wrapper`（xStocks 的 `wrapperAddressV2`） |
| `symbol` | 代幣代號（例：`TSLAB`、`TSLAx`、`TSLA`） |
| `underlying_ticker` | 標的的美股代號 |
| `underlying_isin` | 標的 ISIN，沒有則為空 |
| `underlying_name` | 公司或基金名稱 |
| `underlying_exchange_mic` | 標的掛牌交易所 MIC，沒有則為空 |
| `underlying_currency` | 標的幣別，沒有則為空 |
| `halted` | 官方是否標示暫停交易、暫停發行或暫停贖回 |
| `decimals` | 代幣精度，來源有提供時填 |

### 1.1 bStock（幣安股票代幣清單）

- **SRC-BN-1** 端點：`GET https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/rwa/stock/detail/list/ai?type=3`。免登入。
- **SRC-BN-2** 回應須 `success == true`，`data` 為陣列。已知欄位：`ticker`、`symbol`、`chainId`（BSC 為 `56`）、`contractAddress`、`multiplier`。
- **SRC-BN-3** 對應：`underlying_ticker` ← `ticker`；`chain` 依 `chainId` 對應，非 `56` 的項目忽略並記錄。
- **SRC-BN-4** **實作時須確認**：回應是否含 ISIN、交易所、暫停交易、標的名稱欄位。沒有時對應欄位為空，`halted` 恆為 false；判定規則見 DATA-REG-5、DATA-REG-8、DATA-REG-9。
- **SRC-BN-5** 完整性檢查：`success == true`；每筆都有 `ticker`、`symbol`、`chainId`、`contractAddress`；筆數不少於上次有效清單的 90%（防止截斷的回應被當成大量下架）。名稱、ISIN 等選填欄位缺少不影響清單是否有效。

### 1.2 xStocks 官方 API

- **SRC-XS-1** 端點：`GET https://api.xstocks.fi/api/v2/public/assets?page={n}`，`n` 從 0 開始，每頁 100 筆，`page.hasNextPage` 為 false 時結束。官方文件：[docs.xstocks.fi/apis/openapi](https://docs.xstocks.fi/apis/openapi)。不使用 `api.backed.fi`（含非 xStocks 的舊代幣）與幣安轉列清單（PRD F1-AC1）。
- **SRC-XS-2** 欄位對應：`symbol` → `symbol`；`underlyingSymbol` → `underlying_ticker`；`underlyingIsin` → `underlying_isin`；`underlying.exchange.mic` → `underlying_exchange_mic`；`underlying.currency` → `underlying_currency`。名稱欄位實作時確認。
- **SRC-XS-3** `deployments[]` 中只取 `network` 為 `BinanceSmartChain`、`Solana` 者；每個部署產生一筆 `primary`（`address`），EVM 部署若有 `wrapperAddressV2` 再產生一筆 `wrapper`（PRD F1-AC6）。
- **SRC-XS-4** `halted` = `isTradingHalted == true`，或 `allowedOperations` 缺少發行或贖回任一項（PRD F1-AC11）。
- **SRC-XS-5** 完整性檢查：所有頁面都成功取得、頁碼連續、最後一頁 `hasNextPage == false`；每筆都有 `symbol`、`underlyingSymbol`、`deployments`；總筆數不少於上次有效清單的 90%。任何一頁失敗，整份清單為 `failed`，不得只用部分頁面。

### 1.3 Robinhood 官方 API

- **SRC-RH-1** 端點：`GET https://api.robinhood.com/rhj/assets`。免登入。
- **SRC-RH-2** 欄位對應：`tokenSymbol` → `symbol` 與 `underlying_ticker`；`isin` → `underlying_isin`；`deployments[].contractAddress`（只取 chain ID 4663）→ `address`；`tokenDecimals` → `decimals`。
- **SRC-RH-3** `halted`：狀態不是 `ASSET_STATUS_ACTIVE` 時為 true。**實作時須確認**：`tradingCapabilities` 是否另有表示暫停發行或贖回的值，有則一併納入。
- **SRC-RH-4** 完整性檢查：每筆都有 `tokenSymbol`、`deployments`；筆數不少於上次有效清單的 90%。

### 1.4 清單筆數驟降

- **SRC-LIST-1** 筆數低於上次有效清單 90% 的回應判為 `invalid`（原因 `COUNT_DROP`）。若連續 7 天都因此判為無效，寫入開發者紀錄要求人工確認；確認為真實的大量下架時，由開發者以指令接受新清單作為基準。這是唯一需要人工介入的情境，且只影響下架判定，不影響其他資料更新。

---

## 2. GeckoTerminal（池子、TVL、交易量、日線）

- **SRC-GT-1** 基底網址 `https://api.geckoterminal.com/api/v2`。網路 ID：`bsc`、`solana`、`robinhood`。免費額度約 30 次/分鐘，限速設定為每分鐘 25 次以保留餘裕。
- **SRC-GT-2** **找池子**：`GET /networks/{net}/tokens/{address}/pools?page={n}`。每個池子取：池子地址、`dex` ID、`name`（含池名費率，只用於比對）、base／quote 代幣地址、`pool_created_at`。
- **SRC-GT-3** **快照**：`GET /networks/{net}/pools/multi/{addr1,addr2,...}`，每次最多 30 個地址（官方文件值；上限實作時實測，不足時縮小批次）。取 `reserve_in_usd`（TVL）、`volume_usd.h24`、`base_token_price_usd`、`quote_token_price_usd`，以及 `relationships.base_token`、`relationships.quote_token` 的代幣地址，供上層依地址對應到 token0／token1（CALC-APY-3）。
- **SRC-GT-4** **日線**：`GET /networks/{net}/pools/{address}/ohlcv/day?limit={n}&currency=usd`，每筆含 UTC 日期與美元交易量，最多回傳約 60 天。沒有成交的日子不回傳 K 線，上層視為交易量 0（CALC-AGG-3）。**實作時確認**：日線的日期是否為 UTC 00:00 起算。
- **SRC-GT-5** 回補：新池子第一次被發現時，抓取日線 `limit=60`。之後的例行抓取（`daily_close`）涵蓋 `volume_synced_through − 2` 到昨日，至少 3 天，以吸收資料源的延遲修正與先前的失敗。成功取得、且抓取時間晚於某日結束時，該日以前即視為已同步，更新 `volume_synced_through`（CALC-DAY-4）。
- **SRC-GT-6** GeckoTerminal 沒有歷史 TVL、沒有 APY、沒有 L；這些由本系統的快照與鏈上讀取補上。
- **SRC-GT-7** 完整性檢查：TVL、交易量、兩個代幣價格皆存在且可解析為非負數字；否則該池子這次快照不完整（CALC-STATE-3）。

---

## 3. 鏈上讀取

### 3.1 EVM（BSC、Robinhood Chain）

- **SRC-EVM-1** RPC 端點放在設定檔，每條鏈至少兩個（主要與備援）。Robinhood Chain 預設 `https://rpc.mainnet.chain.robinhood.com`（chain ID 4663）。
- **SRC-EVM-2** 集中流動性池每次快照讀取：`slot0()`（取 `sqrtPriceX96` 與 `feeProtocol`）、`liquidity()`、`fee()`；初次發現時讀 `token0()`、`token1()` 與兩者的 `decimals()` 並存起來。同一輪的多個池子以 Multicall3 批次讀取。
- **SRC-EVM-3** `fee()` 的單位為百萬分之一：`fee_rate = fee() ÷ 1,000,000`（2500 = 0.25%）。
- **SRC-EVM-4** V2 池每次快照不需要鏈上讀取（TVL 取自 GeckoTerminal）；費率與 LP 實得比例依 §4 的 DEX 對照表。

### 3.2 Solana

- **SRC-SOL-1** RPC 端點放在設定檔，至少兩個。以 `getMultipleAccounts`（base64）批次讀取池子帳戶。
- **SRC-SOL-2** Raydium CLMM（程式 `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`）：池子帳戶取 `liquidity`（u128）、`sqrt_price_x64`（u128）、兩個 mint 與精度；費率與抽成比例在池子指向的 `AmmConfig` 帳戶（`trade_fee_rate`、`protocol_fee_rate`、`fund_fee_rate`，單位皆為百萬分之一）。
- **SRC-SOL-3** Orca Whirlpool（程式 `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`）：池子帳戶取 `liquidity`、`sqrt_price`（Q64.64）、`fee_rate`（百萬分之一）、`protocol_fee_rate`（萬分之一，為手續費中協議抽走的比例）、兩個 mint；精度讀 mint 帳戶。
- **SRC-SOL-4** 帳戶的擁有程式不是上述兩者時，不解碼，池子為「無法計算」（`NC_NO_LIQUIDITY_READER`）。
- **SRC-SOL-5** 帳戶欄位的位元組位置以官方 IDL 為準，並以 research 2026-10-24 的腳本交叉驗證；實作須附上「用 √P 算出的價格與 GeckoTerminal 價格比值在 0.98～1.02 之間」的測試。

---

## 4. DEX 對照表

`dex` ID 取自 GeckoTerminal。此表為系統內建資料，隨程式碼維護，是 DEX 相關設定的唯一來源，包含尚在評估的候選 DEX 與已啟用的 DEX。

每個 DEX 有三組**互相獨立**的屬性：
- **計算**：`支援`／`待查證`／`不支援`。只有 `支援` 的 DEX 會計算 APY；其餘若已啟用，照常展示並標示「無法計算」。
- **協議審查**：人工確認該 DEX 的協議架構不是 V4／Infinity 型（池子建立者無法掛載 hook 合約）。記錄依據（官方文件或已驗證的工廠合約地址）與審查日期。未完成時為「尚無」。
- **池子頁面網址格式**：以至少一個真實池子實際開啟確認後填入，同時記錄用來確認的池子與日期。未完成時為「未確認」。

- **SRC-DEX-4** **展示** = `啟用` 若且唯若協議審查與池子頁面網址格式**兩者都已完成**；否則為 `候選`。這是 PRD F2「只展示已啟用 DEX 的池子」的唯一判定依據。候選 DEX 與不在本表的 DEX 處理相同：池子照常寫入資料庫並記錄給開發者（DATA-POOL-6），但不展示（F2-AC27）。展示與否和「計算」屬性無關。

下表為撰寫規格時的現況，實作時逐一完成審查與實測：

| GeckoTerminal `dex` ID | 鏈 | 類型 | 費率來源 | LP 實得比例 `lp_share` | 計算 | 協議審查 | 池子頁面網址格式 | 展示 |
|---|---|---|---|---|---|---|---|---|
| `pancakeswap-v3-bsc` | BSC | 集中流動性 | `fee()` | `1 − p ÷ 10,000`，`p` 為 `feeProtocol` 對應方向的 16 位元值（低 16 位元為 token0，高 16 位元為 token1） | 支援 | 尚無 | 未確認 | 候選 |
| `uniswap-bsc` | BSC | 集中流動性（V3 介面） | `fee()` | `1 − 1 ÷ n`，`n` 為 `feeProtocol` 對應方向的 4 位元值（低 4 位元為 token0）；`n = 0` 時為 1 | 支援 | 尚無 | 未確認 | 候選 |
| `uniswap-v3-robinhood` | Robinhood | 集中流動性 | `fee()` | 同 `uniswap-bsc` | 支援 | 尚無 | 未確認 | 候選 |
| `sushiswap-v3-robinhood` | Robinhood | 集中流動性 | `fee()` | 同 `uniswap-bsc` | 支援 | 尚無 | 未確認 | 候選 |
| `ramses-v3-robinhood` | Robinhood | 集中流動性 | `fee()` | `feeProtocol` 編碼與 Uniswap 不同 | 待查證（`NC_NO_LP_SHARE`） | 尚無 | 未確認 | 候選 |
| `raydium-clmm` | Solana | 集中流動性 | `AmmConfig.trade_fee_rate ÷ 10⁶` | `1 − (protocol_fee_rate + fund_fee_rate) ÷ 10⁶` | 支援 | 尚無 | 未確認 | 候選 |
| `orca` | Solana | 集中流動性 | `fee_rate ÷ 10⁶` | `1 − protocol_fee_rate ÷ 10,000` | 支援 | 尚無 | 未確認 | 候選 |
| PancakeSwap V2（ID 待確認） | BSC | V2 | 合約常數 0.25% | 依官方文件 0.17 ÷ 0.25 = 0.68 | 待查證（SRC-DEX-1；查證紀錄：尚無） | 尚無 | 未確認 | 候選 |
| Byreal、Meteora DLMM（ID 待確認） | Solana | — | — | — | 不支援（PRD F2） | 尚無 | 未確認 | 候選 |

- **SRC-DEX-1** V2 池的費率與抽成寫死在合約中、無法從狀態讀取時，允許以本表的常數代替鏈上讀取，**前提是**該常數已對照區塊瀏覽器上已驗證的合約原始碼，並在本表記下查證紀錄：核對的合約地址（工廠或範例池子）、核對時的區塊高度或版本、核對日期。查證紀錄為「尚無」時，計算狀態只能是 `待查證`。這是 PRD「一律從鏈上讀取」在 V2 合約上的唯一實作方式。
- **SRC-DEX-2** 讀到的 `feeProtocol` 編碼不符預期（例如 Uniswap 型的值不在 0 或 4～10 之間）時，池子為「錯誤」（`ERR_LP_SHARE_OUT_OF_RANGE`）。
- **SRC-DEX-3** **V4 架構排除**（PRD F2-AC13）：`dex` ID 含 `v4` 或 `infinity` 的池子，以及 EVM 上池子 ID 為 32 位元組（`0x` 後接 64 個十六進位字元，V4 的 pool ID 格式，而非 20 位元組的合約地址）的池子，一律不寫入資料庫。兩條規則任一符合即排除，以防新的 V4 型 DEX 名稱不含關鍵字。

---

## 5. 股價（yfinance）

- **SRC-YF-1** 以 yfinance 抓取日 K 線（OHLC）。價格口徑全系統一致：**分割還原、不做股利還原**（`auto_adjust=False`，使用 `Open`／`High`／`Low`／`Close`，不使用 `Adj Close`）。理由：未做分割還原時，拆股會在序列中造成虛假的跳空；股利還原則會在每次除息時微幅改寫全部歷史價格，與增量更新（SRC-YF-2）衝突。代號轉換見 CALC-VOL-7。報價資產序列：`BNB-USD`、`ETH-USD`、`SOL-USD`。
- **SRC-YF-2** 每天抓一次，只補最近 10 個日曆日（涵蓋長週末與短暫失敗）；新代號第一次出現時補足 `SIGMA_WINDOW_CALENDAR_DAYS`。
- **SRC-YF-6** **歷史改寫偵測**：資料源在拆股後會回頭改寫歷史價格，只補最近幾天會讓資料庫中新舊 K 線的尺度不同。每次增量抓取時，比對回應與資料庫中重疊日期的收盤價，任一日相對差異超過 `PRICE_RESYNC_TOLERANCE`，或沒有任何重疊日期（例如連續失敗超過 10 天），即重抓該序列的整個 `SIGMA_WINDOW_CALENDAR_DAYS` 窗口並覆寫，同時寫入開發者紀錄。
- **SRC-YF-3** 鎖定 yfinance 版本。股價抓取只在這一個模組中，介面為「代號 + 日期區間 → 日 K 線列表」，長期失效時可替換為其他來源（例如 Stooq）而不影響其他模組。
- **SRC-YF-5** 每個新代號第一次出現時，另以 yfinance 取得證券名稱（`longName`，沒有時用 `shortName`）並存起來，供 DATA-REG-9 的名稱比對使用；取得失敗時下次清單更新再試。名稱很少變動，之後每 30 天更新一次。
- **SRC-YF-4** 完整性檢查：每根 K 線 OHLC 皆為正數、`low ≤ open, close ≤ high`；不符的 K 線丟棄並記錄。代號查無資料時回報 `invalid`（原因 `UNKNOWN_TICKER`），上層標示 `NC_NO_PRICE_SOURCE`。

---

## 6. DefiLlama（只做對照）

- **SRC-DL-1** `GET https://yields.llama.fi/pools`，只取 Solana 上與本系統池子地址相符的 `apyBase`，用於 CALC-CHK-1。
- **SRC-DL-2** 此來源失敗不影響任何計算與顯示，只記錄。
