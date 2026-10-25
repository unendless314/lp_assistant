# 資料模型規格

> 狀態：初稿（2026-10-26）。
> 需求以 [`prd.md`](../prd.md) 為準。

## 0. 範圍與邊界

**本文件管**：系統內部的資料怎麼組織——資產登記表與其狀態機、股票與池子的歸屬規則、資料庫結構與保存策略、設定檔，以及對外的輸出格式（給前端的 JSON、CLI 的 JSON 輸出）。

**本文件不管**：外部資料怎麼抓（[`sources.md`](sources.md)）；數字怎麼算、狀態怎麼判定（[`calc.md`](calc.md)）；畫面（[`ui.md`](ui.md)）。

**條文編號**：`DATA-<主題>-<序號>`。編號永久不重用。

---

## 1. 識別碼

- **DATA-ID-1** `token_id` = `{chain}:{address}`（地址依 SRC-ALL-5 正規化）。
- **DATA-ID-2** `pool_id` = `{chain}:{pool_address}`。
- **DATA-ID-3** `stock_id`：標的有 ISIN 時為 `isin:{ISIN}`；沒有時為 `ticker:{正規化代號}`。正規化代號：轉大寫，`.`、`-`、`/` 一律換成 `.`（例：`BRK-B`、`BRK/B` → `BRK.B`）。
- **DATA-ID-4** `slug`：前端網址錨點用（F6-AC15），預設為正規化代號（例：`NVDA`、`BRK.B`）。兩個 `stock_id` 的代號相同時，ISIN 較小者保留原代號，其餘加上 `-{ISIN 末 4 碼}`。`slug` 可能隨新股票加入而改變；前端的關注清單存 `stock_id`，不存 `slug`。

---

## 2. 資產登記表

### 2.1 收錄

- **DATA-REG-1** 登記表的每一列是一個 `token_id`，記錄 `OfficialToken` 的欄位（[`sources.md`](sources.md) §1）加上：`stock_id`、`registry_status`、`first_seen_at`、`last_seen_at`、`missing_streak`、`excluded_reason`（若不收錄）。
- **DATA-REG-2** 官方清單出現新的 `token_id` 時自動新增，不需人工核准（F1-AC8）。登記表**沒有刪除操作**：代幣消失只改狀態（F1-AC10）。
- **DATA-REG-3** **有效更新**：某發行商的清單轉接結果為 `ok`（SRC-ALL-6）才算一次有效更新。結果為 `invalid` 或 `failed` 時，該發行商的所有代幣狀態與 `missing_streak` 都不變（F1-AC14）。

### 2.2 狀態機

`registry_status` 的值：`active`、`halted`（暫停交易）、`delisted`（官方已下架）。

- **DATA-REG-4** **下架計數**：每個 UTC 日結束時，對當日至少有一次有效更新的發行商：該發行商的代幣若出現在當日**最後一次**有效清單中，`missing_streak` 歸零；未出現則 `missing_streak + 1`。當日沒有有效更新的發行商，其代幣的 `missing_streak` 不變。`missing_streak ≥ DELIST_MISSING_DAYS` 時狀態轉為 `delisted`（F1-AC9）。
- **DATA-REG-5** **恢復與暫停**：

  | 目前狀態 | 事件 | 新狀態 |
  |---|---|---|
  | `active` | 有效清單中 `halted == true` | `halted` |
  | `halted` | 有效清單中 `halted == false` | `active` |
  | `active`、`halted` | `missing_streak` 達門檻 | `delisted` |
  | `delisted` | 重新出現在有效清單 | 依該筆的 `halted` 轉為 `active` 或 `halted`，`missing_streak` 歸零 |

  暫停狀態以有效更新的當下值為準，不需等日結束（F1-AC11）。
- **DATA-REG-6** 每次狀態變動與新增寫入 `registry_events`（時間、`token_id`、事件類型 `added`／`halted`／`resumed`／`delisted`／`restored`、前後狀態）（F1-AC13）。

### 2.3 收錄過濾

