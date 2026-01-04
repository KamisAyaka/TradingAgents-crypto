from datetime import date

from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Load environment variables from .env file
load_dotenv()

# Create a config based on defaults
config = DEFAULT_CONFIG.copy()

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
default_min_leverage = int(config.get("min_leverage", 5))
default_max_leverage = int(config.get("max_leverage", 10))

# Export the graph object for LangGraph Dev / API
agent = ta.graph

# 导出默认输入状态，方便langgraph dev使用
default_input = {
    "messages": [("human", f"多资产交易分析：{', '.join(default_tickers)}")],
    "assets_under_analysis": default_tickers,
    "trade_date": default_date,
    "available_capital": 100.0,
    "min_leverage": default_min_leverage,
    "max_leverage": default_max_leverage,
}

if __name__ == "__main__":
    # forward propagate for a crypto pair when run as plain script
    _, decision = ta.propagate(
        default_tickers,
        available_capital=100.0,
        min_leverage=default_min_leverage,
        max_leverage=default_max_leverage,
    )
    print(decision)
