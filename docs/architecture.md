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
- **排程時間一律以 UTC 解讀**，不依賴主機的時區設定：排程器以 UTC 計算觸發時間，不使用系統 cron 或任何讀取本地時區的排程方式。理由：主機可能位於任何時區，且當地可能有夏令時間（例如德國），依本地時間會讓實際執行時間隨搬遷或季節改變。主機時區建議設為 UTC，便於對照日誌，但程式不得依賴此設定。

### 5.2 工作清單

| 工作 | 時間（UTC） | 內容 | 失敗時 |
|---|---|---|---|
| `collect` | 每 30 分鐘 | DATA-POOL-7 收集範圍內池子的快照（GeckoTerminal 批次 + 鏈上讀取）；「其他」級別的池子不收集 | 未取得的池子這次快照不完整，由新鮮度反映 |
| `export` | 每次 `collect` 之後（`collect` 失敗也照常執行，讓池子狀態隨時間正確轉為延遲、過期），以及每日工作之後 | 計算並輸出 `latest.json` | 保留上一份檔案 |
| `discover` | 每次 `collect` 之後 | 依序替一批代幣（預設 100 個，約 4 分鐘）找池子，約每 13 小時掃完全部代幣一輪；新池子立即回補 60 天日線 | 下一輪從中斷處繼續 |
| `token_lists` | 每日 00:10，失敗時每小時重試到成功 | 抓三份官方清單，更新登記表（DATA-REG） | 依 DATA-REG-3 不累計下架天數 |
| `daily_close` | 每日 00:20 與 06:20 各開始一輪，之後每次 `collect` 後處理一批（預設 150 個池子，約 6 分鐘），直到該輪跑完 | 抓 DATA-POOL-7 範圍內所有池子的日線（範圍見 SRC-GT-5，覆寫） | 下一次執行補上；落後時由 CALC-DAY-4 反映 |
| `prices` | 每日 04:00 | 抓股價、重算 σ | 沿用上次 σ（CALC-VOL-6） |
| `compact` | 每日 01:00 | 90 天前快照彙整（DATA-STORE-3） | 下一次執行補上 |
| `backup` | 每日 01:30 | 備份資料庫到 VPS 以外的位置（DATA-STORE-5） | 寫入開發者紀錄 |
| `reconcile` | 每日 02:00 | DefiLlama 對照（CALC-CHK-1） | 只記錄 |

- **時間點與資料源的更新節奏**：設計上不依賴資料源「準時」完成，晚到或修正的資料由下一次執行吸收。
  - `prices` 排在 04:00：美股收盤為美東 16:00，即 UTC 20:00（夏令）或 21:00（冬令）。04:00 時前一個交易日已收盤 7～8 小時，不受夏令冬令影響，資料源也有充分時間定案。CALC-VOL-1 不使用計算日當天的 K 線，因此 04:00 算出的 σ 恰好包含到前一個交易日；若資料仍有修正，SRC-YF-2 每日回補最近 10 天，隔天自動更正。
  - `daily_close` 排在 00:20 與 06:20：日線以 UTC 日切分，00:20 取得的前一日數字可能尚未定案，06:20 再抓一次並覆寫（SRC-GT-5）；抓到之前，窗口停在已同步的日子（CALC-DAY-4）。
  - `token_lists` 排在 00:10：官方清單與美股交易時段無關。
- **排程成功的定義**（中斷橫幅用，F6-AC18）：一次 `collect` + `export` 完整跑完，且 `collect` 至少取得一個池子的完整快照。成功時更新 `last_successful_run_at`。
- **各來源互相獨立**（NFR-AC3）：任一來源失敗只影響依賴它的池子或欄位，不中斷同一工作中其他來源的處理。
- **自動恢復**（NFR-AC4）：沒有需要人工清除的失敗狀態；來源恢復後，下一輪自然取得新資料。唯一例外是官方清單筆數驟降（SRC-LIST-1），只影響下架判定。

### 5.3 請求量估算

| 工作 | 每日請求數（GeckoTerminal） |
|---|---|
| `collect`：約 1,500 個池子 ÷ 每批 30 × 48 輪 | 約 2,400 |
| `discover`：每輪 100 個代幣 × 48 輪（約 2,600 個代幣地址，每日約掃 1.8 輪） | 約 4,800 |
| `daily_close`：約 1,500 個池子 × 2 次 | 約 3,000 |
| 合計 | 約 10,200（額度約 36,000） |

**單輪時間預算**：所有工作共用一個佇列與每分鐘 25 次的限速，因此大量抓取一律切成批次、排在 `collect` 之後，不可一次跑完。每 30 分鐘一輪的最壞情況：`collect` 約 50 次（2 分鐘）+ `discover` 100 次（4 分鐘）+ `daily_close` 150 次（6 分鐘）≈ 12 分鐘，餘裕足夠吸收重試與新池子回補。若 `daily_close` 一次跑完 1,500 個池子，約需 60 分鐘，會擋住兩輪 `collect`。

池子與代幣數量為估計值（xStocks 約 1,160 檔 × 2 條鏈，加上 bStock 與 Robinhood）。實際數量上線後由 `runs` 紀錄觀察；接近額度時，`discover` 改為「沒有池子的代幣每 7 天查一次」。

---

## 6. 紀錄與觀測

