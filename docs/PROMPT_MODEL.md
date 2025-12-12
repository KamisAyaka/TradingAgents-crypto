## **量化交易决策提示词模板**

### **核心角色与任务**

你是一个专业的系统化交易代理，在 Hyperliquid 平台上进行永续合约交易。你的核心目标是在严格的风险控制下实现风险调整后的最大化回报。你必须基于以下提供的结构化市场数据、交易假设和当前头寸状态，做出理性的交易决策。

### **核心规则与约束**

1. **默认状态**：除非存在清晰且可执行的交易优势（Edge），否则默认选择"无交易"
2. **资产限制**：只能交易列出的系统符号（如 `xyz:MSFT`, `xyz:NVDA` 等）
3. **决策基础**：
   - 必须从每个资产的"Alpha 假设菜单"中选择**一个**最佳假设进行交易
   - 禁止平均化或组合多个假设
   - 预期价格变动必须超过 0.15%以覆盖交易成本
4. **风险管理优先**：资本保全优于收益追求，必须严格遵守风险控制规则

### **输入数据结构**

每次调用时，系统会提供以下结构化的市场数据：

#### **0. 市场状态快照**

```
It is [日期时间] ET. **0. Context Snapshot (Risk Regime)**
Regime: [风险描述，如：Low-vol, mildly risk-on]
Macro: [宏观背景摘要]
Dog (NDX & leaders): [主要指数和龙头股技术结构]
Tail (Hyperliquid): [衍生品市场资金和杠杆情况]
News: [重要新闻摘要]
```

#### **1. 原始数据仪表板**

为每个交易资产提供：

```
[资产名称，如TSLA]
Global Structure: [4小时框架技术分析，关键支撑阻力]
Local Funding: [资金费率，正负代表市场情绪]
Local OI: [未平仓合约数据]
Rel. Vol: [相对成交量分析]
Dog vs. Tail: [现货vs衍生品市场对比]
```

#### **2. 叙事与现实检验**

列出当前主要市场叙事，每个叙事包含：

```
Theme [编号]: "[叙事标题]"
Narrative: [详细描述]
Time: [叙事存在时间]
Reality Check: [价格与技术面验证]
Catalyst Risk: [潜在催化剂风险]
State: [状态评估，如PRICED IN/ABSORPTION等]
```

#### **3. FOMO 地图与催化剂**

```
Scheduled Macro Events: [即将到来的宏观事件日历]
Thematic Risk Scans: [主题风险扫描]
FOMO Radar: [关键资产的关键突破/跌破水平]
```

#### **4. Alpha 设定：假设菜单**（核心部分）

为每个资产提供 2-3 个详细的交易假设，每个假设必须包含：

```
Hypothesis [字母] – [简短标题]
View: [交易观点，如Bullish/Beairsh]
Timeframe/Style: [时间框架/交易风格]
Alpha Type: [阿尔法类型，如FLOW/NARRATIVE/MEAN REVERSION]
Edge Depth: [优势深度：SHALLOW/MODERATE/DEEP]
Risk Regime: [风险体系：TIGHT/NORMAL/WIDE]
Edge Freshness: [优势新鲜度：NEW/AGING]
Invalidation: [失效条件，必须包含具体技术价位]
Steel Man Risk: [最强反驳论点]
```

#### **5. 优势质量矩阵**

```
High Conviction: [列出高确信度假设]
Tactical Skews: [列出战术性偏斜假设]
No Edge / Avoid: [应避免的交易类型]
Risk manager note: [风险经理特别提示]
```

#### **6. 资本与头寸状态**

```
CURRENT AVAILABLE CAPITAL: [可用资金，数字]
CURRENT NAV: [当前净资产，数字]
CURRENT PRICES OF TRADEABLE COINS: [字典，资产->价格，可能包含None]
CURRENT LIVE POSITIONS AND PERFORMANCE: [现有头寸详细信息列表]
```

### **决策逻辑框架（思维链要求）**

你必须按照以下结构化的思维过程进行决策：

#### **步骤 1：初始化与约束检查**

1. 确认当前日期时间和市场状态
2. 检查可用资本、当前净资产
3. 识别现有头寸及其状态
4. 注意价格缺失（None）的资产，这些资产无法交易

#### **步骤 2：现有头寸管理**

1. 对于每个现有头寸：
   - 检查对应资产的最新"优势质量矩阵"和"Alpha 假设"
   - 验证头寸的原始假设是否仍然有效（价格是否仍在失效条件之上/下）
   - 评估"Steel Man Risk"是否变得紧迫
   - 基于当前市场状况和假设的 Edge Depth，更新置信度评分
   - 决定：持有、加仓、减仓或平仓

#### **步骤 3：新交易机会评估**

1. 遍历每个有有效价格的资产：
   - 参考"优势质量矩阵"，优先考虑"High Conviction"假设
   - 排除"No Edge / Avoid"的资产
2. 对于候选假设：
   - **技术对齐检查**：当前价格是否符合假设的入场条件？
     - 如"Buy dips above 181"，当前价需>181 且接近该水平
     - 如"Fade near 488-490"，当前价需接近该阻力区
   - **时机检查**：
     - 评估"Steel Man Risk"的紧迫性（特别是即将发生的宏观事件）
     - 参考"Risk manager note"的特别警告
   - **置信度计算**：
     - Edge Depth = DEEP → 置信度 0.80-0.95
     - Edge Depth = MODERATE → 置信度 0.70-0.85
     - Edge Depth = SHALLOW → 置信度 0.60-0.75
     - 根据事件风险、新鲜度等调整 ±0.05-0.10

#### **步骤 4：交易参数计算**（对于新开仓）

1. **止损设置**：基于假设的"Invalidation"条件设置具体止损价位
2. **风险计算**：
   - 风险因子 `r` 选择：
     - Risk Regime = WIDE → r = 0.4-0.7
     - Risk Regime = NORMAL → r = 0.3-0.5
     - Risk Regime = TIGHT → r = 0.2-0.3
   - 计算最大风险金额：`risk_usd_max = available_capital * r`
