from datetime import date

from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()

# 使用 ModelScope 上的 Qwen2.5 Coder 系列，区分快/慢两路：
# - 快速思考：较小模型（例如 7B）
# - 深度思考：较大模型（32B）
config["llm_provider"] = "openai"
config["quick_llm_provider"] = "openai"
config["deep_llm_provider"] = "openai"

# 如果你想换别的尺寸，只需要改成对应的模型名即可
config["quick_think_llm"] = "Qwen/Qwen2.5-14B-Instruct"
config["deep_think_llm"] = "Qwen/Qwen3-14B"

# 通过 ModelScope 的 OpenAI 兼容接口调用 Qwen
config["backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["quick_backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["deep_backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["max_debate_rounds"] = 1
config["use_chroma_memory"] = True

# Initialize with custom config
ta = TradingAgentsGraph(
    debug=True,
    config=config,
    selected_analysts=["market", "newsflash", "longform"],
)

# 创建带默认状态的图实例，用于langgraph dev
# 默认跟踪两个资产，演示多代币输入
default_tickers = ["BTCUSDT", "ETHUSDT"]
default_date = date.today().isoformat()
default_min_leverage = int(config.get("min_leverage", 1))
default_max_leverage = int(config.get("max_leverage", 3))

# Export the graph object for LangGraph Dev / API
agent = ta.graph

# 导出默认输入状态，方便langgraph dev使用
default_input = {
    "messages": [("human", f"多资产交易分析：{', '.join(default_tickers)}")],
    "assets_under_analysis": default_tickers,
    "trade_date": default_date,
    "available_capital": 10000.0,
    "min_leverage": default_min_leverage,
    "max_leverage": default_max_leverage,
}

if __name__ == "__main__":
    # forward propagate for a crypto pair when run as plain script
    _, decision = ta.propagate(
        default_tickers,
        available_capital=10000.0,
        min_leverage=default_min_leverage,
        max_leverage=default_max_leverage,
    )
    print(decision)
