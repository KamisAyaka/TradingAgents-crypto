import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    # LLM settings
    "llm_provider": os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openai"),
    "quick_llm_provider": os.getenv("TRADINGAGENTS_QUICK_LLM_PROVIDER", "openai"),
    "deep_llm_provider": os.getenv("TRADINGAGENTS_DEEP_LLM_PROVIDER", "deepseek"),
    "deep_think_llm": os.getenv(
        "TRADINGAGENTS_DEEP_THINK_LLM", "deepseek-ai/DeepSeek-V3.2"
    ),
    "quick_think_llm": os.getenv("TRADINGAGENTS_QUICK_THINK_LLM", "Qwen/Qwen3-8B"),
    "backend_url": os.getenv(
        "TRADINGAGENTS_BACKEND_URL", "https://api-inference.modelscope.cn/v1/"
    ),
    "quick_backend_url": os.getenv(
        "TRADINGAGENTS_QUICK_BACKEND_URL", "https://api-inference.modelscope.cn/v1/"
    ),
    "deep_backend_url": os.getenv(
        "TRADINGAGENTS_DEEP_BACKEND_URL", "https://api-inference.modelscope.cn/v1/"
    ),
    "deep_fallback_backend_url": os.getenv(
        "TRADINGAGENTS_DEEP_FALLBACK_BACKEND_URL", "https://api.deepseek.com/v1"
    ),
    "longform_llm_provider": os.getenv("TRADINGAGENTS_LONGFORM_LLM_PROVIDER", "dashscope"),
    "longform_llm_model": os.getenv("TRADINGAGENTS_LONGFORM_LLM_MODEL", "qwen-turbo"),
    # Memory settings
    "use_chroma_memory": True,
    "chroma_path": os.path.join(
        os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
        "chroma_store",
    ),
    # Trading constraints
    "min_leverage": 5,
    "max_leverage": 10,
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_recur_limit": 100,
    # Logging options
    "suppress_console_output": False,
    "text_log_enabled": False,
    "text_log_dir": None,
    "trader_round_db_path": os.path.join(
        os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
        "trader_round_memory.db",
    ),
    "trace_db_path": os.path.join(
        os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
        "trace_store.db",
    ),
}
