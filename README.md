# TradingAgents Crypto 多智能体交易研究框架

一个面向加密货币/合约交易的多智能体研究与决策框架，基于 LangGraph/LangChain 构建。  
框架会让多名“虚拟分析师”协作完成：行情研究 → 新闻/长文研读 → 牛熊辩论 → 风险讨论 → 最终交易建议。

---

## 功能概览

- **多角色协作**

  - 市场分析师：K 线、Binance 行情。
  - 快讯分析师：Odaily 新闻快讯。
  - 长文分析师：Odaily 长篇文章缓存与加载。
  - 看涨/看跌研究员：围绕研究报告展开牛熊辩论。
  - 激进/保守风险分析师：围绕仓位/杠杆/止损进行风险博弈。
  - 交易员 + 风险法官：收敛为统一执行计划与最终决策。

- **工具与数据流**

  - `tradingagents/dataflows/binance.py`：Binance 行情抓取与本地缓存。
  - `tradingagents/dataflows/odaily.py`：Odaily RSS/快讯抓取，存入 SQLite。
  - `tradingagents/agents/utils/binance_trade_tools.py`：交易执行与仓位查询工具（Agent 直接调用获取仓位，无需本地快照）。
  - 对应 LangGraph ToolNode 封装在 `tradingagents/agents/utils/*_tools.py`。

- **记忆系统与复盘**

  - `FinancialSituationMemory`（Chroma 或内存向量库）存储“情景 → 建议”。
  - `tradingagents/graph/reflection.py` 在每次交易后对各角色表现做反思，并写回记忆。
  - `TradingAgentsGraph.record_trade_reflection()` 可在平仓后调用，结合 `trade_info`（symbol/side/entry/exit/pnl 等）生成完整交易复盘，写入 `trade_memory`。

- **可插拔 LLM**
  - 默认配置使用 Google Gemini + 阿里云 DashScope（长文+embedding）。
  - 示例入口 `main.py` 展示了如何切换到 ModelScope 的 OpenAI 兼容接口（Qwen / DeepSeek）。

---

## 整体流程与思路

1. **数据准备 / 缓存层**
   - 行情、快讯、长文由 `fetchers/binance_fetcher.py` 与 `fetchers/odaily_fetcher.py` 定时写入 `tradingagents/data/` 下的 SQLite，避免多 Agent 运行时重复联网。
   - 仓位信息由 Agent 运行时通过 `get_binance_positions` 工具直接获取，不做轮询快照。

2. **多智能体推理**
   - 调度器 `trigger.py` 会按纽约时间把资产列表、资金、杠杆约束注入到 `TradingAgentsGraph`。流程顺序为：市场报告 → Odaily 快讯 → 长文研究 → 牛熊辩论 → 交易员执行计划 → 风控复核 → 总经理裁决。
   - 每轮结束后，`SessionSummarizer` 会把“这一轮讨论的要点/分歧/待办”写入 `session_memory`，供下一轮复用。

3. **日终总结**
   - `trigger.py` 额外安排了每日 23:50（纽约时间）的日终任务：`generate_daily_session_summary()` 聚合当天所有 `session` 记录为一条 `session_daily` 记忆，并清理对应的轻量条目，保持记忆库精简。

4. **交易复盘**
   - 当仓位监听服务发现某个 `symbol` 的仓位从非零降到 0（意味着平仓），把入场/出场时间、价格、杠杆、PnL 等字段组合成 `trade_info` 调用 `TradingAgentsGraph.record_trade_reflection()`。
   - `TradeCycleReflector` 会引用最近一次 `propagate()` 的 `state`（市场报告、牛熊观点、Trader/Risk/Manager 输出），生成结构化复盘，并写入 `trade_memory`。这样下一次遇到相似场景时，Trader/Risk/Manager 可以按 `memory_type="trade"` 搜索历史执行经验。

5. **记忆与工具复用**
   - Trader 和 Manager 在 prompt 中会按 `memory_type` 拉取对应记忆：`session/session_daily` 用于回顾讨论背景，`trade` 用于学习真实操作经验。
   - 如果你要接入真实交易系统，只需实现两件事：① 开仓时把必要字段（symbol、杠杆、止盈止损等）写入仓位监听；② 平仓后调用 `record_trade_reflection(trade_info)`，让记忆系统自动更新。

