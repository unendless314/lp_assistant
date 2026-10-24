# 架構設計草稿 (Architecture Draft)

> ⚠️ **尚未採用**。這份是討論初期過早寫下的草稿，僅供日後撰寫正式架構文件時參考。
> 需求以 [`prd.md`](prd.md) 為準，資料來源實測以 [`research/2026-10-23-data-sources.md`](research/2026-10-23-data-sources.md) 為準。日期：2026-10-23
>
> **已知與 PRD（2026-10-24 修訂）衝突之處**，撰寫正式架構文件時以 PRD 為準：
> - §0「Solana 以 DefiLlama 為主」：已改為三條鏈都自算 APY，DefiLlama 只做對照（PRD §6）。
> - §0、目錄結構中的「幣安 K 線」：波動率已改用 yfinance 美股日 K 線（PRD F2）。
> - §2 的 APY 公式 `volume × fee_tier ÷ tvl × 365`：已改為全區間 LP 收益，分母用鏈上 L 換算，費率用 LP 實得費率並從鏈上讀取（PRD F2）。架構需新增鏈上 RPC 讀取（EVM 合約、Solana 帳戶）。
> - `apy.py` 的 TWAP/EWMA、APY 波動度折價：已改為 7 天日 APY 中位數，不做折價（PRD F2）。
> - §6 待確認事項中的 Robinhood Chain 資料來源、跨發行商價差：已於 PRD 定案。

---

## 0. 已確認的前提（來自 2026-10-23 的 API 實測）

| 結論 | 依據 |
|---|---|
| **不使用 `baw`**。伺服器端不需要任何錢包登入 | `baw defi investment-list` 需要錢包 session；公開 API 已能取得池子資料 |
| BSC 池子以 **GeckoTerminal** 為主 | 10/10 檔有資料；池名含費率階梯（`TSLAB / USDT 0.25%`）；DefiLlama 漏掉 PancakeSwap V3 |
| Solana 池子以 **DefiLlama** 為主，GeckoTerminal 輔助 | DefiLlama 有 `apyBase`、`apyMean30d`、`volumeUsd1d`、`poolMeta`（費率） |
| 代幣清單、K 線沿用 **幣安公開 API** | 免登入 |
| BSC 可回補歷史交易量 | GeckoTerminal `pools/{addr}/ohlcv/day` 回傳 60 天日線（含 USD 交易量） |
| **GeckoTerminal 沒有歷史 TVL** | 只有當下 `reserve_in_usd`，歷史 TVL 必須自己存快照 |
| 幣安 `type=2`（xStocks）= **Solana 139 + BSC 130**，非全在 Solana | 規劃書第六章的「269 檔 Solana」需修正 |
| 同一條鏈上也有不同發行商 | BSC 上同時有 `TSLAB`（bStock）與 `TSLAx`（xStocks） |
| GeckoTerminal 免費額度約 30 次/分鐘 | 實測連續請求即觸發 429 |

---

## 1. 目錄結構

```
lp_assistant/
├── reference/                 # 原專案，唯讀參考，不被 import
├── docs/
│   └── architecture.md        # 本文件
├── backend/
│   ├── pyproject.toml         # uv 管理
│   ├── src/lp_assistant/
│   │   ├── domain/            # 資料模型（純資料，零依賴）
│   │   │   ├── enums.py       # Chain, Issuer, Dex, PoolKind
│   │   │   └── models.py      # StockToken, Pool, PoolSnapshot, DailyVolume ...
│   │   ├── engine/            # 純數學，不碰網路/資料庫/時鐘
│   │   │   ├── volatility.py  # Yang-Zhang、相對波動率（移植自 reference）
│   │   │   ├── il.py          # 損益平衡波動率、Richness（移植）
│   │   │   ├── range.py       # 集中流動性區間、存活機率（移植）
│   │   │   ├── apy.py         # 手續費 APY 估算、TWAP/EWMA、APY 波動度（新）
│   │   │   ├── screen.py      # 過濾規則：TVL 下限、離群值、迷因幣配對（移植+新）
│   │   │   └── allocate.py    # 安全型 / 進取型配比、稀釋模型（新）
│   │   ├── providers/         # 外部 API → domain 模型的轉接器
│   │   │   ├── base.py        # Provider 介面（Protocol）
│   │   │   ├── http.py        # 共用 HTTP client：重試、限速、User-Agent
│   │   │   ├── binance_rwa.py # 代幣清單、K 線
│   │   │   ├── geckoterminal.py
│   │   │   └── defillama.py
│   │   ├── storage/           # SQLite 讀寫，對外只暴露 repository 函式
│   │   │   ├── db.py
│   │   │   ├── schema.sql
│   │   │   └── repo.py
│   │   ├── services/          # 組裝流程：呼叫 providers → 存 → 呼叫 engine
│   │   │   ├── discover.py    # 每日：代幣清單 → 找出所有池子
│   │   │   ├── collect.py     # 每 30 分鐘：池子快照
│   │   │   ├── backfill.py    # 新池子：回補 60 天日線
│   │   │   ├── compare.py     # 跨鏈/跨發行商/跨費率比較矩陣
│   │   │   └── export.py      # 產出給前端的 snapshot.json
│   │   ├── config.py          # pydantic-settings：門檻值、路徑、限速參數
│   │   └── cli.py             # 入口：discover / collect / backfill / export
│   ├── data/
│   │   └── stablecoins.json   # 各鏈穩定幣地址（沿用並補 Solana）
│   └── tests/
│       ├── engine/            # 純函式測試，不需 mock
│       ├── providers/         # 用錄好的 JSON fixture 測解析
│       └── fixtures/
└── frontend/                  # Vue 3 + Vite（Milestone 3 再建立）
```

