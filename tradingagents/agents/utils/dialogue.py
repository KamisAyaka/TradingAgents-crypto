"""为多智能体交流提供的共享工具。

灵感来自 ``multi_LLM_comm`` 的文本对战模式：每个智能体都会拿到同一份观测模版，并按固定段落
（行动计划 / 团队消息 / 认知更新）回复。下面的工具负责生成共享观测文本、提炼已有研究/辩论信息，
以及解析结构化回复，方便后续节点记录到团队通信日志。
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Union


DEFAULT_SECTION_HEADERS = ["Action Plan:", "Team Message:", "Belief Update:"]


def _truncate(text: str, limit: int = 360) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _latest_line(history: str) -> str:
    history = (history or "").strip()
    if not history:
        return "暂无记录"
    return history.splitlines()[-1][-360:]


def build_observation_block(state: Dict, role: str) -> str:
    """Create a shared observation text used by all downstream agents.

    每位 agent 都会拿到统一的上下文结构，包含：
    - 当前资产、交易日
    - 三个研究报告的摘要
    - 最新的牛熊/风控讨论片段
    - 最近一次团队消息
    这样做可显著降低 prompt 漂移，并让 agent 在输出时
    自动引用相同的“世界状态”。
    """

    market_report = _truncate(state.get("market_report", "")) or "暂无市场报告"
    newsflash_report = _truncate(state.get("newsflash_report", "")) or "暂无快讯摘要"
    longform_report = _truncate(state.get("longform_report", "")) or "暂无长篇研究"

    invest_state = state.get("investment_debate_state", {}) or {}
    risk_state = state.get("risk_debate_state", {}) or {}

    bull_line = _latest_line(invest_state.get("bull_history", ""))
    bear_line = _latest_line(invest_state.get("bear_history", ""))
    risk_line = _latest_line(risk_state.get("history", ""))

    shared_msgs = state.get("team_messages", []) or []
    if shared_msgs:
        tail = shared_msgs[-3:]
        msg_block = "\n".join(
            f"- [{item.get('round', '?')}] {item.get('speaker', 'Agent')}: {item.get('message', '')}"
            for item in tail
        )
    else:
        msg_block = "暂无队友通信。"

    return (
        f"## 基础环境\n"
        f"- 角色：{role}\n"
        f"- 交易对：{state.get('asset_of_interest', '未知资产')}\n"
        f"- 交易日：{state.get('trade_date', '未知日期')}\n"
        f"- 互动轮次：{state.get('interaction_round', 1)}\n"
        "\n## 研究摘要\n"
        f"1. 市场技术：{market_report}\n"
        f"2. 快讯：{newsflash_report}\n"
        f"3. 长篇研究：{longform_report}\n"
        "\n## 辩论快照\n"
        f"- 看涨最新观点：{bull_line}\n"
        f"- 看跌最新观点：{bear_line}\n"
        f"- 风控讨论片段：{_truncate(risk_line)}\n"
        "\n## 队友通信（最近 3 条）\n"
        f"{msg_block}\n"
        "\n---\n"
        "请据此完成本回合任务，并严格按照下述格式回复：\n"
        "Action Plan: <你的核心决策或推理>\n"
        "Team Message: \"<面向团队的 1-2 句明确信息>\"\n"
        "Belief Update: <你对当前市场/风险判断的更新>"
    )


def parse_structured_reply(
    reply: str, headers: List[str] | None = None
) -> Dict[str, str]:
    """Extract structured sections from an agent reply.

    如果某段缺失，则回退到空字符串，以免打断后续流程。
    """

    headers = headers or DEFAULT_SECTION_HEADERS
    sections: Dict[str, str] = {h: "" for h in headers}
    text = reply or ""
    positions: List[Tuple[int, str]] = []
    lower = text
    for header in headers:
        idx = lower.find(header)
        if idx != -1:
            positions.append((idx, header))

    if not positions:
        # 无法解析就默认全部写在 Action Plan
        sections[headers[0]] = text.strip()
        return sections

    positions.sort()
    for i, (start, header) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        content = text[start + len(header) : end].strip()
        sections[header] = content
    return sections


def register_team_message(
    state: Dict,
    speaker: str,
    structured_reply: Dict[str, str],
) -> Tuple[List[Dict[str, Union[str, int]]], int]:
    """Append the structured team message to the rolling history.

    返回 (updated_messages, next_round_id) 供节点写回 state。
    """

    history: List[Dict[str, Union[str, int]]] = list(
        state.get("team_messages", []) or []
    )
    current_round = int(state.get("interaction_round", 1))
    message_text = structured_reply.get("Team Message:", "").strip()
    action = structured_reply.get("Action Plan:", "").strip() or "NA"
    belief = structured_reply.get("Belief Update:", "").strip()

    history.append(
        {
            "round": current_round,
            "speaker": speaker,
            "action": action,
            "message": message_text or "(未提供团队消息)",
            "belief": belief,
        }
    )

    return history[-12:], current_round + 1  # 限制长度防止状态爆炸
