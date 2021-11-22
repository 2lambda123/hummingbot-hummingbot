#!/usr/bin/env python
import time
import asyncio
import logging
import websockets
import ujson
from typing import Optional, List, AsyncIterable, Any
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger
from hummingbot.connector.exchange.southxchange.southxchange_auth import SouthXchangeAuth
from hummingbot.connector.exchange.southxchange.southxchange_constants import PRIVATE_WS_URL, PONG_PAYLOAD
from hummingbot.connector.exchange.southxchange.southxchange_utils import get_market_id
from hummingbot.connector.exchange.southxchange.southxchange_utils import SouthXchangeAPIRequest


class SouthxchangeAPIUserStreamDataSource(UserStreamTrackerDataSource):
    MAX_RETRIES = 20
    MESSAGE_TIMEOUT = 10.0
    PING_TIMEOUT = 5.0

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, southxchange_auth: SouthXchangeAuth, southxchange_api_request: SouthXchangeAPIRequest, trading_pairs: Optional[List[str]] = []):
        self._southxchange__auth: SouthXchangeAuth = southxchange_auth
        self._trading_pairs = trading_pairs
        self._current_listen_key = None
        self._listen_for_user_stream_task = None
        self._last_recv_time: float = 0
        self._ws_client: websockets.WebSocketClientProtocol = None
        self._idMarket = get_market_id(trading_pairs=trading_pairs)
        self._southxchange_api_request: SouthXchangeAPIRequest = southxchange_api_request
        super().__init__()

    @property
    def last_recv_time(self) -> float:
        return self._last_recv_time

    async def listen_for_user_stream(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue) -> AsyncIterable[Any]:
        """
        *required
        Subscribe to user stream via web socket, and keep the connection open for incoming messages
        :param ev_loop: ev_loop to execute this function in
        :param output: an async queue where the incoming messages are stored
        """
        while True:
            # _southxchange_api_request = SouthXchangeAPIRequest(self._southxchange__auth.api_key, self._southxchange__auth.secret_key)
            # loop = asyncio.get_event_loop()
            tokenWS = await self._southxchange_api_request.get_websoxket_token()
            # loop.close()
            # tokenWS = self._southxchange__auth.get_websoxket_token()
            try:
                payload = {
                    "k": "subscribe",
                    "v": self._idMarket
                }
                async with websockets.connect(PRIVATE_WS_URL.format(access_token=tokenWS)) as ws:
                    try:
                        ws: websockets.WebSocketClientProtocol = ws
                        await ws.send(ujson.dumps(payload))

                        async for raw_msg in self._inner_messages(ws):
                            try:
                                msg = ujson.loads(raw_msg)
                                if msg is None:
                                    continue
                                output.put_nowait(msg)
                            except Exception:
                                self.logger().error(
                                    "Unexpected error when parsing SouthXchange message. ", exc_info=True
                                )
                                raise
                    except Exception:
                        self.logger().error(
                            "Unexpected error while listening to SouthXchange messages. ", exc_info=True
                        )
                        raise
                    finally:
                        await ws.close()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error with SouthXchange WebSocket connection. " "Retrying after 30 seconds...", exc_info=True
                )
                await asyncio.sleep(60.0)

    async def _inner_messages(
        self,
        ws: websockets.WebSocketClientProtocol
    ) -> AsyncIterable[str]:
        # Terminate the recv() loop as soon as the next message timed out, so the outer loop can reconnect.
        try:
            while True:
                try:
                    raw_msg: str = await asyncio.wait_for(ws.recv(), timeout=self.MESSAGE_TIMEOUT)
                    self._last_recv_time = time.time()
                    yield raw_msg
                except asyncio.TimeoutError:
                    try:
                        pong_waiter = ws.send(ujson.dumps(PONG_PAYLOAD))
                        await asyncio.wait_for(pong_waiter, timeout=self.PING_TIMEOUT)
                        self._last_recv_time = time.time()
                    except asyncio.TimeoutError:
                        raise
        except asyncio.TimeoutError:
            self.logger().warning("WebSocket ping timed out. Going to reconnect...")
            return
        except websockets.ConnectionClosed:
            return
        finally:
            await ws.close()
