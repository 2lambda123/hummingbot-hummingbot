#!/usr/bin/env python
import logging
import pandas as pd
from typing import Dict
from typing import Optional

from sqlalchemy.engine import RowProxy

from hummingbot.core.data_type.order_book cimport OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_message import LiquidOrderBookMessage
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


cdef class LiquidOrderBook(OrderBook):

    @classmethod
    def logger(cls):
        global lob_logger
        if lob_logger is None:
            lob_logger = logging.getLogger(__name__)
        return lob_logger

    @classmethod
    def snapshot_message_from_exchange(cls,
                                       msg: Dict[str, any],
                                       timestamp: float,
                                       metadata: Optional[Dict] = None) -> (OrderBookMessage):
        """
        *required
        Convert json snapshot data into standard OrderBookMessage format
        :param msg: json snapshot data from live web socket stream
        :param timestamp: timestamp attached to incoming data
        :return: LiquidOrderBookMessage
        """
        if metadata:
            msg.update(metadata)
        return LiquidOrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content=msg,
            timestamp=timestamp
        )

    @classmethod
    def diff_message_from_exchange(cls,
                                   msg: Dict[str, any],
                                   timestamp: Optional[float] = None,
                                   metadata: Optional[Dict] = None) -> OrderBookMessage:
        """
        *required
        Convert json diff data into standard OrderBookMessage format
        :param msg: json diff data from live web socket stream
        :param timestamp: timestamp attached to incoming data
        :return: OrderBookMessage
        """
        if metadata:
            msg.update(metadata)
        if "time" in msg:
            msg_time = pd.Timestamp(msg["time"]).timestamp()
        return LiquidOrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content=msg,
            timestamp=timestamp or msg_time)
