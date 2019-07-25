from typing import NamedTuple, List
import pandas as pd


class MarketOrder(NamedTuple):
    client_order_id: str
    symbol: str
    is_buy: bool
    base_asset: str
    quote_asset: str
    amount: float
    timestamp: float

    @classmethod
    def to_pandas(cls, market_orders: List["MarketOrder"]) -> pd.DataFrame:
        columns = ["order_id", "symbol", "is_buy", "base_asset", "quote_asset", "quantity", "timestamp"]
        data = [[
            market_order.client_order_id,
            market_order.symbol,
            market_order.is_buy,
            market_order.base_asset,
            market_order.quote_asset,
            market_order.amount,
            pd.Timestamp(market_order.timestamp, unit='s', tz='UTC').strftime('%Y-%m-%d %H:%M:%S')
        ] for market_order in market_orders]
        return pd.DataFrame(data=data, columns=columns)
