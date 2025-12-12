# TradingAgents/graph/propagation.py

from typing import Dict, Any
from tradingagents.agents.utils.agent_states import (
    InvestDebateState,
    RiskReviewState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self, asset_symbol: str, trade_date: str
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        return {
            "messages": [("human", asset_symbol)],
            "asset_of_interest": asset_symbol,
            "trade_date": str(trade_date),
            "investment_debate_state": InvestDebateState(
                {
                    "history": "",
                    "bull_history": "",
                    "bear_history": "",
                    "current_response": "",
                    "count": 0,
                }
            ),
            "risk_review_state": RiskReviewState(
                {
                    "history": "",
                    "analyst_report": "",
                    "manager_summary": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "newsflash_report": "",
            "longform_report": "",
            "trader_investment_plan": "",
            "final_trade_decision": "",
            "interaction_round": 1,
        }

    def get_graph_args(self) -> Dict[str, Any]:
        """Get arguments for the graph invocation."""
        return {
            "stream_mode": "values",
            "config": {"recursion_limit": self.max_recur_limit},
        }
