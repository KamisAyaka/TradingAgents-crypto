TradingAgents-crypto
====================

多智能体加密交易研究框架，整合了 Binance 行情工具、Odaily 新闻快讯/长文数据，以及多轮辩论 + 风控裁决链路。当前仓库已启用强制工具调用（行情、快讯节点都会自动调用对应数据源）与 Debug 转录日志，方便复盘每一步交互。

## 功能亮点

- **多分析师协作**：市场、新闻快讯、长文研究三类分析师并行产出，随后由研究员、交易员与风险团队接力形成最终策略。
- **强制数据采集**：市场分析师必须调用 `get_crypto_market_data/get_support_resistance_levels`，新闻分析师必须调用 `get_crypto_newsflash`，避免“空口分析”。
- **多层日志**：默认写入 `eval_results/<符号>/TradingAgentsStrategy_logs/full_states_log_<date>.json`；开启 `text_log_enabled` 后可生成 Markdown 报告；在 `debug=True` 时自动输出 JSON 转录（含每一步消息与 tool call）。
- **可插拔 LLM**：默认走 Google Gemini，可切换到 OpenAI、DeepSeek、Ollama 等，长文与记忆嵌入支持 DashScope。

## 快速上手

### 1. 环境准备

```bash
git clone <repo-url>
cd TradingAgents-crypto
python -m venv .venv && source .venv/bin/activate  # 或使用你喜欢的环境管理工具
pip install -e .  # 安装项目依赖
```

> 需要 Python 3.10 及以上版本。也可以使用 `uv pip sync uv.lock` 等命令完成依赖安装。

### 2. 配置密钥（.env）

创建 `.env` 文件，最常用的变量如下：

```dotenv
# Google Gemini（默认 quick/deep LLM）
GOOGLE_API_KEY=your_google_key

# 如果改用 OpenAI / DeepSeek，可设置：
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...

# 阿里云 DashScope，用于长文抓取与记忆嵌入
DASHSCOPE_API_KEY=...
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 可选
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4                          # 可选

# 结果目录（选填，不设置则使用默认 eval_results/...）
TRADINGAGENTS_RESULTS_DIR=./eval_results
```

根据你的模型提供商选择性地添加其他变量，如 `OPENROUTER_API_KEY` 等。

### 3. 运行示例

`main.py` 提供了最简单的调用示例：

```bash
python main.py
```

该脚本会：

1. `load_dotenv()` 读取密钥；
2. 基于 `DEFAULT_CONFIG` 自定义模型提供商/轮次等；
3. `TradingAgentsGraph(debug=True, selected_analysts=["market","newsflash","longform"])` 创建工作流；
4. 对 `BTCUSDT` 调用 `propagate(trade_date)`，输出最终交易裁决。

运行完成后，可在 `eval_results/BTCUSDT/TradingAgentsStrategy_logs/` 下找到：

- `full_states_log_<date>.json`：所有分析节点、辩论和裁决结果；
- `debug_transcript_<date>_<timestamp>.json`（仅 debug=True 时）：逐消息转录，包含 tool call 参数；
- `analysis_transcript_<date>_<timestamp>.md`（在 `config["text_log_enabled"]=True` 时）：人类可读报告。

### 4. 自定义配置

`tradingagents/default_config.py` 给出了所有可调选项，可在你自己的脚本中修改：

```python
from tradingagents.default_config import DEFAULT_CONFIG
config = DEFAULT_CONFIG.copy()

config.update(
    quick_llm_provider="google",
    quick_think_llm="gemini-2.5-pro",
    deep_llm_provider="google",
    deep_think_llm="gemini-2.5-pro",
    selected_analysts=["market", "newsflash", "longform"],
    text_log_enabled=True,
    text_log_dir="./logs/text",
    debug_log_dir="./logs/debug",
    suppress_console_output=True,
)

graph = TradingAgentsGraph(config=config, debug=True)
```

常用配置项解释：

- `selected_analysts`：可按需裁剪为 `"market"`、`"newsflash"`、`"longform"` 的任意组合；
- `max_debate_rounds` / `max_risk_discuss_rounds`：研究/风控辩论轮次；
- `text_log_enabled` & `text_log_dir`：启用 Markdown 报告并指定目录；
- `debug_log_dir`：开启调试时转录 JSON 的输出路径；
- `suppress_console_output`：若设为 `True`，调试流不会在终端打印；
- `project_dir`, `results_dir`：用于缓存与结果输出的根路径。

### 5. 读取/复盘输出

`full_states_log_<date>.json` 中包含如下键：

- `market_report` / `newsflash_report` / `longform_report`：各分析师最终文字；
- `investment_debate_state`：多轮看涨/看跌对话历史；
- `risk_debate_state`：风险辩论历史；
- `investment_plan`、`trader_investment_plan`、`final_trade_decision`：研究经理、交易员与风险法官输出。

需要查看完整提示词/模型回复，可直接打开调试模式生成的 `debug_transcript_*.json`，该文件按时间顺序列出所有 LangChain 消息与工具调用参数，适合追踪问题或复盘策略演进。

## 常见问题

- **提示“嵌入文本长度超出 8192 字符”**：DashScope 嵌入接口的限制只影响记忆向量，分析文本本身不会被截断；必要时可在 `FinancialSituationMemory` 中实现分片嵌入。
- **新闻/行情分析说无法调用工具**：现在节点已内置强制调用逻辑。如果仍看到该提示，说明多次尝试都未拿到工具响应，可检查网络/凭证。
- **日志过大**：可通过将 `debug` 设为 `False` 或关闭 `text_log_enabled` 来减少额外输出。

欢迎提交 Issue/PR，或在 `main.py` 基础上扩展更多分析节点、交易执行器或回测脚本。
