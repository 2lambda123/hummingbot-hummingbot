#!/usr/bin/env python

import asyncio
import logging

from typing import (
    Optional,
    List,
)
from hummingbot.connector.exchange.southxchange.southxchange_api_user_stream_data_source import \
    SouthxchangeAPIUserStreamDataSource
from hummingbot.connector.exchange.southxchange.southxchange_auth import SouthXchangeAuth
from hummingbot.connector.exchange.southxchange.southxchange_utils import SouthXchangeAPIRequest
from hummingbot.connector.exchange.southxchange.southxchange_constants import EXCHANGE_NAME
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.data_type.user_stream_tracker import (
    UserStreamTracker
)
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
    safe_gather,
)

from hummingbot.logger import HummingbotLogger


class SouthxchangeUserStreamTracker(UserStreamTracker):
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self,
                 southxchange_auth: Optional[SouthXchangeAuth] = None,
                 southxchange_api_request: Optional[SouthXchangeAPIRequest] = None,
                 trading_pairs: Optional[List[str]] = []):
        super().__init__()
        self._southxchange_auth: SouthXchangeAuth = southxchange_auth
        self._southxchange_api_request: SouthXchangeAPIRequest = southxchange_api_request
        self._trading_pairs: List[str] = trading_pairs
        self._ev_loop: asyncio.events.AbstractEventLoop = asyncio.get_event_loop()
        self._data_source: Optional[UserStreamTrackerDataSource] = None
        self._user_stream_tracking_task: Optional[asyncio.Task] = None

    @property
    def data_source(self) -> UserStreamTrackerDataSource:
        """
        *required
        Initializes a user stream data source (user specific order diffs from live socket stream)
        :return: OrderBookTrackerDataSource
        """
        if not self._data_source:
            self._data_source = SouthxchangeAPIUserStreamDataSource(
                southxchange_auth=self._southxchange_auth,
                southxchange_api_request=self._southxchange_api_request,
                trading_pairs=self._trading_pairs
            )
        return self._data_source

    @property
    def exchange_name(self) -> str:
        """
        *required
        Name of the current exchange
        """
        return EXCHANGE_NAME

    async def start(self):
        """
        *required
        Start all listeners and tasks
        """
        self._user_stream_tracking_task = safe_ensure_future(
            self.data_source.listen_for_user_stream(self._ev_loop, self._user_stream)
        )
        await safe_gather(self._user_stream_tracking_task)