在官方清單中但不收錄的代幣仍寫入登記表，`excluded_reason` 註明原因，不產生任何卡片、不參與搜尋。過濾規則依序：

- **DATA-REG-7** **人工排除**：設定檔 `overrides.yaml` 中以 `token_id` 排除者（`MANUAL`）。
- **DATA-REG-8** **非美股**（F1-AC3、F1-AC4）：依序判斷，先符合者為準：
  1. `underlying_exchange_mic` ∈ {`XNYS`、`XNAS`、`ARCX`、`BATS`、`XASE`} → 美股。
  2. `underlying_exchange_mic` 為其他非空值 → 非美股（`NON_US`）。
  3. `underlying_exchange_mic` 為空且 `underlying_currency == USD` → 美股（處理 `PDDx` 等缺欄位的代幣）。
  4. 兩者皆空 → 依發行商預設：bStock、Robinhood 視為美股（兩者目前只發行美股，實作時以清單內容確認）；xStocks 視為非美股並寫入開發者紀錄。

  不使用 ISIN 國別前綴判斷（research 2026-10-25 §3：在美上市公司的 ISIN 可能是 `JE`、`IE`）。
- **DATA-REG-9** **槓桿與反向 ETF**（F1-AC5）：以下任一成立且不在允許名單中，即排除（`LEVERAGED`）：
  - 標的代號在內建的**槓桿 ETF 名單**中（初始值取自 research 2026-10-25 §4：`TSLL`、`TMF`、`UVXY`、`SQQQ`、`SOXL`、`SOXS`、`NVDL`、`MUU`、`SKUU`、`SKDD` 等）。
  - 標的名稱符合關鍵字（不分大小寫）：`2x`、`3x`、`-1x`、`ultrapro`、`ultra `（後接空白）、`short`、`bear`、`bull`、`leveraged`、`inverse`、`daily target`。

  內建的**允許名單**用來排除誤判，初始值：`RBC`（RBC Bearings）、`BLSH`（Bullish）、`JPST`（JPMorgan Ultra-Short Income）。關鍵字新命中的代幣一律寫入開發者紀錄，供開發者決定加入哪份名單。寧可誤排除也不誤收錄：誤收錄的槓桿 ETF 會因高波動被錯誤估算，而誤排除只是少一張卡片，且會被紀錄發現。

  **名稱來源**：關鍵字比對使用的標的名稱依序取自：(1) 發行商清單本身；(2) 同一張卡片（DATA-STOCK-1、DATA-STOCK-2）上其他發行商代幣的名稱；(3) Yahoo 該代號的證券名稱（SRC-YF-5）。三者都取不到時，代幣**不收錄**（`NAME_UNVERIFIED`），寫入開發者紀錄，並在之後每次清單更新時重試，取得名稱後自動依規則收錄。此規則讓每個收錄的代幣都經過關鍵字檢查（F1-AC5），且不需人工介入；被擋下的代幣在 Yahoo 上也查不到資料，本來就無法計算 σ，排除不會損失可排名的池子。名稱缺失不會使整份清單失效。
- **DATA-REG-10** 槓桿 ETF 名單、允許名單與核心報價資產地址表（DATA-POOL-2）屬於**系統內建資料**，隨程式碼維護，不放在可移除的人工設定檔中（F1-AC12）。

### 2.4 股票歸屬

- **DATA-STOCK-1** 每個收錄的代幣歸到一個 `stock_id`（一張卡片）。有 ISIN 的代幣依 ISIN 歸屬，ISIN 相同者合併，不論鏈、發行商、代號寫法；ISIN 不同者即使代號相同也不合併（F1-AC15）。
- **DATA-STOCK-2** 沒有 ISIN 的代幣依正規化代號找卡片：恰好一張有 ISIN 的卡片使用此代號時歸入該卡片；沒有時歸入 `ticker:{代號}` 卡片；有兩張以上（例如不同股票類別共用代號）時無法判斷，歸入 `ticker:{代號}` 卡片並寫入開發者紀錄。
- **DATA-STOCK-3** 卡片的顯示代號與公司名稱：優先取有 ISIN 來源的值，依發行商順序 xStocks、Robinhood、bStock 取第一個非空者。
- **DATA-STOCK-4** 同一 EVM 代幣的 `primary` 與 `wrapper` 地址歸到同一張卡片（F1-AC6），兩者的池子都收錄。

