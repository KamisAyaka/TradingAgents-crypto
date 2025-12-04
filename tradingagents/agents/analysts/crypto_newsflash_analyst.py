from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage

from tradingagents.agents.utils.agent_utils import get_crypto_newsflash


def create_crypto_newsflash_analyst(llm):
    """
    Analyst node focusing on Odaily news flashes for rapid crypto market context.
    """

    def crypto_newsflash_node(state):
        current_date = state.get("trade_date", "Unknown date")
        asset = state.get("asset_of_interest", "crypto market")

        tools = [get_crypto_newsflash]

        system_message = (
            "你是一名加密快讯分析师，负责梳理 Odaily 最新的短新闻，并说明其对短期交易的影响。"
            "总结每条事件、标注多空倾向，并强调对数字资产交易者的可执行含义。\n"
            "- 将同类型事件（协议升级、监管动作等）聚合点评。\n"
            "- 给出具体结论以及可能的价格/情绪冲击。\n"
            "- 结尾附上 Markdown 表格：标题、偏向、关键要点。"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你正在与其他协作代理共同完成任务。如需更多信息请调用可用工具；若已掌握所需信息可直接回答。"
                    " 当前日期：{current_date}，关注资产：{asset}。\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message, current_date=current_date, asset=asset)
        chain = prompt | llm.bind_tools(tools)

        # Force at least one attempt that issues a tool call so Odaily快讯数据一定被抓取。
        reminder = HumanMessage(
            content="系统提醒：你必须先调用 get_crypto_newsflash 工具获取快讯，再输出分析。"
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
            raise RuntimeError("Newsflash analyst failed to generate a response")

        report = ""
        if not getattr(result, "tool_calls", None):
            report = result.content or "【错误】未调用 get_crypto_newsflash 工具，无法生成快讯分析。"

        return {
            "messages": [result],
            "newsflash_report": report,
        }

    return crypto_newsflash_node
