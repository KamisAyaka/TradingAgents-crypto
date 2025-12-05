from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from datetime import date
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["quick_llm_provider"] = "openai"
config["quick_think_llm"] = "deepseek-ai/DeepSeek-V3.2"
config["deep_llm_provider"] = "openai"
config["deep_think_llm"] = "deepseek-ai/DeepSeek-V3.2"
config["backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["quick_backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["deep_backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["max_debate_rounds"] = 1
config["use_chroma_memory"] = False

# Initialize with custom config
ta = TradingAgentsGraph(
    debug=True,
    config=config,
    selected_analysts=["market", "newsflash", "longform"],
)

# forward propagate for a crypto pair
trade_date = date.today().isoformat()  # 或任何你想测试的日期字符串
_, decision = ta.propagate("BTCUSDT", trade_date)
print(decision)
