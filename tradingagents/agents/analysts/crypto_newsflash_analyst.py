from datetime import date
from typing import Sequence, Any
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, MessagesState, START, END

from tradingagents.agents.utils.agent_utils import (
    get_crypto_newsflash_candidates,
    get_crypto_newsflash_content,
)
from tradingagents.constants import DEFAULT_ASSETS


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
        current_date = state.get("trade_date") or date.today().isoformat()
        assets = state.get("assets_under_analysis") or list(DEFAULT_ASSETS)
        asset_list = ", ".join(assets)
        base_system_message = f"""
你是一名加密快讯分析师，需要在一次推理中梳理 Odaily 最新短新闻，并提炼其对多资产组合的影响。
务必遵循以下流程：
1. 先调用候选列表工具拉取最近 24h 的快讯标题与时间戳。
2. 再根据标题挑选与 {asset_list} 直接相关或可能影响这些资产/宏观情绪的条目，调用内容工具时一次性传入逗号分隔的 entry_id 列表批量取回正文。
3. 将所有快讯压缩为具体的主题集群（监管、链上、宏观、资金流等），概述关键事实、触发背景与方向，不需要逐条列出所有事件。
4. 对每个集群说明可能受影响的资产以及净效应或潜在矛盾。
5. 最后仅输出单行 JSON，严格遵守字段定义，不得附加其他文字。

JSON 结构示例：
{{{{
  "analysis_date": "YYYY-MM-DD",
  "assets": ["ASSET1","ASSET2"],
  "sentiment_summary": {{{{
    "overall": "bullish|bearish|neutral",
    "confidence": "high|medium|low",
    "rationale": "一句话说明主因"
  }}}},
  "themes": [
    {{{{
      "theme": "regulation|macro|exchange|onchain|project|security",
      "highlights": [
        "关键事件摘要1",
        "关键事件摘要2"
      ],
      "impacted_assets": ["ASSET1","ASSET2"],
      "net_effect": "bullish|bearish|mixed",
      "confidence": "high|medium|low"
    }}}}
  ],
}}}}
""".strip()

        system_message = (
            "你隶属于一个多智能体的加密研究团队。"
            f" 当前日期：{current_date}，本轮关注资产：{asset_list}。\n"
            f"{base_system_message}"
        )

        graph = build_graph(system_message)
        conversation = list(state["messages"])

        result_state = graph.invoke(
            {"messages": conversation}, config={"recursion_limit": 100}
        )
        final_messages: Sequence[BaseMessage] = result_state["messages"]
        result: Any = final_messages[-1]

        report_text = _extract_text_from_message(result)
        report = report_text or "【错误】快讯分析生成失败。"

        return {
            "messages": final_messages,
            "newsflash_report": report,
        }

    return crypto_newsflash_node
