"""
Binance USDT-M futures execution helpers.

This module wraps the official binance derivatives SDK so tools/agents can
query existing positions, change leverage and submit market orders using the
account configured via environment variables.
"""

import os
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from binance_common.configuration import ConfigurationRestAPI
from binance_common.errors import Error as ClientError
from binance_sdk_derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)


load_dotenv()

DEFAULT_FUTURES_URL = "https://fapi.binance.com"


class BinanceFuturesError(RuntimeError):
    """Wrap lower level client errors with a friendly message."""


def _format_quantity(quantity: float | str) -> str:
    if isinstance(quantity, str):
        return quantity
    # Trim trailing zeros without losing precision needed by Binance.
    formatted = f"{quantity:.12f}".rstrip("0").rstrip(".")
    return formatted or "0"


@dataclass
class BinanceFuturesSettings:
    api_key: str
    api_secret: str
    base_url: str = DEFAULT_FUTURES_URL
    recv_window: int = 5000

    @classmethod
    def from_env(cls) -> "BinanceFuturesSettings":
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_SECRET_KEY")
        if not api_key or not api_secret:
            raise BinanceFuturesError(
                "缺少 BINANCE_API_KEY / BINANCE_SECRET_KEY，无法连接币安期货。"
            )

        base_url = os.getenv("BINANCE_FUTURES_BASE_URL", DEFAULT_FUTURES_URL)
        recv_window = int(os.getenv("BINANCE_RECV_WINDOW", "5000"))
        return cls(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            recv_window=recv_window,
        )