- 每次工作寫入 `runs` 資料表：開始、結束、結果、各來源的成功／失敗筆數（NFR-AC10）。
- 業務層面需要開發者注意的事件寫入 `dev_log`（[`data-model.md`](spec/data-model.md) §4.1），例如費率不符、對照差距、歸屬無法判斷、新命中的槓桿關鍵字。
- 程式日誌輸出到 stdout，JSON Lines 格式，由 systemd journal 保存。
- CLI 查詢：`lpa report runs`、`lpa report devlog`、`lpa report registry`。預設輸出給人看的表格；加 `--json` 輸出機器可讀格式，契約見 [`data-model.md`](spec/data-model.md) §7。查詢指令一律以唯讀模式開啟資料庫，與排程程序同時執行時不影響寫入（WAL 允許一個寫入者與多個讀取者並行）。
- 不另外架設監控服務；開發者以 CLI 與網頁上的中斷橫幅察覺問題。通知不由本系統推送，見 §10「同機 agent 存取」。

---

## 7. 部署

- **主機**：使用者既有的 VPS。排程程序以非 root 使用者執行，只有 `data/`、`site/data/` 的寫入權限。
- **網頁**：Caddy 服務 `frontend` 建置產物與 `site/data/latest.json`。Cloudflare 在前：靜態資產長快取（檔名含雜湊）；`latest.json` 快取 5 分鐘。
- **部署方式**：`git pull` 後執行部署腳本（後端 `uv sync`、資料庫遷移、前端建置、重啟 systemd 服務）。
- **備份**：每日備份上傳到 Cloudflare R2 的專用 bucket（憑證只能寫入該 bucket）。每月以腳本還原最新備份並跑 `PRAGMA integrity_check` 與筆數比對（NFR-AC11）。
- **資料庫遷移**：schema 版本存在資料庫中，程式啟動時依序套用未執行的遷移腳本；遷移前自動備份。
- **同機 agent（選用）**：若在同一台 VPS 上執行 agent 框架（§10），它以獨立的 systemd 服務執行，與排程程序互不依賴：agent 停止或出錯不影響排程與網頁，排程也不等待 agent。信任定位與維運政策見 §8。

---

## 8. 安全

- 伺服器不存放私鑰、助記詞或錢包憑證；沒有任何交易功能（NFR-AC1）。
- 本系統唯一的憑證：可能使用的付費 RPC 金鑰（放 `.env`），以及 R2 備份憑證（限定單一 bucket、只能寫入）。
- **同機 agent 的信任定位**：同機 agent 具一般主機操作能力（通用 shell、SSH、可寫專案路徑），是**受信任的主機操作者，不構成安全隔離**。agent 會讀到外部資料（例如官方清單中的代幣名稱），也會收到通訊軟體上的訊息，兩者都可能夾帶誘導它執行指令的內容（prompt injection）；本架構不宣稱能技術性地阻止被誘導或被入侵的 agent 越界。
  - **維運政策**：雲端 VPS 只執行、不修改。agent 依政策只透過資料介面（`latest.json`、CLI 查詢指令 `--json`）讀取，不修改本站的程式、資料與設定；程式與設定的變更一律在開發機完成，經 `git pull` 部署（§7）。此政策降低人為與模型誤操作的風險，但不是對 agent 的技術控制。
  - **唯讀資料介面的作用**：讓正常整合不會因查詢而改寫資料（DATA-CLI-4），並提供比直接讀資料庫更穩定、耦合更少的契約。它是防呆與穩定性設計，不是安全邊界。
  - **不新增對外入口**：通訊整合不得替本站新增公開的監聽埠或 Caddy 路由；agent 的 gateway 以對外連線（輪詢或長連線）與通訊平台溝通。若日後改用需要入站連線的 webhook，須另做入站驗證與安全審查。
  - **憑證**：agent 自己的 LLM 金鑰與通訊軟體 bot token 不放進本專案的 `.env`；它們不是錢包憑證，不違反 NFR-AC1。
  - **復原**：資料被意外改寫時，依賴 VPS 以外的每日備份（DATA-STORE-5）復原。
  - **日後若要成為真正的邊界**：部署後的程式、設定與虛擬環境改由另一個帳號持有、agent 不可寫，變更只能經由受控的部署帳號或 CI/CD 送入；agent 只拿到固定的查詢與通知工具，沒有通用 shell。目前不在範圍。
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
| 同機 agent 存取 | 同一台 VPS 上的 agent 框架（例如 Hermes Agent）透過本機介面讀取資料，再經由自己的 gateway 連到通訊軟體與使用者互動。本系統只提供本機資料介面：市場資料讀 `latest.json`，營運資料用 CLI `--json`（§6、[`data-model.md`](spec/data-model.md) §7）。不開網路 API，信任定位見 §8 |
| 通知提醒 | 由同機 agent 實現：定期讀取 `latest.json`（資料每 30 分鐘更新，讀取頻率不需更高）、比對門檻後以 agent 自己的通訊管道推送。本系統不新增推送工作，也不需要網頁寫入功能；使用者的持倉等個人資料留在 agent 端 |
| 淨收益歷史走勢、長期穩定度 | `pool_snapshots` 與 `pool_snapshots_daily` 已永久保存；匯出另一個按需載入的歷史檔 |
| 跨發行商比價 | `engine` 新增計算；`sources` 已有代幣價格 |
| 非美股 | DATA-REG-8 的交易所清單改為設定；`prices` 支援非美股代號 |
| 英文介面 | 新增 `locales/en.json` |
| 資金配比、區間試算 | 前端計算，`engine` 的公式以相同測試向量另實作一份 TypeScript 版本 |
