# distutils: language=c++
# distutils: sources=hummingbot/core/cpp/OrderBookEntry.cpp

import logging
from decimal import Decimal
from typing import Dict

import numpy as np

from hummingbot.core.data_type.order_book_row import OrderBookRow
from hummingbot.logger import HummingbotLogger

_btaot_logger = None
s_empty_diff = np.ndarray(shape=(0, 4), dtype="float64")

FtxPerpetualOrderBookTrackingDictionary = Dict[Decimal, Dict[str, Dict[str, any]]]


class FtxPerpetualActiveOrderTracker:
    def __init__(self,
                 active_asks: FtxPerpetualOrderBookTrackingDictionary = None,
                 active_bids: FtxPerpetualOrderBookTrackingDictionary = None):
        super().__init__()
        self._active_asks = active_asks or {}
        self._active_bids = active_bids or {}

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global _btaot_logger
        if _btaot_logger is None:
            _btaot_logger = logging.getLogger(__name__)
        return _btaot_logger

    @property
    def active_asks(self) -> FtxPerpetualOrderBookTrackingDictionary:
        return self._active_asks

    @property
    def active_bids(self) -> FtxPerpetualOrderBookTrackingDictionary:
        return self._active_bids

    def volume_for_ask_price(self, price) -> float:
        return sum([float(msg["remaining_size"]) for msg in self._active_asks[price].values()])

    def volume_for_bid_price(self, price) -> float:
        return sum([float(msg["remaining_size"]) for msg in self._active_bids[price].values()])

    def get_rates_and_quantities(self, entry) -> tuple:
        return float(entry[0]), float(entry[1])

    def convert_diff_message_to_np_arrays(self, message):
        content = message.content
        bid_entries = content["bids"]
        ask_entries = content["asks"]
        timestamp = message.timestamp

        bids = s_empty_diff
        asks = s_empty_diff

        if len(bid_entries) > 0:
            bids = np.array(
                [[timestamp,
                  float(price),
                  float(quantity),
                  timestamp]
                 for price, quantity in [self.get_rates_and_quantities(entry) for entry in bid_entries]],
                dtype="float64",
                ndmin=2
            )

        if len(ask_entries) > 0:
            asks = np.array(
                [[timestamp,
                  float(price),
                  float(quantity),
                  timestamp]
                 for price, quantity in [self.get_rates_and_quantities(entry) for entry in ask_entries]],
                dtype="float64",
                ndmin=2
            )

        return bids, asks

    def convert_snapshot_message_to_np_arrays(self, message):
        content: dict = message.content
        bid_entries: list = content["bids"]
        ask_entries: list = content["asks"]
        timestamp: float = message.timestamp

        bids = s_empty_diff
        asks = s_empty_diff

        if len(bid_entries) > 0:
            bids = np.array(
                [[timestamp,
                  float(price),
                  float(quantity),
                  timestamp]
                 for price, quantity in [self.get_rates_and_quantities(entry) for entry in bid_entries]],
                dtype="float64",
                ndmin=2
            )

        if len(ask_entries) > 0:
            asks = np.array(
                [[timestamp,
                  float(price),
                  float(quantity),
                  timestamp]
                 for price, quantity in [self.get_rates_and_quantities(entry) for entry in ask_entries]],
                dtype="float64",
                ndmin=2
            )

        return bids, asks

    def convert_trade_message_to_np_array(self, message):
        trade_type_value = 2.0

        return np.array(
            [message.timestamp, trade_type_value, float(message.content["price"]), float(message.content["size"])],
            dtype="float64"
        )

    def convert_diff_message_to_order_book_row(self, message):
        np_bids, np_asks = self.convert_diff_message_to_np_arrays(message)
        bids_row = [OrderBookRow(price, qty, update_id) for ts, price, qty, update_id in np_bids]
        asks_row = [OrderBookRow(price, qty, update_id) for ts, price, qty, update_id in np_asks]
        return bids_row, asks_row

    def convert_snapshot_message_to_order_book_row(self, message):
        np_bids, np_asks = self.convert_snapshot_message_to_np_arrays(message)
        bids_row = [OrderBookRow(price, qty, update_id) for ts, price, qty, update_id in np_bids]
        asks_row = [OrderBookRow(price, qty, update_id) for ts, price, qty, update_id in np_asks]
        return bids_row, asks_row
