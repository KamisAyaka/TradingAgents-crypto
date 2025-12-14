### 一次完整调用的生命周期

1. **初始化图**

   - 在 `main.py` 中构造 `TradingAgentsGraph(config=...)`。
   - 根据配置创建 quick/deep LLM、记忆实例、工具节点和条件逻辑。
   - 通过 `GraphSetup.setup_graph(selected_analysts=[...])` 构建 `StateGraph` 并编译为 `graph`。

2. **构造初始状态**

   - 调用 `TradingAgentsGraph.propagate(asset_symbols, trade_date, available_capital=...)`（`asset_symbols` 可为单个交易对或列表，`available_capital` 用于执行链路的资金分配）。
   - 内部使用 `Propagator.create_initial_state(asset_symbols, trade_date)` 得到初始 `AgentState`，并在外部注入资金等额外字段。

3. **基础研究阶段**

   - 根据 `selected_analysts` 并行运行：
     - `Crypto Market Analyst`（行情/技术面）
     - `Crypto Newsflash Analyst`（快讯）
     - `Longform Cache Loader`（长文缓存，长文单独分析，按时间定时触发，一天分析一次即可，获取的时候直接读取数据库数据就行）
   - 分析师通过工具节点访问 Binance / Odaily，并将结果写入：
     - `state["market_report"]`
     - `state["newsflash_report"]`
     - `state["longform_report"]`

4. **牛熊辩论阶段**

   - `Bull Researcher` 与 `Bear Researcher` 轮流发言：
     - 输入：研究报告、历史辩论记录、记忆库返回的“经验教训”。
     - 输出：带 Action Plan / Team Message / Belief Update 的文本。
     - 这些文本被追加到：
       - `investment_debate_state["history"]`
       - `investment_debate_state["bull_history"]` / `["bear_history"]`
   - `ConditionalLogic.should_continue_debate` 根据 `max_debate_rounds` 和当前说话方决定：
     - 继续轮换到对方研究员；
     - 或结束辩论，将控制权交给 Trader。

5. **交易员裁决阶段**

   - `Trader` 节点读取：
     - 牛熊辩论历史 `investment_debate_state["history"]`
     - 市场分析报告 `state["market_report"]`
     - 过往“研究裁决经验”与“交易执行经验”记忆
   - 输出一份“统一投资计划字符串”，写入：
     - `state["trader_investment_plan"]`
     - `investment_debate_state["current_response"]`（给后续节点引用）

6. **风险经理阶段**

   - 单一 `Risk Manager` 节点从风险视角评估交易员方案：
     - 读取市场/快讯/长文报告、交易员操作和风险记忆；
     - 输出结构化的风控建议，写入 `risk_review_state["analyst_report"]` 并累计到 `["history"]`；
     - 将控制权交给下一节点 `Manager`。

7. **总经理阶段**

   - `Manager` 节点汇总交易员方案与风险经理建议以及历史操作记忆，执行最终裁决：
     - 写入 `risk_review_state["manager_summary"]`
     - 同时写入 `final_trade_decision`，供外部系统使用。

8. **反思与记忆更新**

   在一笔交易结束后，调用：

   - `TradingAgentsGraph.reflect_and_remember(returns_losses)`

   这会：

   - 对看涨/看跌研究员、Trader、风控经理和总经理分别生成复盘文本；
   - 使用 `FinancialSituationMemory.add_situations` 将 `(situation, recommendation)` 写入对应记忆库；
   - 下次在类似行情下，相关节点可通过 `get_memories` 取回这些“经验教训”。