---

## 快速开始

### 环境要求

- Python `>= 3.10`
- 推荐在虚拟环境中安装依赖（`venv` / `uv` / `conda` 均可）。
- TA-Lib 等依赖可能需要操作系统级的预编译库（可按本机环境安装）。

### 安装依赖

```bash
pip install -e .
```

或使用 `uv`：

```bash
uv sync
```

### 配置 LLM 与环境变量

框架默认配置在 `tradingagents/default_config.py` 中，支持通过环境变量覆盖（下方以你给出的 Qwen + DeepSeek 组合为例）：

- 使用默认的 Google Gemini + DashScope：
  - 设置 `GOOGLE_API_KEY`（用于 `llm_provider="google"`）。
  - 设置 `DASHSCOPE_API_KEY`，以及可选的 `DASHSCOPE_BASE_URL` / `DASHSCOPE_EMBEDDING_MODEL`。
- 或参考 `main.py`，覆盖为 ModelScope 的 OpenAI 兼容接口：
  - `config["llm_provider"] = "openai"` 等。
  - `config["backend_url"] = "https://api-inference.modelscope.cn/v1/"`。
  - 将 `OPENAI_API_KEY` 设置为 ModelScope 的 API Key。

推荐：通过环境变量配置“快模型=ModelScope Qwen / 深模型=DeepSeek（优先 ModelScope 免费接口，失败再切换官方）”。

```bash
# 快模型：ModelScope Qwen3-8B（OpenAI 兼容接口）
export TRADINGAGENTS_QUICK_LLM_PROVIDER="openai"
export TRADINGAGENTS_QUICK_THINK_LLM="Qwen/Qwen3-8B"
export TRADINGAGENTS_QUICK_BACKEND_URL="https://api-inference.modelscope.cn/v1/"
export OPENAI_API_KEY="<你的 ModelScope API Key>"

# 深模型：DeepSeek（优先走 ModelScope 免费接口）
export TRADINGAGENTS_DEEP_LLM_PROVIDER="deepseek"
export TRADINGAGENTS_DEEP_THINK_LLM="deepseek-ai/DeepSeek-V3.2"
export TRADINGAGENTS_DEEP_BACKEND_URL="https://api-inference.modelscope.cn/v1/"
export TRADINGAGENTS_DEEP_FALLBACK_BACKEND_URL="https://api.deepseek.com/v1"
export DEEPSEEK_API_KEY="<你的 DeepSeek 官方 Key>"

# 若你想额外设置 fallback Key（可选）：
# export DEEPSEEK_FALLBACK_API_KEY="<你的 DeepSeek 官方 Key>"
```

记忆模块 `FinancialSituationMemory` 依赖 DashScope embedding，缺少 `DASHSCOPE_API_KEY` 会直接报错。

### 运行一次完整流程

当前默认入口是 `main.py`，会用多 Agent 框架分析多个交易对（示例：`BTCUSDT` + `ETHUSDT`），并支持传入一次运行可支配的总资金：

```bash
python main.py
```

它会：

1. 构建一个 `TradingAgentsGraph`，注入 LLM、工具与记忆。
2. 默认按当天日期和你传入的资产列表初始化（若缺省则使用 `BTCUSDT`, `ETHUSDT`；日期默认当天 `ISO8601`），并可选传入 `available_capital`（默认 10,000 美元记账单位）供 Trader/风控层分配。
3. 依次调用行情/快讯/长文分析师（每个分析师会对资产列表逐个出报告）→ 牛熊辩论 → 风险讨论 → 风险法官。
4. 控制台打印整合后的交易建议（多资产买入/卖出/观望 + 理由）。

如果你使用 LangGraph Dev，可以直接用仓库自带的配置：

```bash
langgraph dev
```

`langgraph.json` 已将 `main.py:agent` 暴露为可交互的图。

---

## 代码结构一览

