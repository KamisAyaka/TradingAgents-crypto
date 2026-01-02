### 一次完整调用的生命周期

1. **初始化图**

   - 在 `main.py` 中构造 `TradingAgentsGraph(config=...)`。
   - 根据配置创建 quick/deep LLM、记忆实例、工具节点和条件逻辑。
   - 通过 `GraphSetup.setup_graph(selected_analysts=[...])` 构建 `StateGraph` 并编译为 `graph`。
   - 图结构保留分析师阶段 + 辩论阶段 + 交易员阶段 + 硬性风控门槛。

2. **构造初始状态**

   - 调用 `TradingAgentsGraph.propagate(asset_symbols, trade_date, available_capital=...)`。
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
     - 输入：研究报告、历史辩论记录。
     - 输出：辩论观点与论据的文本。
     - 这些文本被追加到：
       - `investment_debate_state["history"]`
   - `ConditionalLogic.should_continue_debate` 根据 `max_debate_rounds` 和当前说话方决定：
     - 继续轮换到对方研究员；
     - 或结束辩论，将控制权交给 Trader。

5. **交易员判断阶段**

   - `Trader` 节点读取：
     - 市场分析报告 `state["market_report"]`
     - 过往“交易执行经验”记忆
     - 两位辩论员辩论的结果
   - 输出一份“统一投资计划字符串”，写入：
     - `state["trader_investment_plan"]`
   - 交易员方案需包含入场价、止损价与杠杆信息，供硬性风控计算与调整。

6. **硬性风控与直接执行**

   - 在交易员方案输出后立刻执行硬性风控校验，允许所有方案进入执行链路，但对按入场价与杠杆折算后亏损超过 10% 的止损强制调整为 10%。
   - 风控通过后直接调用执行函数完成下单，不再将“执行交易”包装成工具节点供 agent 调用。
   - 执行结果与状态写入 `final_trade_decision`，供外部系统调用。
