#!/usr/bin/env python3
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.binance_future import get_service


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _find_open_entries(conn):
    return conn.execute(
        """
        SELECT r.*
        FROM trader_rounds r
        WHERE r.decision IN ('LONG', 'SHORT')
          AND r.asset IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM trader_rounds c
              WHERE c.asset = r.asset
                AND c.created_at > r.created_at
                AND c.decision IN ('CLOSE_LONG', 'CLOSE_SHORT')
          )
        ORDER BY r.created_at ASC, r.id ASC
        """
    ).fetchall()


def _get_latest_wait_round(conn):
    return conn.execute(
        """
        SELECT * FROM trader_rounds
        WHERE decision = 'WAIT'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()


def backfill_exchange_closes():
    db_path = DEFAULT_CONFIG["trader_round_db_path"]
    conn = _connect_db(db_path)
    svc = get_service()
    inserted = 0

    latest_round = _get_latest_wait_round(conn)
    latest_summary = latest_round["summary"] if latest_round else ""
    latest_situation = latest_round["situation"] if latest_round else ""
    combined_context = "\n\n".join(
        [part for part in (latest_summary, latest_situation) if part]
    )

    for entry in _find_open_entries(conn):
        symbol = (entry["asset"] or "").upper()
        if not symbol:
            continue
        try:
            positions = svc.get_positions([symbol])
        except Exception:
            continue

        has_position = False
        for pos in positions:
            try:
                if abs(float(pos.get("positionAmt", 0.0))) > 0:
                    has_position = True
                    break
            except (TypeError, ValueError):
                continue
        if has_position:
            continue

        decision = "CLOSE_LONG" if entry["decision"] == "LONG" else "CLOSE_SHORT"
        summary = f"[结论] {symbol} | {decision} | 交易所自动平仓回填"
        situation = combined_context or entry["situation"] or summary
        assets_text = entry["assets"] or symbol
        created_at = _utcnow_iso()
        conn.execute(
            """
            INSERT INTO trader_rounds (
                created_at, round_id, assets, situation, summary,
                decision, asset, is_open_entry, entry_price, stop_loss,
                take_profit, leverage
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                entry["round_id"],
                assets_text,
                situation,
                summary,
                decision,
                symbol,
                0,
                entry["entry_price"],
                entry["stop_loss"],
                entry["take_profit"],
                entry["leverage"],
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    count = backfill_exchange_closes()
    print(f"backfill done: {count} closes added")
