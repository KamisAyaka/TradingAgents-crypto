
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

            # 提前把止盈目标规范化（四舍五入），避免下游重复处理。
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
            missing_stop_loss = stop_loss_price is None or stop_loss_price <= 0
            if missing_stop_loss:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 stop_loss_price，无法校验 10% 规则。"
                )
            missing_take_profit = False
            if isinstance(risk.get("take_profit_targets"), list):
                targets = risk.get("take_profit_targets") or []
                missing_take_profit = not targets
            else:
                tp_value = risk.get("take_profit_targets")
                missing_take_profit = tp_value is None or tp_value <= 0
            if missing_take_profit:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 take_profit_targets，无法执行止盈/止损设置。"
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

        # 获取可用资本并执行
        available_capital = state.get("available_capital") or 0.0
        execution_results = self._execute_plan(plan, available_capital, warnings)

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

    def _execute_plan(
        self,
        plan: Dict[str, Any],
        available_capital: float,
        warnings: list[str],
    ) -> list[Dict[str, Any]]:
        """
        执行具体的交易计划。
        
        参数:
            plan: 解析后的交易计划。
            available_capital: 账户可用 USDT 余额。
            warnings: 用于收集执行过程中的警告列表。
            
        返回:
            list[Dict]: 每笔交易的执行结果摘要。
        """
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
                
                # 有持仓时优先用交易所 entryPrice 回写给前端/日志展示。
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
               
                # 基于交易所实际挂单判断是否需要更新止盈/止损。
                update_stop_loss = bool(stop_loss_price)
                update_take_profit = bool(take_profit_price)

                if update_stop_loss:
                    protection_result = set_binance_take_profit_stop_loss.invoke(
                        {
                            "symbol": asset,
                            "stop_loss_price": stop_loss_price or 0.0,
                            "take_profit_price": 0.0,
                            "working_type": "MARK_PRICE",
                        }
                    )
                if update_take_profit:
                    protection_result = set_binance_take_profit_stop_loss.invoke(
                        {
                            "symbol": asset,
                            "stop_loss_price": 0.0,
                            "take_profit_price": take_profit_price or 0.0,
                            "working_type": "MARK_PRICE",
                        }
                    )
            elif exec_action == "CLOSE":
                # 处理平仓逻辑
                if not asset:
                    warnings.append("存在未提供 asset 的平仓决策，已跳过执行。")
                    continue
                # 调用工具平掉该符号的所有仓位
                entry_result = close_binance_position.invoke({"symbol": asset})
                
                # 构建平仓记录，用于后续的“复盘 (Reflection)”
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
