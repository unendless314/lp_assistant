# 架構文件

> 狀態：初稿（2026-10-26）。取代 `architecture-draft.md`（已刪除，內容可從 git 紀錄查閱）。
> 需求以 [`prd.md`](prd.md) 為準。

## 0. 文件地圖

| 文件 | 管什麼 | 條文編號 |
|---|---|---|
| [`prd.md`](prd.md) | 要做什麼、為什麼；驗收條件 | `F*-AC*`、`NFR-AC*` |
| 本文件 | 模組邊界、排程、部署、技術選型 | — |
| [`spec/calc.md`](spec/calc.md) | 公式、門檻、狀態判定、排序 | `CALC-*` |
| [`spec/sources.md`](spec/sources.md) | 外部資料來源契約 | `SRC-*` |
| [`spec/data-model.md`](spec/data-model.md) | 登記表、資料庫、設定檔、輸出 JSON | `DATA-*` |
| [`spec/ui.md`](spec/ui.md) | 頁面呈現與互動 | `UI-*` |
| [`spec/test.md`](spec/test.md) | 測試策略與追溯矩陣 | — |
| [`research/`](research/) | 有日期的實測紀錄，不隨規格更新 | — |

PRD 中的「計算規格」「UI 規格」「測試規格」分別對應 `calc.md`、`ui.md`、`test.md`；「數據規格」拆成 `sources.md`（外部來源）與 `data-model.md`（內部資料）。

**維護原則**

- 每個概念只在一份文件中定義，其他文件以編號引用，不重抄。
- 規格只寫系統**現在**的行為；版本範圍（第一版做什麼、不做什麼）只寫在 PRD。
- 條文編號永久不重用；廢止的條文保留編號並標示「已廢止」。
- 一份規格超過約 500 行時再考慮拆分；不到約 50 行的內容併入相鄰文件。

---

## 1. 系統概觀

```
 官方清單 ─┐                                         ┌─────────────┐
 GeckoTerminal ─┤   ┌────────────┐   ┌─────────┐    │ latest.json │   ┌──────────┐   ┌────────────┐
 EVM／Solana RPC ─┼─▶│  排程程序   │──▶│ SQLite  │──▶│  （匯出）    │──▶│ 靜態網站  │──▶│ Cloudflare │──▶ 訪客
 yfinance ─┤   │（單一程序） │   └─────────┘    └─────────────┘   │（Caddy） │   └────────────┘
 DefiLlama ─┘   └────────────┘        │                                    └──────────┘
                                     └──▶ 每日備份（VPS 以外）
```

- 後端只有一個常駐的排程程序：抓資料、寫入 SQLite、計算、匯出 JSON。
- 前端是純靜態檔案，只讀 `latest.json`。訪客的任何操作都不會打到後端程式，也不會觸發外部 API（NFR-AC2、NFR-AC8）。
- 沒有對外的 API 伺服器、沒有資料庫連線埠對外開放、沒有任何錢包憑證（NFR-AC1）。

---

## 2. 技術選型

| 項目 | 選擇 | 理由 |
|---|---|---|
| 後端語言 | Python 3.13 | 可直接移植參考專案的數學模組 |
| 套件管理 | `uv` | — |
| 品質工具 | `ruff`、`mypy --strict`、`pytest`、`import-linter` | `import-linter` 強制 §4 的依賴方向 |
| HTTP | `httpx` | 同步即可；限速才是瓶頸，不需要非同步 |
| 設定 | `pydantic` 驗證 YAML | 設定錯誤時整個工作失敗，不使用部分內容（DATA-CFG-2） |
| 資料庫 | 標準庫 `sqlite3`（WAL） | 單一寫入者、資料量小；備份簡單 |
| 股價 | `yfinance`（鎖定版本） | PRD 已定；封裝在單一模組（SRC-YF-3） |
| 前端 | Vue 3 + Vite + TypeScript | 卡片、展開、搜尋、語系切換的狀態管理需求適中 |
| 前端測試 | Vitest（邏輯）、Playwright（端對端） | — |
| 網頁伺服器 | Caddy | 自動 HTTPS 設定簡單；只服務靜態檔 |

---

## 3. 目錄結構

