from decimal import Decimal
from typing import Any, Dict, List, Optional

from hummingbot.connector.derivative.ftx_perpetual.ftx_perpetual_order_status import FtxPerpetualOrderStatus
from hummingbot.connector.in_flight_order_base import InFlightOrderBase
from hummingbot.core.event.events import MarketEvent, OrderType, TradeType


class FtxPerpetualInFlightOrder(InFlightOrderBase):
    def __init__(self,
                 client_order_id: str,
                 exchange_order_id: Optional[str],
                 trading_pair: str,
                 order_type: OrderType,
                 trade_type: TradeType,
                 price: Decimal,
                 amount: Decimal,
                 created_at: float,
                 leverage: int,
                 position_action: str,
                 initial_state: str = "new"):
        super().__init__(
            client_order_id,
            exchange_order_id,
            trading_pair,
            order_type,
            trade_type,
            price,
            amount,
            initial_state
        )
        self.created_at = created_at
        self.state = FtxPerpetualOrderStatus.new
        self.leverage = leverage
        self.position = position_action

    def __repr__(self) -> str:
        return f"super().__repr__()" \
               f"created_at='{str(self.created_at)}'')"

    def to_json(self) -> Dict[str, Any]:
        response = super().to_json()
        response["created_at"] = str(self.created_at)
        response["leverage"] = self.leverage
        response["position"] = self.position
        return response

    @property
    def is_done(self) -> bool:
        return self.state is FtxPerpetualOrderStatus.closed

    @property
    def is_failure(self) -> bool:
        return self.state is FtxPerpetualOrderStatus.FAILURE or self.is_cancelled

    @property
    def is_cancelled(self) -> bool:
        return self.state is FtxPerpetualOrderStatus.closed and self.executed_amount_base < self.amount

    def set_status(self, status: str):
        self.last_state = status
        self.state = FtxPerpetualOrderStatus[status]

    @property
    def order_type_description(self) -> str:
        order_type = "market" if self.order_type is OrderType.MARKET else "limit"
        side = "buy" if self.trade_type is TradeType.BUY else "sell"
        return f"{order_type} {side}"

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> InFlightOrderBase:
        retval: FtxPerpetualInFlightOrder = FtxPerpetualInFlightOrder(
            data["client_order_id"],
            data["exchange_order_id"],
            data["trading_pair"],
            getattr(OrderType, data["order_type"]),
            getattr(TradeType, data["trade_type"]),
            Decimal(data["price"]),
            Decimal(data["amount"]),
            data["leverage"],
            data["position"],
            float(data["created_at"] if "created_at" in data else 0),
            data["last_state"]
        )
        retval.executed_amount_base = Decimal(data["executed_amount_base"])
        retval.executed_amount_quote = Decimal(data["executed_amount_quote"])
        retval.fee_asset = data["fee_asset"]
        retval.fee_paid = Decimal(data["fee_paid"])
        retval.last_state = data["last_state"]
        retval.state = FtxPerpetualOrderStatus[retval.last_state]
        return retval

    def update(self, data: Dict[str, Any]) -> List[Any]:
        events: List[Any] = []

        new_status: FtxPerpetualOrderStatus = FtxPerpetualOrderStatus[data["status"]]
        old_executed_base: Decimal = self.executed_amount_base
        old_executed_quote: Decimal = self.executed_amount_quote
        overall_executed_base: Decimal = data["filledSize"]
        overall_remaining_size: Decimal = self.amount - overall_executed_base
        if data["avgFillPrice"] is not None:
            overall_executed_quote: Decimal = overall_executed_base * data["avgFillPrice"]
        else:
            overall_executed_quote: Decimal = Decimal("0")

        diff_base: Decimal = overall_executed_base - old_executed_base
        diff_quote: Decimal = overall_executed_quote - old_executed_quote

        if diff_base > 0:
            diff_price: Decimal = diff_quote / diff_base
            events.append((MarketEvent.OrderFilled, diff_base, diff_price, None))
            self.executed_amount_base = overall_executed_base
            self.executed_amount_quote = overall_executed_quote

        if not self.is_done and new_status == FtxPerpetualOrderStatus.closed:
            if overall_remaining_size > 0:
                events.append((MarketEvent.OrderCancelled, None, None, None))
            elif self.trade_type is TradeType.BUY:
                events.append((MarketEvent.BuyOrderCompleted, overall_executed_base, overall_executed_quote, None))
            else:
                events.append((MarketEvent.SellOrderCompleted, overall_executed_base, overall_executed_quote, None))

        self.state = new_status
        self.last_state = new_status.name

        return events

    def update_fees(self, new_fee: Decimal):
        self.fee_paid += new_fee
