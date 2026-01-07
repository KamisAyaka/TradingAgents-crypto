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


def _get_asset_rounds(conn, asset: str):
    return conn.execute(
        """
        SELECT *
        FROM trader_rounds
        WHERE asset = ?
        ORDER BY created_at ASC, id ASC
        """,
        (asset,),
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


def _get_assets(conn):
    rows = conn.execute(
        """
        SELECT DISTINCT asset
        FROM trader_rounds
        WHERE asset IS NOT NULL AND asset <> ''
        """
    ).fetchall()
    return [row["asset"] for row in rows]


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

    for asset in _get_assets(conn):
        symbol = (asset or "").upper()
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

        rounds = _get_asset_rounds(conn, symbol)
        open_entry = None
        for row in rounds:
            decision = (row["decision"] or "").upper()
            if decision in ("LONG", "SHORT"):
                if open_entry is None:
                    open_entry = row
                continue
            if decision in ("CLOSE_LONG", "CLOSE_SHORT"):
                open_entry = None
                continue
            if decision == "WAIT" and open_entry:
                close_decision = (
                    "CLOSE_LONG" if open_entry["decision"] == "LONG" else "CLOSE_SHORT"
                )
                summary = f"[结论] {symbol} | {close_decision} | 交易所自动平仓回填"
                wait_summary = row["summary"] or ""
                wait_situation = row["situation"] or ""
                wait_context = "\n\n".join(
                    [part for part in (wait_summary, wait_situation) if part]
                )
                situation = (
                    wait_context or combined_context or open_entry["situation"] or summary
                )
                assets_text = open_entry["assets"] or symbol
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
                        row["created_at"],
                        open_entry["round_id"],
                        assets_text,
                        situation,
                        summary,
                        close_decision,
                        symbol,
                        0,
                        open_entry["entry_price"],
                        open_entry["stop_loss"],
                        open_entry["take_profit"],
                        open_entry["leverage"],
                    ),
                )
                inserted += 1
                open_entry = None

    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    count = backfill_exchange_closes()
    print(f"backfill done: {count} closes added")
