from datetime import date

from tradingagents.dataflows.odaily import get_latest_longform_analysis
from tradingagents.constants import DEFAULT_ASSETS

def create_longform_cache_loader(max_age_days: int = 14):
    """
    Lightweight node that reads the most recent cached longform analysis from SQLite.
    """

    def longform_cache_node(state):
        current_date = state.get("trade_date") or date.today().isoformat()
        assets = state.get("assets_under_analysis") or list(DEFAULT_ASSETS)
        asset_hint = ", ".join(assets)

        record = get_latest_longform_analysis(max_age_days=max_age_days)
        if record:
            analysis_date = record.get("analysis_date") or "未知日期"
            created_at = record.get("created_at") or "未知时间"
            report = record.get("report") or ""
            header = (
                f"【缓存长文分析】关注资产：{asset_hint} | 分析日：{analysis_date} | 入库：{created_at}\n\n"
            )
            content = header + report
        else:
            content = (
                f"尚未在缓存中找到长文分析（交易日 {current_date}）。"
                " 请先运行长文分析师任务并写入数据库。"
            )

        return {
            "longform_report": content,
            "messages": state["messages"],
        }

    return longform_cache_node
