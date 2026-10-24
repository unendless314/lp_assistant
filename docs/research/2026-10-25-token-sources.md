# 股票代幣官方清單來源

> 調查日期：2026-10-25。外部 API 隨時可能改版，引用前請確認日期。

## 目的

確認三個發行商的代幣清單能否都取自發行商的官方來源，而不是第三方整理的清單。

## 結論摘要

1. **xStocks 有官方公開 API**，免登入，已寫在官方文件中。
2. **幣安轉列的 xStocks 清單（269 檔）地址全數與官方清單一致**，但官方清單有 1,474 檔，約為 5 倍。
3. **bStock 的發行商是幣安集團關聯企業**，幣安清單即官方來源。
4. xStocks 官方清單含非美股、槓桿與反向 ETF，需要過濾；部分代幣缺少交易所欄位。

---

## 1. xStocks 官方 API

- 端點：`GET https://api.xstocks.fi/api/v2/public/assets?page={n}`，從 0 開始，每頁 100 筆，以 `page.hasNextPage` 判斷是否還有下一頁。實測共 15 頁、**1,474 檔**。
- 官方文件：[docs.xstocks.fi/apis/openapi](https://docs.xstocks.fi/apis/openapi)。production 的 base URL 為 `https://api.xstocks.fi/api/v2`，文件寫明「Public endpoints are available without authentication」。未載明限額。
- 另有 `https://api.backed.fi/api/v1/token`（1,491 筆，單頁），多出 17 筆舊的 Backed `b` 前綴代幣（如 `bNVDA`），不屬於 xStocks，不採用。
- 每檔欄位：`symbol`、`isin`（代幣本身）、`underlyingSymbol`、**`underlyingIsin`**、`underlying.exchange.mic`、`underlying.currency`、`isTradingHalted`、`allowedOperations`、`deployments[]`（`network`、`address`、EVM 鏈另有 `wrapperAddressV2`）。
- 每檔都列出 11 條鏈的部署地址，包含 `BinanceSmartChain`、`Solana`；地址存在不代表有流動性。Solana 地址帶 `svm:` 前綴。
- **沒有 multiplier 欄位**；官方文件有 Corporate Actions 區段，未深入查。

## 2. 與幣安清單比對

幣安 `rwa/stock/detail/list/ai?type=2` 回傳 269 檔（Solana 139、BSC 130）：

| 結果 | 筆數 |
|---|---|
| 對到官方主地址（Solana） | 139 |
| 對到官方主地址（BSC） | 128 |
| 對到官方 `wrapperAddressV2`（BSC） | 2（`wPOPMTx`、`wTCENTx`，代號多一個 `w`） |
| 對不到 | 0 |

## 3. 標的掛牌地

| 掛牌地 | 標的幣別 | 筆數 |
|---|---|---|
| 美國交易所（XNYS、XNAS、ARCX、BATS、XASE） | USD | 1,163 |
| **缺交易所欄位** | USD | 21 |
| 倫敦 | GBP | 100 |
| 香港 | HKD | 79 |
| 歐陸各交易所 | EUR | 111 |

- 缺交易所欄位的 21 檔包括 `PDDx`、`JDx`、`BBx`、`CARTx`、`UVXYx`，實際都在美國掛牌。只看交易所欄位會誤判，需要備援規則（例如標的幣別 USD）。
- 標的 ISIN 的國別前綴不可靠：Aptiv、Amcor 為 `JE`，nVent 為 `IE`，但都在美國掛牌。
- ADR 的掛牌地為美國：`BABAx`（XNYS）、`TSMx`（XNYS）、`ASMLx`（XNAS）。
- 7 檔 `isTradingHalted = true`（如 `AXPx`、`WBDx`）；1 檔 `allowedOperations` 只剩 `Redemption`。

## 4. 槓桿與反向 ETF

以名稱關鍵字（`2x`、`3x`、`Ultra`、`Short`、`Bull`、`Bear`、`Leverage`）搜尋標的幣別 USD 的代幣，命中 20 檔，其中：

- 確實是槓桿或反向 ETF：`TSLLx`、`TMFx`、`UVXYx`、`SQQQx`、`SOXLx`、`SOXSx`、`NVDLx`、`MUUx`、`SKUUx`、`SKDDx` 等。
- **誤判**：`RBCx`（RBC Bearings）、`BLSHx`（Bullish）、`JPSTx`（JPMorgan Ultra-Short Income，非槓桿）。

官方資料的 `underlying.type` 皆為 null，沒有證券類型欄位可用。名稱判斷必須搭配人工確認。

## 5. bStock 發行商

- 發行商為 **BTech Holdings Limited，幣安集團關聯企業**，由 ADGM 金融服務監管局核准。2026-06-12 於幣安交易所上線，1:1 對應託管中的股票，BNB Chain 上為 BEP-20。
- 未找到 BTech 自己公開的代幣清單。
- 來源：[Binance 新聞稿（AAP / Cision）](https://www.aap.com.au/aapreleases/cision20260612ae82369/)、[BNB Chain blog](https://www.bnbchain.org/en/blog/introducing-bstocks-on-bnb-chain-trade-24-7-with-zero-fees-deploy-across-defi-protocols-with-full-self-custody)。

## 6. 對後續設計的影響

- xStocks 收錄範圍從 269 檔增加到約 1,184 檔（美股、扣除槓桿 ETF 前），每日找池子的請求數相應增加。依 GeckoTerminal 約 30 次/分鐘的限額，若每檔每條鏈查一次，需時超過 1 小時。架構規格需處理，例如沒有池子的代幣降低查詢頻率。
