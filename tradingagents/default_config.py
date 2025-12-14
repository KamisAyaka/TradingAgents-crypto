import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    # LLM settings
    "llm_provider": "google",
    "quick_llm_provider": None,
    "deep_llm_provider": None,
    "deep_think_llm": "gemini-2.0-flash-lite",
    "quick_think_llm": "gemini-2.0-flash-lite",
    "backend_url": "https://generativelanguage.googleapis.com/v1",
    "quick_backend_url": None,
    "deep_backend_url": None,
    "longform_llm_provider": "dashscope",
    "longform_llm_model": "qwen-plus",
    # Memory settings
    "use_chroma_memory": True,
    "chroma_path": os.path.join(os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"), "chroma_store"),
    # Trading constraints
    "min_leverage": 1.0,
    "max_leverage": 3.0,
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_recur_limit": 100,
    # Logging options
    "suppress_console_output": False,
    "text_log_enabled": False,
    "text_log_dir": None,
}