3. **头寸规模计算**：
   - 止损距离 = |入场价 - 止损价|
   - 最大数量 = risk_usd_max / 止损距离
   - 考虑杠杆限制（最大 10 倍）和保证金要求
4. **止盈设置**：至少为风险回报比 1.5:1，参考 FOMO 地图中的关键水平

#### **步骤 5：最终决策汇总**

1. 现有头寸：确定最终操作（持有/调整/平仓）
2. 新交易：选择 1-2 个最高确信度的机会，确保不过度集中
3. 考虑相关性：避免同时持有高度相关的多个头寸
4. 尊重风险提示：特别关注"Risk manager note"中的警告

### **输出格式规范**

你必须输出一个**单一的、有效的 JSON 对象**，格式如下：

```json
{
  "[系统符号，如xyz:MSFT]": {
    "signal": "hold|buy_to_enter|sell_to_enter|close_position",
    "quantity": [数量，小数],
    "profit_target": [止盈价格，数字],
    "stop_loss": [止损价格，数字],
    "invalidation_condition": "[描述性失效条件，字符串]",
    "leverage": [杠杆倍数，整数，1-10],
    "confidence": [置信度，0-1的小数],
    "add": [布尔值，仅对现有头寸有意义，表示是否加仓],
    "risk_usd": [风险金额，数字，从入场到止损的美元损失],
    "justification": "[1-3句的决策理由，引用相关假设和风险考量]"
  },
  "[其他资产系统符号]": { ... }
}
```

### **特殊情况处理**

1. **价格缺失**：如果资产价格为`None`，不生成该资产的交易信号
2. **无交易机会**：如果没有任何资产满足交易条件，输出空对象 `{}`
3. **现有头寸调整**：
   - 如果决定调整现有头寸的止损/止盈，在`justification`中说明理由
   - 如果决定加仓，设置`add: true`并重新计算所有参数
4. **事件风险处理**：
   - 重大事件（CPI、FOMC）前 24-48 小时：避免新开仓，减小现有头寸规模
   - 事件后：等待价格稳定再评估新机会

### **示例输出**

```json
{
  "xyz:MSFT": {
    "signal": "hold",
    "quantity": 12.935,
    "profit_target": 504.9,
    "stop_loss": 470.0,
    "invalidation_condition": "Daily close below 470.00",
    "leverage": 10,
    "confidence": 0.85,
    "add": false,
    "risk_usd": 175.1,
    "justification": "Holding MSFT long as per Hypothesis A: uptrend continuation above 481-482 with contrarian negative funding. The deep edge and AI leadership narrative remain intact, though sizing is reduced due to CPI/FOMC event risk next week. Stop at 470 provides protection below key technical support."
  }
}
```

### **使用说明**

1. **模板变量**：`[ ]`中的内容需要在实际使用时用具体数据替换
2. **思维链强制执行**：模型必须展示上述步骤的思考过程
3. **一致性要求**：决策必须与提供的数据、假设和风险提示保持一致
4. **保守偏向**：在不确定或高风险时期，优先选择更保守的选项

user_prompt:

CURRENT STATE OF MARKETS
It is Saturday, December 06, 2025 08:43 am ET. **0. Context Snapshot (Risk Regime)**
Regime: Low-vol, mildly risk-on, indices near range highs.
Macro: Soft-landing baseline, dense Fed/CPI window next week = event-volatility risk.
Dog (NDX & leaders): Uptrend intact, 4h structures bullish/sideways.
Tail (Hyperliquid): Funding tiny, no crowded leverage; only mild MSFT/PLTR short-lean.
News: All AI/infra items are incremental and multi-day narrative, not fresh impulses.

1. Raw Data Dashboard (Dog vs. Tail)
   TSLA

Global Structure: 4h uptrend, higher lows mid‑440s → mid‑450s; intraday 30–60m tight consolidation just below highs (~454–456).
Local Funding: +0.00125%/8h (tiny positive).
Local OI: N/A (no change series).
Rel. Vol: Normal to slightly elevated focus (most-active list), but price quiet.
Dog vs. Tail: Global Up / Local Flat (no perp skew).
NDX (XYZ100 / QQQ)

Global Structure: NDX +0.4%, VXN -2.8%; 4h holding above 624–625, near range highs; intraday tight band 625–626.
Local Funding (XYZ100): +0.00125%/8h.
Local OI: N/A.
Rel. Vol: QQQ modestly > SPY; growth tilt, but not blow-off.
Dog vs. Tail: Global Up / Local Flat (brief HL downtick, but no leverage signal).
NVDA

Global Structure: 4h bullish, holding above 181–181.5, closing near top of range; intraday grind higher, higher lows.
Local Funding: +0.00125%/8h (neutral).
Local OI: ~118k, trend N/A.
Rel. Vol: High activity, price slightly red recently but intraday strength into close; sector semis bid via SOXL.
Dog vs. Tail: Global Up / Local Flat.
MSFT

Global Structure: 4h reclaim above 481–482, intraday stair-step 481.4 → 483+, closing at highs. Uptrend intact.
Local Funding: -0.0141%/8h (mild negative).
Local OI: ~8.5k, trend N/A.
Rel. Vol: Solid participation, leadership within mega-cap tech.
Dog vs. Tail: Global Up / Local Mild Short (contrarian bullish).
AMZN

Global Structure: 4h sideways 228–231; intraday 229–230 range, no expansion.
Local Funding: -0.0010%/8h (slightly negative).
Local OI: ~31.8k, trend N/A.
Rel. Vol: Normal; benefits from cyclical + growth tilt.
Dog vs. Tail: Global Sideways / Local Mild Short (slight contrarian bullish).
GOOG

Global Structure: 4h reclaim 320–321, closing near top of range; intraday grind 321 → 322, no late selling.
Local Funding: +0.00123%/8h (tiny positive).
Local OI: ~83.8k, trend N/A.
Rel. Vol: Healthy; comm services leadership.
Dog vs. Tail: Global Up / Local Flat.
PLTR

Global Structure: 4h uptrend 170s → low‑180s, holding near highs; intraday tight 181.7–181.9 consolidation.
Local Funding: -0.0031%/8h (mild negative).
Local OI: ~35.1k, trend N/A.
Rel. Vol: Elevated recently (strong 4h advance), now compressing.
Dog vs. Tail: Global Up / Local Mild Short (contrarian bullish). 2. Narrative vs. Reality Check
Theme 1: “New PLTR–NVDA AI infra deals = big upside now”

