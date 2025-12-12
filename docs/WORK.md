# TradingAgents Crypto – 精简工作记录

## 核心共识

- **交易动作 = 工具调用**：5 种原子动作 (`open_long/open_short/close_long/close_short/wait`) 必须通过工具触发，LLM 只在自然语言里解释为何调用；执行层与币安 api 接口进行交互调用开仓。
- **实时仓位/资金快照**：不再在入口写死 `position_state`，Trader 在链路内调用仓位/资金工具获取真实数据（来自交易所 + DB 缓存），并把 `entry_thesis` 与风险指标写回工具或状态。
- **单次多资产**：LangGraph 一次运行即覆盖最多 3 个标的，所有分析师/辩论/风控节点共享同一 `AgentState`，禁止对每个 symbol 循环跑整张图。
- **全流程必跑**：无论是否持仓，都按“基础研究 → 牛熊辩论 → Trader → 风险经理 → Manager”执行，只是提示词在“首次开仓 vs 持仓管理”时强调不同焦点。
- **成本优化滞后**：可以通过研究缓存、轻量 LLM、候选筛选降本，但前提是不破坏单次多资产 + 工具化执行的主架构。

---

## 现有能力速览（基于当前仓库）

- **多智能体链路已搭建**：市场/快讯/长文分析师、牛熊研究员、Trader、风险经理与总经理的节点和提示词在 `tradingagents/agents/*` 中已有实现，可消费 Binance 行情、Odaily 新闻以及 `FinancialSituationMemory`。
- **单标的状态机稳定**：`TradingAgentsGraph.propagate` 以 `asset_of_interest` 为单位跑完整工作流，支持 LangGraph Dev 调试、记忆回写（`reflection.py`）。
- **数据抓取与工具底层**：`tradingagents/dataflows/binance.py`、`odaily.py` 提供行情/新闻抓取、缓存与 ToolNode 封装。
- **执行层仍是文本信号**：Trader/Manager 目前只输出“买/卖/观望”的文字，没有可被直接执行的工具标准，也没有多资产/资本管理接口。

---

## 对齐 PROMPT_MODEL（美股交易代理）的新增需求

1. **多资产上下文**：PROMPT_MODEL 在一次调用里提供多个资产的 Raw Dashboard、Narrative、FOMO Map、Alpha 假设。我们需要把 `AgentState` 扩展为 `assets: dict[symbol -> AssetContext]`，让每个节点在单次推理中读写多个标的的研究结果与仓位数据。
2. **Hypothesis 驱动的讨论逻辑**：Bull/Bear/Trader/风险经理/总经理节点必须引用 `alpha_menu` 中的假设 ID、Edge Depth、Steel Man Risk，说明为何采纳/拒绝，确保与 PROMPT_MODEL 的“先选假设再决策”一致。
3. **资本/仓位/价格工具化**：除了 `get_positions`，还要 `get_capital_snapshot()`、`get_asset_prices(symbols)` 等，保证 Trader/Manager 在做 sizing 时读取真实可用保证金、NAV、最新价，并把决策通过 `submit_trade_action` tool 执行。
4. **事件与风险约束**：PROMPT_MODEL 强调 CPI/FOMC 等事件对仓位 sizing 的影响，需要在状态里记录 `event_schedule` 与 `risk_regime`，由风险团队据此调整 `risk_factor`、`confidence`、`leverage`。
5. **输出/执行一体化**：AI 不再输出 JSON 报告，而是用工具直接加仓/平仓/等待；同时在自然语言总结中回溯所选假设与风险判断，方便审计。

---

## 动作工具输入（`submit_trade_action`）

```
submit_trade_action(
  symbol: str,
  action: Literal["open_long","open_short","close_long","close_short","wait"],
  context: Optional[str],
  leverage: Optional[float],
  size: Optional[str],
  stop_loss: Optional[float],
  take_profit: Optional[float],
  confidence: Optional[int],
  reasoning: str
)
```

> 开仓类动作需同时提供 `leverage/stop_loss/take_profit`；`reasoning` 用于记录所选假设、Edge Depth、事件风险等，供执行与风控审计。

---

## 工具设计（草案）

- `get_positions(symbols: list[str]) -> list[PositionState]`
  - 返回每个 symbol 的方向、仓位量、均价、杠杆、止损/止盈、`entry_thesis`、`unrealized_pnl`。
