from typing import Sequence
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, MessagesState, START, END

from tradingagents.agents.utils.agent_utils import (
    get_crypto_longform_candidates,
    get_crypto_article_content,
)
from tradingagents.dataflows.odaily import save_longform_analysis


def create_crypto_longform_analyst(llm):
    """
    Analyst node that reviews Odaily long-form articles for fundamental crypto context,
    使用 LangGraph 的 ToolNode + bind_tools 模式自动循环调用工具。
    """

    # 1. 绑定工具到 LLM（和官方示例一样）
    tools = [get_crypto_longform_candidates, get_crypto_article_content]
    llm_with_tools = llm.bind_tools(tools)

    # 2. ToolNode：真正执行工具的节点
    tool_node = ToolNode(tools)

    # 3. 定义“是否继续”的路由逻辑（和官方示例的 should_continue 类似）
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

    # 5. 对外暴露的节点函数（和你原来一样返回一个 node）
    def crypto_longform_node(state):
    
        current_date = state.get("trade_date", "Unknown date")
        asset = state.get("asset_of_interest", "BTCUSDT")

        # 原来的系统提示词，稍微补充了日期和资产信息
        base_system_message = (
            "你是加密市场的长文研究员，请分析过去一周 Odaily 的深度文章，提炼可持续的基本面主题。\n"
            "请严格按照以下步骤进行分析：\n"
            "1. 调用候选列表工具获取最新的长文标题\n"
            "2. 根据标题选择你感兴趣的长文，调用内容工具获取详情\n"
            "3. 重点关注叙事（基础设施升级、监管进展、宏观驱动等），并说明对未来几天仓位的潜在影响\n"
            "4. 将每篇文章压缩成\"观点/论据/风险\"\n"
            "5. 在可能时区分主流共识与逆势观点\n"
            "6. 给交易者提供可执行的见解\n"
            "7. 最后只输出一个严格的JSON格式结果，不要包含其他任何文字\n\n"
            "输出的JSON格式示例：\n"
            "{{\n"
            '  "analysis_date": "YYYY-MM-DD",\n'
            '  "asset": "crypto asset",\n'
            '  "overall_thesis": "总体观点",\n'
            '  "key_articles": [\n'
            '    {{\n'
            '      "title": "文章标题",\n'
            '      "sentiment": "bullish|bearish|neutral",\n'
            '      "thesis": "核心观点",\n'
            '      "argument": "支持论据",\n'
            '      "risk": "风险提示",\n'
            '      "contrarian_view": "逆势观点（如果有）"\n'
            '    }},\n'
            '  ],\n'
            '  "market_narratives": ["主要叙事1", "主要叙事2"],\n'
            '  "trading_implications": "交易影响分析",\n'
            "}}"
        )

        # 加上团队/日期/资产的前置说明（类似你原来的 system 模板）
        system_message = (
            "你隶属于一个多智能体的加密研究团队。"
            " 请先调用候选列表工具审阅最新长文，再针对选定文章调用内容工具。"
            f" 当前日期：{current_date}，关注资产：{asset}。\n"
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
        # 确保report是字符串类型后再传递给save_longform_analysis
        if report and isinstance(report, str):
            save_longform_analysis(asset, report, current_date)

        return {
            "messages": final_messages,
            "longform_report": report,
        }

    return crypto_longform_node
