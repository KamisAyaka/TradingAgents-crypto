from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from tradingagents.agents.utils.crypto_market_tools import (
    get_crypto_market_data,
    get_support_resistance_levels,
)
from tradingagents.agents.utils.news_data_tools import (
    get_crypto_longform_articles,
    get_crypto_longform_candidates,
    get_crypto_article_content,
    get_crypto_newsflash_candidates,
    get_crypto_newsflash_content,
)


def create_msg_delete():
    def delete_messages(state):
        """Clear all messages atomically and insert a placeholder."""
        placeholder = HumanMessage(content="继续进行分析。")
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                placeholder,
            ]
        }

    return delete_messages
