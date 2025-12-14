from datetime import date
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
from tradingagents.constants import DEFAULT_ASSETS


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
    
        current_date = state.get("trade_date") or date.today().isoformat()
        assets = state.get("assets_under_analysis") or list(DEFAULT_ASSETS)
        focus_assets = ", ".join(assets)
        base_system_message = f"""
你是加密市场的长文研究员，负责阅读 Odaily 深度文章，提炼可持续的基本面主题并写入缓存。请严格按照以下步骤执行：
1. 调用候选列表工具获取过去几天的长文标题，并记录发布日期。
2. 选择与当前关注资产（{focus_assets}）或其上游叙事最相关的文章，调用内容工具获取全文。
3. 对每篇文章提炼“观点 / 支撑论据 / 关键风险”，并标注它主要影响哪些资产/生态。
4. 在整体结论中说明主流叙事、逆势观点、潜在催化剂以及对仓位管理的启示。
5. 只输出单行 JSON，不得混入其它文字。

JSON 结构示例：
{{{{
  "analysis_date": "YYYY-MM-DD",
  "focus_assets": ["{focus_assets}"],
  "themes": [
    {{{{
      "title": "文章或主题标题",
      "primary_assets": ["涉及资产"],
      "sentiment": "bullish|bearish|neutral",
      "thesis": "核心观点",
      "arguments": ["论据1","论据2"],
      "risks": ["风险提示1","风险提示2"],
      "contrarian": "若与主流相反则说明原因"
    }}}}
  ],
  "narrative_summary": {{{{
    "dominant": "当前主流叙事",
    "contrarian": "逆势观点",
    "event_triggers": ["催化剂/关键事件"]
  }}}},
  "trading_implications": {{{{
    "positioning": "仓位/敞口建议或触发条件",
    "monitoring": ["需要跟踪的催化剂或指标"]
  }}}}
}}}}
""".strip()

        system_message = (
            "你隶属于一个多智能体的加密研究团队。"
            f" 当前日期：{current_date}，请重点关注以下资产相关的叙事：{focus_assets}。\n"
            f"{base_system_message}"
        )

        graph = build_graph(system_message)
        conversation = list(state["messages"])

        result_state = graph.invoke(
            {"messages": conversation}, config={"recursion_limit": 100}
        )
        final_messages: Sequence[BaseMessage] = result_state["messages"]
        result = final_messages[-1]

        report = result.content or ""
        if report and isinstance(report, str):
            save_longform_analysis(report, analysis_date=current_date)

        return {
            "messages": final_messages,
            "longform_report": report,
        }

    return crypto_longform_node
