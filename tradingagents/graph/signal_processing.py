# TradingAgents/graph/signal_processing.py

from langchain_openai import ChatOpenAI


class SignalProcessor:
    """负责将长文本信号提取成最终的可执行决策。"""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """初始化时注入一个快速 LLM，用于做结果抽取。"""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """
        Process a full trading signal to extract the core decision.

        Args:
            full_signal: 完整的交易信号文本

        Returns:
            BUY/SELL/HOLD 三选一的最终裁决
        """
        messages = [
            (
                "system",
                "你是一名高效的交易助理，需要从分析师团队给出的长段交易信号中提取最终决策。"
                "请只输出 BUY / SELL / HOLD 之一，且不要附加任何额外解释或文字。",
            ),
            ("human", full_signal),
        ]

        return self.quick_thinking_llm.invoke(messages).content # type: ignore
