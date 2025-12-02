from langchain_core.messages import HumanMessage, RemoveMessage

from tradingagents.agents.utils.crypto_market_tools import (
    get_crypto_market_data,
    get_support_resistance_levels,
)
from tradingagents.agents.utils.news_data_tools import (
    get_crypto_newsflash,
    get_crypto_longform_articles,
    get_crypto_longform_candidates,
    get_crypto_article_content,
)

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]
        
        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages


        
