from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage

from tradingagents.agents.utils.agent_utils import (
    get_crypto_longform_articles,
)
from tradingagents.dataflows.odaily import save_longform_analysis


def create_crypto_longform_analyst(llm):
    """
    Analyst node that reviews Odaily long-form articles for fundamental crypto context.
    """

    def crypto_longform_node(state):
        current_date = state.get("trade_date", "Unknown date")
        asset = state.get("asset_of_interest", "crypto market")

        system_message = (
            "你是加密市场的长文研究员，请分析过去一周 Odaily 的深度文章，提炼可持续的基本面主题。"
            "重点关注叙事（基础设施升级、监管进展、宏观驱动等），并说明对未来几天仓位的潜在影响。\n"
            "- 系统已经为你拉取最近的长文摘要，你需要从中筛选重点。\n"
            "- 将每篇文章压缩成“观点/论据/风险”。\n"
            "- 在可能时区分主流共识与逆势观点。\n"
            "- 给交易者提供可执行的见解。\n"
            "- 最后以 JSON 结构输出（数组元素包含文章标题、核心观点、偏向、风险提示等字段）"
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

        articles_text = get_crypto_longform_articles.invoke({"limit": 3, "lookback_days": 7})

        prompt = prompt.partial(system_message=system_message, current_date=current_date, asset=asset)
        chain = prompt | llm

        conversation = list(state["messages"]) + [
            HumanMessage(content=f"【Odaily 长文摘要】\n{articles_text}")
        ]

        result = chain.invoke(conversation)
        report = result.content or ""
        if report:
            save_longform_analysis(asset, report, current_date)

        return {
            "messages": [result] if result else [],
            "longform_report": report,
        }

    return crypto_longform_node