---

## 3. 池子

- **DATA-POOL-1** 池子的靜態屬性在第一次發現時寫入：`pool_id`、`chain`、`dex`、`kind`（`v2`／`clmm`）、`token0`、`token1`（含精度）、`name`、`created_at`、`discovered_at`。另有一個隨日線抓取更新的欄位 `volume_synced_through`（CALC-DAY-4、SRC-GT-5）。
- **DATA-POOL-2** **報價資產分級**（F5）：池子兩邊的代幣依序判斷：
  1. 在登記表中且已收錄 → 股票代幣。
  2. 在**核心報價資產地址表**中 → 核心。
  3. 其他 → 其他。

  至少一邊是股票代幣、另一邊是股票代幣或核心時，池子才可能收錄（F5-AC1）；否則池子的級別為「其他」，資料照常寫入資料庫，但不出現在卡片、不計入交易量（F5-AC2）。名稱或代號不參與判斷（F5-AC3）。
- **DATA-POOL-3** **核心報價資產地址表**（系統內建，以 `token_id` 為鍵）：

  | 鏈 | 代幣 | 類型 | 價格序列（非穩定幣） | 地址 | 依據 |
  |---|---|---|---|---|---|
  | BSC | USDT | 穩定幣 | — | `0x55d398326f99059ff775485246999027b3197955` | 參考專案 `stablecoins.json` |
  | BSC | USDC | 穩定幣 | — | `0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d` | 同上 |
  | BSC | U | 穩定幣 | — | `0xce24439f2d9c6a2289f741120fe202248b666666` | 同上 |
  | BSC | USD1 | 穩定幣 | — | `0x8d0d000ee44948fc98c9b98a4fa4921476f08b0d` | 同上 |
  | BSC | WBNB | 原生幣 | `BNB-USD` | `0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c` | **上線前須核對**官方來源 |
  | Solana | USDC | 穩定幣 | — | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | **上線前須核對** |
  | Solana | USDT | 穩定幣 | — | `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` | **上線前須核對** |
  | Solana | USDG | 穩定幣 | — | `2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH` | Paxos 官方文件（research 2026-10-23 §7） |
  | Solana | WSOL | 原生幣 | `SOL-USD` | `So11111111111111111111111111111111111111112` | **上線前須核對** |
  | Robinhood | USDG | 穩定幣 | — | `0x5fc5360d0400a0fd4f2af552add042d716f1d168` | Paxos 官方文件（同上） |
  | Robinhood | WETH | 原生幣 | `ETH-USD` | 待查 | **上線前須核對** |

  每一列必須附上可查證的官方來源；未核對的列不得上線。
  「類型」決定 σ 的算法：穩定幣用 CALC-VOL-2，原生幣用 CALC-VOL-3 並採「價格序列」欄的報價序列。本表是 CALC-VOL-4 對照表的唯一資料來源，程式中不得另外寫死代幣分類。
- **DATA-POOL-4** 股票配股票的池子同時屬於兩張卡片，資料只存一份（F3-AC2）。
- **DATA-POOL-5** V4／Infinity 池在寫入前就被排除（SRC-DEX-3），不存在於資料庫中，因此不可能出現在卡片、搜尋或交易量加總（F2-AC13）。
- **DATA-POOL-6** **未啟用 DEX**：`dex` 不在 DEX 對照表中，或在表上但展示狀態為 `候選`（[`sources.md`](sources.md) SRC-DEX-4）的池子，照常寫入 `pools` 並收集快照（之後啟用時已有歷史資料），標記為 `dex_not_enabled`；每個 `dex` ID 第一次出現這種池子時寫入開發者紀錄（不在表上為 `UNLISTED_DEX`，候選為 `DEX_NOT_ENABLED`，含池子數）。這類池子不收錄，不輸出（F2-AC27）。V4 排除（DATA-POOL-5）先於此規則：V4 池連資料都不保存。
- **DATA-POOL-7** **收集範圍**：
  | 池子 | 靜態屬性 | 快照（`collect`） | 日線（`daily_close`） | 目的 |
  |---|---|---|---|---|
  | 報價資產分級可收錄（DATA-POOL-2），不論 DEX 是否啟用、TVL 是否高於下限 | 保存 | 每輪 | 每日 | 收錄判定需要日平均 TVL（CALC-INC-1），低於下限的池子回升時才能判斷；候選 DEX 啟用時已有歷史 |
  | 「其他」級別 | 保存 | 不收集 | 不收集 | F5「保留資料」以靜態屬性滿足；分級改變（例如代幣加入登記表）時，下一輪起開始收集並依 SRC-GT-5 回補 60 天日線 |

  資料源回報池子不存在時，池子停止收集並寫入開發者紀錄，資料保留。