class BinanceFuturesService:
    """Thin wrapper around the official derivatives REST client with helpers."""

    def __init__(self, settings: BinanceFuturesSettings):
        self.settings = settings
        config = ConfigurationRestAPI(
            api_key=settings.api_key,
            api_secret=settings.api_secret,
            base_path=settings.base_url.rstrip("/"),
            timeout=10_000,
        )
        self._connector = DerivativesTradingUsdsFutures(config_rest_api=config)
        self._rest = self._connector.rest_api
        self._symbol_info_cache: Dict[str, Dict[str, Any]] = {}
        self._hedge_mode: Optional[bool] = None

    @classmethod
    def from_env(cls) -> "BinanceFuturesService":
        return cls(BinanceFuturesSettings.from_env())

    # ------------------------ Query helpers ------------------------ #
    def get_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Return non-zero USDT-M positions. Filter by symbols when provided."""
        params: Dict[str, Any] = {"recvWindow": self.settings.recv_window}
        if symbols and len(symbols) == 1:
            params["symbol"] = symbols[0]
        data = self._call_rest(
            self._rest.position_information_v2,
            symbol=params.get("symbol"),
            recv_window=self.settings.recv_window,
        )

        positions: List[Dict[str, Any]] = []
        for entry in data:
            position_amt = float(entry.get("positionAmt", 0.0))
            if not position_amt:
                continue
            symbol = entry.get("symbol")
            if symbols and len(symbols) != 1:
                if symbol not in symbols:
                    continue
            entry["positionAmt"] = position_amt
            entry["entryPrice"] = float(entry.get("entryPrice") or 0.0)
            entry["markPrice"] = float(entry.get("markPrice") or 0.0)
            positions.append(entry)
        return positions

    def get_mark_price(self, symbol: str) -> float:
        data = self._call_rest(self._rest.mark_price, symbol=symbol.upper())
        return float(data.get("markPrice") or 0.0)

    def summarize_positions(self, symbols: Optional[List[str]] = None) -> str:
        positions = self.get_positions(symbols)
        if not positions:
            return "当前无持仓。"

        lines = ["当前持仓："]
        for pos in positions:
            direction = "多头" if pos["positionAmt"] > 0 else "空头"
            lines.append(
                f"- {pos['symbol']} | {direction} {abs(pos['positionAmt'])} 合约 | "
                f"均价 {pos['entryPrice']} | 标记价 {pos['markPrice']} | "
                f"未实现盈亏 {pos.get('unRealizedProfit')} | 杠杆 {pos.get('leverage')}"
            )
        return "\n".join(lines)

    def cancel_symbol_orders(self, symbol: str) -> Dict[str, Any]:
        """Cancel all open orders (including TP/SL) for a symbol."""
        cancel_func = getattr(self._rest, "cancel_all_open_orders", None)
        if cancel_func is None:
            raise BinanceFuturesError("当前 SDK 不支持取消未完成委托操作。")
        return self._call_rest(
            cancel_func,
            symbol=symbol.upper(),
            recv_window=self.settings.recv_window,
        )

    def cancel_all_algo_orders(self, symbol: str) -> Dict[str, Any]:
        cancel_func = getattr(self._rest, "cancel_all_algo_open_orders", None)
        if cancel_func is None:
            raise BinanceFuturesError("当前 SDK 不支持取消算法委托操作。")
        return self._call_rest(
            cancel_func,
            symbol=symbol.upper(),
            recv_window=self.settings.recv_window,
        )

    def configure_exit_orders(
        self,
        symbol: str,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        working_type: str = "MARK_PRICE",
        replace_existing: bool = True,
    ) -> Dict[str, Any]:
        """
        Replace current TP/SL orders with new stop-market / take-profit-market triggers.
        Requires an existing open position to infer close side.
        """
        if stop_loss_price in (None, 0) and take_profit_price in (None, 0):
            raise BinanceFuturesError("请至少提供止损价或止盈价。")

        symbol = symbol.upper()
        positions = self.get_positions([symbol])
        if not positions:
            raise BinanceFuturesError(f"{symbol} 当前没有持仓，无法设置止盈/止损。")
        position = positions[0]
        position_amt = float(position.get("positionAmt") or 0.0)
        if position_amt == 0:
            raise BinanceFuturesError(f"{symbol} 当前净仓位为 0，无法设置止盈/止损。")

        closing_side = "SELL" if position_amt > 0 else "BUY"
        working_type = working_type.upper() if working_type else "MARK_PRICE"
        
        # Determine strict position side for algo order
        is_hedge = self._is_hedge_mode()
        # In Hedge Mode:
        # If we have a LONG position (amt > 0), we close it by SELLing with positionSide="LONG"
        # If we have a SHORT position (amt < 0), we close it by BUYing with positionSide="SHORT"
        
        pos_side_arg = "BOTH"
        if is_hedge:
            pos_side_arg = "LONG" if position_amt > 0 else "SHORT"

        if replace_existing:
            try:
                self.cancel_all_algo_orders(symbol)
            except BinanceFuturesError:
                self.cancel_symbol_orders(symbol)

        results: Dict[str, Any] = {}
        if stop_loss_price is not None and stop_loss_price > 0:
            results["stop_loss"] = self._submit_algo_exit_order(
                symbol=symbol,
                side=closing_side,
                order_type="STOP_MARKET",
                trigger_price=stop_loss_price,
                working_type=working_type,
                position_side=pos_side_arg,
            )
        if take_profit_price is not None and take_profit_price > 0:
            results["take_profit"] = self._submit_algo_exit_order(
                symbol=symbol,
                side=closing_side,
                order_type="TAKE_PROFIT_MARKET",
                trigger_price=take_profit_price,
                working_type=working_type,
                position_side=pos_side_arg,
            )
        if not results:
            raise BinanceFuturesError("止盈/止损价格无效，未能创建任何订单。")
        return results

    # ------------------------ Execution helpers ------------------------ #
    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        return self._call_rest(
            self._rest.change_initial_leverage,
            symbol=symbol.upper(),
            leverage=int(leverage),
            recv_window=self.settings.recv_window,
        )

    def market_order(
        self,
        symbol: str,
        side: str,
        quantity: float | str,
        reduce_only: bool = False,
        position_side: Optional[str] = None,
    ) -> Dict[str, Any]:
        prepared_quantity = self._prepare_quantity(symbol, quantity)
        resolved_position_side = self._resolve_position_side(
            side, reduce_only, position_side
        )
        request_kwargs: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": prepared_quantity,
            "position_side": resolved_position_side,
            "recv_window": self.settings.recv_window,
        }
        if reduce_only:
            request_kwargs["reduce_only"] = True
        return self._call_rest(self._rest.new_order, **request_kwargs)

    def market_order_notional(
        self,
        symbol: str,
        side: str,
        notional_usdt: float,
        reference_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        if notional_usdt <= 0:
            raise BinanceFuturesError("下单金额必须大于 0。")
        price = reference_price or self.get_mark_price(symbol)
        if price <= 0:
            raise BinanceFuturesError("无法获取有效的标记价格，无法换算数量。")
        quantity = notional_usdt / price
        return self.market_order(symbol, side, quantity, reduce_only=False)

    def close_position(
        self, symbol: str, quantity: Optional[float] = None
    ) -> Dict[str, Any]:
        symbol = symbol.upper()
        positions = self.get_positions([symbol])
        if not positions:
            raise BinanceFuturesError(f"{symbol} 当前没有持仓。")
        position = positions[0]
        amt = abs(position["positionAmt"]) if quantity is None else float(quantity)
        if amt <= 0:
            raise BinanceFuturesError("平仓数量必须大于 0。")
        side = "SELL" if position["positionAmt"] > 0 else "BUY"
        return self.market_order(
            symbol=symbol,
            side=side,
            quantity=amt,
            reduce_only=False,
            position_side=position.get("positionSide", "BOTH"),
        )

    # ------------------------ Misc helpers ------------------------ #
    @staticmethod
    def _format_error(error: ClientError) -> str:
        payload = getattr(error, "error_message", None) or str(error)
        return f"Binance Futures API 调用失败：{payload}"

    def _prepare_quantity(self, symbol: str, quantity: float | str) -> str:
        try:
            quantity_dec = Decimal(str(quantity))
        except InvalidOperation as exc:
            raise BinanceFuturesError("下单数量格式无效。") from exc
        adjusted = self._apply_step_size(symbol, quantity_dec)
        if adjusted <= 0:
            raise BinanceFuturesError("精度截断后下单数量为 0，请提高下单金额。")
        adjusted_str = format(adjusted.normalize(), "f")
        return _format_quantity(adjusted_str)

    def _apply_step_size(self, symbol: str, quantity: Decimal) -> Decimal:
        info = self._get_symbol_info(symbol)
        lot_filter = next(
            (flt for flt in info.get("filters", []) if flt.get("filterType") == "LOT_SIZE"),
            None,
        )
        if not lot_filter:
            return quantity

        step_size = Decimal(lot_filter.get("stepSize", "0"))
        if step_size > 0:
            steps = (quantity / step_size).to_integral_value(rounding=ROUND_DOWN)
            quantity = steps * step_size

        min_qty = Decimal(lot_filter.get("minQty", "0"))
        if min_qty and quantity < min_qty:
            raise BinanceFuturesError(
                f"{symbol.upper()} 下单数量小于最小交易数量 {min_qty}。"
            )

        max_qty = Decimal(lot_filter.get("maxQty", "0"))
        if max_qty and max_qty > 0 and quantity > max_qty:
            raise BinanceFuturesError(
                f"{symbol.upper()} 下单数量超过最大交易数量 {max_qty}。"
            )
        return quantity

    def _normalize_price(self, price: float | str) -> str:
        try:
            price_dec = Decimal(str(price))
        except InvalidOperation as exc:
            raise BinanceFuturesError("止盈/止损价格格式无效。") from exc
        if price_dec <= 0:
            raise BinanceFuturesError("止盈/止损价格必须大于 0。")
        normalized = format(price_dec.normalize(), "f")
        return normalized

    def _submit_exit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        trigger_price: float | str,
        working_type: str,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type,
            "stop_price": self._normalize_price(trigger_price),
            "close_position": True,
            "working_type": working_type.upper(),
            "recv_window": self.settings.recv_window,
        }
        return self._call_rest(self._rest.new_order, **params)

    def _submit_algo_exit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        trigger_price: float | str,
        working_type: str,
        position_side: str = "BOTH",
    ) -> Dict[str, Any]:
        return self._call_rest(
            self._rest.new_algo_order,
            algo_type="CONDITIONAL",
            symbol=symbol.upper(),
            side=side.upper(),
            type=order_type,
            trigger_price=float(self._normalize_price(trigger_price)),
            working_type=working_type.upper(),
            close_position="true",
            position_side=position_side,
            recv_window=self.settings.recv_window,
        )

    def _get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        symbol = symbol.upper()
        cached = self._symbol_info_cache.get(symbol)
        if cached:
            return cached
        data = self._call_rest(self._rest.exchange_information)
        symbol_info: Optional[Dict[str, Any]] = None
        if isinstance(data, dict):
            symbols = data.get("symbols")
            if isinstance(symbols, list):
                for entry in symbols:
                    if entry.get("symbol") == symbol:
                        symbol_info = entry
                        break
        elif isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get("symbol") == symbol:
                    symbol_info = entry
                    break
        if symbol_info is None:
            raise BinanceFuturesError(f"无法获取 {symbol} 的交易规则。")
        self._symbol_info_cache[symbol] = symbol_info
        return symbol_info

    def _is_hedge_mode(self) -> bool:
        if self._hedge_mode is not None:
            return self._hedge_mode
        try:
            data = self._call_rest(
                self._rest.get_current_position_mode, recv_window=self.settings.recv_window
            )
            flag = data.get("dualSidePosition")
            self._hedge_mode = bool(flag)
            return self._hedge_mode
        except Exception:
            # Fallback to False if query fails
            return False

    def _resolve_position_side(
        self, side: str, reduce_only: bool, explicit: Optional[str]
    ) -> str:
        if explicit:
            return explicit
        if not self._is_hedge_mode():
            return "BOTH"
        # In Hedge Mode:
        # If opening (not reduce_only), 'BUY' -> 'LONG', 'SELL' -> 'SHORT'
        # If closing (reduce_only or close_position), we need to know which side we are closing.
        # However, for market_order with reduce_only=True, if we don't know, we might fail.
        # Standard logic: BUY -> LONG, SELL -> SHORT is valid for opening.
        # For closing, usually we pass explicit position_side from higher level logic.
        return "LONG" if side.upper() == "BUY" else "SHORT"

    def _call_rest(self, func: Any, **kwargs: Any) -> Any:
        try:
            response = func(**kwargs)
            data = response.data()
        except ClientError as exc:
            raise BinanceFuturesError(self._format_error(exc)) from exc
        return self._normalize(data)

    @staticmethod
    def _normalize(data: Any) -> Any:
        if data is None:
            return None
        if isinstance(data, list):
            return [BinanceFuturesService._normalize(item) for item in data]
        if hasattr(data, "to_dict"):
            return data.to_dict()
        return data


_SERVICE: Optional[BinanceFuturesService] = None


def get_service() -> BinanceFuturesService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = BinanceFuturesService.from_env()
    return _SERVICE
