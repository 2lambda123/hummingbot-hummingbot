import asyncio
import logging
from datetime import datetime
from time import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from bidict import bidict

from hummingbot.core.network_iterator import NetworkStatus, safe_ensure_future
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.data_feed.candles_feed.candles_base import CandlesBase
from hummingbot.data_feed.candles_feed.coinbase_advanced_trade_spot_candles import constants as CONSTANTS
from hummingbot.logger import HummingbotLogger


class CoinbaseAdvancedTradeSpotCandles(CandlesBase):
    _logger: Optional[HummingbotLogger] = None

    class NotEnoughDataAvailableError(Exception):
        pass

    class HistoricalCallOnEmptyCandles(Exception):
        pass

    interval_to_seconds: bidict[str, int] = CONSTANTS.INTERVALS

    @classmethod
    def logger(cls) -> HummingbotLogger | logging.Logger:
        if cls._logger is None:
            cls._logger: HummingbotLogger | logging.Logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, trading_pair: str, interval: str = "ONE_MINUTE", max_records: int = 150):
        super().__init__(trading_pair, interval, max_records)

    @property
    def name(self) -> str:
        """Name of the exchange with candle pair tracked."""
        return f"coinbase_advanced_trade_{self._trading_pair}"

    @property
    def rest_url(self) -> str:
        """REST URL for the exchange."""
        return CONSTANTS.REST_URL

    @property
    def wss_url(self) -> str:
        """Websocket URL for the exchange."""
        return CONSTANTS.WSS_URL

    @property
    def health_check_url(self) -> str:
        """Health check URL for the exchange."""
        return self.rest_url + CONSTANTS.HEALTH_CHECK_ENDPOINT

    @property
    def candles_url(self) -> str:
        """Candles URL for the exchange."""
        return self.rest_url + CONSTANTS.CANDLES_ENDPOINT.format(product_id=self._ex_trading_pair)

    @property
    def rate_limits(self) -> Dict[str, int]:
        """Rate limits for the exchange."""
        return CONSTANTS.RATE_LIMITS

    @property
    def intervals(self) -> Dict[str, int]:
        """Intervals supported by the exchange."""
        return CONSTANTS.INTERVALS

    @property
    def candle_keys_order(self) -> Tuple[str, ...]:
        """Order in which to arrange the REST and WSS candle information keys"""
        return "start", "open", "high", "low", "close", "volume"

    @property
    def candles_df(self) -> pd.DataFrame:
        """Dataframe with the candles' information."""
        df = pd.DataFrame(self._candles, columns=["timestamp"] + list(self.candle_keys_order[1:]), dtype=float)
        df = df.reindex(columns=self.columns, fill_value=0.0)
        df["timestamp"] = df["timestamp"] * 1000
        return df.sort_values(by="timestamp", ascending=True)

    async def check_network(self) -> NetworkStatus:
        """Verifies the exchange status."""
        rest_assistant = await self._api_factory.get_rest_assistant()
        await rest_assistant.execute_request(url=self.health_check_url,
                                             throttler_limit_id=CONSTANTS.HEALTH_CHECK_ENDPOINT)
        return NetworkStatus.CONNECTED

    def get_exchange_trading_pair(self, trading_pair) -> str:
        """Returns the trading pair in the format required by the exchange."""
        return trading_pair.replace("-", "-")

    async def fetch_candles(
            self,
            start_time: int | None = None,
            end_time: int | None = None,
            limit: int | None = 500) -> np.ndarray:
        """
        Fetches candles from the exchange.
        :param start_time: the start time of the candles to be fetched
        :param end_time: the end time of the candles to be fetched
        :param limit: the quantity of candles to be fetched
        :return: a numpy array with the candles
        https://docs.cloud.coinbase.com/advanced-trade-api/reference/retailbrokerageapi_getcandles
        """
        rest_assistant = await self._api_factory.get_rest_assistant()
        params = {"granularity": self.interval,
                  "start": str(start_time) or str(int(datetime(2023, 1, 1).timestamp())),
                  "end": str(end_time) or str(time())}
        data = await rest_assistant.execute_request(
            url=self.candles_url,
            throttler_limit_id=CONSTANTS.CANDLES_ENDPOINT_ID,
            params=params)

        return np.array(
            [
                [float(candle[key]) for key in self.candle_keys_order]
                for candle in data["candles"]
            ]
        )

    async def fill_historical_candles(self) -> None:
        """
        Fills the historical candles deque with the candles fetched from the exchange.
        Ideally, one request should provide the number of candles needed to fill the deque.
        """
        while not self.is_ready:
            if len(self._candles) == 0:
                self.logger().error(
                    "fill_historical_candles() was called on an empty candles deque."
                )
                raise CoinbaseAdvancedTradeSpotCandles.HistoricalCallOnEmptyCandles

            end_timestamp: int = int(self._candles[0][0])
            interval_s: float = self.get_seconds_from_interval(self.interval)
            # Estimated start_time to gather maxlen candles given the current interval
            start_time: int = end_timestamp - int(self._candles.maxlen * interval_s)

            try:
                candles = await self.fetch_candles(
                    end_time=end_timestamp,
                    start_time=start_time)

                if len(candles) == 0:
                    # No candles were fetched (Coinbase Advanced Trade may only have 9 days of candles)
                    raise CoinbaseAdvancedTradeSpotCandles.NotEnoughDataAvailableError
            except asyncio.CancelledError:
                raise
            except (CoinbaseAdvancedTradeSpotCandles.NotEnoughDataAvailableError,
                    StopAsyncIteration):
                self.logger().error("There is not enough data available to fill historical"
                                    f" candles for {self.name}. Relying upon websocket feed")
                break
            except Exception as e:
                self.logger().exception(
                    f"Unexpected error occurred when getting historical candles {e}. Retrying in 1 seconds...",
                )
                await self._sleep(1.0)
                continue

            # Sort in reversed order to fill the deque from the oldest to the newest candle
            sorted_indices = candles[:, 0].argsort()[::-1]
            candles = candles[sorted_indices]

            # Verify that we don't override the last candle fetched with websocket (initial value)
            if candles[0][0] == end_timestamp:
                candles = candles[1:]

            # we are computing again the quantity of records again since the websocket process is able to
            # modify the deque and if we extend it, the new observations are going to be dropped.
            missing_records = self._candles.maxlen - len(self._candles)
            if missing_records > len(candles):
                # Not enough candles were fetched to fill the deque, possibly the end time did not match well
                self.logger().debug(f"Missing {missing_records - len(candles)} candles to fill the deque. Attempting "
                                    "to fetch more.")
                self._candles.extendleft(candles)
            else:
                # Enough or too many candles were fetched to fill the deque
                self._candles.extendleft(candles[:missing_records])

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the candles events through the provided websocket connection.
        :param ws: the websocket assistant used to connect to the exchange
        """
        try:
            payload = {
                "type": "subscribe",
                "product_ids": [self._ex_trading_pair],
                "channel": "candles",
            }
            subscribe_candles_request: WSJSONRequest = WSJSONRequest(payload=payload)

            await ws.send(subscribe_candles_request)
            self.logger().info("Subscribed to public candles...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to public candles...",
                exc_info=True
            )
            raise

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant):
        async for ws_response in websocket_assistant.iter_messages():
            data: Dict[str, Any] = ws_response.data
            if data is not None and data.get("channel") == "candles":
                for event in data["events"]:
                    for candle in event["candles"]:
                        candle = np.array([float(candle[key]) for key in self.candle_keys_order])

                        if len(self._candles) == 0:
                            self._candles.append(candle)
                            safe_ensure_future(self.fill_historical_candles())

                        elif candle[0] > int(self._candles[-1][0]):
                            # TODO: validate also that the diff of timestamp == interval (issue with 1M interval).
                            self._candles.append(candle)

                        elif candle[0] == int(self._candles[-1][0]):
                            self._candles.pop()
                            self._candles.append(candle)