---

## 4. 資料庫

使用 SQLite（單一檔案，WAL 模式）。

### 4.1 資料表

| 資料表 | 主鍵 | 內容 | 可否重建 |
|---|---|---|---|
| `tokens` | `token_id` | 登記表（DATA-REG-1） | 部分：歷史狀態不可重建 |
| `registry_events` | 自增 | 登記表變動紀錄 | 否 |
| `list_fetches` | 自增 | 每次官方清單抓取的結果（`ok`／`invalid`／`failed`、原因、筆數） | 否 |
| `pools` | `pool_id` | 池子靜態屬性 | 是 |
| `pool_snapshots` | `(pool_id, ts)` | TVL、24h 交易量、兩個代幣美元價格、`fee_rate`、`lp_share`、L、√P、`complete` | **否，最重要的資產** |
| `pool_snapshots_daily` | `(pool_id, day)` | 超過 90 天後彙整的每日資料（DATA-STORE-3） | 否 |
| `pool_daily_volume` | `(pool_id, day)` | 外部日線的交易量；抓取涵蓋範圍內沒有成交的日子存明確的 0，沒有資料列表示未知（SRC-GT-4、CALC-AGG-3） | 部分：只能回補約 60 天 |
| `price_bars` | `(series, date)` | 股價與報價資產日 K 線 | 是 |
| `sigmas` | `series_key` | 最新 σ、樣本數、最後成功計算時間 | 是 |
| `runs` | 自增 | 每次排程工作的開始、結束、結果、各來源結果（NFR-AC10） | 否 |
| `dev_log` | 自增 | 開發者紀錄（費率不符、對照差距、無法判斷的歸屬、新命中的關鍵字等） | 否 |

- **DATA-STORE-1** 日 APY、中位數、狀態等衍生值**不存成權威資料**，每次輸出時從上表重新計算；需要快取時可另存，但快取可隨時刪除重建。
- **DATA-STORE-2** 所有時間欄位存 UTC ISO 8601。金額存浮點數（展示用途精度足夠）；鏈上原始整數（L、√P）以字串存，避免超過 64 位元。

### 4.2 保存與彙整

- **DATA-STORE-3** `pool_snapshots` 保留最近 90 天的原始資料。更早的日子，凡在 `pool_daily_volume` 有交易量或有完整快照者，每日彙整成 `pool_snapshots_daily` 一筆：
  - **觀測值**：TVL 平均、最高、最低（只用當日 `complete` 快照；當日沒有完整快照時為空）；當日交易量（取自 `pool_daily_volume`）。
  - **已決定的計算輸入**：`denom_usd`（CALC-APY-2／CALC-APY-3）、`tvl_denom_usd`（池子平均 APY 的分母，CALC-APY-7）、`fee_rate`、`lp_share`、`approx`。彙整時以 `engine` 中與每日 APY 相同的函式決定（含 CALC-APY-4 的近似回退），之後不再重新選取。

  因此彙整前後算出的每日數值一致（NFR-AC5），回補日與斷線日也不例外。已決定的計算輸入是 PRD 列舉之外的必要欄位：只存觀測值時，集中流動性池與近似日的歷史 APY 都無法重算。
