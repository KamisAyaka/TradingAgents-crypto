from datetime import date
from typing import Sequence
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, MessagesState, START, END

from tradingagents.agents.utils.crypto_market_tools import (
    get_crypto_market_batch,
    get_support_resistance_batch,
)
from tradingagents.constants import DEFAULT_ASSETS


def create_crypto_market_analyst(llm):
    """
    Analyst node that focuses on Binance market structure and technical context.
    使用 LangGraph 的 ToolNode + bind_tools 模式自动循环调用工具。
    """

    # 1. 绑定工具到 LLM（和官方示例一样）
    tools = [
        get_crypto_market_batch,
        get_support_resistance_batch,
    ]
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
        current_date = state.get("trade_date") or date.today().isoformat()
        assets = state.get("assets_under_analysis") or list(DEFAULT_ASSETS)
        asset_list = ", ".join(assets)

        base_system_message = """
你是专注于加密市场的技术分析师，必须在一次推理中覆盖多个交易对。对于列表中的每个资产你都要：
1. 使用批量工具 `get_crypto_market_batch` / `get_support_resistance_batch`，一次性传入完整资产列表（逗号分隔），获取 OHLCV、成交量、区间与关键价位。
2. 提炼趋势与指标共识（均线/MACD/KDJ/布林带等），标出触发/失效条件。
3. 给出 bull/base/bear 三种路径，以便 Trader 对是否执行交易做出相关的判断。
4. 仅输出单行 JSON，不得附加其他文字。

JSON 结构示例：
{{
  "analysis_date": "YYYY-MM-DD",
  "assets": ["ASSET1","ASSET2"],
  "per_asset": [
    {{
      "symbol": "ASSET1",
      "trend_view": {{
        "direction": "bullish|bearish|range",
        "evidence": ["依据"],
        "triggers": ["触发条件"],
        "invalidations": ["失效条件"]
      }},
      "levels": [
        {{
          "type": "support|resistance",
          "range": "价格区间",
          "confidence": "high|medium|low"
        }}
      ],
      "scenario_map": [
        {{
          "case": "bull|base|bear",
          "path": "行情演绎",
          "fail_if": "终止条件"
        }}
      ],
      "indicator_summary": "一句话指标共识"
    }}
  ],
}}
""".strip()

        system_message = (
            "你隶属于一个多智能体的加密研究团队。"
            f" 当前日期：{current_date}，本轮需要覆盖的资产：{asset_list}。\n"
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

        return {
            "messages": final_messages,
            "market_report": report,
        }

    return crypto_market_node
