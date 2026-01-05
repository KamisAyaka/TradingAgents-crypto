
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from tradingagents.dataflows.trader_round_memory import TraderRoundMemoryStore
from tradingagents.agents.utils.binance_trade_tools import (
    set_binance_leverage,
    open_binance_position_usdt,
    close_binance_position,
    set_binance_take_profit_stop_loss,
)
from tradingagents.dataflows.binance_future import get_service

logger = logging.getLogger(__name__)


class ExecutionManager:
    """
    负责将“交易计划 JSON”转换为实际的 Binance 订单，并执行风控检查。
    """

    def __init__(self, trader_round_store: TraderRoundMemoryStore):
        self.trader_round_store = trader_round_store

    def apply_risk_controls_and_execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行风控与交易"""
        plan_text = state.get("trader_investment_plan") or ""
        plan = self._extract_plan_json(plan_text)
        adjustments: list[str] = []
        warnings: list[str] = []
        execution_results: list[Dict[str, Any]] = []

        if not plan:
            warnings.append("未能解析交易员计划 JSON，跳过风控与执行。")
            state["final_trade_decision"] = json.dumps(
                {
                    "risk_control": {"warnings": warnings},
                    "execution": execution_results,
                    "trader_plan_raw": plan_text,
                },
                ensure_ascii=False,
            )
            return state

        per_asset = plan.get("per_asset_decisions") or []
        for decision in per_asset:
            if not isinstance(decision, dict):
                continue
            action = str(decision.get("decision") or "").upper()
            if action not in {"LONG", "SHORT"}:
                continue

            execution = decision.get("execution") or {}
            risk = decision.get("risk_management") or {}
            asset = str(decision.get("asset") or "")
            entry_price_for_risk = None
            if asset:
                try:
                    positions = get_service().get_positions([asset])
                    if positions:
                        pos = positions[0]
                        position_amt = float(pos.get("positionAmt", 0.0))
                        if abs(position_amt) > 0:
                            entry_price_for_risk = self._coerce_float(
                                pos.get("entryPrice")
                            )
                except Exception:
                    entry_price_for_risk = None
            leverage = self._coerce_int(execution.get("leverage"))
            stop_loss_price = self._round_price(
                self._coerce_float(risk.get("stop_loss_price"))
            )
            if stop_loss_price is not None:
                risk["stop_loss_price"] = stop_loss_price

            take_profit_targets = risk.get("take_profit_targets")
            if isinstance(take_profit_targets, list):
                rounded_targets = [
                    self._round_price(self._coerce_float(target))
                    for target in take_profit_targets
                ]
                rounded_targets = [target for target in rounded_targets if target is not None]
                risk["take_profit_targets"] = rounded_targets
            elif take_profit_targets is not None:
                risk["take_profit_targets"] = self._round_price(
                    self._coerce_float(take_profit_targets)
                )

            if entry_price_for_risk is None:
                continue
            if leverage is None or leverage <= 0:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 leverage，无法校验 10% 规则。"
                )
                continue
            if stop_loss_price is None or stop_loss_price <= 0:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 stop_loss_price，无法校验 10% 规则。"
                )
                continue

            allowed_distance = 0.10 / leverage
            if action == "LONG":
                allowed_stop = entry_price_for_risk * (1 - allowed_distance)
                should_adjust = stop_loss_price < allowed_stop
            else:
                allowed_stop = entry_price_for_risk * (1 + allowed_distance)
                should_adjust = stop_loss_price > allowed_stop

            if should_adjust:
                distance_pct = abs(stop_loss_price - entry_price_for_risk) / entry_price_for_risk
                leveraged_loss = distance_pct * leverage
                risk["stop_loss_price"] = self._round_price(allowed_stop)
                decision["risk_management"] = risk
                adjustments.append(
                    f"{decision.get('asset')}: 止损风险 {leveraged_loss:.2%} > 10%，已调整为 {risk['stop_loss_price']}。"
                )

        available_capital = state.get("available_capital") or 0.0
        execution_results = self._execute_plan(plan, available_capital, warnings)

        state["trader_investment_plan"] = json.dumps(plan, ensure_ascii=False)
        state["final_trade_decision"] = json.dumps(
            {
                "risk_control": {
                    "max_loss_per_trade": 0.10,
                    "adjustments": adjustments,
                    "warnings": warnings,
                },
                "execution": execution_results,
                "trader_plan": plan,
            },
            ensure_ascii=False,
        )
        pending = [
            item["trade_info"] for item in execution_results if item.get("trade_info")
        ]
        if pending:
            state["_pending_trade_info"] = pending
        return state

    def _execute_plan(
        self,
        plan: Dict[str, Any],
        available_capital: float,
        warnings: list[str],
    ) -> list[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        per_asset = plan.get("per_asset_decisions") or []
        for decision in per_asset:
            if not isinstance(decision, dict):
                continue
            asset = str(decision.get("asset") or "")
            action = str(decision.get("decision") or "").upper()
            exec_action = action
            trade_info = None
            if action in {"CLOSE_LONG", "CLOSE_SHORT"}:
                exec_action = "CLOSE"
            execution = decision.get("execution") or {}
            risk = decision.get("risk_management") or {}

            leverage = self._coerce_int(execution.get("leverage"))
            stop_loss_price = self._coerce_float(risk.get("stop_loss_price"))
            take_profit_targets = risk.get("take_profit_targets")
            take_profit_price = None
            if isinstance(take_profit_targets, list) and take_profit_targets:
                take_profit_price = self._coerce_float(take_profit_targets[0])
            elif take_profit_targets is not None:
                take_profit_price = self._coerce_float(take_profit_targets)

            entry_result = ""
            leverage_result = ""
            protection_result = ""

            if exec_action in {"LONG", "SHORT"}:
                if not asset:
                    warnings.append("存在未提供 asset 的交易决策，已跳过执行。")
                    continue
                if leverage is None or leverage <= 0:
                    warnings.append(f"{asset}: 未提供有效 leverage，跳过执行。")
                    continue
                
                # 1. 设定杠杆
                leverage_result = set_binance_leverage.invoke(
                    {"symbol": asset, "leverage": leverage}
                )

                # 2. 计算目标名义价值 (Target Notional)
                target_notional = float(available_capital) * float(leverage)
                if target_notional <= 0:
                    warnings.append(f"{asset}: 可用本金不足，跳过执行。")
                    continue
                
                # 3. 获取当前持仓 (Current Position)
                current_position_amt = 0.0
                has_position = False
                is_same_direction = False
                
                entry_price_from_position = None
                try:
                    positions = get_service().get_positions([asset])
                    if positions:
                        pos = positions[0]
                        current_position_amt = float(pos.get("positionAmt", 0.0))
                        entry_price_from_position = self._coerce_float(
                            pos.get("entryPrice")
                        )
                        if abs(current_position_amt) > 0:
                            has_position = True
                            # check direction
                            current_side = "LONG" if current_position_amt > 0 else "SHORT"
                            if current_side == exec_action:
                                is_same_direction = True
                except Exception as e:
                    warnings.append(f"{asset}: 获取当前持仓失败 ({str(e)})，跳过执行以防风险。")
                    continue

                # STRICT SIMPLE MODE:
                # 1. 只有当“无持仓”时，才执行开仓 (Open)
                # 2. 如果已持仓且方向一致，直接跳过 (Hold)
                # 3. 如果已持仓但方向不一致（反向），则报警（还是只平仓？简单起见，提示反向持仓需人工干预或等待平仓信号）
                
                if has_position and entry_price_from_position:
                    execution["entry_price"] = entry_price_from_position
                    decision["execution"] = execution

                if has_position:
                    if is_same_direction:
                        entry_result = f"已持有 {asset} {exec_action} 仓位 ({current_position_amt})，保持不动 (No Rebalance)。"
                    else:
                        entry_result = f"警告：当前持有反向仓位 ({current_position_amt})，但在请求开 {exec_action}。请先平仓。"
                else:
                    # 无持仓 -> 执行开仓
                    side = "BUY" if exec_action == "LONG" else "SELL"
                    entry_result = open_binance_position_usdt.invoke(
                        {"symbol": asset, "side": side, "notional_usdt": target_notional}
                    )
                    try:
                        positions = get_service().get_positions([asset])
                        if positions:
                            pos = positions[0]
                            entry_price_from_position = self._coerce_float(
                                pos.get("entryPrice")
                            )
                            if entry_price_from_position:
                                execution["entry_price"] = entry_price_from_position
                                decision["execution"] = execution
                    except Exception:
                        pass
               
                exchange_stop_loss = None
                exchange_take_profit = None
                if has_position:
                    exchange_orders = get_service().get_open_exit_orders(asset)
                    exchange_stop_loss = self._round_price(
                        self._coerce_float(exchange_orders.get("stop_loss"))
                    )
                    exchange_take_profit = self._round_price(
                        self._coerce_float(exchange_orders.get("take_profit"))
                    )

                should_update_protection = False
                if has_position:
                    update_stop_loss = (
                        exchange_stop_loss is None
                        and stop_loss_price is not None
                        and stop_loss_price > 0
                    )
                    update_take_profit = (
                        take_profit_price is not None
                        and take_profit_price > 0
                        and take_profit_price != exchange_take_profit
                    )
                    if exchange_stop_loss is not None:
                        stop_loss_price = exchange_stop_loss
                    should_update_protection = update_stop_loss or update_take_profit
                else:
                    should_update_protection = bool(stop_loss_price or take_profit_price)

                if should_update_protection:
                    protection_result = set_binance_take_profit_stop_loss.invoke(
                        {
                            "symbol": asset,
                            "stop_loss_price": stop_loss_price or 0.0,
                            "take_profit_price": take_profit_price or 0.0,
                            "working_type": "MARK_PRICE",
                        }
                    )
            elif exec_action == "CLOSE":
                if not asset:
                    warnings.append("存在未提供 asset 的平仓决策，已跳过执行。")
                    continue
                entry_result = close_binance_position.invoke({"symbol": asset})
                trade_info = self._build_trade_info_from_open_entry(
                    asset, exec_action, None
                )
                if trade_info:
                    trade_info["exit_price"] = self._safe_mark_price(asset)
                    trade_info["exit_time"] = datetime.now(timezone.utc).isoformat()
                    trade_info["notes"] = "active_close"

            if exec_action in {"LONG", "SHORT", "CLOSE"}:
                results.append(
                    {
                        "asset": asset,
                        "action": action,
                        "set_leverage": leverage_result,
                        "entry_order": entry_result,
                        "protection": protection_result,
                        "trade_info": trade_info if exec_action == "CLOSE" else None,
                    }
                )
        return results

    def _safe_mark_price(self, symbol: str) -> Optional[float]:
        try:
            return get_service().get_mark_price(symbol)
        except Exception:
            return None

    def _build_trade_info_from_open_entry(
        self, symbol: str, action: str, price: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        entry = self.trader_round_store.get_latest_open_entry(symbol)
        if not entry:
            return None
        side = "LONG" if entry.get("decision") == "LONG" else "SHORT"
        entry_price = entry.get("entry_price")
        exit_price = price
        pnl = None
        if entry_price and exit_price:
            direction = 1 if side == "LONG" else -1
            pnl = (exit_price - entry_price) / entry_price * direction
        return {
            "symbol": symbol,
            "side": side,
            "entry_time": entry.get("created_at"),
            "entry_price": entry_price,
            "exit_time": None,
            "exit_price": exit_price,
            "leverage": entry.get("leverage"),
            "notional": None,
            "pnl": pnl,
            "stop_loss": entry.get("stop_loss"),
            "take_profit": entry.get("take_profit"),
            "notes": "",
        }

    @staticmethod
    def _extract_plan_json(plan_text: str) -> Optional[Dict[str, Any]]:
        if not plan_text:
            return None
        try:
            return json.loads(plan_text)
        except Exception:
            start = plan_text.find("{")
            end = plan_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(plan_text[start : end + 1])
            except Exception:
                return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None:
            return None

    @staticmethod
    def _round_price(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return float(int(round(value)))

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            text = str(value).strip().lower().replace("x", "")
            return int(float(text))
        except Exception:
            return None
