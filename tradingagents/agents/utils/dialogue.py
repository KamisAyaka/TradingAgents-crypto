"""为多智能体交流提供的共享工具。

灵感来自 ``multi_LLM_comm`` 的文本对战模式：每个智能体都会拿到同一份观测模版，并按固定段落
（行动计划 / 团队消息 / 认知更新）回复。下面的工具负责生成共享观测文本、提炼已有研究/辩论信息，
以及解析结构化回复，方便后续节点记录到团队通信日志。
"""

from __future__ import annotations

from typing import Dict, List, Tuple


DEFAULT_SECTION_HEADERS = ["Action Plan:", "Team Message:", "Belief Update:"]


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
