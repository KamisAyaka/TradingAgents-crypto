from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage

from tradingagents.agents.utils.crypto_market_tools import (
    get_crypto_market_data,
    get_support_resistance_levels,
)


def create_crypto_market_analyst(llm):
    """
    Analyst node that focuses on Binance market structure and technical context.
    """

    def crypto_market_node(state):
        current_date = state.get("trade_date", "Unknown date")
        symbol = state.get("asset_of_interest", "BTCUSDT")

        tools = [
            get_crypto_market_data,
            get_support_resistance_levels,
        ]

        system_message = (
            "你是一名专注于币安现货数据的加密市场技术分析师。请利用提供的 Binance 工具获取 OHLCV、EMA5/10/20、布林带、MACD、KDJ 以及结构化的支撑/压力数据，输出以交易执行为目标的分析。\n"
            "- 评估动能、波动率、流动性空洞与关键结构位，尤其关注 `get_support_resistance_levels` 返回的价位与指标对齐情况。\n"
            "- 将均线、MACD、KDJ、布林带等指标的共振映射到可执行的偏向（多/空/观望），并说明这些信号对突破或均值回归情景的触发条件与失效价位。\n"
            "- 根据杠杆最低 5x 的假设，评估当前到支撑/压力的距离是否足以放置止损，不满足时要强调风险或建议观望。\n"
            "- 最后附上一个 Markdown 表格，包含时间框架、方向偏好、关键价位、预计触发条件与置信度，明确引用所用指标或支撑/压力来源。"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你正在与其他加密分析师协同工作。如需更多数据请调用币安行情工具。"
                    " 当前日期：{current_date}，关注交易对：{symbol}。\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message, current_date=current_date, symbol=symbol)
        chain = prompt | llm.bind_tools(tools)

        reminder = HumanMessage(
            content="系统提醒：必须调用 get_crypto_market_data / get_support_resistance_levels 取得行情后再写分析。"
        )
        conversation = list(state["messages"])
        result = None
        max_attempts = 2

        for _ in range(max_attempts):
            result = chain.invoke(conversation)
            if getattr(result, "tool_calls", None):
                break
            conversation = conversation + [result, reminder]

        if result is None:
            raise RuntimeError("Market analyst failed to generate a response")

        report = ""
        if not getattr(result, "tool_calls", None):
            report = result.content or "【错误】未调用行情工具，无法生成市场分析。"

        return {
            "messages": [result],
            "market_report": report,
        }

    return crypto_market_node
