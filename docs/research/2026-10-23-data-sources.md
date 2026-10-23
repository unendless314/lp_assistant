# 資料來源可行性調查

> 調查日期：2026-10-23。外部 API 隨時可能改版、改限額，引用前請確認日期。

## 目的

確認「不登入任何錢包」的前提下，能不能取得代幣化股票 LP 池子的 APY、TVL、交易量、費率階梯。

## 結論摘要

1. 原專案的池子資料全部來自 `baw`（Binance Agentic Wallet CLI），**必須登入錢包 session**，不適合放在伺服器上。
2. 改用公開 API 可以涵蓋 **BSC、Solana 與 Robinhood Chain**，不需要 baw。
3. 主要缺口：BSC 與 Robinhood 沒有現成 APY、沒有歷史 TVL、抓不到挖礦獎勵 APY。
4. Robinhood Chain 有**官方公開的股票代幣清單**（含 ISIN），可用來核對地址、排除第三方代幣；約一半的股票池是 Uniswap V4（見 §7）。

---

## 1. 原專案（reference）的資料來源

依原專案 `SKILL.md` 的資料來源表：

| 資料 | 來源 | 需登入 |
|---|---|---|
| 股票代幣清單 | 幣安公開 API `bapi/defi/.../rwa/stock/detail/list/ai` | 否 |
| K 線 | 幣安公開 API `bapi/defi/.../dex/market/token/kline/ai` | 否 |
| LP 池子 APY / TVL | `baw defi investment-list` | **是** |
| 池子組成、V3 費率 | `baw defi investment-info` | **是** |
| 持有部位 | `baw defi position` | **是** |

baw 的風險：
- 登入後的 session 能執行存入/提領等操作，放在伺服器上等於常駐一個能動用錢包的憑證。
- session 會過期（`SESSION_EXPIRED`），重新登入需人工驗證，無法無人值守。
- 每次呼叫要啟動一個 Node CLI 子程序（原專案註解記載約 0.6 秒以上）。
- 本次調查沒有安裝 baw，以上依原專案文件判斷，未實測。

## 2. 幣安股票代幣清單

| `type` | 發行商 | 筆數 | 鏈分布 |
|---|---|---|---|
| 3 | bStock（`...B`） | 100 | 全在 BSC |
| 2 | xStocks（`...x`） | 269 | **Solana 139、BSC 130** |

- 規劃書寫的「269 檔 Solana xStocks」不正確，xStocks 同時發行在兩條鏈上。
- 因此 BSC 上同一檔股票可能同時有 bStock 和 xStocks 兩種代幣（例如 `TSLAB` 與 `TSLAx`）。
- 每筆資料有 `multiplier` 欄位（例如 `1.0072`），表示 1 顆代幣對應的股數，跨發行商比價時要考慮。

## 3. 公開 API 涵蓋情況

樣本：TSLA、NVDA、AAPL、MU、COIN、SPY、QQQ、MSTR、GOOGL、CRCL，共 10 檔。

| 來源 | BSC bStock | Solana xStocks | BSC xStocks | 提供的欄位 |
|---|---|---|---|---|
| GeckoTerminal | 10/10 | 10/10 | 10/10（池子少） | TVL、24h 交易量；費率寫在池名（`TSLAB / USDT 0.25%`） |
| DexScreener | 10/10 | 9/10（MUx 僅 2 池） | 1/10 | TVL、交易量；無費率 |
| DefiLlama Yields | 部分（漏 PancakeSwap V3） | 10/10 | 0/10 | `apyBase`、`apyMean30d`、`volumeUsd1d`、費率（`poolMeta`）；混有借貸池需過濾 |

### 範例：TSLA

BSC（GeckoTerminal）：

| 池子 | TVL | 24h 交易量 |
|---|---|---|
| PancakeSwap V3 `TSLAB/USDT 0.25%` | 205 萬 | 197 萬 |
| PancakeSwap V3 `TSLAB/USDT 1%` | 14 萬 | 6 萬 |
| Uniswap `TSLAB/USDT 0.05%` | 5 萬 | 50 萬 |

DefiLlama 對 TSLAB 只收錄了上表的 Uniswap 小池，**漏掉最大的 PancakeSwap V3 池**。

Solana（DefiLlama）：

| 池子 | TVL | APY | 30 天平均 APY |
|---|---|---|---|
| Raydium CLMM `TSLAx/USDC 0.1%` | 239 萬 | 28.7% | 25.1% |
| Orca `TSLAx/USDC` | 10.6 萬 | 37.0% | 42.5% |

## 4. 歷史資料

- GeckoTerminal `networks/{net}/pools/{address}/ohlcv/day`：實測回傳 **60 天**日線，含收盤價與 USD 交易量。BSC 可回補 30 天 TWAP 所需的交易量。
- **沒有歷史 TVL**：GeckoTerminal 只提供當下的 `reserve_in_usd`。歷史 TVL 必須自己定期存快照。

## 5. 限額與批次

