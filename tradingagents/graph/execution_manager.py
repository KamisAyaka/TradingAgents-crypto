
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from tradingagents.dataflows.trader_round_memory import TraderRoundMemoryStore
from tradingagents.dataflows.binance_future import get_service

logger = logging.getLogger(__name__)


class ExecutionManager:
    """
    执行管理器 (ExecutionManager)
    
    职责：
    1. 解析交易员生成的投资计划 (JSON)。
    2. 执行风险控制检查 (Risk Control)：
       - 强制检查 10% 最大止损规则 (基于杠杆调整后的名义价值)。
       - 验证必填参数 (Leverage, Stop Loss)。
    3. 执行交易指令 (Execution)：
       - 设置杠杆。
       - 计算目标仓位价值。
       - 检查当前持仓状态 (避免重复开仓或反向持仓)。
       - 提交开仓/平仓订单到 Binance。
       - 更新止盈止损保护单。
    """

    def __init__(self, trader_round_store: TraderRoundMemoryStore):
        self.trader_round_store = trader_round_store

    def apply_risk_controls_and_execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用风控规则并执行交易。
        
        流程：
        1. 解析 state 中的 `trader_investment_plan`。
        2. 遍历每个资产的决策，执行风控检查 (validate constraints)。
           - 如果止损范围超过 10% (adjust to max 10% loss)，自动修正止损价格。
           - 记录所有警告和调整信息。
        3. 调用 `_execute_plan` 执行实际的下单操作。
        4. 更新 state 中的 `final_trade_decision`，包含风控结果和执行结果。
        """
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

        # 逐资产处理计划，并且只对“已有真实持仓”的资产做风控校验。
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
            # 风控基准价使用交易所持仓的 entryPrice，而不是计划中的估算价。
            entry_price_for_risk = None
            current_price_for_risk = None
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
                    current_price_for_risk = self._coerce_float(
                        get_service().get_mark_price(asset)
                    )
                except Exception:
                    entry_price_for_risk = None
                    current_price_for_risk = None
            leverage = self._coerce_int(execution.get("leverage"))
            stop_loss_price = self._round_price(
                self._coerce_float(risk.get("stop_loss_price"))
            )
            if stop_loss_price is not None:
                risk["stop_loss_price"] = stop_loss_price

            # 提前把止盈价规范化（四舍五入），避免下游重复处理。
            take_profit_price = self._round_price(
                self._coerce_float(risk.get("take_profit_price"))
            )
            if take_profit_price is not None:
                risk["take_profit_price"] = take_profit_price

            if entry_price_for_risk is None:
                continue
            if leverage is None or leverage <= 0:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 leverage，无法校验 10% 规则。"
                )
                continue
            missing_stop_loss = stop_loss_price is None or stop_loss_price <= 0
            if missing_stop_loss:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 stop_loss_price，无法校验 10% 规则。"
                )
            missing_take_profit = (
                take_profit_price is None or take_profit_price <= 0
            )
            if missing_take_profit:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 take_profit_price，无法执行止盈/止损设置。"
                )
            if stop_loss_price is None:
                continue
            if not missing_stop_loss:
                # 风控核心逻辑：
                # 允许的最大亏损为本金的 10%。
                # 公式: Allowed_Distance = 10% / 杠杆倍数
                # 例如 10x 杠杆，允许价格波动 1% (1% * 10 = 10% 亏损)
                allowed_distance = 0.10 / leverage
                if action == "LONG":
                    allowed_stop = entry_price_for_risk * (1 - allowed_distance)
                    should_adjust = stop_loss_price < allowed_stop
                else:
                    allowed_stop = entry_price_for_risk * (1 + allowed_distance)
                    should_adjust = stop_loss_price > allowed_stop

                if should_adjust:
                    distance_pct = (
                        abs(stop_loss_price - entry_price_for_risk)
                        / entry_price_for_risk
                    )
                    leveraged_loss = distance_pct * leverage
                    risk["stop_loss_price"] = self._round_price(allowed_stop)
                    decision["risk_management"] = risk
                    adjustments.append(
                        f"{decision.get('asset')}: 止损风险 {leveraged_loss:.2%} > 10%，已调整为 {risk['stop_loss_price']}。"
                    )

                # 方向校验：多单止损必须低于现价，空单止损必须高于现价。
                if current_price_for_risk is None:
                    current_price_for_risk = entry_price_for_risk
                if current_price_for_risk and stop_loss_price is not None:
                    if action == "LONG" and stop_loss_price >= current_price_for_risk:
                        candidate = allowed_stop
                        if candidate >= current_price_for_risk:
                            candidate = current_price_for_risk * 0.999
                            warnings.append(
                                f"{decision.get('asset')}: 现价已低于风控允许止损，已将止损压到现价下方。"
                            )
                        risk["stop_loss_price"] = self._round_price(candidate)
                        decision["risk_management"] = risk
                    elif action == "SHORT" and stop_loss_price <= current_price_for_risk:
                        candidate = allowed_stop
                        if candidate <= current_price_for_risk:
                            candidate = current_price_for_risk * 1.001
                            warnings.append(
                                f"{decision.get('asset')}: 现价已高于风控允许止损，已将止损抬到现价上方。"
                            )
                        risk["stop_loss_price"] = self._round_price(candidate)
                        decision["risk_management"] = risk

                # 方向校验：多单止盈必须高于现价，空单止盈必须低于现价。
                if current_price_for_risk is None:
                    current_price_for_risk = entry_price_for_risk
                if (
                    current_price_for_risk
                    and not missing_take_profit
                    and take_profit_price is not None
                ):
                    if action == "LONG" and take_profit_price <= current_price_for_risk:
                        risk["take_profit_price"] = self._round_price(
                            current_price_for_risk * 1.001
                        )
                        decision["risk_management"] = risk
                        warnings.append(
                            f"{decision.get('asset')}: 止盈价低于现价，已上调到现价上方。"
                        )
                    elif action == "SHORT" and take_profit_price >= current_price_for_risk:
                        risk["take_profit_price"] = self._round_price(
                            current_price_for_risk * 0.999
                        )
                        decision["risk_management"] = risk
                        warnings.append(
                            f"{decision.get('asset')}: 止盈价高于现价，已下调到现价下方。"
                        )

        # 获取可用资本并执行
        available_capital = state.get("available_capital") or 0.0
        execution_results: list[Dict[str, Any]] = []
        for decision in per_asset:
            if not isinstance(decision, dict):
                continue
            asset = str(decision.get("asset") or "")
            action = str(decision.get("decision") or "").upper()
            exec_action = action
            if action in {"CLOSE_LONG", "CLOSE_SHORT"}:
                exec_action = "CLOSE"
            execution = decision.get("execution") or {}
            risk = decision.get("risk_management") or {}

            leverage = self._coerce_int(execution.get("leverage"))
            stop_loss_price = self._coerce_float(risk.get("stop_loss_price"))
            take_profit_price = self._coerce_float(risk.get("take_profit_price"))

            entry_result = ""
            leverage_result = ""
            protection_result = ""
            trade_info = None

            if exec_action == "CLOSE":
                entry_result, trade_info = self._execute_close(
                    asset, exec_action, warnings
                )
            elif exec_action in {"LONG", "SHORT"}:
                # 先检查是否已有仓位，决定是更新保护单还是开仓
                has_position = False
                is_same_direction = False
                current_position_amt = 0.0
                entry_price_from_position = None
                if asset:
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
                                current_side = (
                                    "LONG" if current_position_amt > 0 else "SHORT"
                                )
                                if current_side == exec_action:
                                    is_same_direction = True
                    except Exception as e:
                        warnings.append(
                            f"{asset}: 获取当前持仓失败 ({str(e)})，跳过执行以防风险。"
                        )
                        continue

                if has_position:
                    if entry_price_from_position:
                        execution["entry_price"] = entry_price_from_position
                        decision["execution"] = execution
                    if is_same_direction:
                        entry_result = (
                            f"已持有 {asset} {exec_action} 仓位 ({current_position_amt})，保持不动 (No Rebalance)。"
                        )
                        protection_result = self._apply_protection_orders(
                            asset, stop_loss_price, take_profit_price
                        )
                    else:
                        entry_result = (
                            f"警告：当前持有反向仓位 ({current_position_amt})，但在请求开 {exec_action}。请先平仓。"
                        )
                else:
                    (
                        entry_result,
                        leverage_result,
                        protection_result,
                    ) = self._execute_open(
                        decision,
                        asset,
                        exec_action,
                        leverage,
                        available_capital,
                        stop_loss_price,
                        take_profit_price,
                        warnings,
                    )

            if exec_action in {"LONG", "SHORT", "CLOSE"}:
                execution_results.append(
                    {
                        "asset": asset,
                        "action": action,
                        "set_leverage": leverage_result,
                        "entry_order": entry_result,
                        "protection": protection_result,
                        "trade_info": trade_info if exec_action == "CLOSE" else None,
                    }
                )

        # 更新状态，序列化最终决策供后续步骤或前端使用
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

    def _execute_open(
        self,
        decision: Dict[str, Any],
        asset: str,
        exec_action: str,
        leverage: Optional[int],
        available_capital: float,
        stop_loss_price: Optional[float],
        take_profit_price: Optional[float],
        warnings: list[str],
    ) -> tuple[str, str, str]:
        entry_result = ""
        leverage_result = ""
        protection_result = ""

        if not asset:
            warnings.append("存在未提供 asset 的交易决策，已跳过执行。")
            return entry_result, leverage_result, protection_result
        if leverage is None or leverage <= 0:
            warnings.append(f"{asset}: 未提供有效 leverage，跳过执行。")
            return entry_result, leverage_result, protection_result

        svc = get_service()
        try:
            resp = svc.set_leverage(asset, leverage)
            leverage_result = (
                f"已将 {resp.get('symbol')} 杠杆调整为 {resp.get('leverage')}x。"
            )
        except Exception as exc:
            leverage_result = str(exc)

        target_notional = float(available_capital) * float(leverage)
        if target_notional <= 0:
            warnings.append(f"{asset}: 可用本金不足，跳过执行。")
            return entry_result, leverage_result, protection_result

        current_position_amt = 0.0
        has_position = False
        is_same_direction = False
        entry_price_from_position = None
        try:
            positions = svc.get_positions([asset])
            if positions:
                pos = positions[0]
                current_position_amt = float(pos.get("positionAmt", 0.0))
                entry_price_from_position = self._coerce_float(pos.get("entryPrice"))
                if abs(current_position_amt) > 0:
                    has_position = True
                    current_side = "LONG" if current_position_amt > 0 else "SHORT"
                    if current_side == exec_action:
                        is_same_direction = True
        except Exception as e:
            warnings.append(f"{asset}: 获取当前持仓失败 ({str(e)})，跳过执行以防风险。")
            return entry_result, leverage_result, protection_result

        if has_position and entry_price_from_position:
            execution = decision.get("execution") or {}
            execution["entry_price"] = entry_price_from_position
            decision["execution"] = execution

        if has_position:
            if is_same_direction:
                entry_result = (
                    f"已持有 {asset} {exec_action} 仓位 ({current_position_amt})，保持不动 (No Rebalance)。"
                )
            else:
                entry_result = (
                    f"警告：当前持有反向仓位 ({current_position_amt})，但在请求开 {exec_action}。请先平仓。"
                )
        else:
            side = "BUY" if exec_action == "LONG" else "SELL"
            try:
                svc.cancel_symbol_orders(asset)
            except Exception:
                pass
            try:
                resp = svc.market_order_notional(
                    symbol=asset,
                    side=side,
                    notional_usdt=target_notional,
                )
            except Exception as exc:
                return str(exc), leverage_result, protection_result
            avg_price = resp.get("avgPrice") or resp.get("avg_price")
            cum_quote = resp.get("cumQuote") or resp.get("cum_quote")
            executed_qty = resp.get("executedQty") or resp.get("executed_qty")
            actual_usdt = None
            try:
                if cum_quote:
                    actual_usdt = float(cum_quote)
                elif avg_price and executed_qty:
                    actual_usdt = float(avg_price) * float(executed_qty)
            except (TypeError, ValueError):
                actual_usdt = None
            actual_text = (
                f"，实际名义≈{actual_usdt:.2f} USDT"
                if actual_usdt is not None
                else ""
            )
            shortfall_text = ""
            if (
                actual_usdt is not None
                and float(target_notional) > 0
                and actual_usdt + 1e-6 < float(target_notional)
            ):
                shortfall_text = "（实际成交名义低于计划，可能因余额/限额/最小下单量）"
            entry_result = (
                f"下单成功：{resp.get('symbol')} {resp.get('side')} 数量 {executed_qty} "
                f"（计划名义 {target_notional} USDT{actual_text}）{shortfall_text}，订单 ID {resp.get('orderId')}。"
                "（已在下单前自动清理历史止盈/止损委托，记得立即设置新的保护价）"
            )
            try:
                positions = svc.get_positions([asset])
                if positions:
                    pos = positions[0]
                    entry_price_from_position = self._coerce_float(
                        pos.get("entryPrice")
                    )
                    if entry_price_from_position:
                        execution = decision.get("execution") or {}
                        execution["entry_price"] = entry_price_from_position
                        decision["execution"] = execution
            except Exception:
                pass

        protection_result = self._apply_protection_orders(
            asset, stop_loss_price, take_profit_price
        )
        return entry_result, leverage_result, protection_result

    def _execute_close(
        self,
        asset: str,
        exec_action: str,
        warnings: list[str],
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        if not asset:
            warnings.append("存在未提供 asset 的平仓决策，已跳过执行。")
            return "", None
        try:
            resp = get_service().close_position(asset)
            entry_result = (
                f"已平仓 {resp.get('symbol')} 数量 {resp.get('executedQty')}，"
                f"订单 ID {resp.get('orderId')}。"
            )
        except Exception as exc:
            entry_result = str(exc)
        trade_info = self._build_trade_info_from_open_entry(asset, exec_action, None)
        if trade_info:
            trade_info["exit_price"] = self._safe_mark_price(asset)
            trade_info["exit_time"] = datetime.now(timezone.utc).isoformat()
            trade_info["notes"] = "active_close"
        return entry_result, trade_info

    def _apply_protection_orders(
        self,
        asset: str,
        stop_loss_price: Optional[float],
        take_profit_price: Optional[float],
    ) -> str:
        if not asset:
            return ""
        update_stop_loss = bool(stop_loss_price)
        update_take_profit = bool(take_profit_price)
        if not update_stop_loss and not update_take_profit:
            return ""

        sl_value = stop_loss_price if update_stop_loss else None
        tp_value = take_profit_price if update_take_profit else None
        try:
            result = get_service().configure_exit_orders(
                symbol=asset,
                stop_loss_price=sl_value,
                take_profit_price=tp_value,
                working_type="MARK_PRICE",
                replace_existing=True,
            )
        except Exception as exc:
            return str(exc)

        def _format_algo(resp: Dict[str, Any]) -> tuple[str, Any]:
            algo_id = resp.get("algoId") or resp.get("algo_id") or resp.get("orderId")
            algo_text = str(algo_id) if algo_id is not None else "unknown"
            trigger = (
                resp.get("triggerPrice")
                or resp.get("stopPrice")
                or resp.get("trigger_price")
            )
            return algo_text, trigger

        parts: list[str] = []
        if isinstance(result, dict) and "stop_loss" in result:
            algo_id, trigger = _format_algo(result["stop_loss"])
            parts.append(f"止损单已创建（Algo ID {algo_id}，触发价 {trigger}）。")
        if isinstance(result, dict) and "take_profit" in result:
            algo_id, trigger = _format_algo(result["take_profit"])
            parts.append(f"止盈单已创建（Algo ID {algo_id}，触发价 {trigger}）。")
        return " ".join(parts) if parts else "未创建任何止盈/止损委托。"

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
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except Exception:
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
