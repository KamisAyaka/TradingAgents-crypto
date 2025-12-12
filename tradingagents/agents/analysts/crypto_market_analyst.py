from typing import Sequence
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, MessagesState, START, END

from tradingagents.agents.utils.crypto_market_tools import (
    get_crypto_market_data,
    get_support_resistance_levels,
)


def create_crypto_market_analyst(llm):
    """
    Analyst node that focuses on Binance market structure and technical context.
    使用 LangGraph 的 ToolNode + bind_tools 模式自动循环调用工具。
    """

    # 1. 绑定工具到 LLM（和官方示例一样）
    tools = [get_crypto_market_data, get_support_resistance_levels]
    llm_with_tools = llm.bind_tools(tools)

    # 2. ToolNode：真正执行工具的节点
    tool_node = ToolNode(tools)

    # 3. 定义"是否继续"的路由逻辑（和官方示例的 should_continue 类似）
    def should_continue(state: MessagesState):
        messages: Sequence[BaseMessage] = state["messages"]
        last_message = messages[-1]
        # 如果最后一条消息里有 tool_calls，就去 tools 节点；否则结束
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    # 4. 根据不同的 system_message 构建一个图（里面包含 call_model + tools 节点）
    def build_graph(system_message: str):
        # 内部的 call_model 会捕获 system_message 这个闭包变量

        def call_model(state: MessagesState):
            messages = state["messages"]

            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_message),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            chain = prompt | llm_with_tools
            # 这里传入的是 {"messages": messages}，对应 MessagesPlaceholder
            response = chain.invoke({"messages": messages})
            return {"messages": [response]}

        builder = StateGraph(MessagesState)
        builder.add_node("call_model", call_model)
        builder.add_node("tools", tool_node)

        builder.add_edge(START, "call_model")
        builder.add_conditional_edges("call_model", should_continue, ["tools", END])
        builder.add_edge("tools", "call_model")

        return builder.compile()

    def crypto_market_node(state):
        current_date = state.get("trade_date", "Unknown date")
        symbol = state.get("asset_of_interest", "BTCUSDT")

        base_system_message = (
            "你是一名专注于币安现货数据的加密市场技术分析师。请分析给定交易对的市场结构和技术上下文，输出以交易执行为目标的分析。\n"
            "请严格按照以下步骤进行分析：\n"
            "1. 调用行情数据工具获取数据\n"
            "2. 调用支撑/阻力工具获取关键技术价位\n"
            "3. 将均线、MACD、KDJ、布林带等指标的共振映射到可执行的偏向（多/空/观望）\n"
            "4. 给出具体的技术分析结论以及可能的价格走势预测\n"
            "5. 最后只输出一个严格的JSON格式结果，不要包含其他任何文字\n\n"
            "输出的JSON格式示例：\n"
            "{{\n"
            '  "analysis_date": "YYYY-MM-DD",\n'
            '  "asset": "crypto asset",\n'
            '  "overall_bias": "bullish|bearish|neutral",\n'
            '  "key_levels": [\n'
            '    {{\n'
            '      "type": "support/resistance",\n'
            '      "price": 1234,\n'
            '      "confidence": "high/medium/low",\n'
            '    }}\n'
            '  ],\n'
            '  "technical_signals": [\n'
            '    {{\n'
            '      "indicator": "macd",\n'
            '      "signal": "bullish|bearish|neutral",\n'
            '      "strength": "strong/medium/weak"\n'
            '    }}\n'
            '  ],\n'
            '  "market_structure": "市场结构分析",\n'
            '  "risk_assessment": "风险评估",\n'
            "}}"
        )

        # 加上团队/日期/资产的前置说明（类似你原来的 system 模板）
        system_message = (
            "你隶属于一个多智能体的加密研究团队。请调用可用工具获取更多信息。"
            f" 当前日期：{current_date}，关注交易对：{symbol}。\n"
            f"{base_system_message}"
        )

        # 为当前这次调用构建一张图（包含 call_model + tools + 循环）
        graph = build_graph(system_message)

        # 只传递原始对话消息，工具调用由图自动循环处理
        conversation = list(state["messages"])

        result_state = graph.invoke({"messages": conversation})
        final_messages: Sequence[BaseMessage] = result_state["messages"]
        result = final_messages[-1]

        report = result.content or ""

        return {
            "messages": final_messages,
            "market_report": report,
        }

    return crypto_market_node