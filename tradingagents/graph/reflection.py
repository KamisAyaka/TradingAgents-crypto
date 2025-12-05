# TradingAgents/graph/reflection.py

from typing import Dict, Any, Union
from langchain_openai import ChatOpenAI


class Reflector:
    """负责对各角色的决策进行复盘，并将经验写入记忆库。"""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """初始化反思器，需要注入一个快速 LLM。"""
        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = self._get_reflection_prompt()

    def _get_reflection_prompt(self) -> str:
        """构建中文反思提示词。"""
        return """
你是一名资深加密货币分析师，负责对本团队的交易决策进行复盘。请严格按照以下步骤输出：

1. **判定决策成败**：结合收益/回撤情况，说明该次决策（买入、卖出、观望）是成功还是失误。
2. **技术 + 市场因素**：逐项拆解导致结果的核心因素，例如：
   - 价格结构（支撑阻力、趋势断层、清算区）
   - 新闻/叙事（监管事件、技术升级、生态催化）
   - 宏观流动性（美元指数、利率、全球风险偏好）
   并指出每个因素的作用方向与相对权重。
3. **修正建议**：若决策存在瑕疵，提出具体可执行的改进措施（如调整仓位、设定新的止损/止盈、关注什么触发条件等）。
4. **迁移经验**：总结本次复盘的关键洞察，说明在未来的加密市场场景中如何快速应用。
5. **一句话摘要**：用不超过 1000 tokens 的中文语句，浓缩最重要的经验，以便搜索与留档。

输入将包含客观的市场报告（价格、技术指标、快讯、长文研究等）；请生成结构化、可执行且聚焦加密市场的复盘结果。
"""

    def _extract_current_situation(self, current_state: Dict[str, Any]) -> str:
        """从状态中提取当前市场情境。"""
        curr_market_report = current_state["market_report"]
        curr_newsflash_report = current_state["newsflash_report"]
        curr_longform_report = current_state["longform_report"]

        return f"{curr_market_report}\n\n{curr_newsflash_report}\n\n{curr_longform_report}"

    def _reflect_on_component(
        self, component_type: str, report: str, situation: str, returns_losses
    ) -> str:
        """对指定角色生成反思内容。"""
        messages = [
            ("system", self.reflection_system_prompt),
            (
                "human",
                f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}",
            ),
        ]

        raw_content = self.quick_thinking_llm.invoke(messages).content
        return self._normalize_content(raw_content)

    @staticmethod
    def _normalize_content(content: Union[str, list, dict, None]) -> str:
        """LangChain 的返回可能是字符串、列表或富结构，这里统一转成字符串。"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        if content is None:
            return ""
        return str(content)

    def reflect_bull_researcher(self, current_state, returns_losses, bull_memory):
        """反思看涨研究员的表现，并更新记忆。"""
        situation = self._extract_current_situation(current_state)
        bull_debate_history = current_state["investment_debate_state"]["bull_history"]

        result = self._reflect_on_component(
            "BULL", bull_debate_history, situation, returns_losses
        )
        bull_memory.add_situations([(situation, result)])

    def reflect_bear_researcher(self, current_state, returns_losses, bear_memory):
        """反思思看跌研究员。"""
        situation = self._extract_current_situation(current_state)
        bear_debate_history = current_state["investment_debate_state"]["bear_history"]

        result = self._reflect_on_component(
            "BEAR", bear_debate_history, situation, returns_losses
        )
        bear_memory.add_situations([(situation, result)])

    def reflect_trader(self, current_state, returns_losses, trader_memory, invest_judge_memory):
        """反思交易员（兼裁决者）的决策，并同步到两类记忆。"""
        situation = self._extract_current_situation(current_state)
        trader_decision = current_state["trader_investment_plan"]

        result = self._reflect_on_component(
            "TRADER", trader_decision, situation, returns_losses
        )
        trader_memory.add_situations([(situation, result)])
        invest_judge_memory.add_situations([(situation, result)])

    def reflect_risk_manager(self, current_state, returns_losses, risk_manager_memory):
        """反思风险法官的决策。"""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["risk_debate_state"]["judge_decision"]

        result = self._reflect_on_component(
            "RISK JUDGE", judge_decision, situation, returns_losses
        )
        risk_manager_memory.add_situations([(situation, result)])