- **DATA-STORE-4** 彙整在同一個交易中完成：先寫入 `pool_snapshots_daily`，驗證筆數，再刪除原始快照。
- **DATA-STORE-5** 每日備份資料庫（SQLite online backup）到 VPS 以外的位置，保留最近 30 份每日備份與每月一份長期備份。備份檔須能以 `sqlite3` 開啟並通過 `PRAGMA integrity_check`（NFR-AC11）。
- **DATA-STORE-6** 外部回應原始檔存於 `data/raw/{source}/{YYYY-MM-DD}/`，gzip，保留 30 天（SRC-ALL-4），不納入備份。

---

## 5. 設定檔

| 檔案 | 內容 | 可移除 |
|---|---|---|
| `config/settings.yaml` | [`calc.md`](calc.md) §1 的所有門檻、排程頻率、RPC 端點、限速參數 | 否（缺少時用程式內預設值） |
| `config/overrides.yaml` | 以 `token_id` 排除代幣、為代幣加註記 | **是**（F1-AC12） |
| `config/devs_pick.yaml` | Dev's Pick：`stock_id` 列表與短評，依檔案順序顯示（F6-AC21） | 是（缺少時區塊不顯示） |
| `.env` | 需要金鑰的 RPC 端點（若使用） | — |

- **DATA-CFG-1** 系統內建資料（核心報價資產地址表、DEX 對照表、槓桿 ETF 名單與允許名單）放在程式碼中，不在 `config/` 下。
- **DATA-CFG-2** 所有設定檔在每次工作開始時載入並驗證，格式錯誤時該次工作失敗並記錄，不使用部分內容。
- **DATA-CFG-3** 設定檔與 `.env` 中不得出現私鑰、助記詞或錢包憑證（NFR-AC1）。

---

## 6. 輸出給前端的 JSON

前端只讀一個靜態檔 `data/latest.json`，每次匯出整份覆寫（先寫暫存檔再原子性改名）。