```
lp_assistant/
├── backend/
│   ├── pyproject.toml
│   ├── src/lp_assistant/
│   │   ├── domain/        # 資料模型（frozen dataclass、enum），零依賴
│   │   ├── engine/        # 純函式：calc.md 的全部內容與登記表狀態機
│   │   │   ├── volatility.py   # 移植自參考專案（年化改為 252）
│   │   │   ├── il.py           # 移植自參考專案
│   │   │   ├── apy.py          # 日 APY、中位數、趨勢
│   │   │   ├── status.py       # 池子狀態判定
│   │   │   ├── ranking.py      # 選取與排序
│   │   │   ├── registry.py     # 登記表狀態機、收錄過濾、股票歸屬
│   │   │   └── classify.py     # 報價資產分級、V4 排除
│   │   ├── builtin/       # 系統內建資料：核心報價資產、DEX 對照表、槓桿 ETF 名單
│   │   ├── sources/       # 外部來源轉接器，每個來源一個模組
│   │   │   ├── http.py         # 共用客戶端：逾時、重試、限速
│   │   │   ├── binance_bstock.py
│   │   │   ├── xstocks.py
│   │   │   ├── robinhood.py
│   │   │   ├── geckoterminal.py
│   │   │   ├── evm.py
│   │   │   ├── solana.py
│   │   │   ├── prices.py       # yfinance 封裝
│   │   │   └── defillama.py
│   │   ├── storage/       # SQLite schema、遷移、repository 函式
│   │   ├── jobs/          # 排程工作：組合 sources、storage、engine
│   │   ├── export/        # 產生 latest.json
│   │   ├── scheduler.py   # 常駐程序
│   │   ├── settings.py
│   │   └── cli.py
│   └── tests/
├── frontend/
│   ├── src/
│   ├── locales/zh-TW.json
│   └── tests/
├── shared/                # 前後端共用的測試案例（例：ranking_cases.json）
├── config/                # settings.yaml、overrides.yaml、devs_pick.yaml
├── deploy/                # systemd unit、Caddyfile、備份腳本
├── docs/
└── reference/             # 參考專案，唯讀，不被 import
```

---

## 4. 模組邊界與依賴方向

```
domain ◀── engine ◀── jobs ──▶ sources ──▶ domain
             ▲          │
             │          ▼
          export ──▶ storage ──▶ domain
```

- `engine` 只能 import `domain`、`builtin` 與標準庫（不含 `datetime.now`、`random`、網路與檔案 I/O）。現在時間由呼叫端傳入。這讓 [`calc.md`](spec/calc.md) 的每一條都能用純單元測試驗證。
- `sources` 只做「抓取 → 驗證 → 轉成 `domain` 模型」（[`sources.md`](spec/sources.md) §0），不判斷、不計算、不寫資料庫。
- `storage` 只做讀寫，不含業務規則。
- `jobs` 與 `export` 是唯一把各層接起來的地方。
- 以上規則寫成 `import-linter` 契約，CI 中違反即失敗。

**改動的影響範圍**（PRD NFR「可維護性」）：

| 改動 | 影響 |
|---|---|
| 改公式或門檻 | `engine`、`config/settings.yaml` |
| 換資料源（例如 yfinance → Stooq） | `sources` 中的單一模組 |
| 加新鏈 | `sources`（RPC 讀取）、`builtin`（核心資產、DEX 對照表）、`domain` 的鏈列舉 |
| 加新 DEX | `builtin` 的 DEX 對照表；集中流動性池另需 `sources` 的解碼器 |

---

## 5. 排程

### 5.1 單一程序、單一工作佇列

排程程序由 systemd 維持常駐（`Restart=always`），程序內只有一個工作執行緒，工作依序執行。理由：

- GeckoTerminal 的限速（約 30 次/分鐘）必須由所有工作共用；同一程序內的限速器才能準確控管。
- SQLite 只有一個寫入者，不需要處理鎖競爭。
- 程序重啟後從頭開始即可：每個工作都是冪等的，可重複執行。

### 5.2 工作清單

| 工作 | 時間（UTC） | 內容 | 失敗時 |
|---|---|---|---|
| `collect` | 每 30 分鐘 | 所有池子的快照（GeckoTerminal 批次 + 鏈上讀取） | 未取得的池子這次快照不完整，由新鮮度反映 |
| `export` | 每次 `collect` 之後（`collect` 失敗也照常執行，讓池子狀態隨時間正確轉為延遲、過期），以及每日工作之後 | 計算並輸出 `latest.json` | 保留上一份檔案 |
| `discover` | 每次 `collect` 之後 | 依序替一批代幣（預設 100 個，約 4 分鐘）找池子；新池子立即回補 60 天日線 | 下一輪從中斷處繼續 |
| `token_lists` | 每日 00:10，失敗時每小時重試到成功 | 抓三份官方清單，更新登記表（DATA-REG） | 依 DATA-REG-3 不累計下架天數 |
| `daily_close` | 每日 00:20 與 06:20 | 抓所有池子最近 3 天的日線（覆寫，以吸收資料源的延遲修正） | 下一次執行補上 |
| `prices` | 每日 23:00（美股收盤後） | 抓股價、重算 σ | 沿用上次 σ（CALC-VOL-6） |
| `compact` | 每日 01:00 | 90 天前快照彙整（DATA-STORE-3） | 下一次執行補上 |
| `backup` | 每日 01:30 | 備份資料庫到 VPS 以外的位置（DATA-STORE-5） | 寫入開發者紀錄 |
| `reconcile` | 每日 02:00 | DefiLlama 對照（CALC-CHK-1） | 只記錄 |

- **排程成功的定義**（中斷橫幅用，F6-AC18）：一次 `collect` + `export` 完整跑完，且 `collect` 至少取得一個池子的完整快照。成功時更新 `last_successful_run_at`。
- **各來源互相獨立**（NFR-AC3）：任一來源失敗只影響依賴它的池子或欄位，不中斷同一工作中其他來源的處理。
- **自動恢復**（NFR-AC4）：沒有需要人工清除的失敗狀態；來源恢復後，下一輪自然取得新資料。唯一例外是官方清單筆數驟降（SRC-LIST-1），只影響下架判定。