Narrative: PLTR Chain Reaction OS (with NVDA), rodeo edge AI, Malaysia NVL72 DC → “new AI super-cycle leg.”
Time: ~1–4 days old.
Reality Check:
NVDA: 4h uptrend intact, but only modest recent price response; no explosive breakout.
PLTR: Strong 4h rally then sideways near highs; no failure of structure.
Catalyst Risk (Unknown/Hypothetical):
Hypothetical: US/ally government announces large, near-term AI infra contracts explicitly naming PLTR/NVDA.
Hypothetical: Regulatory pushback on AI infra security or export controls that slow deployments.
State: PRICED IN → mild ongoing NARRATIVE support (no fresh impulse).
Theme 2: “AWS Graviton5 & AI tools change AMZN trajectory”

Narrative: AMZN cloud/AI competitiveness step-change.
Time: ~2–3 days.
Reality Check: AMZN 4h still sideways 228–231; no structural breakout or breakdown.
Catalyst Risk (Hypothetical):
Hypothetical: Major hyperscaler customer migration announcement (e.g., large enterprise shifts workloads to AWS for AI).
Hypothetical: Cloud pricing war compressing margins.
State: PRICED IN / DISTRIBUTION-lite (good news, flat price).
Theme 3: “Macro soft landing + expected Fed cut = tech can only go up”

Narrative: Low recession probability, expected 25bp cut (4.0 → 3.75) = durable tailwind for NDX.
Time: Ongoing, but FOMC/CPI in 4–5 days.
Reality Check: NDX at/near highs, low vol; no break of support, but also no blow-off.
Catalyst Risk (Real):
CPI hotter than expected → market prices fewer/future cuts.
Fed signals slower easing path or higher terminal real rates.
State: DIVERGENCE RISK (good macro narrative, but event risk could flip it).
Theme 4: “PLTR is now core AI infra, must chase”

Narrative: Chain Reaction OS + multiple AI deployments → PLTR as structural AI infra winner.
Time: 1–3 days.
Reality Check: 4h trend up, price near highs, but intraday momentum has stalled; HL shows momentum cooling and mild short-lean.
Catalyst Risk (Hypothetical):
Hypothetical: Large regulated-utility or federal contract explicitly tied to Chain Reaction.
Hypothetical: Negative press/regulatory scrutiny on data/AI governance.
State: ABSORPTION (bullish narrative, price consolidating after move). 3. FOMO Map & Catalyst Horizon
Scheduled Macro Events (High Impact for NDX & AI leaders)

2025‑12‑09: JOLTs.
2025‑12‑10:
13:30 – CPI / Core CPI.
19:00 – FOMC decision & projections (market expects -25bp).
2025‑12‑11: PPI, jobless claims.
2025‑12‑16: NFP, unemployment, retail sales, PMIs, housing.
2025‑12‑18–19: Inflation/PCE, income/spending.
Thematic Risk Scans

Fed/Rates (Dec ’25 outlook)

Baseline: Mild bear-steepening, front-end easing; neutral-to-slightly supportive for growth.
Hypothetical Upside Surprise: CPI soft + Fed hints at faster cuts → duration/growth chase, NDX breakout.
Hypothetical Downside Surprise: CPI hot or Fed “one-and-done” tone → repricing of cuts, NDX pullback.
Geopolitics / Trade

No fresh hard headlines in feed.
Hypothetical: New US–China tech export controls (chips, cloud) → NVDA/GOOG/MSFT hit.
Hypothetical: Tariff rhetoric on autos → TSLA risk.
Corporate / Regulatory

MSFT: Routine dividend; no structural change.
Hypothetical: Antitrust actions vs. MSFT/GOOG/AMZN AI bundling.
Hypothetical: Large AI infra partnership announcements (PLTR/NVDA/AMZN/MSFT).
FOMO Radar (Key Levels & Traps)
TSLA

Upside Chase: Above ~457–460 (recent intraday highs), funds/retail likely chase “flag breakout” in a risk-on tape.
Downside Flush: Below ~453–454 (4h support), recent buyers trapped; could accelerate toward mid‑440s.
NDX

Upside Chase: Clear break/hold above recent 4h highs (≈ NDX 25,700–25,800 / QQQ > ~627–628) post-CPI/Fed → systematic & retail chase.
Downside Flush: Lose 624–625 (QQQ) on a macro miss → fast de-risking, especially in high-beta names.
NVDA

Upside Chase: Hold above 185 and extend >188–190 → “new leg” narrative, FOMO from funds underweight semis.
Downside Flush: Lose 181–181.5 → breaks current 4h support band, opens 175–177.
MSFT

Upside Chase: Sustained trade >485–488 → continuation of structural AI leader trend; negative HL funding adds contrarian fuel.
Downside Flush: Back below 481–482 → suggests failed reclaim; could mean mean-reversion toward 475.
AMZN

Upside Chase: Break and hold >231–232 (top of 4h range) → “AWS AI + consumer resilience” chase.
Downside Flush: Lose 228 → range breakdown, consumer macro worries reprice.
GOOG

Upside Chase: Above 323–325 → confirms reclaim of prior breakdown zone; comm services leadership extends.
Downside Flush: Below 320–321 → failed reclaim, opens 315–317.
PLTR

Upside Chase: Above 183–185 with volume → “Chain Reaction” + AI infra FOMO, especially if macro benign.
Downside Flush: Below 180–181 → breaks current 4h higher-low structure; late longs trapped. 4. Alpha Setups: Menu of Hypotheses
TSLA
Hypothesis A – 4h Uptrend Continuation

View: Bullish continuation while 453–454 holds.
Timeframe/Style: SHORT SWING (2–5 days).
Alpha Type: FLOW / MEAN REVERSION (buy dips in uptrend).
Edge Depth: MODERATE.
Risk Regime: NORMAL.
Edge Freshness: NEW.
Invalidation: Clean 4h close below 453.
Steel Man Risk:
Macro: CPI/Fed hawkish surprise hits high-beta growth.
Micro: Weak consumer data or EV headlines; TSLA’s beta amplifies any NDX pullback.
Hypothesis B – Range Fade (Short Near 457–460)

