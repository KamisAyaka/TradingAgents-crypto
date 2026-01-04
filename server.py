import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tradingagents.dataflows.binance import BINANCE_DB_PATH, load_cached_klines
from tradingagents.dataflows.trader_round_memory import TraderRoundMemoryStore
from tradingagents.dataflows.trace_store import TraceStore
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from trigger import (
    configure_scheduler,
    execute_startup_tasks,
)


class RunRequest(BaseModel):
    assets: List[str] = ["BTCUSDT", "ETHUSDT"]
    available_capital: float = 100.0
    min_leverage: int = 5
    max_leverage: int = 10


class SchedulerManager:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self._configured = False
        self.run_config = RunRequest()

    def update_config(self, config: RunRequest) -> None:
        self.run_config = config
        
        # Inject config into environment variables so trigger.py functions pick them up dynamically
        assets_str = ",".join([a.upper() for a in config.assets])
        os.environ["ANALYSIS_ASSETS"] = assets_str
        os.environ["BINANCE_SYMBOLS"] = assets_str
        os.environ["LONGFORM_ASSETS"] = assets_str
        
        os.environ["ANALYSIS_CAPITAL"] = str(config.available_capital)
        os.environ["ANALYSIS_MIN_LEVERAGE"] = str(config.min_leverage)
        os.environ["ANALYSIS_MAX_LEVERAGE"] = str(config.max_leverage)
        
        # Note: Analysis interval is handled via API/Env separately, defaulting to env var or 300

    def _configure(self) -> None:
        if self._configured:
            return
        
        # Use the unified configuration logic from trigger.py
        # This ensures server.py runs EXACTLY the same jobs as trigger.py cli
        configure_scheduler(self.scheduler)
        self._configured = True

    def start(self) -> None:
        self._configure()
        
        # Start or Resume the scheduler
        if not self.scheduler.running:
            self.scheduler.start()
        elif self.scheduler.state == 2: # STATE_PAUSED
            self.scheduler.resume()
            
        # Run startup tasks immediately (Async/Threaded via separate job to avoid blocking API?)
        # actually execute_startup_tasks is synchronous. 
        # To avoid blocking the API response too long, we submit it to the scheduler as a run-once job.
        from datetime import datetime
        self.scheduler.add_job(
            execute_startup_tasks, 
            "date", 
            run_date=datetime.now(),
            id="immediate_startup_tasks"
        )

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.pause()

    def status(self) -> Dict[str, Any]:
        # 0=STOPPED, 1=RUNNING, 2=PAUSED
        is_active = self.scheduler.running and self.scheduler.state == 1
        return {
            "running": is_active,
            "jobs": [
                {"id": job.id, "next_run": str(job.next_run_time)}
                for job in self.scheduler.get_jobs()
            ],
        }


config = DEFAULT_CONFIG.copy()
graph = TradingAgentsGraph(
    debug=True,
    config=config,
    selected_analysts=["market", "newsflash", "longform"],
)
memory_store = TraderRoundMemoryStore(
    config.get("trader_round_db_path")
    or os.path.join(config["results_dir"], "trader_round_memory.db")
)
trace_store = TraceStore(
    config.get("trace_db_path")
    or os.path.join(config["results_dir"], "trace_store.db")
)

scheduler_manager = SchedulerManager()

app = FastAPI(title="TradingAgents API", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/klines")
def get_klines(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("15m"),
    limit: int = Query(120, ge=10, le=2000),
) -> Dict[str, Any]:
    symbol = symbol.upper()
    klines = load_cached_klines(symbol, interval, limit)
    interval_used = interval
    available_intervals: Dict[str, int] = {}
    if not klines:
        try:
            with sqlite3.connect(BINANCE_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                for table in ("klines", "klines_15m", "klines_4h"):
                    try:
                        rows = conn.execute(
                            f"""
                            SELECT interval, COUNT(*) AS cnt
                            FROM {table}
                            WHERE symbol = ?
                            GROUP BY interval
                            """,
                            (symbol,),
                        ).fetchall()
                        for row in rows:
                            available_intervals[row["interval"]] = (
                                available_intervals.get(row["interval"], 0)
                                + int(row["cnt"])
                            )
                    except sqlite3.Error:
                        continue
        except sqlite3.Error:
            available_intervals = {}

        if available_intervals:
            interval_used = max(
                available_intervals, key=lambda k: available_intervals.get(k, 0)
            )
            klines = load_cached_klines(symbol, interval_used, limit)
    return {
        "symbol": symbol,
        "interval": interval,
        "interval_used": interval_used,
        "available_intervals": available_intervals,
        "db_path": str(BINANCE_DB_PATH),
        "klines": klines,
    }


@app.get("/api/trades")
def get_trades(
    limit: int = Query(50, ge=1, le=500),
    symbol: Optional[str] = Query(None),
) -> Dict[str, Any]:
    rows = memory_store.get_recent_rounds(limit=limit)
    if symbol:
        symbol = symbol.upper()
        rows = [row for row in rows if row.get("asset") == symbol]
    return {"trades": rows}


@app.get("/api/trace/latest")
def get_latest_trace() -> Dict[str, Any]:
    record = trace_store.get_latest_trace()
    if not record or not record.get("payload"):
        return {"trace": None}
    return {"trace": json.loads(record["payload"])}


@app.get("/api/trace/history")
def get_trace_history(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    records, total = trace_store.get_trace_history(limit=limit, offset=offset)
    traces = []
    for record in records:
        payload = record.get("payload")
        if not payload:
            continue
        try:
            trace_payload = json.loads(payload)
        except json.JSONDecodeError:
            continue
        traces.append(
            {
                "id": record["id"],
                "created_at": record["created_at"],
                "trace": trace_payload,
            }
        )
    return {"total": total, "limit": limit, "offset": offset, "traces": traces}


@app.post("/api/run")
def run_once(payload: RunRequest) -> Dict[str, Any]:
    assets = [item.upper() for item in payload.assets]
    _, decision = graph.propagate(
        assets,
        available_capital=payload.available_capital,
        min_leverage=payload.min_leverage,
        max_leverage=payload.max_leverage,
    )
    return {"decision": decision}


@app.get("/api/scheduler/status")
def scheduler_status() -> Dict[str, Any]:
    return scheduler_manager.status()


@app.post("/api/scheduler/start")
def scheduler_start(payload: Optional[RunRequest] = None) -> Dict[str, Any]:
    if payload:
        scheduler_manager.update_config(payload)
    scheduler_manager.start()
    return scheduler_manager.status()


@app.post("/api/scheduler/stop")
def scheduler_stop() -> Dict[str, Any]:
    scheduler_manager.stop()
    return scheduler_manager.status()