- `main.py`：示例入口，演示如何配置 LLM 并调用支持多资产的 `TradingAgentsGraph.propagate`。
- `tradingagents/default_config.py`：所有 LLM/内存/日志相关的默认配置。
- `tradingagents/graph/`
  - `setup.py`：定义整套多 Agent 工作流图（StateGraph wiring）。
  - `propagation.py`：初始化状态（`assets_under_analysis`、日期、debate state 等）。
  - `trading_graph.py`：对外的高层封装（`TradingAgentsGraph`），包含 `propagate` / `reflect_and_remember`。
  - `conditional_logic.py`：控制牛熊辩论的轮数与轮转逻辑。
  - `signal_processing.py`：将复杂讨论结果压缩为最终信号字符串。
  - `reflection.py`：复盘各角色的表现并写入记忆库。
- `tradingagents/agents/`
  - `analysts/`：市场、快讯、长文等基础研究节点。
  - `researchers/`：看涨/看跌研究员节点（消费研究报告 + 过往记忆）。
  - `risk_mgmt/`：单一风险经理节点，负责在交易员方案基础上输出风控建议。
  - `managers/`：总经理节点（最终 buy/hold/sell 决策）。
  - `trader/`：交易员/执行者，将牛熊辩论与记忆收敛为一份交易计划。
  - `utils/`：工具封装（行情/新闻工具、状态类型、内存接口等）。
- `tradingagents/dataflows/`
  - `binance.py`：Binance 行情抓取、缓存与查询工具。
  - `odaily.py`：Odaily 快讯/长文 RSS 抓取与 SQLite 存储。
  - `utils.py`：通用数据抓取/解析辅助函数。
- `tradingagents/data/`
  - `binance_cache.db`：本地行情缓存。
  - `odaily_rss.db`：Odaily 新闻与文章存储。

---

## 开发指南（简要版）

更完整、按模块拆分的开发文档请见：`docs/DEVELOPMENT_GUIDE.md`。  
这里给出最常用的几个扩展路径：

### 1. 新增/修改分析师角色

- 在 `tradingagents/agents/analysts/` 下新增一个模块，实现一个接收 `state`、返回局部 `dict` 更新的节点函数。
- 在 `tradingagents/agents/__init__.py` 中导出你的工厂函数（例如 `create_my_new_analyst`）。
- 在 `tradingagents/graph/setup.py` 中：
  - 在 `selected_analysts` 支持你的新 key；
  - 为其 `add_node`，必要时增加 ToolNode 和清理节点；
  - 接好前置/后置的 wiring（参考 `market` / `newsflash` / `longform`）。

### 2. 调整辩论轮数

- 修改 `tradingagents/default_config.py`：
  - `max_debate_rounds`：控制牛/熊轮流说几轮。
- `tradingagents/graph/conditional_logic.py` 会读取该值，决定何时跳转到 Trader；风险经理与总经理阶段固定串行执行。

### 3. 调整或替换 LLM 提示词

- 各角色的中文 prompt 都写在对应节点文件里，例如：
  - `tradingagents/agents/researchers/bull_researcher.py`
  - `tradingagents/agents/researchers/bear_researcher.py`
  - `tradingagents/agents/risk_mgmt/*.py`
  - `tradingagents/agents/trader/trader.py`
- 你可以直接编辑这些 prompt，或抽离成模板文件再在代码中加载。

### 4. 使用与调试记忆库

- 记忆类统一在 `tradingagents/agents/utils/memory.py` 中定义：
  - 默认使用 Chroma 的持久化向量库（`use_chroma_memory=True`），路径由 `chroma_path` 控制。
  - 若未安装 Chroma 或初始化失败，会自动退回 `_SimpleMemoryCollection`（内存版）。
- 研究员/交易员会通过 `get_memories(curr_situation, n_matches=2)` 查询“类似行情下的历史建议”。
- 交易结束后，可调用 `TradingAgentsGraph.reflect_and_remember(returns_losses)` 写入新记忆。

---

## 后续计划

这个仓库仍在演进中，典型可扩展方向包括：

- 接入更多交易所或现货/期权数据源；
- 为各智能体加入更细粒度的工具（链上数据、情绪指标等）；

如果你准备在此基础上做二次开发或接入自己的执行系统，强烈建议先阅读  
`docs/DEVELOPMENT_GUIDE.md` 了解整体数据流与 Agent 交互约定。