View: Fade local resistance into macro event week; expect chop, not breakout.
Timeframe/Style: SCALP (intraday/1–2 days).
Alpha Type: MEAN REVERSION.
Edge Depth: SHALLOW.
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: 30–60m acceptance above 460 with NDX strong.
Steel Man Risk:
NDX breaks to new highs; TSLA becomes beta vehicle for upside.
Shorting into structural risk-on regime with no clear selling pressure.
Hypothesis C – Tail Neutrality (No HL Edge)

View: HL perp is flat; no squeeze or crowding → rely on Dog only.
Timeframe/Style: SCALP / SHORT SWING.
Alpha Type: FLOW (index-driven).
Edge Depth: SHALLOW.
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Sudden HL funding spike (>|0.05%/8h|) with price dislocation vs NDX.
Steel Man Risk: HL remains irrelevant; edge never materializes.
NDX
Hypothesis A – Structural Bullish Bias into/through Events

View: Uptrend intact; buy dips above 624–625, but size down for event risk.
Timeframe/Style: SHORT SWING.
Alpha Type: FLOW / NARRATIVE (soft-landing, expected cut).
Edge Depth: MODERATE.
Risk Regime: WIDE (event risk).
Edge Freshness: AGING (trend known, but still valid).
Invalidation: Daily close below 624 (QQQ) / clear break of recent 4h lows.
Steel Man Risk: CPI/Fed surprise reprices rates sharply higher; NDX mean-reverts lower.
Hypothesis B – Event Hedge / Tactical Short Above Range

View: Use strength near highs to position small tactical short into CPI/Fed.
Timeframe/Style: SHORT SWING (1–4 days).
Alpha Type: NARRATIVE / MEAN REVERSION.
Edge Depth: SHALLOW.
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Strong dovish surprise (soft CPI + dovish Fed) with NDX closing above recent highs.
Steel Man Risk: Fighting structural AI/mega-cap tailwind; short can be steamrolled by upside surprise.
Hypothesis C – HL Tail Calm = Dog-Driven Breakout Potential

View: HL XYZ100 shows no leverage stress; if macro is benign, breakout can be clean (no forced covering yet).
Timeframe/Style: SWING (Structural).
Alpha Type: FLOW.
Edge Depth: MODERATE.
Risk Regime: NORMAL.
Edge Freshness: NEW.
Invalidation: HL funding spikes negative with NDX stalling at highs (sign of crowded longs elsewhere).
Steel Man Risk: Breakout fails due to macro shock, not positioning.
NVDA
Hypothesis A – Structural AI Bull, Buy Dips Above 181

View: Bullish; 4h support 181–181.5 holds, macro neutral-to-supportive, AI infra news adds tailwind.
Timeframe/Style: SWING (Structural).
Alpha Type: FLOW / NARRATIVE.
Edge Depth: DEEP (within AI structural bull regime).
Risk Regime: WIDE (high beta + event week).
Edge Freshness: NEW–MODERATE.
Invalidation: 4h close below 181.
Steel Man Risk:
Macro: Rates spike on CPI/Fed.
Micro: New export controls or AI capex slowdown headlines.
Hypothesis B – Short-Term Mean Reversion Short Near 188–190

View: If NVDA spikes into 188–190 pre-events, fade extension for a pullback to 182–184.
Timeframe/Style: SCALP / very SHORT SWING.
Alpha Type: MEAN REVERSION.
Edge Depth: SHALLOW (counter-trend vs AI leader).
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Strong 4h close above 190 with volume.
Steel Man Risk: Structural AI demand + news flow can turn any breakout into sustained trend; shorting strength is dangerous.
Hypothesis C – HL Neutral Tail = Trust the Dog

View: With HL funding neutral and no OI signal, NVDA’s path is dominated by NDX + macro; no perp edge.
Timeframe/Style: SCALP / SHORT SWING.
Alpha Type: FLOW.
Edge Depth: SHALLOW.
Risk Regime: NORMAL.
Edge Freshness: NEW.
Invalidation: HL funding or OI suddenly spike with divergence vs spot.
Steel Man Risk: Overfitting to tiny HL data; real leverage sits on other venues.
MSFT
Hypothesis A – Uptrend Continuation with Contrarian Tailwind

View: Bullish; 4h reclaim above 481–482 + HL negative funding = “Global Up / Local Mild Short.”
Timeframe/Style: SWING (Structural).
Alpha Type: FLOW / NARRATIVE.
Edge Depth: DEEP (AI leader, structural tailwind).
Risk Regime: NORMAL–WIDE (event risk).
Edge Freshness: NEW.
Invalidation: 4h close back below 481.
Steel Man Risk: Fed/CPI hawkish surprise hits duration; MSFT, as crowded long, could see de-grossing.
Hypothesis B – Tactical Short Fade Near 488–490

View: Fade local extension into macro events, expecting reversion to 481–482.
Timeframe/Style: SCALP / SHORT SWING.
Alpha Type: MEAN REVERSION.
Edge Depth: SHALLOW (counter-trend vs AI leader).
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Strong 4h close above 490.
Steel Man Risk: Negative HL funding can fuel a squeeze; structural buyers step in on any dip.
Hypothesis C – HL Short Bias Caps Upside

View: Slightly bearish multi-day skew: persistent negative funding may indicate overhead supply from perps.
Timeframe/Style: SHORT SWING.
Alpha Type: MEAN REVERSION / SENTIMENT.
Edge Depth: SHALLOW (HL is tiny).
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Funding flips positive while price holds >482–483.
Steel Man Risk: HL volume is negligible; reading too much into tiny funding.
AMZN
Hypothesis A – Range Break Higher on AI + Cyclical Tailwind

View: Bullish bias; if 231–232 breaks, chase toward 236–238.
Timeframe/Style: SHORT SWING.
Alpha Type: FLOW / NARRATIVE (AWS AI + consumer cyclicals leadership).
Edge Depth: MODERATE.
Risk Regime: NORMAL.
Edge Freshness: NEW.
Invalidation: Failed breakout (4h close back below 231).
Steel Man Risk: Consumer sentiment weakens further; retail sales miss; macro hits discretionary.
Hypothesis B – Range Trade / Fade Extremes

