from typing import Sequence, Any
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, MessagesState, START, END

from tradingagents.agents.utils.agent_utils import (
    get_crypto_newsflash_candidates,
    get_crypto_newsflash_content,
)


def _extract_text_from_message(message: Any) -> str:
    """Best-effort extraction of plain text from a LangChain message."""
    if message is None:
        return ""

    content = getattr(message, "content", message)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text = (
                    chunk.get("text")
                    or chunk.get("content")
                    or ""
                )
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(chunk))
        return "\n".join(parts)

    return str(content)

def create_crypto_newsflash_analyst(llm):
    """
    Analyst node focusing on Odaily news flashes for rapid crypto market context，
    使用 LangGraph 的 ToolNode + bind_tools 模式自动循环调用工具。
    """

    # 将工具绑定到 LLM
    tools = [get_crypto_newsflash_candidates, get_crypto_newsflash_content]
    llm_with_tools = llm.bind_tools(tools)

    # ToolNode：真正执行工具调用
    tool_node = ToolNode(tools)

    # 是否继续（是否还有 tool_calls）的路由逻辑
    def should_continue(state: MessagesState):
        messages: Sequence[BaseMessage] = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    # 根据 system_message 构建一张 Graph（内部包含 call_model + tools 循环）
    def build_graph(system_message: str):
        def call_model(state: MessagesState):
            messages = state["messages"]

            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_message),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            chain = prompt | llm_with_tools
            # 对应 MessagesPlaceholder(variable_name="messages")
            response = chain.invoke({"messages": messages})
            return {"messages": [response]}

        builder = StateGraph(MessagesState)
        builder.add_node("call_model", call_model)
        builder.add_node("tools", tool_node)

        builder.add_edge(START, "call_model")
        builder.add_conditional_edges("call_model", should_continue, ["tools", END])
        builder.add_edge("tools", "call_model")

        return builder.compile()

    # 对外暴露的节点函数
    def crypto_newsflash_node(state):
        current_date = state.get("trade_date", "Unknown date")
        asset = state.get("asset_of_interest", "BTCUSDT")

        base_system_message = (
            "你是一名加密快讯分析师，负责梳理 Odaily 最新的短新闻，并说明其对交易的影响。\n"
            "请严格按照以下步骤进行分析：\n"
            "1. 调用候选列表工具获取最新的快讯标题\n"
            "2. 根据标题选择你感兴趣的快讯，调用内容工具获取详情\n"
            "3. 分析每条事件、标注多空倾向，并强调对数字资产交易者的可执行含义\n"
            "4. 将同类型事件（协议升级、监管动作等）聚合点评\n"
            "5. 给出具体结论以及可能的价格/情绪冲击\n"
            "6. 最后只输出一个严格的JSON格式结果，不要包含其他任何文字\n\n"
            "输出的JSON格式示例：\n"
            "{{\n"
            '  "analysis_date": "YYYY-MM-DD",\n'
            '  "asset": "crypto asset",\n'
            '  "overall_sentiment": "bullish|bearish|neutral",\n'
            '  "key_events": [\n'
            '    {{\n'
            '      "title": "新闻标题",\n'
            '      "sentiment": "bullish|bearish|neutral",\n'
            '      "impact": "high|medium|low",\n'
            '      "summary": "事件摘要",\n'
            '      "implications": "对交易的影响"\n'
            '    }}\n'
            '  ],\n'
            '  "market_impact": "总体市场影响分析",\n'
            "}}"
        )

        # 加上协作、多智能体、日期、资产的上下文
        system_message = (
            "你隶属于一个多智能体的加密研究团队。请调用可用工具获取最新的新闻。"
            f" 当前日期：{current_date}，关注资产：{asset}。\n"
            f"{base_system_message}"
        )

        # 为本次任务构建一张 Graph
        graph = build_graph(system_message)

        # 只传递原始消息，工具调用交给 Graph 自动处理
        conversation = list(state["messages"])

        result_state = graph.invoke({"messages": conversation})
        final_messages: Sequence[BaseMessage] = result_state["messages"]
        result: Any = final_messages[-1]

        report_text = _extract_text_from_message(result)
        report = report_text or "【错误】快讯分析生成失败。"

        return {
            "messages": final_messages,
            "newsflash_report": report,
        }

    return crypto_newsflash_node
