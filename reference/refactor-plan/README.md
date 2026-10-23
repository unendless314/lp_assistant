# 新專案架構規劃與開發藍圖 (Refactor & Architecture Plan)

> **專案定位與來源說明**：  
> - **原始參考儲存庫**：[0xLokiz/bstocks-lp-assistant](https://github.com/0xLokiz/bstocks-lp-assistant)（詳細出處與 Commit 雜湊見 [`SOURCE.md`](../SOURCE.md)）。
> - 本資料夾已主動移除 `.git` 追蹤，純粹保留作為**量化演算法、風控規則與參考實作之學習樣板**，可安全嵌入其他父層 Git 專案中，避免巢狀倉庫衝突。
> - 未來將基於本文件規劃，啟動全新的獨立專案，實現跨鏈支援（BNB Chain、Solana、Robinhood Chain 等鏈上股票/代幣資產）、橫向利差分析與公開 Web 儀表板。

---

## 一、 核心願景與目標 (Vision & Goals)

打造一個**全網跨鏈、具備橫向收益率對比、多源 Data Provider 解耦的「RWA 代幣化股票 LP 量化投資終端」**。

1. **核心資產聚焦**：真實世界資產（RWA）、代幣化美股（Tokenized Stocks，如 TSLA, NVDA, AAPL, SpaceX 等）之流動性池（LP）。
2. **跨鏈全局視角（Cross-Chain Unified View）**：打破單鏈資訊孤島，橫向比對同一美股標的在不同公鏈上的真實手續費收益率。
3. **純唯讀安全架構（Read-Only by Design）**：
   - 伺服器端 **絕不存放任何錢包私鑰**、**不具備任何交易下單/資金調用功能**。
   - 專注於「市場數據採集、量化風險計算、視覺化呈現」，適合安全部署於公開 VPS 與網域。
4. **高內聚低耦合模組化**：
   - 將數據採集（Data Provider）、量化分析引擎（Quant Engine）、橫向對比模組（Cross-Chain Comparator）與可視化看板（Dashboard）徹底解耦。

---

## 二、 為什麼必須重構？（三大核心痛點與動機）

原專案雖然數學模型精湛，但在產品與架構層面存在致命缺陷：

### 1. 「單眼盲人」問題：作者人為屏蔽了 Solana 與其他公鏈
- 原專案硬編碼了 `BSTOCK_TYPE = 3`（僅限 BNB Chain 上的 bStock），並在 `stablecoins.json` 中漏掉非 EVM 鏈。
- **事實上，幣安官方後端早已收錄了 Solana 鏈上的 269 檔股票代幣（xStocks, `type=2`）**。原專案完全視而不見，導致使用者被困在單一鏈的視野中。

### 2. 錯失 RWA 股票代幣天生的「同風險、異收益」套利機會
- **無常損失風險完全相同**：無論是 BSC 上的 `TSLAB`、Solana 上的 `TSLAx`，還是 Robinhood 鏈上的代幣化特斯拉，底層都是美股 TSLA，其**真實歷史波動率 $\sigma$ 在全網是完全一致的**。
- **鏈上手續費收益天差地遠**：Solana 鏈上散戶活躍、換手率極高，手續費池分紅可能達 45%；而 BSC 可能沉澱資金多但交易量平淡，淨 APY 僅 12%。
- 原專案無法橫向比對，會把 BSC 的 12% 誤判為最佳選擇，讓投資者平白承擔相同的波動風險，卻平白損失巨額收益。

### 3. 原生資金配置邏輯過於原始
- 原專案僅在單一池子內做「打算存入 $10,000 是否會佔據該池 20% TVL」的簡單防稀釋檢查，無法跨鏈進行全局的最優資金權重調配。

---

## 三、 繼承本專案（`bstocks-lp-assistant`）的核心量化精華

新專案將完整借鑑並移植原專案最精華的**純數學量化與風控邏輯**：

1. **真實波動率估計**：
   - 採用 **Yang-Zhang (2000) OHLC 波動率模型**（比傳統收盤價波動率統計效率高 5~14 倍）。
   - 跨非穩定幣對（如 Token/ETH、Token/BNB）之時間戳對齊**相對波動率計算**。
2. **期權定價視角之「豐富度評級（Richness Score）」**：
   - 將 AMM LP 視為放空跨式期權（Short Straddle），推導損益平衡波動率：
     $$\sigma^* = \sqrt{8 \cdot \text{APY}}$$
   - 以 $\text{vol\_ratio} = \sigma_{\text{realized}} / \sigma^*$ 作為單一客觀篩選指標（`< 1` 代表補償高於承擔風險）。
3. **集中流動性（Concentrated Liquidity）區間推算**：
   - Uniswap V3 / Orca Whirlpools 資本效率倍數 $M$。
   - 基於 Brownian Motion 雙邊障礙反射級數（Double-barrier reflection series）推導一年內價格不脫離區間的精確存活率 $P(\text{active})$。
4. **前置數據清洗與安全過濾網**：
   - 剔除動態手續費突增（> 5%/swap）之虛假高 APY。
   - 剔除微型流動性池（TVL < $5,000 USD）。
   - 同行 APY 中位數離群值檢驗（防止單筆交易扭曲 24h 收益）。
   - 未審計外部 Hook（如 V4-style hooks）之風險提示與阻擋。

---

## 四、 新增核心模組：橫向收益率對比與資產配置 (Cross-Chain Comparator)

這是新專案的核心架構擴展，新增獨立的業務模組：

```
                    ┌────────────────────────────────────────┐
                    │       Web Dashboard (唯讀儀表板)        │
                    └───────────────────▲────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────┐
                    │  橫向收益率對比與資產配置模組 (新模組)   │
                    │  (CrossChainComparator & SizingEngine) │
                    └───────▲────────────────────────▲───────┘
                            │                        │
       ┌────────────────────┴───────────┐            │
       │   Quant & Risk Engine (純數學) │            │
       │ (Yang-Zhang / TWAP / Richness) │            │
       └────────────────────▲───────────┘            │
                            │                        │
  ┌─────────────────────────┴────────────────────────┴─────────────────────────┐
  │                        統一資料格式 (Normalized Schema)                     │
  ├─────────────────────────┬─────────────────────────┬────────────────────────┤
  │    BinanceBawAdapter    │ RobinhoodChainAdapter   │    SolanaDexAdapter    │
  │ (BSC: bStocks / Pancake)│ (Chain 4663: RPC / V3)  │(CT_501: xStocks/Raydium│
  └─────────────────────────┴─────────────────────────┴────────────────────────┘
```

### 1. 標的統一正規化索引 (Ticker Normalization Index)
- 建立映射表，將不同鏈的包裝代幣對齊到同一個美股 Underlying Ticker：
  - `TSLA` $\rightarrow$ `TSLAB` (BNB Chain), `TSLAx` (Solana), `TSLA` (Robinhood Chain)
  - `NVDA` $\rightarrow$ `NVDAB` (BNB Chain), `NVDAx` (Solana), `NVDA` (Robinhood Chain)
- 在計算波動率時，直接共用同一個 Underlying 美股標的的高階波動率 $\sigma$。

### 2. 橫向利差矩陣（Cross-Chain Yield Matrix）
針對同一股票代幣，即時輸出各鏈的收益與容量矩陣：
- 各鏈實質手續費率 vs 激勵代幣比例
- 各鏈 TVL 與 24h 交易量（換手率指標 $V/\text{TVL}$）
- 風險調整後真實淨 APY（Net APY）與 Richness 評級排名

### 3. 同 DEX 多費率階梯聚合與最佳費率選取 (Intra-DEX Multi-Fee-Tier Optimization)
在 Uniswap V3、PancakeSwap V3 或 Orca Whirlpools 中，同一個交易對經常同時存在多種手續費階梯（例如 `TSLAB/USDT 0.05%` vs `TSLAB/USDT 0.25%` vs `TSLAB/USDT 1.0%`）：
- **風險向量完全相同**：同鏈、同 DEX、同標的，其智能合約風險、發行商信用風險與無常損失完全一致。
- **「薄利多銷」vs「暴利少銷」的動態均衡**：
  - **0.05% 池**：手續費低，DEX 聚合器（1inch / Jupiter）最愛走此路由，交易量（Volume）通常極大。
  - **0.25% / 1% 池**：單筆手續費高 5~20 倍，即便交易量較少，只要有散戶直接在該池換幣，收益率可能反而勝出。
- **處理策略**：
  1. **剔除殭屍費率池（Zombie Pools Filter）**：自動過濾因人為誤建、TVL < $5,000 且 7 天無真實交易量的無效費率池。
  2. **純收益對決（Pure TWAP Net Yield Competition）**：直接以 7D/30D TWAP 淨 APY 判定誰是該 DEX 的最優手續費階梯。
  3. **UI 聚合摺疊（Sub-Tier Collapsible UX）**：在前端預設只展示該 DEX 的「最佳費率冠軍池」，並提供下拉展開「查看其他費率階梯（如 0.05% 與 0.25% 對比）」，避免同名池子重複洗版。

---

## 五、 量化演算法重大升級：時間加權收益率與機率分佈資金配比

為了解決現實中「某鏈當天 APY 暴衝，但長期收益在另一條鏈」的陷阱，引入兩大演算法升級：

### 1. 時間加權平均收益率 (TWAP / EWMA APY) 與收益持久度 (Fee Durability)
- **單日切片 APY 的致命傷**：DEX 報價的 APY 通常是過去 24 小時的交易量年化。如果昨天某鏈有一隻巨鯨大額換手，該鏈當天的 APY 會瞬間飆升數倍，次日又打回原形。
- **演算法改進**：
  - 引入 **7D / 30D 時間加權移動平均（TWAP / EWMA）**，計算平滑後的持續性收益：
    $$\overline{\text{APY}}_{\text{TWAP}} = \sum_{t=1}^{N} w_t \cdot \text{APY}_t$$
  - 計算**收益穩定度指標（Fee Volatility $\sigma_{\text{APY}}$）**：若某鏈的 APY 忽高忽低極不穩定，在推薦評分中施加波動懲罰折價（Haircut）。

### 2. 拒絕 0% / 100% 切割：基於機率分佈與容量約束的動態資金配比
- **為什麼不能非黑即白（0% 或 100% All-in）？**
  - **容量飽和與自我稀釋（Self-Dilution）**：若把 100% 資金一口氣全部塞進收益最高的那條鏈，你的本金可能會直接佔據池子 30% 以上的 TVL，導致手續費被嚴重稀釋，實際到手的 APY 崩跌。
  - **流動性與跨鏈手續費摩擦**：全額搬家有跨鏈橋手續費、滑點與時間成本。
  - **收益持久度的不確定性**：不同鏈的交易活躍度呈現隨機過程（Stochastic Process）。
### 2. 策略 A：【收益進取型（Alpha 模式 - 歷史 APY 驅動）】
- **核心思維**：以「追求最高淨 APY」為目標，同時防範自我稀釋與單日尖峰。
- **演算法公式**：
  將投資人預計投入的總資金 $C_{\text{total}}$ 視為最佳化分配問題：
  $$\max_{\{w_i\}} \sum_{i} w_i \cdot \overline{\text{Net APY}}_i - \lambda \sum_{i} w_i^2 \sigma_{\text{APY}, i}^2$$
  $$\text{subject to } \sum_{i} w_i = 1, \quad 0 \le w_i \cdot C_{\text{total}} \le \alpha \cdot \text{TVL}_i$$
  其中 $\alpha$ 為最大池子佔比安全上限（通常為 10%~15%），避免本金自我稀釋。
- **適合客群**：中小資金、主動追求高報酬率、願意承擔適度鏈間流動性變化的進取型投資者。

### 3. 策略 B：【安全防禦型（Beta 模式 - TVL 深度共識加權）】
- **核心思維**：不盲目追逐高收益，以「全網資金投票的林迪效應（Lindy Effect）」為依歸，流動性深度最深、共識最強者配比最高。
- **演算法公式**：
  純粹按照各鏈該標的之 TVL 佔比直接切分權重：
  $$w_i = \frac{\text{TVL}_i}{\sum_j \text{TVL}_j}$$
- **適合客群**：大資金（Whales）、機構型投資者、將「本金安全、合約無破綻、隨時平滑退場無滑點」置於收益率之上的保守型投資者。

### 4. 前端 UI 呈現方案：雙視圖對照與動態滑桿
在前端 Dashboard 面板中，提供極具實用價值的互動體驗：
- **雙卡片並排對照（Side-by-Side Cards）**：
  - 左卡片【🛡️ 安全防禦建議】：展示純 TVL 深度配比（預估年化 Y%，容納深度最高，滑點最低）。
  - 右卡片【🚀 收益進取建議】：展示 TWAP 淨 APY 最佳化配比（預估年化 X%，最大化手續費）。
- **動態偏好滑桿（Risk-Return Slider）**：
  提供 `[ 100% 安全優先 (TVL) <────────●────> 100% 收益優先 (APY) ]` 滑桿，允許使用者依自身風險偏好（例如 70% 穩健 + 30% 進取）動態生成客製化的跨鏈資金配比！

---

## 六、 支援網路與底層技術背景釐清

### 1. Robinhood Chain（Chain ID: `4663`）
- **性質**：Robinhood 推出的專屬 Layer 2 區塊鏈網路，專注於鏈上代幣化美股與 RWA AMM。
- **架構**：基於 **Arbitrum Orbit（Nitro 技術棧）**，以以太坊作為結算層，原生 Gas 代幣為 ETH。
- **節點與規格**：官方主網 Chain ID 為 **`4663`**，端點為 `https://rpc.mainnet.chain.robinhood.com`。
- **為什麼原專案 `baw` 不能解？**  
  幣安官方伺服器並未為 Robinhood Chain 建立 AMM 索引器，因此必須自己透過 `RobinhoodChainAdapter` 直接以 RPC 連線合約解析。

### 2. Solana 網路（Chain ID: `CT_501`）
- **資產現況**：幣安官方資料庫早已收錄 **269 檔 Solana 上的股票化代幣（xStocks, `type=2`）**（如 TSLAx, NVDAx, AAPLx 等）。
- **DEX 生態**：主要流動性與交易量集中於 **Raydium** 與 **Orca**。
- **適配策略**：在補齊 Solana 穩定幣合約（USDC: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`）後，可直接透過幣安現成資料庫或 Raydium/Orca 開放 API 快速接入。

---

## 七、 VPS 公開部署與唯讀安全架構

### 1. 安全原則
- **Zero-Key Principle（零私鑰原則）**：伺服器完全不需要配置任何錢包私鑰、助記詞或提款權限。
- **Read-Only / Air-gapped Execution**：面板只負責展示「全網哪裡有好收益、跨鏈利差、推薦配置權重、區間試算」，任何實際資金操作均引導使用者自行在個人客戶端操作。

### 2. 快取與效能保護
- **背景非同步定時排程（Cron / Background Worker）**：
  每 15~60 分鐘定期向各 Provider 抓取一次資料，計算並寫入本地快取（SQLite / Redis）。
- **外部請求零直接打鏈**：
  外部訪客打開網頁時，只讀取已算好的本地快照資料，保護外部 API 不會被刷爆頻率（Rate-limit protection）。

### 3. 前端呈現技術選型與框架深度評估 (Vue.js vs. Astro)

> **後續 AI / 開發者決策指南**：  
> 開發者本身已有數個線上 Astro 專案經驗（如 `astroplate`, `starwoven`, `exopolitics`），且全權由 AI 操刀寫程式。本節客觀記錄 **Vue.js** 與 **Astro** 在「金融量化儀表板」場景下的深度技術權衡，供後續接手開發的 AI 進行架構覆核與最終選型決策。

#### (1) 四大核心維度深度對比

| 比較維度 | Vue.js (Vue 3 + Vite + Tailwind) | Astro (SSG / 靜態優先) | 評估分析結論 |
| :--- | :--- | :--- | :--- |
| **可維護性**<br>*(AI 生成代碼)* | 🏆 **極高**。<br>強制「數據與 UI 徹底分離」，AI 寫出的 `<script setup lang="ts">` 具備強型別，修改計算公式不會改壞畫面排版。 | ⚠️ **動態場景偏低**。<br>Astro 無內建響應式狀態，AI 實現滑桿連動時會被迫寫原生 JS 操作 DOM（`querySelector`），易產生義大利麵條代碼與靜默 Bug。 | **Vue.js 勝出**。<br>對 AI 來說，宣告式狀態比原生 DOM 更加穩定且容易長期維護。 |
| **可擴展性**<br>*(未來功能演進)* | 🏆 **極強**。<br>組件完全隔離（SFC），有 Pinia 全局狀態中心。未來新增回測圖、手續費計算器、多幣種切換時，AI 只需要加新組件，絕不影響舊代碼。 | ⚠️ **有技術天花板**。<br>適合展示型內容，一旦未來加入多圖表聯動、虛擬滾動大表格、WebSocket 即時推播，Astro 終究需要重構為組件孤島。 | **Vue.js 勝出**。<br>工業級 SPA 能支撐從小工具長大為大型金融終端，不會撞牆。 |
| **潛在攻擊面**<br>*(安全性)* | 🛡️ **極低**。<br>編譯為純靜態檔案（`dist/`）由 Nginx 託管，無伺服器端 Node.js 執行風險。模板 `{{ }}` 默認防範 XSS。 | 🛡️ **極低（微幅勝出）**。<br>同樣走 Nginx 靜態託管。因發送至瀏覽器的 JS 總量較少，第三方 npm 套件漏洞庫存量極小。 | **兩者平手**。<br>在純唯讀 + Nginx 靜態部署架構下，公網攻擊面近乎為零。 |
| **運行時資源佔用**<br>*(VPS 與客戶端)* | **VPS 端**：極低（Nginx 僅佔 5~10MB RAM，CPU 0.01%）。<br>**客戶端**：虛擬 DOM 差量更新，拖動滑桿時手機/電腦排版運算極度平穩。 | **VPS 端**：極低（與 Vue 完全一致）。<br>**客戶端**：首頁打開極快（JS 體積小）；但若用原生 JS 頻繁 innerHTML 重繪，客戶端 CPU 反而容易瞬間飆高。 | **各有千秋**。<br>Astro 首屏載入稍快；Vue.js 在高頻率計算與滑桿拖曳時更絲滑。 |

#### (2) 三種技術實施路線（供後續開發 AI 評估裁決）

- **路線 A（推薦首選：Vue 3 SPA）**：
  採用 `Vite + Vue 3 + Tailwind CSS`，打包為純靜態 SPA 丟給 Nginx。
  - **優點**：AI 寫出的代碼品質最工整、未來功能擴展無天花板、動態計算體驗最絲滑。
- **路線 B（備選：純 Astro）**：
  採用 Astro 框架，由 Python 定時產出 `pools.json`，Astro 讀取並以 SSG 生成靜態頁面。
  - **優點**：完全沿用開發者既有的 Astro 專案工作流，極致輕量。
  - **代價**：遇到滑桿拖曳、即時動態計算時，AI 的代碼容易退化為原生 DOM 操作，維護難度上升。
- **路線 C（折衷混合方案：Astro + Vue 孤島）**：
  採用 Astro 作為網站外殼與導航，安裝 `@astrojs/vue`，僅將「核心資金分配滑桿與利差矩陣」包成單一 Vue 組件嵌入。
  - **優點**：兼具 Astro 的極速首屏與 Vue 的即時響應式計算。

### 4. 具體部署環境與現有資源規劃 (Deployment Context)
- **主機資產**：**已具備現成租用的獨立 VPS**，直接利用現有伺服器資源部署，零額外主機租金負擔。
- **網域規劃**：手上已有數個閒置現成網域名稱，待系統完成後直接選取一個綁定解析即可，無需額外購買網域。
- **防護與加速拓撲**：
  1. 將選定網域之 Nameserver 指向 **Cloudflare**（開啟橘色 Proxy 小雲朵），**完全隱藏 VPS 真實 IP**，杜絕直接攻擊與主機商封鎖風險。
  2. Cloudflare 免費承擔靜態資源分發（CDN）與 API 邊緣快取，最大化壓低 VPS 頻寬與 CPU 負載。
  3. VPS 本機端僅需運行 **Nginx（反向代理與靜態託管）** + **FastAPI 後端** + **非同步背景定時更新 Worker**，乾淨輕量。

---

## 八、 開發里程碑 (Milestones)

- [ ] **Milestone 1：獨立新專案初始化**
  - 開立全新 Repo，建立標準工程結構（`src/`、`tests/`、`docs/`）。
  - 將本專案的 `volatility.py`、`il_model.py`、`range_model.py` 移植為高內聚的純數學量化模組，並加上強型別（Pydantic / dataclass）。
- [ ] **Milestone 2：抽象 Data Provider 介面與 Solana xStocks 解鎖**
  - 定義 `BaseDataProvider`。
  - 解鎖幣安 API 中的 `type=2`（xStocks，269 檔 Solana 代幣化美股）。
  - 補齊 Solana 穩定幣對齊邏輯。
- [ ] **Milestone 3：實作 Robinhood Chain（Chain ID: 4663）鏈上對接**
  - 串接 Robinhood Chain RPC（`https://rpc.mainnet.chain.robinhood.com`）。
  - 解析該鏈上代幣化美股合約與 V3 AMM 流動性池。
  - 實作 `RobinhoodChainAdapter`。
- [ ] **Milestone 4：開發「橫向收益率對比模組」與「動態機率分佈調配演算法」**
  - 實作跨鏈 Ticker 統一對齊索引。
  - 實作 7D/30D TWAP APY 平滑演算法與收益波動懲罰模型。
  - 實作基於 TVL 容量上限約束的多鏈權重配比計算器。
- [ ] **Milestone 5：Web Dashboard 儀表板實作與 VPS 部署**
  - 依第七章第三節技術評估結論，選定 **Vue 3 SPA**（推薦首選）或 **Astro** 實作前端動態面板。
  - 繪製跨鏈同標的利差對比看板。
  - 實作資金分配模擬器（支援雙視圖：TVL 深度加權 vs TWAP APY 收益最佳化）。
  - Docker 容器化封裝，完成公開 VPS + Nginx 部署。