### 5.3 請求量估算

| 工作 | 每日請求數（GeckoTerminal） |
|---|---|
| `collect`：約 1,500 個池子 ÷ 每批 30 × 48 輪 | 約 2,400 |
| `discover`：約 2,600 個代幣地址，每日一輪 | 約 2,600 |
| `daily_close`：約 1,500 個池子 × 2 次 | 約 3,000 |
| 合計 | 約 8,000（額度約 36,000） |

池子與代幣數量為估計值（xStocks 約 1,160 檔 × 2 條鏈，加上 bStock 與 Robinhood）。實際數量上線後由 `runs` 紀錄觀察；接近額度時，`discover` 改為「沒有池子的代幣每 7 天查一次」。

---

## 6. 紀錄與觀測

- 每次工作寫入 `runs` 資料表：開始、結束、結果、各來源的成功／失敗筆數（NFR-AC10）。
- 業務層面需要開發者注意的事件寫入 `dev_log`（[`data-model.md`](spec/data-model.md) §4.1），例如費率不符、對照差距、歸屬無法判斷、新命中的槓桿關鍵字。
- 程式日誌輸出到 stdout，JSON Lines 格式，由 systemd journal 保存。
- CLI 查詢：`lpa report runs`、`lpa report devlog`、`lpa report registry`。
- 不另外架設監控服務；開發者以 CLI 與網頁上的中斷橫幅察覺問題。通知屬於第二版（PRD §9）。

---

## 7. 部署

- **主機**：使用者既有的 VPS。排程程序以非 root 使用者執行，只有 `data/`、`site/data/` 的寫入權限。
- **網頁**：Caddy 服務 `frontend` 建置產物與 `site/data/latest.json`。Cloudflare 在前：靜態資產長快取（檔名含雜湊）；`latest.json` 快取 5 分鐘。
- **部署方式**：`git pull` 後執行部署腳本（後端 `uv sync`、資料庫遷移、前端建置、重啟 systemd 服務）。
- **備份**：每日備份上傳到 Cloudflare R2 的專用 bucket（憑證只能寫入該 bucket）。每月以腳本還原最新備份並跑 `PRAGMA integrity_check` 與筆數比對（NFR-AC11）。
- **資料庫遷移**：schema 版本存在資料庫中，程式啟動時依序套用未執行的遷移腳本；遷移前自動備份。

---

## 8. 安全

- 伺服器不存放私鑰、助記詞或錢包憑證；沒有任何交易功能（NFR-AC1）。
- 唯一的憑證：可能使用的付費 RPC 金鑰（放 `.env`），以及 R2 備份憑證（限定單一 bucket、只能寫入）。
- 網頁沒有寫入端點（NFR-AC8），Caddy 只允許 `GET`、`HEAD`。
- 依賴套件鎖定版本，CI 跑 `pip-audit` 與 `npm audit`。

---

## 9. 從參考專案移植

| 參考專案檔案 | 處理 |
|---|---|
| `volatility.py` | 移植 Yang-Zhang、收盤價波動率、相對波動率到 `engine/volatility.py`；年化改為 252；相對波動率移除覆蓋率檢查（CALC-VOL-3） |
| `il_model.py` | 移植 `expected_il_fraction`、`breakeven_volatility`、`vol_richness_ratio` 到 `engine/il.py`；不移植 `richness_grade`（前端改用損耗比） |
| `risk_screen.py` | 只沿用門檻常數（費率上限、離群倍數、最少同儕數），規則依 CALC-STATE 重寫；不移植 `securityScore` |
| `range_model.py` | 不移植（區間模型延後，PRD F2） |
| `api.py`、`market_data.py`、`scan.py`、`cli.py` | 不移植 |
| `stablecoins.json` | 內容併入 `builtin` 的核心報價資產地址表（DATA-POOL-3） |
| 參考專案的測試 | 移植數學模組時一併移植對應的測試案例 |

移植的檔案開頭保留原 MIT 授權與版權聲明（`Copyright (c) 2026 0xLokiz`）（NFR-AC12）。

---

## 10. 已知的擴充點

僅記錄目前架構如何承接 PRD §9 的候選功能，不代表會做。

| 候選功能 | 承接方式 |
|---|---|
| 通知提醒 | 新增一個讀取匯出結果、比對門檻後推送的工作；不需要網頁寫入功能 |
| 淨收益歷史走勢、長期穩定度 | `pool_snapshots` 與 `pool_snapshots_daily` 已永久保存；匯出另一個按需載入的歷史檔 |
| 跨發行商比價 | `engine` 新增計算；`sources` 已有代幣價格 |
| 非美股 | DATA-REG-8 的交易所清單改為設定；`prices` 支援非美股代號 |
| 英文介面 | 新增 `locales/en.json` |
| 資金配比、區間試算 | 前端計算，`engine` 的公式以相同測試向量另實作一份 TypeScript 版本 |