View: Sell near 231–232, buy near 228 until macro breaks the range.
Timeframe/Style: SCALP.
Alpha Type: MEAN REVERSION.
Edge Depth: MODERATE (clear range).
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Sustained 4h close outside 228–232.
Steel Man Risk: Event-driven breakout invalidates range quickly.
Hypothesis C – HL Slight Short Tilt as Contrarian Bullish

View: Mild negative funding with flat price = shorts not getting paid; lean long vs 228.
Timeframe/Style: SHORT SWING.
Alpha Type: MEAN REVERSION / SENTIMENT.
Edge Depth: SHALLOW.
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Funding turns more negative with price rolling over below 228.
Steel Man Risk: HL signal too small; real shorting may be elsewhere.
GOOG
Hypothesis A – Reclaim & Extend Above 320–321

View: Bullish; 4h reclaim of 320–321 with comm services leadership; target 325–330.
Timeframe/Style: SHORT SWING.
Alpha Type: FLOW / NARRATIVE.
Edge Depth: MODERATE.
Risk Regime: NORMAL.
Edge Freshness: NEW.
Invalidation: 4h close back below 320.
Steel Man Risk: Macro shock hits ad/cyclical exposure; GOOG underperforms defensives.
Hypothesis B – Fade into 323–325

View: Short-term mean reversion if price stretches into 323–325 pre-events.
Timeframe/Style: SCALP.
Alpha Type: MEAN REVERSION.
Edge Depth: SHALLOW.
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Strong acceptance above 325 with NDX breakout.
Steel Man Risk: Communication services leadership persists; shorting strength in a risk-on tape.
Hypothesis C – HL Microstructure Noise, Ignore Tail

View: HL near-static band with stacked offers is micro noise; no directional edge.
Timeframe/Style: SCALP / SHORT SWING.
Alpha Type: FLOW (Dog-driven).
Edge Depth: SHALLOW.
Risk Regime: NORMAL.
Edge Freshness: NEW.
Invalidation: HL funding or OI show persistent skew with divergence vs spot.
Steel Man Risk: Overconfidence in ignoring a potential early sentiment tell.
PLTR
Hypothesis A – Structural AI Uptrend, Buy Dips Above 180–181

View: Bullish; 4h higher lows, AI infra narrative, macro supportive for capex.
Timeframe/Style: SWING (Structural).
Alpha Type: FLOW / NARRATIVE.
Edge Depth: MODERATE (not as entrenched as NVDA/MSFT).
Risk Regime: WIDE (high beta).
Edge Freshness: NEW.
Invalidation: 4h close below 180.
Steel Man Risk: Narrative > near-term earnings; any macro risk-off hits PLTR harder than mega-caps.
Hypothesis B – Short-Term Momentum Fade

View: Momentum has cooled (MACD rolled, RSI down); fade strength toward 183–185 for pullback to 180–181.
Timeframe/Style: SCALP / very SHORT SWING.
Alpha Type: MEAN REVERSION.
Edge Depth: SHALLOW (counter-trend vs current 4h up).
Risk Regime: TIGHT.
Edge Freshness: NEW.
Invalidation: Strong 4h close above 185 with volume.
Steel Man Risk: Fresh AI headlines or NDX breakout reignite PLTR FOMO.
Hypothesis C – HL Mild Short Bias as Fuel for Squeeze

View: Slightly negative funding + uptrend = potential for squeeze if price breaks 183–185.
Timeframe/Style: SHORT SWING.
Alpha Type: SENTIMENT / FLOW.
Edge Depth: SHALLOW–MODERATE.
Risk Regime: NORMAL.
Edge Freshness: NEW.
Invalidation: Funding normalizes to flat/positive while price stalls below 183.
Steel Man Risk: HL is tiny; shorts may be mostly on listed options/stock, not perps. 5. Edge Quality Matrix
High Conviction (Deep Edge / Wide Risk / Structural Tailwind)

NVDA – Hypothesis A: Buy dips above 181 (AI infra + 4h support).
MSFT – Hypothesis A: Long above 481–482 with HL contrarian short-lean.
NDX – Hypothesis A: Buy dips above 624–625, but size down for CPI/Fed.
PLTR – Hypothesis A: Buy dips above 180–181 (AI infra narrative + 4h trend), with sizing discipline.
Tactical Skews (Shallow Edge / Tight Risk / Counter-Trend)

TSLA – Hypothesis B: Fade 457–460 resistance for short-term mean reversion.
NVDA – Hypothesis B: Fade 188–190 if reached pre-events.
MSFT – Hypothesis B: Fade 488–490 for pullback to 481–482.
AMZN – Hypothesis B: Range trade 228–232.
GOOG – Hypothesis B: Fade 323–325 if NDX stalls.
PLTR – Hypothesis B: Fade 183–185 for pullback to 180–181.
No Edge / Avoid (for now)

HL-driven standalone trades across all names: Funding and OI are too small and flat to justify trades by themselves; use HL only as a minor sentiment overlay, not a primary signal.
Pure macro bets via single names into CPI/Fed without clear technical levels: Event risk dominates; better expressed via indices or options with defined risk.
Risk manager note: Into next week’s CPI/Fed cluster, prioritize defined-risk structures (options, tight stops) and avoid oversized directional bets, especially counter-trend shorts in AI leaders unless key supports (NVDA 181, MSFT 481, NDX 624–625) break on volume.

CURRENT AVAILABLE CAPITAL
12234.463653
CURRENT NAV
12853.946765
CURRENT PRICES OF TRADEABLE COINS
{'xyz:TSLA': 455.065, 'xyz:XYZ100': 25663.5, 'xyz:NVDA': None, 'xyz:GOOGL': 320.105, 'xyz:MSFT': 483.135, 'xyz:AMZN': 229.65, 'xyz:PLTR': 181.21}
CURRENT LIVE POSITIONS AND PERFORMANCE
{'symbol': 'xyz:MSFT', 'quantity': 12.935, 'entry_price': 483.54, 'current_price': 483.135, 'liquidation_price': 458.11, 'unrealized_pnl': -5.24, 'leverage': 10, 'exit_plan': {'profit_target': 504.9, 'stop_loss': 470.0, 'invalidation_condition': 'Daily close below 470.00'}, 'confidence': 0.0, 'risk_usd': 0.0, 'sl_oid': -1, 'tp_oid': -1, 'wait_for_fill': False, 'entry_oid': -1, 'notional_usd': 6249.35}

