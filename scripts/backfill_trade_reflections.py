#!/usr/bin/env python3
import os
import sqlite3
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.reflection.trade_cycle_reflector import TradeCycleReflector


def _connect_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _load_rounds(conn):
    return conn.execute(
        "SELECT * FROM trader_rounds ORDER BY created_at ASC, id ASC"
    ).fetchall()


def _get_reflector():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，无法生成复盘。")
    llm = ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=SecretStr(api_key),
        extra_body={"enable_thinking": False},
    )
    return TradeCycleReflector(llm)


def backfill_reflections(limit: int | None = None):
    db_path = DEFAULT_CONFIG["trader_round_db_path"]
    conn = _connect_db(db_path)
    rows = _load_rounds(conn)

    reflector = _get_reflector()
    memory = FinancialSituationMemory("trade_memory", DEFAULT_CONFIG)

    open_entry = None
    created = 0
    for row in rows:
        decision = (row["decision"] or "").upper()
        if decision in ("LONG", "SHORT"):
            open_entry = row
            continue
        if decision in ("CLOSE_LONG", "CLOSE_SHORT") and open_entry:
            symbol = open_entry["asset"]
            entry_time = open_entry["created_at"]
            existing = memory.get_entries(
                where={"symbol": symbol, "entry_time": entry_time}, limit=1
            )
            if existing:
                open_entry = None
                continue

            trade_info = {
                "symbol": symbol,
                "side": "LONG" if open_entry["decision"] == "LONG" else "SHORT",
                "entry_time": open_entry["created_at"],
                "entry_price": open_entry["entry_price"],
                "exit_time": row["created_at"],
                "exit_price": None,
                "stop_loss": open_entry["stop_loss"],
                "take_profit": open_entry["take_profit"],
                "leverage": open_entry["leverage"],
                "pnl": None,
                "notes": "backfill_reflection",
            }
            state = {
                "open_position_context": f"{open_entry['summary']}\n\n{open_entry['situation']}",
                "close_position_context": row["situation"] or row["summary"],
            }

            result = reflector.reflect(trade_info, state)
            summary = result.get("summary")
            context = result.get("context")
            if summary and context:
                memory.add_situations(
                    [(context, summary)],
                    metadata_list=[
                        {
                            "memory_type": "trade",
                            "symbol": symbol,
                            "side": trade_info["side"],
                            "entry_time": trade_info["entry_time"],
                            "exit_time": trade_info["exit_time"],
                            "leverage": trade_info["leverage"],
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                )
                created += 1
                if limit and created >= limit:
                    break
            open_entry = None

    conn.close()
    return created


if __name__ == "__main__":
    count = backfill_reflections()
    print(f"backfill done: {count} reflections added")
