# TradingAgents/graph/propagation.py

from typing import Dict, Any, Iterable, List, Sequence, Union
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
        self, asset_symbols: Union[str, Sequence[str]], trade_date: str
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        if isinstance(asset_symbols, str):
            assets: List[str] = [asset_symbols]
        else:
            assets = [symbol for symbol in asset_symbols if symbol]
        if not assets:
            raise ValueError("必须提供至少一个交易对。")
        asset_desc = ", ".join(assets)
        return {
            "messages": [("human", f"多资产交易分析：{asset_desc}")],
            "assets_under_analysis": assets,
            "trade_date": str(trade_date),
            "min_leverage": 1.0,
            "max_leverage": 1.0,
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