思维链：

First, I am a systematic trading agent trading on Hyperliquid. My goal is to maximize risk-adjusted returns while preserving capital. The default state is "No Trade" unless there's a clear edge. I'm given a menu of hypotheses for each asset, and I need to pick the best one or decide not to trade.

Current State: It's Saturday, December 06, 2025, 08:43 am ET. Markets are low-vol, mildly risk-on, near range highs. Macro events next week: JOLTs, CPI, FOMC, etc., so event-volatility risk. Dog (NDX) uptrend intact, Tail (Hyperliquid) funding tiny, no crowded leverage.

Available Capital: $12,234.46

Current NAV: $12,853.95

Current Positions: I have one open position in MSFT:

Symbol: xyz:MSFT

Quantity: 12.935

Entry Price: 483.54

Current Price: 483.135

Unrealized PNL: -5.24 (slightly negative)

Leverage: 10x

Profit Target: 504.9

Stop Loss: 470.0

Invalidation Condition: Daily close below 470.00

Confidence: 0.0 (this might be from previous, but I need to reassess)

I need to manage this existing position. For each call, I must output an action for all positions, including hold, add, or close.

Now, let's look at the hypotheses for each asset, and decide if I should enter new trades or manage existing ones.

Assets: TSLA, XYZ100 (NDX), NVDA, GOOGL, MSFT, AMZN, PLTR. NVDA current price is None, so I can't trade it now. I should skip NVDA since no price is given.

From the data, NVDA price is None, so I'll exclude it from consideration.

Focus on assets with prices: TSLA, XYZ100, GOOGL, MSFT, AMZN, PLTR.

I need to evaluate the hypotheses for each and select the best one if confidence is high enough (>0.70).

Also, consider the "Steel Man Risk" for the chosen hypothesis; if it's imminent, skip the trade.

Start with MSFT since I have an existing position.

MSFT Current Position Analysis:

Current Price: 483.135

Entry Price: 483.54, so slightly underwater.

Profit Target: 504.9, which is about +4.5% from entry.

Stop Loss: 470.0, which is about -2.8% from entry.

Unrealized PNL: -5.24, small.

Hypotheses for MSFT:

Hypothesis A: Uptrend Continuation with Contrarian Tailwind. Bullish, 4h reclaim above 481-482, HL funding negative (mild short), so contrarian bullish. Edge Depth: DEEP. Risk Regime: NORMAL-WIDE. Invalidation: 4h close below 481.

Hypothesis B: Tactical Short Fade. Fade near 488-490. Edge Depth: SHALLOW. Counter-trend.

Hypothesis C: HL Short Bias Caps Upside. Slightly bearish. Edge Depth: SHALLOW.

The current position is long, and Hypothesis A seems strong with deep edge. The price is at 483.135, which is above 481-482, so the trend is intact. HL funding negative could fuel a squeeze if it continues.

Steel Man Risk for Hypothesis A: Fed/CPI hawkish surprise could hit MSFT.

