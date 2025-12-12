from tradingagents.dataflows.odaily import get_latest_longform_analysis

def create_longform_cache_loader(max_age_days: int = 14):
    """
    Lightweight node that reads the most recent cached longform analysis from SQLite.
    """

    def longform_cache_node(state):
        current_date = state.get("trade_date", "Unknown date")
        asset = state.get("asset_of_interest", "BTCUSDT")

        record = get_latest_longform_analysis(asset, max_age_days=max_age_days)
        if record:
            analysis_date = record.get("analysis_date") or "未知日期"
            created_at = record.get("created_at") or "未知时间"
            report = record.get("report") or ""
            header = (
                f"【缓存长文分析】资产：{asset} | 分析日：{analysis_date} | 入库时间：{created_at}\n\n"
            )
            content = header + report
        else:
            content = (
                f"尚未在缓存中找到 {asset} 的长文分析（交易日 {current_date}）。"
                " 请先运行长文分析师任务并写入数据库。"
            )

        return {
            "longform_report": content,
            "messages": state["messages"],
        }

    return longform_cache_node