- GeckoTerminal 免費額度約 30 次/分鐘，連續請求即觸發 HTTP 429。
- 批次端點 `networks/{net}/pools/multi/{addresses}`：以 3 個池子實測成功。一次上限 30 個是依官方文件的記憶，**未實測**。
- 代幣總數約 370（bStock 100 + xStocks 269），逐一查詢池子清單約需 13 分鐘。

## 6. 資料品質觀察

- **APY 算法不一致**：GeckoTerminal 不提供 APY，DefiLlama 有自己的算法。自行以 `24h 交易量 × 費率 ÷ TVL × 365` 估算時，對 CLMM 池是粗估（手續費只分給區間內流動性）。尚未與幣安錢包顯示的 APY 對照。
- **挖礦獎勵 APY**（例如 CAKE 獎勵）在公開來源中基本抓不到。
- **迷因幣配對很多**：例如 `TeslaSI/TSLAB`（TVL 18 萬、24h 交易量 49 萬）、`Roadster/TSLAB`。
- **仿冒代幣**：搜尋「牛来」出現多個不同地址的同名代幣（`NiuLai`、`NIULAI`），交易量趨近於零；真正的牛来主要池子都指向 `0xbeea1d618e533a387d941f58a7d4c9b7bd377777`。搜尋「幣安人生」只找到交易量為 0 的小池，疑似仿冒，未能確認正確地址。
- **股票 × 迷因幣的大池**：`QQQB/牛来`（PancakeSwap V2）TVL 約 113 萬。

## 7. Robinhood Chain（Chain ID 4663）

### 代幣清單：官方公開 API

- `GET https://api.robinhood.com/rhj/assets`，免登入。實測 **195 檔**，全部部署在 4663、狀態皆為 `ASSET_STATUS_ACTIVE`。
- 每檔欄位：`tokenSymbol`、`deployments[].contractAddress`、`currentMultiplier` / `pendingMultiplier`（分割、配息調整）、**`isin`**、`tradingCapabilities`（各交易時段是否可交易）、`tokenDecimals`（18）。
- 抽查 GeckoTerminal 上 7 檔股票池的代幣地址（NVDA、SPY、CRCL、MSTR、SPCX、QQQ、USO），**全部與官方清單一致**；第三方整理（[SQD](https://sqd.dev/learn/robinhood-tokenized-stocks/)）的 NVDA、SPY 地址也一致。
- 不在官方清單的代幣可視為第三方發行。例：`AAPLx3L`（3 倍槓桿 AAPL，TVL 約 1,057 萬）不在清單中。
- 官方文件（[docs.robinhood.com/chain/stock-tokens](https://docs.robinhood.com/chain/stock-tokens/)）：鑄造/贖回時段為週一 02:00 至週六 02:00（CET/CEST），鏈上交易 24/7 不受限。

### 池子資料

| 來源 | 涵蓋 | 說明 |
|---|---|---|
| GeckoTerminal | **有** | 網路 ID `robinhood`；收錄 50 個 DEX（Uniswap V2/V3/V4、PancakeSwap、Aerodrome、Ramses、Sushi 等） |
| DefiLlama Yields | 無 LP 池 | 81 個池子幾乎都是借貸（Morpho、Spark、LayerBank），沒有 Uniswap 等 DEX |
| RPC `rpc.mainnet.chain.robinhood.com` | 可連線 | `eth_chainId` 回傳 `0x1237`（4663） |

依 24h 交易量排序的前 60 個池子中，含官方股票代幣的有 16 個：Uniswap V3 7 個、**Uniswap V4 7 個**、Aerodrome 1 個、Ramses 1 個。主要股票池：

| 池子 | TVL | 24h 交易量 |
|---|---|---|
| Uniswap V3 `NVDA/USDG 0.05%` | 301 萬 | 527 萬 |
| Uniswap V3 `CRCL/USDG 0.3%` | 287 萬 | 454 萬 |
| Uniswap V3 `USO/USDG 0.3%` | 204 萬 | 154 萬 |
| Uniswap V3 `SPY/WETH 0.05%` | 197 萬 | 305 萬 |
| Uniswap V4 `MSTR/USDG 0.25%` | 170 萬 | 169 萬 |
| Uniswap V4 `SPY/NVDA 0.025%` | 166 萬 | 236 萬 |

- 隨機抽 12 檔官方股票，每檔都有池子；冷門股最大池 TVL 僅數千美元（如 SLS 4,383、IBRX 5,146）。
- **歷史資料**：`NVDA/USDG 0.05%` 的 `ohlcv/day` 回傳 60 天日線，與 BSC 相同。
- **V4 池**：GeckoTerminal 不顯示池子掛載的 hook。部分 V4 池名稱沒有費率（例如 `SPCX / USDG`），疑為動態費率，無法用公式估算 APY。
- **主要報價幣 USDG**（Paxos Global Dollar），GeckoTerminal 上地址為 `0x5fc5360d0400a0fd4f2af552add042d716f1d168`，**尚未與 Paxos 官方核對**。

## 8. 尚未調查

- 幣安 K 線 API 是否收錄迷因幣、是否收錄 Robinhood Chain
- 公式估算的 APY 與幣安錢包顯示值的差距
- Uniswap V4 池的 hook 能否從鏈上讀取（PoolManager 合約）
- USDG 合約地址的官方核對