Events are next week, not imminent right now (it's Saturday, events start on Tuesday), so not immediate. But since it's a swing trade, I need to be cautious.

Current exit plan has stop at 470, which is below 481, but Hypothesis A invalidation is 4h close below 481. So my stop is tighter than the hypothesis suggests? 470 is lower than 481, so it's giving more room, but 481 is a key level.

Hypothesis A says invalidation is clean 4h close below 481, but my stop is at 470, which might be too conservative or not aligned.

I need to decide whether to hold, add, or close this position.

Confidence in the trade: Initially, confidence was 0.0, but from the hypothesis, Hypothesis A has deep edge, so I might have high confidence now.

But I need to recalc confidence based on current data.

For existing positions, I should hold if the thesis still holds.

Look at the justification: The position was entered with a stop at 470, invalidation daily close below 470, but Hypothesis A suggests 4h close below 481. So there's a discrepancy.

Since the hypothesis is still valid (price above 481), and edge is deep, I should hold or even add if confident.

But I need to check if the Steel Man Risk is imminent. Events are in a few days, not today, so it might be okay.

Now, other assets.

First, for new entries, I need confidence >0.70.

List all assets and their best hypotheses:

TSLA:
Hyp A: Bullish continuation, MODERATE edge, NORMAL risk. Invalidation below 453-454.
Hyp B: Range fade short, SHALLOW edge, TIGHT risk. Invalidation above 460.
Hyp C: No edge, SHALLOW.
Best: Hyp A if bullish, but edge is MODERATE, not deep. Price is 455.065, above 453-454, so trend intact. But confidence might not be high enough? Hyp A edge depth MODERATE, so confidence cap 0.70-0.80. But need to see if it meets confidence threshold.
From Alpha Setups, High Conviction list includes NVDA A, MSFT A, NDX A, PLTR A. TSLA is not in high conviction.

TSLA Hyp A is MODERATE edge, so confidence around 0.75 maybe, but need to check.

Also, TSLA price is 455.065, and upside chase above 457-460, downside flush below 453-454. Currently in between.

XYZ100 (NDX):
Hyp A: Structural Bullish, buy dips above 624-625. MODERATE edge, WIDE risk due to events. Invalidation below 624.
Hyp B: Event hedge short, SHALLOW edge, TIGHT risk.
Hyp C: HL calm, MODERATE edge.
Best: Hyp A. Price is 25663.5, which for NDX, probably corresponds to QQQ levels. From data, NDX at range highs, 4h holding above 624-625 (QQQ price). Current XYZ100 price is 25663.5, but I need to map to QQQ. From FOMO map, NDX upside chase above 25,700-25,800 / QQQ >627-628. XYZ100 is likely the perp for NDX, so price 25663.5 might be the index level, not QQQ. Typically, NDX index is around 18k-20k, but here it's given as 25663.5, which might be a different representation. In the data, for NDX, it says "NDX +0.4%", and "QQQ modestly > SPY", so XYZ100 is probably the perp symbol for NDX index. But the price 25663.5 seems high for NDX index; normal NDX is around 18k, but perhaps it's scaled. I should use the given price as is. From hypotheses, invalidation for Hyp A is daily close below 624 for QQQ, but XYZ100 price is different. Need to be careful.
In the Raw Data Dashboard for NDX: "Global Structure: NDX +0.4%, VXN -2.8%; 4h holding above 624–625, near range highs; intraday tight band 625–626." This 624-625 is likely the QQQ price, not the NDX index. But XYZ100 is the perp for NDX, so its price should be correlated. Current XYZ100 price is 25663.5, which might be the index value or something else. Typically, Hyperliquid perps might have different tick sizes, but I have to work with the given price.

Perhaps XYZ100 price is the index level. NDX index is around 18k, but 25663.5 is possible if it's a different index or scaled. I'll assume the price given is correct for trading.

From FOMO map for NDX: "Upside Chase: Clear break/hold above recent 4h highs (≈ NDX 25,700–25,800 / QQQ > ~627–628)". So NDX index highs at 25,700-25,800, and current price is 25,663.5, so near highs but not broken. Invalidation for Hyp A is lose 624-625 for QQQ, which corresponds to NDX index around? QQQ at 624-625, NDX index is roughly QQQ \* 40 or something, but not exact. Typically, NDX index is about 40 times QQQ, so QQQ 625 ≈ NDX 25,000. So current XYZ100 at 25,663.5 is above 25,000, and invalidation might be around 25,000 for NDX index.

Hypothesis A for NDX: "Invalidation: Daily close below 624 (QQQ)". But for XYZ100, I need to map that. Since XYZ100 is the perp for NDX, its price should be the NDX index level. So if QQQ below 624, NDX index might be below 25,000 approximately. But to be precise, I should use the price levels given.

In the hypothesis, it says "invalidation: Daily close below 624 (QQQ)", but for trading XYZ100, I need to set stop based on XYZ100 price. This is messy.

Perhaps I should infer that for XYZ100, a key level is around 25,000 or something. Current price 25,663.5, and range highs 25,700-25,800, so it's near highs.

For simplicity, I'll use the price as is and set stops relative to it.

Hyp A for NDX has MODERATE edge, WIDE risk due to events. Confidence might be around 0.75-0.80.

GOOGL:

Hyp A: Reclaim & extend above 320-321, bullish, MODERATE edge. Invalidation below 320.
Hyp B: Fade into 323-325, SHALLOW edge.
Hyp C: No edge, SHALLOW.
Best: Hyp A. Current price 320.105, just above 320-321, so reclaim might be happening. Edge MODERATE.
AMZN:

Hyp A: Range break higher, MODERATE edge. Invalidation failed breakout below 231.
Hyp B: Range trade, MODERATE edge for range.
Hyp C: HL slight short tilt, SHALLOW.
Current price 229.65, in range 228-231. Hyp A is for breakout above 231-232, not yet broken. Hyp B is range trade.
PLTR:

Hyp A: Structural AI uptrend, buy dips above 180-181, MODERATE edge. Invalidation below 180.
Hyp B: Momentum fade, SHALLOW.
Hyp C: HL mild short bias, SHALLOW-MODERATE.
Current price 181.21, above 180-181, so trend intact. Edge MODERATE.
From the Alpha Setups, High Conviction are:

NVDA A (but price none, skip)
MSFT A
NDX A
PLTR A
Also, TSLA not in high conviction.

For MSFT, I have an existing long position.

Now, for new entries, I need to see if confidence is high enough.

First, assess confidence for each potential trade.

Confidence is derived from edge depth and alignment.

Also, fee hurdle: expected move must exceed 0.15%.

Since markets are low-vol and event risk next week, I should be cautious with new entries, especially counter-trend.

For MSFT existing position, I should hold if the thesis still holds.

Hypothesis A for MSFT: bullish, invalidation 4h close below 481. Current price 483.135 > 481, so still valid. Steel Man Risk is Fed/CPI hawkish, but not imminent today (Saturday), so I can hold.

I might consider adding if confidence is high.

But let's calculate confidence.

Edge Depth for MSFT Hyp A is DEEP, so confidence can be 0.85+.

Risk Regime is NORMAL-WIDE, so risk factor r could be 0.5-0.8.

For existing position, I need to decide to hold, add, or close.

The position is already open, with stop at 470, which is below the invalidation level of 481. So the stop is tighter, which might be good for risk management, but it might get stopped out early if it dips to 481 but not 470.

Hypothesis A suggests invalidation at 481, so if I believe in Hyp A, I should move stop to 481 or something. But the exit_plan has stop at 470, and it's set.

As a systematic agent, I should probably hold with the existing plan, unless the thesis changes.

For the output, for existing positions, I need to signal hold, add, or close.

Similarly for new trades.

Now, for new entries, let's see which one has the highest confidence.

PLTR Hyp A: MODERATE edge, not deep, so confidence cap 0.70-0.80. Price 181.21, above 180, so okay.

NDX Hyp A: MODERATE edge, WIDE risk, confidence 0.70-0.80.

GOOGL Hyp A: MODERATE edge, confidence similar.

AMZN: not broken out, so Hyp B range trade might be good, MODERATE edge for range.

But range trading might have lower confidence because it's mean reversion.

TSLA Hyp A: MODERATE edge.

MSFT already has position.

NVDA not available.

The highest edge is MSFT Hyp A with DEEP edge.

Since I already have a position in MSFT, I might consider adding to it if confidence is high.

But I need to check correlation: if I add MSFT, it's similar to NDX, so might be correlated.

Also, available capital is 12k, NAV 12.8k, so the MSFT position has notional usd 6249.35, which is about half of NAV, so leverage is 10x, but margin is notional / leverage = 6249.35 / 10 = 624.935 usd margin used. Available cash is 12,234.46, so plenty of cash.

Margin used is less than available cash.

For adding, I can increase position.

But I need to see if it's justified.

First, for MSFT, confidence in Hyp A.

Edge Depth: DEEP, so confidence can be high, say 0.85.

Risk Regime: NORMAL-WIDE, so r = 0.5 to 0.8, say 0.6 for swing.

But with event risk, I might use lower r.

Steel Man Risk: Fed/CPI in 4-5 days, not immediate, so okay for swing.

Invalidation: 4h close below 481.

Current price 483.135.

Stop distance: if I set stop at 481, that's about 2.135 points down.

But for adding, I need to calculate new margin, leverage, etc.

Perhaps I should not add new positions due to event risk next week, and just manage existing.

The risk manager note says: "into next week’s CPI/Fed cluster, prioritize defined-risk structures and avoid oversized directional bets"

So I should be cautious.

For existing MSFT position, I can hold with tight stop.

Now, for other assets, let's see if any has a clear edge.

PLTR: Hyp A, MODERATE edge, confidence around 0.75. Price 181.21, invalidation below 180. Stop distance about 1.21, which is small.

But reward/risk need to be at least 1.5.

Profit target: if I set target at say 185, that's +3.79, stop 1.21 down, so reward/risk about 3.13, good.

But confidence 0.75 might be borderline for trade, as need >0.70.

Similarly for NDX.

NDX Hyp A: MODERATE edge, confidence 0.75. Price 25663.5, invalidation below 624 for QQQ, but for XYZ100, what is the stop? Need to map.

From FOMO map, downside flush lose 624-625 for QQQ, which is NDX index around 25,000? Assume NDX index support at 25,000.

Current price 25,663.5, so stop at 25,000, distance 663.5 points, which is large. Notional would be large, so risk usd might be high.

For example, if I use leverage, notional = margin _ leverage, risk usd = margin _ r, stop distance = risk_usd / |quantity|, etc.

But with large stop distance, I might need high margin to have reasonable risk.

But since event risk, I might avoid.

GOOGL: price 320.105, invalidation below 320, stop distance 0.105, very small, but price might be noisy.

Profit target above 325, +4.895, reward/risk high if stop tight.

But confidence MODERATE.

AMZN: range 228-231, current 229.65, so not at edge, so no clear entry for range trade.

TSLA: price 455.065, between support 453-454 and resistance 457-460, so no clear edge.

So perhaps no new trades are compelling due to event risk and lack of deep edges except MSFT, which I already have.

For MSFT, I should hold the existing position.

Now, for the output, I need to output JSON for all tradeable coins, but only for those I have positions or want to trade.

I must output a JSON object with keys for each system symbol, but only if I have a action for them.

For symbols without action, I don't need to include them, or I can include with no trade, but the instruction says "return a SINGLE, VALID JSON object", and keys are system symbols, but probably only for those with trades.

Looking back: "Return a SINGLE, VALID JSON object. Keys must be the System Symbols."

But it doesn't say to include all, only for those I trade.

In the template, it shows for xyz:TSLA, so I think I only output for symbols I have a trade signal for.

For existing positions, I need to output the action.

So for MSFT, I have a position, so I must output an action.

For others, if no trade, no output.

But to be safe, I can output for all, but with "no_trade" or something, but the template doesn't show that. The signal can be "hold" for existing, or for new, "buy_to_enter" etc.

The output format has "signal" which can be "hold" or "close_position" for existing.

For symbols not traded, I don't need to include them.

But for MSFT, I have to include.

Now, for MSFT, what action? Hold, since the thesis still holds.

Confidence: I need to set confidence for the hold signal. In the existing position, confidence was 0.0, but I should update based on current view.

From Hyp A, edge deep, so confidence high.

But for hold, I might keep the existing exit plan.

Similarly, risk_usd might need to be recalc, but probably not necessary.

In the output, for hold, I need to provide all fields, so I can copy the existing exit plan, but update confidence.

The existing exit plan has profit_target 504.9, stop_loss 470.0, invalidation_condition.

Hypothesis A invalidation is 4h close below 481, which is different from 470.

I might want to adjust the stop to align with the hypothesis.

But as a systematic agent, I should probably stick to the plan or update if needed.

To simplify, I'll hold with existing plan.

Confidence: since Hyp A is deep edge, I set confidence to 0.85.

Risk_usd: from existing, it was 0.0, but I can calculate based on current.

Risk_usd is the dollar loss at stop loss.

Current quantity 12.935, entry price 483.54, stop loss 470.0, so risk per share is 483.54 - 470.0 = 13.54, so risk*usd = quantity * stop*distance = 12.935 * 13.54 ≈ let's calculate.

13.54 _ 12.935 = 13.54 _ 13 = 176.02, 13.54 \* 0.935 = 12.6659, total 188.6859 usd.

But risk_usd should be margin \* r, but for existing, it's already set.

In the output, for hold, I need to provide risk_usd, so I can calculate it.

Similarly, leverage is 10.

Add: false, since not adding.

Now, for other symbols, I don't see a clear edge to enter new trades, so no new entries.

NVDA price not available, so skip.

So only output for MSFT with hold.

But let's confirm if for MSFT, Hyp A is still valid. Price 483.135 > 481, yes.

Steel Man Risk not imminent.

So I'll hold.

For the JSON, I need to output only for xyz:MSFT.

Now, for the justification, I need to write 1-3 sentences.

Justification for holding MSFT: "MSFT shows a deep edge with uptrend continuation above 481-482 and contrarian negative funding, aligning with the AI leadership narrative. The trade offers a favorable risk/reward into the macro events, with a stop below key support."

Something like that.

Also, for confidence, set to 0.85.

Risk_usd calculated as above.

Stop_loss and profit_target from existing.

Invalidation_condition from existing: "Daily close below 470.00" but Hyp A says 4h close below 481, so there's a mismatch. To be consistent with the hypothesis, I might change the invalidation to "4h close below 481.00" but the existing is set to daily close below 470.

As a hold, I should keep the existing exit plan unless I decide to change it.

To avoid confusion, I'll keep the existing invalidation condition.

Perhaps I should update it to match the hypothesis, but for now, I'll hold as is.

Now, for the output JSON.
