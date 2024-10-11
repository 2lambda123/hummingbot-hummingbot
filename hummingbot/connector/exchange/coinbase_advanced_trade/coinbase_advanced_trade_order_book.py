import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from hummingbot.connector.exchange.coinbase_advanced_trade.coinbase_advanced_trade_constants import (
    WS_ORDER_SUBSCRIPTION_CHANNELS,
)
from hummingbot.connector.exchange.coinbase_advanced_trade.coinbase_advanced_trade_web_utils import (
    get_timestamp_from_exchange_time,
)
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.logger import HummingbotLogger


class CoinbaseAdvancedTradeOrderBook(OrderBook):
    """
    Coinbase Advanced Trade Order Book class
    """
    # Mapping of WS channels to their respective sequence numbers
    _sequence_nums: Dict[str, int] = {channel: 0 for channel in WS_ORDER_SUBSCRIPTION_CHANNELS.inv.keys()}

    _logger: HummingbotLogger | logging.Logger | None = None

    @classmethod
    def logger(cls) -> HummingbotLogger | logging.Logger:
        if cls._logger is None:
            name: str = HummingbotLogger.logger_name_for_class(cls)
            cls._logger = logging.getLogger(name)
        return cls._logger

    @classmethod
    def snapshot_message_from_exchange(cls,
                                       msg: Dict[str, any],
                                       timestamp: float,
                                       metadata: Optional[Dict] = None) -> OrderBookMessage:
        """
        Creates a snapshot message with the order book snapshot message
        :param msg: the response from the exchange when requesting the order book snapshot
        :param timestamp: the snapshot timestamp
        :param metadata: a dictionary with extra information to add to the snapshot data
        :return: a snapshot message with the snapshot information received from the exchange
        """
        if metadata:
            msg |= metadata

        ob_msg: OrderBookMessage = OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": msg["trading_pair"],
            "update_id": int(get_timestamp_from_exchange_time(msg["pricebook"]["time"], "s")),
            "bids": [[d["price"], d["size"]] for d in msg["pricebook"]["bids"][:10]],
            "asks": [[d["price"], d["size"]] for d in msg["pricebook"]["asks"][:10]]
        }, timestamp=timestamp)

        return ob_msg

    @classmethod
    async def level2_or_trade_message_from_exchange(
            cls,
            msg: Dict[str, Any],
            symbol_to_pair: Callable[[...], Coroutine[None, None, str]]) -> Optional[OrderBookMessage]:
        """
        Process messages from the order book or trade channel
        https://docs.cdp.coinbase.com/advanced-trade/docs/ws-channels#level2-channel
        The snapshot is the first message received form the 'level2' channel. It has a sequence_num = 0
        :param msg: the response from the exchange when requesting the order book snapshot
        :param symbol_to_pair: Method to retrieve a Hummingbot trading pair from an exchange symbol
        :return: a snapshot message with the snapshot information received from the exchange
        """
        CoinbaseAdvancedTradeOrderBook.logger().debug("      '-> level2_...")
        if "events" not in msg or "channel" not in msg:
            cls.logger().error(f"Unexpected message from Coinbase Advanced Trade: {msg}"
                               " - missing 'events' or 'channel' key")
            return None
        channel = msg["channel"]

        if channel not in cls._sequence_nums:
            cls.logger().warning(f"Unexpected message 'channel' from Coinbase Advanced Trade: {channel}")
            return None

        cls._sequence_nums[channel] = msg["sequence_num"] + 1

        if channel == "l2_data":
            CoinbaseAdvancedTradeOrderBook.logger().debug("      '-> sending to internal level2")
            return await cls._level2_order_book_message(msg, symbol_to_pair)

        elif channel == "market_trades":
            return await cls._market_trades_order_book_message(msg, symbol_to_pair)

        elif channel in ["subscriptions", "heartbeat"]:
            cls.logger().debug(f"Ignoring message from Coinbase Advanced Trade: {msg}")
            return None

        cls.logger().error(f"Unexpected message 'channel' from Coinbase Advanced Trade: {channel}")
        raise ValueError(f"Unexpected channel: {channel}")

    @classmethod
    async def _level2_order_book_message(
            cls,
            msg: Dict[str, any],
            symbol_to_pair: Callable[[...], Coroutine[None, None, str]]) -> Optional[OrderBookMessage]:
        """
        Process messages from the order book or trade channel
        https://docs.cdp.coinbase.com/advanced-trade/docs/ws-channels#level2-channel
        The snapshot is the first message received form the 'level2' channel. It has a sequence_num = 0
        :param msg: the response from the exchange when requesting the order book snapshot
        :param symbol_to_pair: Method to retrieve a Hummingbot trading pair from an exchange symbol
        :return: a snapshot message with the snapshot information received from the exchange
        {
            'channel': 'l2_data',
            'client_id': '',
            'timestamp': '2024-10-08T09:10:36.04370306Z',
            'sequence_num': 9,
            'events': [
                {
                    'type': 'update',
                    'product_id': 'BTC-USD',
                    'updates': [
                        {
                            'side': 'bid',
                            'event_time': '2024-10-08T09:10:34.970831Z',
                            'price_level': '62319.46',
                            'new_quantity': '0.00169'
                        },
                        {
                            'side': 'bid',
                            'event_time': '2024-10-08T09:10:34.970831Z',
                            'price_level': '62318.81',
                            'new_quantity': '0'
                        },
                        {
                            'side': 'offer'
                            'event_time': '2024-10-08T09:10:34.970831Z',
                            'price_level': '62336.65',
                            'new_quantity': '0.03021537'
                        }
                    ]
                }
            ]
        }
        """

        for event in msg["events"]:
            trading_pair = await symbol_to_pair(event["product_id"])
            CoinbaseAdvancedTradeOrderBook.logger().debug(f"      '-> product_id: {event['product_id']}")
            event_type = event["type"]

            obm_content_updates = {
                "trading_pair": trading_pair,
                "update_id": int(get_timestamp_from_exchange_time(msg["timestamp"], "s")),
                "bids": [],
                "asks": []
            }

            obm_content_snapshot = {
                "trading_pair": trading_pair,
                "update_id": int(get_timestamp_from_exchange_time(msg["timestamp"], "s")),
                "bids": [],
                "asks": []
            }

            # Process updates or snapshots
            for update in event.get("updates"):
                if update["side"] == "bid":
                    if event_type == "update":
                        # For updates, append all entries
                        obm_content_updates["bids"].append([update["price_level"], update["new_quantity"]])
                    else:  # For snapshots, limit to the first 10 entries
                        if len(obm_content_snapshot["bids"]) < 10:
                            obm_content_snapshot["bids"].append([update["price_level"], update["new_quantity"]])
                else:  # For "ask" side
                    if event_type == "update":
                        obm_content_updates["asks"].append([update["price_level"], update["new_quantity"]])
                    else:  # For snapshots, limit to the first 10 entries
                        if len(obm_content_snapshot["asks"]) < 10:
                            obm_content_snapshot["asks"].append([update["price_level"], update["new_quantity"]])

            # Handle the return of messages based on event type
            if event_type == "update":
                CoinbaseAdvancedTradeOrderBook.logger().debug("      '-> returning OBM DIFF")
                return OrderBookMessage(OrderBookMessageType.DIFF,
                                        obm_content_updates,
                                        timestamp=obm_content_updates['update_id'])

            elif event_type == "snapshot":
                # obm_content["first_update_id"] = 0  # Uncomment if needed
                CoinbaseAdvancedTradeOrderBook.logger().debug("      '-> returning OBM SNAPSHOT")
                return OrderBookMessage(OrderBookMessageType.SNAPSHOT,
                                        obm_content_snapshot,
                                        timestamp=obm_content_snapshot['update_id'])
            else:
                cls.logger().warning(f"Unexpected event type: {event_type}")
                return None

    @classmethod
    async def _market_trades_order_book_message(
            cls,
            msg: Dict[str, Any],
            symbol_to_pair: Callable[[...], Coroutine[None, None, str]]) -> OrderBookMessage:
        """
        Process messages from the market trades channel
        https://docs.cdp.coinbase.com/advanced-trade/docs/ws-channels#market-trades-channel
        :param msg: the response from the exchange when requesting the order book snapshot
        :param symbol_to_pair: Method to retrieve a Hummingbot trading pair from an exchange symbol
        :return: a trade message with the trade information received from the exchange
        {
            'channel': 'market_trades',
            'client_id': '',
            'timestamp': '2024-10-08T09:10:52.425044603Z',
            'sequence_num': 328,
            'events': [
                {
                    'type': 'update',
                    'trades': [
                        {
                            'product_id': 'BTC-USD',
                            'trade_id': '699871154',
                            'price': '62322.43',
                            'size': '0.00005535',
                            'time': '2024-10-08T09:10:52.378779Z',
                            'side': 'BUY'
                        }
                    ]
                }
            ]
        }
        """
        for event in msg["events"]:
            for trade in event["trades"]:
                ts: float = get_timestamp_from_exchange_time(msg["timestamp"], "s")
                trading_pair = await symbol_to_pair(trade["product_id"])

                return OrderBookMessage(
                    OrderBookMessageType.TRADE,
                    {
                        "trading_pair": trading_pair,
                        "trade_type": float(TradeType.SELL.value) if trade["side"] else float(TradeType.BUY.value),
                        "trade_id": int(trade["trade_id"]),
                        "update_id": int(ts),
                        "price": trade["price"],
                        "amount": trade["size"]
                    },
                    timestamp=ts)