### 依賴方向（強制）

```
domain  ←  engine  ←  services  →  providers  →  domain
                         ↓
                      storage  →  domain
```

- `engine` 只 import `domain` 和標準庫。不准 import `providers`、`storage`、`httpx`、`sqlite3`。
- `providers` 只負責「抓 + 轉成 domain 模型」，不做任何判斷與計算。
- `services` 是唯一可以把各層接起來的地方。
- 用 `import-linter` 寫成規則，放進 CI，違反即失敗。

這樣做的好處：改公式只動 `engine`，換資料源只動 `providers`，兩邊互不影響。

---

## 2. Domain 模型（Schema）

以 Python dataclass（`frozen=True`）表示。金額用 `float`（USD，展示用途精度足夠），費率與 APY 一律用**小數**（`0.0025` = 0.25%，`0.30` = 30%）。單位統一只在 provider 轉換時處理一次。

```python
class Chain(StrEnum):        BSC = "bsc";  SOLANA = "solana";  ROBINHOOD = "robinhood"
class Issuer(StrEnum):       BSTOCK = "bstock";  XSTOCKS = "xstocks";  ONDO = "ondo"
class PoolKind(StrEnum):     V2 = "v2";  CLMM = "clmm";  OTHER = "other"

@dataclass(frozen=True)
class StockToken:
    chain: Chain
    address: str               # EVM 一律小寫；Solana 保留原大小寫（區分大小寫）
    symbol: str                # TSLAB / TSLAx
    underlying: str            # TSLA
    issuer: Issuer
    multiplier: float          # 幣安清單提供，1 顆代幣 = multiplier 股（配息再投入會 >1）

@dataclass(frozen=True)
class Pool:                    # 池子的靜態屬性，discover 時寫入
    chain: Chain
    address: str
    dex: str                   # pancakeswap-v3 / raydium-clmm / orca ...
    kind: PoolKind
    fee_tier: float | None     # 0.0025；抓不到時為 None
    base: str                  # 代幣地址
    quote: str
    created_at: datetime | None

@dataclass(frozen=True)
class PoolSnapshot:            # 時間序列，每次 collect 一筆
    chain: Chain
    pool_address: str
    ts: datetime               # UTC
    tvl_usd: float
    volume_24h_usd: float
    reported_fee_apy: float | None    # 資料源自己算的（DefiLlama apyBase），僅供對照
    reward_apy: float | None          # 挖礦獎勵，多數來源抓不到
    source: str

@dataclass(frozen=True)
class DailyVolume:             # 日線，backfill 與每日彙整
    chain: Chain
    pool_address: str
    day: date
    volume_usd: float
    close_price_usd: float
    tvl_usd: float | None      # 回補的歷史日為 None，之後由快照補齊
    source: str
```

### 關鍵設計決定：跨鏈比較只用同一套 APY 算法

不同資料源的 APY 算法不一樣（DefiLlama 有自己的公式，GeckoTerminal 沒有 APY）。如果直接混用，跨鏈比較會帶入方法論的偏差，這正是本專案最不能錯的地方。

所以：**所有池子的手續費 APY 一律由 engine 用同一個公式算**

```
fee_apy = volume_24h_usd × fee_tier ÷ tvl_usd × 365
```

`reported_fee_apy` 只存起來做對照與異常偵測（兩者差太多就標記），不參與排名。

已知限制（要在前端標示）：
- 對 CLMM 池是粗估，因為手續費只分給區間內的流動性。
- 不含挖礦獎勵。
- 回補的歷史日用「當下 TVL」當分母，是近似值，自己的快照累積後會逐步取代。

---

## 3. 資料儲存（SQLite）

