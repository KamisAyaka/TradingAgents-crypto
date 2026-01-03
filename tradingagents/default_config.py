import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    # LLM settings
    "llm_provider": "openai",
    "quick_llm_provider": "openai",
    "deep_llm_provider": "openai",
    "deep_think_llm": "Qwen/Qwen2.5-7B-Instruct",
    "quick_think_llm": "Qwen/Qwen2.5-7B-Instruct",
    "backend_url": "https://api-inference.modelscope.cn/v1/",
    "quick_backend_url": "https://api-inference.modelscope.cn/v1/",
    "deep_backend_url": "https://api-inference.modelscope.cn/v1/",
    "longform_llm_provider": "dashscope",
    "longform_llm_model": "qwen-turbo",
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
