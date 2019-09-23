#!/usr/bin/env python

import asyncio
import logging
from typing import Optional, List
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger
from hummingbot.core.data_type.user_stream_tracker import UserStreamTrackerDataSourceType, UserStreamTracker
from hummingbot.market.bitroyal.bitroyal_api_user_stream_data_source import bitroyalAPIUserStreamDataSource
from hummingbot.market.bitroyal.bitroyal_auth import bitroyalAuth


class bitroyalUserStreamTracker(UserStreamTracker):
    _cbpust_logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._bust_logger is None:
            cls._bust_logger = logging.getLogger(__name__)
        return cls._bust_logger

    def __init__(
        self,
        data_source_type: UserStreamTrackerDataSourceType = UserStreamTrackerDataSourceType.EXCHANGE_API,
        bitroyal_auth: Optional[bitroyalAuth] = None,
        symbols: Optional[List[str]] = [],
    ):
        super().__init__(data_source_type=data_source_type)
        self._bitroyal_auth: bitroyalAuth = bitroyal_auth
        self._symbols: List[str] = symbols
        self._ev_loop: asyncio.events.AbstractEventLoop = asyncio.get_event_loop()
        self._data_source: Optional[UserStreamTrackerDataSource] = None
        self._user_stream_tracking_task: Optional[asyncio.Task] = None

    @property
    def data_source(self) -> UserStreamTrackerDataSource:
        if not self._data_source:
            if self._data_source_type is UserStreamTrackerDataSourceType.EXCHANGE_API:
                self._data_source = bitroyalAPIUserStreamDataSource(
                    bitroyal_auth=self._bitroyal_auth, symbols=self._symbols
                )
            else:
                raise ValueError(f"data_source_type {self._data_source_type} is not supported.")
        return self._data_source

    @property
    def exchange_name(self) -> str:
        return "bitroyal"

    async def start(self):
        self._user_stream_tracking_task = asyncio.ensure_future(
            self.data_source.listen_for_user_stream(self._ev_loop, self._user_stream)
        )
        await asyncio.gather(self._user_stream_tracking_task)