- `get_capital_snapshot() -> CapitalState`
- 提供 `available_capital`、`nav`、`margin_usage` 等，Trader/Manager 必须先读取再 sizing。
- `get_asset_prices(symbols: list[str]) -> dict[str, PriceInfo]`
  - 减少节点重复查价，统一缓存。
- `submit_trade_action(...)`
- Trader / Manager 通过 tool 执行最终动作，执行层监听工具事件即可。
- `update_entry_thesis(symbol, thesis_payload)`（可选）
  - 首次开仓或论点改变时写入，用于后续持仓管理与对比。

> 需限定各 Agent 的工具使用权限（研究层通常只读 state，不直接调工具），并约定错误/超时的处理流程。

---

## 角色可见的信息

- **基础研究层（行情/快讯/长文）**：主要关注市场与叙事，可读取每个 symbol 是否持仓及事件日历，但默认不读细节仓位。
- **牛熊研究员**：读取各 symbol 的 `alpha_menu`、优势矩阵、entry_thesis（若已持仓），围绕“沿用/废弃哪条假设”展开辩论。
- **Trader**：必须在每次决策前调用 `get_positions` 和 `get_capital_snapshot`，明确当前仓位、资金、可承受风险，再决定是否通过工具执行动作。
- **风险经理 & Manager**：获得所有仓位详情、事件日历、Risk Manager Notes，重点评估 sizing、leverage、止损设置是否符合边界条件，再由总经理拍板。

---

## 当前待办

- [ ] **工具层对齐**：设计并实现 `get_positions`、`get_capital_snapshot`、`get_asset_prices`、`submit_trade_action`、`update_entry_thesis` 的输入/输出结构、异常与权限控制。
- [ ] **状态建模升级**：将 `AgentState` 扩展为 `assets: dict[symbol -> AssetContext]` + `portfolio_state`，支持多资产行情摘要、仓位、Alpha 菜单、entry_thesis、事件日历等信息共享。
- [ ] **多资产入口与数据注入**：在 `TradingAgentsGraph.propagate`／`graph/setup.py` 中新增多资产初始化逻辑，保证市场/快讯/长文分析师在单次运行内为每个 symbol 生成摘要，并写入对应 `AssetContext`。
- [ ] **Hypothesis/优势矩阵管理节点**：实现专门的工具或 Agent，从外部 JSON/存储中加载“Alpha 假设菜单 + 优势质量矩阵 + Risk Manager Note”，并把索引/字段写入 state，供后续节点引用。
- [ ] **提示词重写**：更新 Bull/Bear/Trader/风险经理/Manager 的 prompt，要求引用 `alpha_menu`、指明假设 ID、Edge Depth、Steel Man Risk，Trader/Manager 必须先调用数据工具再 `submit_trade_action`。
- [ ] **事件/风险注入**：建立 `event_schedule` 数据结构及生成节点，让风控层根据 FOMC/CPI 等事件动态调整 `risk_factor`、`confidence`、`leverage`。
- [ ] **端到端校验**：编写测试脚本，模拟 3 个 symbol + PROMPT_MODEL 样式的结构化输入，验证单次图运行即可完成研究 →Trader→Manager→ 工具调用的闭环。

---

## 分阶段落地建议

1. **基础设施阶段**：先完成工具接口与多资产 `AgentState`，确保所有节点能读取统一的仓位/资金/行情数据；在 `main.py` 中提供示例入口（一次性传入多 symbol 与结构化输入）。
2. **Hypothesis 驱动阶段**：实现 Alpha 菜单/优势矩阵注入节点，重写研究员、Trader 与风控层提示词，保证每次讨论都引用具体假设、Edge Depth、Steel Man Risk。
3. **执行落地阶段**：让 Trader/Manager 真实调用工具执行，并在 `Reflection`/记忆系统中记录“假设 → 动作 → 结果”，为后续复盘提供数据。

---

## 后续讨论点

- 多资产输入格式：结构化数据（宏观、Raw Dashboard、Narrative、FOMO、Alpha 菜单）如何在一次调用中传入并与各 Agent 对齐。
- 是否需要额外工具支持部分减仓、止损调整等更细粒度动作（超出 5 个原子动作的扩展）。
- 决策频率/触发方式：在多资产单次运行的前提下，如何缓存研究输出、调节高频 Trader 调用与低频研究刷新。
