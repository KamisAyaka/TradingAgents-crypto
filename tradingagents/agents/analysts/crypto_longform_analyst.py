from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage

from tradingagents.agents.utils.agent_utils import (
    get_crypto_longform_candidates,
    get_crypto_article_content,
)
from tradingagents.dataflows.odaily import save_longform_analysis


def create_crypto_longform_analyst(llm):
    """
    Analyst node that reviews Odaily long-form articles for fundamental crypto context.
    """

    def crypto_longform_node(state):
        current_date = state.get("trade_date", "Unknown date")
        asset = state.get("asset_of_interest", "crypto market")

        tools = [get_crypto_longform_candidates, get_crypto_article_content]

        system_message = (
            "你是加密市场的长文研究员，请分析过去一周 Odaily 的深度文章，提炼可持续的基本面主题。"
            "重点关注叙事（基础设施升级、监管进展、宏观驱动等），并说明对未来几天仓位的潜在影响。\n"
            "- 先调用“候选文章”工具，基于标题挑选最有价值的条目，再根据 entry_id 调用“文章内容”工具获取全文。\n"
            "- 将每篇文章压缩成“观点/论据/风险”。\n"
            "- 在可能时区分主流共识与逆势观点。\n"
            "- 给交易者提供可执行的见解。\n"
            "- 最后附上 Markdown 表格，包含文章标题、核心观点与偏向。"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你隶属于一个多智能体的加密研究团队。"
                    " 请先调用候选列表工具审阅最新长文，再针对选定文章调用内容工具。"
                    " 当前日期：{current_date}，关注资产：{asset}。\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message, current_date=current_date, asset=asset)
        chain = prompt | llm.bind_tools(tools)
        tool_map = {tool.name: tool for tool in tools}

        history = list(state["messages"])
        report = ""
        result = None
        while True:
            result = chain.invoke(history)
            history.append(result)

            if result.tool_calls:
                for tool_call in result.tool_calls:
                    tool_name = tool_call["name"]
                    tool = tool_map.get(tool_name)
                    if tool is None:
                        tool_result = f"工具 {tool_name} 不存在。"
                    else:
                        args = tool_call.get("args") or {}
                        tool_result = tool.invoke(args)
                    history.append(
                        ToolMessage(
                            content=tool_result,
                            tool_call_id=tool_call.get("id", ""),
                        )
                    )
                continue

            report = result.content or ""
            if report:
                save_longform_analysis(asset, report, current_date)
            break

        return {
            "messages": [result] if result else [],
            "longform_report": report,
        }

    return crypto_longform_node
