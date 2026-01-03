from typing import Annotated, List, Optional

from langchain_core.tools import tool

from tradingagents.dataflows.binance_future import (
    BinanceFuturesError,
    BinanceFuturesService,
    get_service,
)


def _parse_symbols(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    normalized = raw.replace("\n", ",")
    return [token.strip().upper() for token in normalized.split(",") if token.strip()]


def _service() -> BinanceFuturesService:
    return get_service()


@tool
def get_binance_positions(
    symbols: Annotated[str, "可选，逗号分隔的币对列表，如 BTCUSDT,ETHUSDT"] = "",
) -> str:
    """
    获取币安 USDT 永续合约的当前持仓，返回文本摘要。
    """
    try:
        return _service().summarize_positions(_parse_symbols(symbols))
    except BinanceFuturesError as exc:
        return str(exc)


@tool
def set_binance_leverage(
    symbol: Annotated[str, "需要调整杠杆的币对，如 BTCUSDT"],
    leverage: Annotated[int, "新的杠杆倍数，整数 5-25"],
) -> str:
    """
    调整某个交易对的合约杠杆（仅支持 USDT 永续）。
    """
    try:
        resp = _service().set_leverage(symbol.upper(), int(leverage))
    except BinanceFuturesError as exc:
        return str(exc)
    return f"已将 {resp.get('symbol')} 杠杆调整为 {resp.get('leverage')}x。"


@tool
def open_binance_position_usdt(
    symbol: Annotated[str, "币对（USDT 永续），如 BTCUSDT"],
    side: Annotated[str, "BUY 表示做多，SELL 表示做空"],
    notional_usdt: Annotated[float, "下单金额，单位 USDT"],
) -> str:
    """
    以 USDT 名义金额市价开仓，内部自动换算为合约数量。
    """
    svc = _service()
    try:
        svc.cancel_symbol_orders(symbol.upper())
        resp = svc.market_order_notional(
            symbol=symbol.upper(),
            side=side.upper(),
            notional_usdt=notional_usdt,
        )
    except BinanceFuturesError as exc:
        return str(exc)
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
    if actual_usdt is not None and float(notional_usdt) > 0 and actual_usdt + 1e-6 < float(notional_usdt):
        shortfall_text = "（实际成交名义低于计划，可能因余额/限额/最小下单量）"
    return (
        f"下单成功：{resp.get('symbol')} {resp.get('side')} 数量 {executed_qty} "
        f"（计划名义 {notional_usdt} USDT{actual_text}）{shortfall_text}，订单 ID {resp.get('orderId')}。"
        "（已在下单前自动清理历史止盈/止损委托，记得立即设置新的保护价）"
    )


@tool
def close_binance_position(
    symbol: Annotated[str, "币对（USDT 永续），如 BTCUSDT"],
    quantity: Annotated[float, "可选，若不填则全部平仓"] = 0.0,
) -> str:
    """
    以市价 reduceOnly 平仓，默认平掉该交易对的全部仓位。
    """
    qty = None if quantity <= 0 else quantity
    try:
        resp = _service().close_position(symbol.upper(), qty)
    except BinanceFuturesError as exc:
        return str(exc)
    return (
        f"已平仓 {resp.get('symbol')} 数量 {resp.get('executedQty')}，"
        f"订单 ID {resp.get('orderId')}。"
    )


@tool
def set_binance_take_profit_stop_loss(
    symbol: Annotated[str, "币对（USDT 永续），如 BTCUSDT"],
    stop_loss_price: Annotated[float, "触发止损的价格（0 表示不设置）"] = 0.0,
    take_profit_price: Annotated[float, "触发止盈的价格（0 表示不设置）"] = 0.0,
    working_type: Annotated[str, "触发价格类型：MARK_PRICE 或 CONTRACT_PRICE"] = "MARK_PRICE",
) -> str:
    """
    为当前持仓设置新的止盈/止损触发价，会自动替换旧的止盈/止损委托。
    """
    sl_value = None if stop_loss_price <= 0 else stop_loss_price
    tp_value = None if take_profit_price <= 0 else take_profit_price
    try:
        result = _service().configure_exit_orders(
            symbol=symbol.upper(),
            stop_loss_price=sl_value,
            take_profit_price=tp_value,
            working_type=working_type,
            replace_existing=True,
        )
    except BinanceFuturesError as exc:
        return str(exc)

    def _format_algo(resp):
        algo_id = resp.get("algoId") or resp.get("algo_id") or resp.get("orderId")
        trigger = (
            resp.get("triggerPrice")
            or resp.get("stopPrice")
            or resp.get("trigger_price")
        )
        return algo_id, trigger

    parts = []
    if "stop_loss" in result:
        sl_resp = result["stop_loss"]
        algo_id, trigger = _format_algo(sl_resp)
        parts.append(
            f"止损单已创建（Algo ID {algo_id}，触发价 {trigger}）。"
        )
    if "take_profit" in result:
        tp_resp = result["take_profit"]
        algo_id, trigger = _format_algo(tp_resp)
        parts.append(
            f"止盈单已创建（Algo ID {algo_id}，触发价 {trigger}）。"
        )
    return " ".join(parts) if parts else "未创建任何止盈/止损委托。"