### 6.1 頂層

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-10-26T12:30:00Z",        // 本次匯出時間
  "last_successful_run_at": "2026-10-26T12:30:00Z", // 最後一次成功完成的收集＋匯出（橫幅判斷，F6-AC18）
  "thresholds": { "freshness_delayed_hours": 2, "freshness_stale_hours": 24, "pipeline_banner_hours": 2 }, // 前端唯一的門檻來源（UI-FRESH）
  "stocks": [ /* 6.2，所有收錄代幣的卡片，含情況 C */ ],
  "pools":  { /* pool_id → 6.3 */ },
  "ranking": [ /* 市場收益排行的 stock_id 順序（CALC-RANK-5） */ ],
  "devs_pick": [ { "stock_id": "...", "comment": "..." } ]
}
```

### 6.2 股票卡片

```jsonc
{
  "stock_id": "isin:US88160R1014",
  "slug": "TSLA",
  "ticker": "TSLA",
  "name": "Tesla, Inc.",
  "case": "A",                      // A／B／C（CALC-RANK-4）
  "volume_24h_usd": 3520000,        // CALC-RANK-3
  "best_pool_id": "bsc:0x...",      // 情況 A 才有
  "best_net_yield": 0.013,
  "best_approx": false,
  "best_hints": ["anomaly"],        // 最佳池子的提示類標記（F6-AC7）
  "primary_reason": null,           // 情況 B 的主要原因狀態代碼（CALC-RANK-6）
  "tokens": [
    { "token_id": "bsc:0x...", "chain": "bsc", "issuer": "bstock", "symbol": "TSLAB",
      "address": "0x...", "address_role": "primary", "explorer_url": "https://bscscan.com/token/0x...",
      "registry_status": "active" }
  ],
  "pool_ids": ["bsc:0x...", "solana:..."],
  "fee_groups": [ { "default_pool_id": "bsc:0x...", "other_pool_ids": ["bsc:0x..."] } ]  // CALC-RANK-8
}
```

### 6.3 池子

```jsonc
{
  "pool_id": "bsc:0x...",
  "chain": "bsc", "dex": "pancakeswap-v3-bsc", "dex_name": "PancakeSwap V3", "kind": "clmm",
  "pool_url": "https://pancakeswap.finance/...",            // F6-AC10
  "sides": [                                                // 池子兩邊的代幣，順序同鏈上 token0、token1；池子所屬的卡片由 sides[].stock_id 推導（股票配股票時有兩張）
    { "token_id": "bsc:0x...", "symbol": "TSLAB", "kind": "stock", "issuer": "bstock", "stock_id": "isin:US88160R1014" },
    { "token_id": "bsc:0x55d3...", "symbol": "USDT", "kind": "core", "issuer": null, "stock_id": null }
  ],
  "pair_label": "TSLAB/USDT",                               // 只供顯示；判斷發行商與另一邊股票一律用 sides
  "fee_rate": 0.0025,
  "tvl_usd": 2060000, "volume_24h_usd": 1360000,
  "apy_7d": 0.031, "apy_7d_approx": false,
  "apy_30d": 0.025, "apy_30d_approx": false,               // 缺值為 null
  "trend": "up",                                            // up／down／null
  "pool_avg_apy_7d": 0.604,                                 // 只有 clmm 有
  "net_yield": 0.013,
  "fee_loss_ratio": 0.58,                                   // 數字、"inf"，或 null（無法計算時）
  "headroom": 0.31,
  "history_days": 45,
  "status": { "primary": null, "secondary": [] },           // 排除類狀態代碼
  "hints": ["delayed"],                                     // 提示類：delayed／anomaly／volatile
  "last_complete_snapshot_at": "2026-10-26T12:00:00Z",      // 從未有完整快照時為 null
  "dev": { "reason_codes": [] }                             // F2-AC20；前端不顯示
}
```

- **DATA-OUT-1** 比率一律為小數，不做四捨五入；格式化由前端依 CALC-DISP 處理。未計算的數值（例如資料不足時的 `apy_7d`）為 `null`。
- **DATA-OUT-2** 狀態代碼：排除類 `delisted`、`halted`、`error`、`not_computable`、`stale`、`insufficient_history`；提示類 `delayed`、`anomaly`、`volatile`。前端依代碼查語系檔取得顯示文字，`error` 與 `not_computable` 對應同一段文字（F2-AC20）。
- **DATA-OUT-3** 「其他」級別的池子、低於 TVL 下限的池子、未啟用 DEX 的池子不輸出（F5-AC2、F2-AC3、F2-AC27）。
- **DATA-OUT-4** 輸出中不得包含任何會讓瀏覽器呼叫外部資料 API 的網址（區塊瀏覽器與 DEX 頁面連結只在使用者點擊時開啟，不算）（NFR-AC2）。
- **DATA-OUT-5** 同樣的資料庫內容與同樣的 `now`，產生的 JSON 位元組完全相同：物件鍵依字母排序，陣列依 CALC-RANK 規則或 `id` 排序（F6-AC23）。

---

## 7. CLI 的 JSON 輸出

CLI 查詢指令（[`../architecture.md`](../architecture.md) §6）加上 `--json` 時的輸出。使用者是開發者的腳本與同機 agent（[`../architecture.md`](../architecture.md) §10），因此與 `latest.json` 一樣視為對外介面。

- **DATA-CLI-1** 輸出一個 JSON 物件到 stdout，頂層含 `schema_version`（整數）、`generated_at`（UTC ISO 8601）與資料本體；錯誤訊息只寫到 stderr，並以非零結束碼結束，stdout 不混入非 JSON 內容。
- **DATA-CLI-2** 欄位命名、狀態代碼與比率單位與 §6 相同（DATA-OUT-1、DATA-OUT-2），同一個概念不在兩種輸出中用不同名稱。
- **DATA-CLI-3** 新增欄位不升版；刪除、改名或改變欄位意義時，`schema_version` 加一。`latest.json` 的 `schema_version` 採相同規則。
- **DATA-CLI-4** 查詢指令只讀不寫：以唯讀模式開啟資料庫，不寫入任何資料表或檔案（包括 `runs` 與 `dev_log`）。