| 表 | 主鍵 | 寫入時機 |
|---|---|---|
| `tokens` | (chain, address) | discover，每日 |
| `pools` | (chain, address) | discover，每日 |
| `pool_snapshots` | (chain, address, ts) | collect，每 30 分鐘 |
| `pool_daily` | (chain, address, day) | backfill + 每日彙整 |
| `klines` | (chain, address, interval, open_time) | 計算波動率前補齊 |

**原始回應另存一份**：每次 API 回應以 gzip JSON 存到 `data/raw/{source}/{YYYY-MM-DD}/`，保留 30 天。provider 的解析邏輯日後修正時，可以拿原始資料重新處理，不用等重新收集。

`pool_snapshots` 是**不可重建的資產**（歷史 TVL 只有我們自己有），需要定期備份。

---

## 4. 排程與限速

代幣總數約 370（bStock 100 + xStocks Solana 139 + xStocks BSC 130），GeckoTerminal 免費額度約 30 次/分鐘，所以要依更新頻率拆成三個工作：

| 工作 | 頻率 | 請求量估計 |
|---|---|---|
| `discover`：每顆代幣找出它的池子 | 每日 1 次 | ~370 次（約 13 分鐘） |
| `collect`：更新已知池子的 TVL/交易量 | 每 30 分鐘 | 批次端點一次最多 30 池，數百個池子約 10~20 次 |
| `backfill`：新池子回補 60 天日線 | 發現新池子時 | 每池 1 次 |

`providers/http.py` 內建全域限速器（token bucket），所有 provider 共用，不依賴各自 `sleep`。

---

## 4.5 報價資產分級與自選代幣

池子依「另一邊的資產」分三級，名單放在 `backend/data/quote_assets.json`，**一律以合約地址比對，不用名稱**（迷因幣常有同名仿冒幣，例如實測搜尋「牛来」時出現多個不同地址的 `NiuLai` / `NIULAI`）。

| 級別 | 內容 | 處理方式 |
|---|---|---|
| `core` | 穩定幣、原生幣（WBNB、SOL）、其他股票代幣 | 自動納入排名 |
| `watchlist` | 使用者指定的代幣（例如牛来 `0xbeea1d618e533a387d941f58a7d4c9b7bd377777`） | 納入，用相對波動率評分，前端加標籤 |
| `other` | 其他所有代幣 | **照樣儲存**，但不顯示、不參與排名；之後加入白名單即有歷史資料 |

**自選池（純迷因幣池，例如 `牛来/USDT`）**：
- `discover` 的代幣來源 = 幣安股票代幣清單 + `watchlist` 代幣。
- 收集、APY 計算、波動率共用同一套流程。
- 沒有對應的美股標的，不進跨鏈比較矩陣，前端另開「自選池」頁面，不混進股票排行榜。
- 優先順序：先做「股票 × 自選代幣」的池子（如 `QQQB/牛来`，TVL 約 113 萬），純自選池頁面放在後面的里程碑。

---

## 5. 從 reference 移植的範圍

| reference 檔案 | 處理方式 |
|---|---|
| `volatility.py`、`il_model.py`、`range_model.py` | **移植**到 `engine/`，加型別，帶上原測試案例 |
| `risk_screen.py` | **移植規則**（門檻常數、離群值檢查）到 `engine/screen.py`；移除 baw 專屬的 `securityScore` |
| `scan.py`、`cli.py` | **不移植**，只參考判定規則（ENTER / WATCH / NO_TRADE） |
| `api.py`、`market_data.py` | **不移植**，baw 相關全部捨棄；幣安 URL 搬到 `providers/binance_rwa.py` |
| `stablecoins.json` | 搬到 `backend/data/`，補上 Solana USDC/USDT |

原專案是 MIT 授權，移植的檔案開頭需保留原作者版權聲明（`Copyright (c) 2026 0xLokiz`）。

---

## 6. 待確認事項

- [x] GeckoTerminal 批次端點 `networks/{net}/pools/multi/{addresses}` 可用（2026-10-23 以 3 個池子實測成功）。官方文件寫一次上限 30 個，尚未實測上限
- [x] 迷因幣配對的過濾規則 → 採用三級分類，見 §4.5
- [ ] 「幣安人生」的正確合約地址（GeckoTerminal 搜尋結果疑似仿冒幣，待使用者提供）
- [ ] 迷因幣的波動率來源：幣安 K 線 API 是否收錄，否則改用 GeckoTerminal 池子日線
- [ ] 同標的跨發行商的價差（溢價/折價）要不要做成一個比較維度
- [ ] Robinhood Chain 的資料來源（GeckoTerminal 是否已收錄，或需要自己讀 RPC）

---

## 7. 工具鏈

- Python 3.13、`uv`、`ruff`、`mypy --strict`、`pytest`、`import-linter`
- 執行期依賴盡量少：`httpx`、`pydantic-settings`、`typer`；資料庫用標準庫 `sqlite3`
