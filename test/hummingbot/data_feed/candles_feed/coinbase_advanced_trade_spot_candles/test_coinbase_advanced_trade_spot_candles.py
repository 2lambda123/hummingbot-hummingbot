import asyncio
import json
import re
from collections import deque
from test.isolated_asyncio_wrapper_test_case import IsolatedAsyncioWrapperTestCase
from test.logger_mixin_for_test import LoggerMixinForTest
from unittest.mock import AsyncMock, MagicMock, call, patch

import numpy as np
from aioresponses import aioresponses

from hummingbot.connector.test_support.network_mocking_assistant import NetworkMockingAssistant
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.data_feed.candles_feed.coinbase_advanced_trade_spot_candles import (
    CoinbaseAdvancedTradeSpotCandles,
    constants as CONSTANTS,
)


class TestCoinbaseAdvancedTradeSpotCandles(IsolatedAsyncioWrapperTestCase, LoggerMixinForTest):
    trading_pair = None
    quote_asset = "USDT"
    base_asset = "BTC"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()
        cls.interval = "ONE_MINUTE"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = cls.trading_pair

    def setUp(self) -> None:
        super().setUp()
        self.mocking_assistant = NetworkMockingAssistant()
        self.data_feed = CoinbaseAdvancedTradeSpotCandles(trading_pair=self.trading_pair, interval=self.interval)

        self.set_loggers([self.data_feed.logger()])
        self.resume_test_event = asyncio.Event()

    def get_candles_rest_data_mock(self):
        data = {
            "candles": [
                {
                    "start": "150",
                    "low": "140.21",
                    "high": "140.21",
                    "open": "140.21",
                    "close": "140.21",
                    "volume": "06437345"
                },
                {
                    "start": "170",
                    "low": "141.21",
                    "high": "141.21",
                    "open": "141.21",
                    "close": "141.21",
                    "volume": "16437345"
                },
                {
                    "start": "190",
                    "low": "142.21",
                    "high": "142.21",
                    "open": "142.21",
                    "close": "142.21",
                    "volume": "26437345"
                },
            ]
        }
        return data

    def get_candles_ws_data_mock_1(self):
        data = {
            "channel": "candles",
            "client_id": "",
            "timestamp": "2023-06-09T20:19:35.39625135Z",
            "sequence_num": 0,
            "events": [
                {
                    "type": "snapshot",
                    "candles": [
                        {
                            "start": "200",
                            "high": "1867.72",
                            "low": "1865.63",
                            "open": "1867.38",
                            "close": "1866.81",
                            "volume": "0.20269406",
                            "product_id": "ETH-USD",
                        },
                        {
                            "start": "260",
                            "high": "1867.72",
                            "low": "1865.63",
                            "open": "1867.38",
                            "close": "1866.81",
                            "volume": "0.20269406",
                            "product_id": "ETH-USD",
                        }
                    ]
                }
            ]
        }
        return data

    def get_candles_ws_data_mock_2(self):
        data = {
            "channel": "candles",
            "client_id": "",
            "timestamp": "2023-06-09T20:19:35.39625135Z",
            "sequence_num": 0,
            "events": [
                {
                    "type": "snapshot",
                    "candles": [
                        {
                            "start": "260",
                            "high": "2000.72",
                            "low": "1865.63",
                            "open": "1867.38",
                            "close": "1866.81",
                            "volume": "0.20269406",
                            "product_id": "ETH-USD",
                        },
                        {
                            "start": "320",
                            "high": "1867.72",
                            "low": "1865.63",
                            "open": "1867.38",
                            "close": "1866.81",
                            "volume": "0.20269406",
                            "product_id": "ETH-USD",
                        }
                    ]
                }
            ]
        }
        return data

    def assertDequeEqual(self, deque1, deque2):
        self.assertEqual(len(deque1), len(deque2))
        self.assertEqual(deque1.maxlen, deque2.maxlen)

        for arr1, arr2 in zip(deque1, deque2):
            np.testing.assert_array_equal(arr1, arr2)

    def test_properties(self):
        self.assertEqual(self.data_feed.rest_url, CONSTANTS.REST_URL)
        self.assertEqual(self.data_feed.wss_url, CONSTANTS.WSS_URL)
        self.assertEqual(self.data_feed.health_check_url, self.data_feed.rest_url + CONSTANTS.HEALTH_CHECK_ENDPOINT)
        self.assertEqual(self.data_feed.candles_url,
                         self.data_feed.rest_url + CONSTANTS.CANDLES_ENDPOINT.format(product_id=self.ex_trading_pair))
        self.assertEqual(self.data_feed.rate_limits, CONSTANTS.RATE_LIMITS)
        self.assertEqual(self.data_feed.intervals, CONSTANTS.INTERVALS)
        self.assertEqual(self.data_feed.candle_keys_order, ("start", "open", "high", "low", "close", "volume"))

    def test_intervals(self):
        self.assertEqual("ONE_MINUTE", self.data_feed.intervals["1m"])
        self.assertEqual(60, self.data_feed.intervals["ONE_MINUTE"])
        self.assertEqual(60, self.data_feed.intervals[self.data_feed.intervals["1m"]])

    def test_get_exchange_trading_pair(self):
        self.assertEqual(self.data_feed.get_exchange_trading_pair("BTC-USDT"), "BTC-USDT")

    @patch.object(CoinbaseAdvancedTradeSpotCandles, "fetch_candles")
    async def test_fill_historical_sufficient_candles(self, mock_fetch_candles):
        self.interval = "ONE_MINUTE"
        mock_fetch_candles.return_value = np.array(
            [
                [(1697498000 + 0), 1, 1, 1, 1, 1],
                [(1697498000 + 60), 2, 2, 2, 2, 2],
                [(1697498000 + 120), 3, 3, 3, 3, 3]
            ])
        self.data_feed._candles = deque(
            np.array([[(1697498000 + 180), 4, 4, 4, 4, 4]]),
            maxlen=3
        )

        await self.data_feed.fill_historical_candles()
        mock_fetch_candles.assert_called_once()
        self.assertEqual(3, self.data_feed.candles_df.shape[0])
        self.assertEqual(10, self.data_feed.candles_df.shape[1])
        self.assertDequeEqual(deque(
            np.array([
                [(1697498000 + 60), 2, 2, 2, 2, 2],
                [(1697498000 + 120), 3, 3, 3, 3, 3],
                [(1697498000 + 180), 4, 4, 4, 4, 4],
            ]),
            maxlen=3
        ), self.data_feed._candles)

    @patch.object(CoinbaseAdvancedTradeSpotCandles, "fetch_candles")
    async def test_fill_historical_insufficient_candles(self, mock_fetch_candles):
        self.interval = "ONE_MINUTE"
        mock_fetch_candles.side_effect = [
            np.array([
                [(1697498000 + 0), 1, 1, 1, 1, 1],
                [(1697498000 + 60), 2, 2, 2, 2, 2],
                [(1697498000 + 120), 3, 3, 3, 3, 3],
                [(1697498000 + 180), 4, 4, 4, 4, 4],
                [(1697498000 + 240), 5, 5, 5, 5, 5],
                [(1697498000 + 300), 5, 5, 5, 5, 5]  # This should not be in the final deque
            ]),
            np.array([])]
        self.data_feed._candles = deque(
            np.array([[(1697498000 + 300), 6, 6, 6, 6, 6]]),
            maxlen=9
        )

        await self.data_feed.fill_historical_candles()

        mock_fetch_candles.assert_has_calls([
            call(end_time=1697498300, start_time=1697497760),  # 8 intervals: 8 * 60 = 480 seconds -> 1697497760
            call(end_time=1697498000, start_time=1697497460)])  # Verifying that the start_time is not too short
        self.assertEqual(6, self.data_feed.candles_df.shape[0])
        self.assertEqual(10, self.data_feed.candles_df.shape[1])
        self.assertDequeEqual(deque(
            np.array([
                [(1697498000 + 0), 1, 1, 1, 1, 1],
                [(1697498000 + 60), 2, 2, 2, 2, 2],
                [(1697498000 + 120), 3, 3, 3, 3, 3],
                [(1697498000 + 180), 4, 4, 4, 4, 4],
                [(1697498000 + 240), 5, 5, 5, 5, 5],
                [(1697498000 + 300), 6, 6, 6, 6, 6],
            ]),
            maxlen=9
        ), self.data_feed._candles)

    @patch.object(CoinbaseAdvancedTradeSpotCandles, "fetch_candles", new_callable=AsyncMock)
    async def test_fill_historical_candles_empty_candles(self, mock_fetch_candles):
        with self.assertRaises(CoinbaseAdvancedTradeSpotCandles.HistoricalCallOnEmptyCandles):
            await self.data_feed.fill_historical_candles()

    @patch.object(CoinbaseAdvancedTradeSpotCandles, "fetch_candles", new_callable=AsyncMock)
    async def test_fill_historical_candles_empty_data(self, mock_fetch_candles):
        # Mock to return an empty array
        self.data_feed._candles = deque(np.array([[1, 2, 3, 4, 5, 6]]), maxlen=2)
        mock_fetch_candles.return_value = np.array([])

        await self.data_feed.fill_historical_candles()
        self.assertTrue(self.is_partially_logged("ERROR", "There is not enough data available to fill historical candles for "))

    @patch.object(CoinbaseAdvancedTradeSpotCandles, "_sleep", new_callable=AsyncMock)
    @patch.object(CoinbaseAdvancedTradeSpotCandles, "fetch_candles", new_callable=AsyncMock)
    async def test_fill_historical_candles_unexpected_exception(self, mock_fetch_candles, mock_sleep):
        # Mock to raise an unexpected exception
        self.data_feed._candles = deque(np.array([[1, 2, 3, 4, 5, 6]]), maxlen=2)
        mock_fetch_candles.side_effect = [Exception("Something went wrong")]

        await self.data_feed.fill_historical_candles()

        # Verify that sleep was called, implying a retry attempt
        mock_sleep.assert_called_once_with(1.0)
        self.assertTrue(self.is_partially_logged(
            "ERROR",
            "Unexpected error occurred when getting historical candles Something went wrong"))

    @aioresponses()
    async def test_fetch_candles(self, mock_api: aioresponses):
        start_time = 1
        end_time = 1639508050 + 60 * 60 * 24 * 7
        url = (f"{CONSTANTS.REST_URL}{CONSTANTS.CANDLES_ENDPOINT.format(product_id=self.ex_trading_pair)}?"
               f"end={end_time}&granularity=ONE_MINUTE&start={start_time}")
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        data_mock = self.get_candles_rest_data_mock()
        mock_api.get(url=regex_url, body=json.dumps(data_mock))

        resp = await self.data_feed.fetch_candles(start_time=start_time, end_time=end_time)

        self.assertEqual(resp.shape[1], 6)
        self.assertEqual(resp.shape[0], len(data_mock.get("candles")))

    def test_candles_empty(self):
        self.assertTrue(self.data_feed.candles_df.empty)

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    async def test_listen_for_subscriptions_subscribes_to_candles(self, ws_connect_mock):
        ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()

        result_subscribe_klines = {
            "result": None,
            "id": 1
        }

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(result_subscribe_klines))

        self.listening_task = asyncio.create_task(self.data_feed.listen_for_subscriptions())

        # Man, this thing is annoying!
        # self.mocking_assistant.run_until_all_aiohttp_messages_delivered(ws_connect_mock.return_value)
        all_delivered = self.mocking_assistant._all_incoming_websocket_aiohttp_delivered_event[
            ws_connect_mock.return_value]
        await asyncio.wait_for(all_delivered.wait(), 1)

        sent_subscription_messages = self.mocking_assistant.json_messages_sent_through_websocket(
            websocket_mock=ws_connect_mock.return_value)

        self.assertEqual(1, len(sent_subscription_messages))
        expected_kline_subscription = {
            "type": "subscribe",
            "product_ids": [f"{self.ex_trading_pair}"],
            "channel": "candles"}

        self.assertEqual(expected_kline_subscription, sent_subscription_messages[0])

        self.assertTrue(self.is_logged(
            "INFO",
            "Subscribed to public candles..."),
            self.log_records
        )

    @patch(
        "hummingbot.data_feed.candles_feed.coinbase_advanced_trade_spot_candles.CoinbaseAdvancedTradeSpotCandles._sleep")
    @patch("aiohttp.ClientSession.ws_connect")
    async def test_listen_for_subscriptions_raises_cancel_exception(self, mock_ws, _: AsyncMock):
        mock_ws.side_effect = asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = asyncio.create_task(self.data_feed.listen_for_subscriptions())
            await asyncio.wait_for(self.listening_task, 1)

    @patch("hummingbot.data_feed.candles_feed.coinbase_advanced_trade_spot_candles.CoinbaseAdvancedTradeSpotCandles"
           "._sleep")
    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    async def test_listen_for_subscriptions_logs_exception_details(self, mock_ws, sleep_mock: AsyncMock):
        mock_ws.side_effect = Exception("TEST ERROR.")
        sleep_mock.side_effect = lambda _: self._create_exception_and_unlock_test_with_event(
            asyncio.CancelledError())

        self.listening_task = asyncio.create_task(self.data_feed.listen_for_subscriptions())

        await self.resume_test_event.wait()

        self.assertTrue(
            self.is_logged(
                "ERROR",
                "Unexpected error occurred when listening to public klines. Retrying in 1 seconds..."),
            self.log_records
        )

    async def test_subscribe_channels_raises_cancel_exception(self):
        mock_ws = MagicMock()
        mock_ws.send.side_effect = asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = asyncio.create_task(self.data_feed._subscribe_channels(mock_ws))
            await asyncio.wait_for(self.listening_task, 1)

    async def test_subscribe_channels_raises_exception_and_logs_error(self):
        mock_ws = MagicMock()
        mock_ws.send.side_effect = Exception("Test Error")

        with self.assertRaises(Exception):
            self.listening_task = asyncio.create_task(self.data_feed._subscribe_channels(mock_ws))
            await asyncio.wait_for(self.listening_task, 1)

        self.assertTrue(
            self.is_logged("ERROR", "Unexpected error occurred subscribing to public candles..."),
            self.log_records
        )

    @patch("hummingbot.data_feed.candles_feed.coinbase_advanced_trade_spot_candles.CoinbaseAdvancedTradeSpotCandles"
           ".fill_historical_candles",
           new_callable=AsyncMock)
    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    async def test_process_websocket_messages_empty_candle(self, ws_connect_mock, fill_historical_candles_mock):
        ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(self.get_candles_ws_data_mock_1()))

        self.listening_task = asyncio.create_task(self.data_feed.listen_for_subscriptions())

        all_delivered = self.mocking_assistant._all_incoming_websocket_aiohttp_delivered_event[
            ws_connect_mock.return_value]
        await asyncio.wait_for(all_delivered.wait(), 1)

        self.assertEqual(self.data_feed.candles_df.shape[0], 2)
        self.assertEqual(self.data_feed.candles_df.shape[1], 10)
        fill_historical_candles_mock.assert_called_once()

    @patch("hummingbot.data_feed.candles_feed.coinbase_advanced_trade_spot_candles.CoinbaseAdvancedTradeSpotCandles"
           ".fill_historical_candles",
           new_callable=AsyncMock)
    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    async def test_process_websocket_messages_duplicated_candle_not_included(self, ws_connect_mock,
                                                                             fill_historical_candles):
        ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()
        fill_historical_candles.return_value = None

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(self.get_candles_ws_data_mock_1()))

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(self.get_candles_ws_data_mock_1()))

        self.listening_task = asyncio.create_task(self.data_feed.listen_for_subscriptions())

        all_delivered = self.mocking_assistant._all_incoming_websocket_aiohttp_delivered_event[
            ws_connect_mock.return_value]
        await asyncio.wait_for(all_delivered.wait(), 2)

        self.assertEqual(self.data_feed.candles_df.shape[0], 2)
        self.assertEqual(self.data_feed.candles_df.shape[1], 10)

    @patch("hummingbot.data_feed.candles_feed.coinbase_advanced_trade_spot_candles.CoinbaseAdvancedTradeSpotCandles"
           ".fill_historical_candles")
    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    async def test_process_websocket_messages_with_two_valid_messages(self, ws_connect_mock, _):
        ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(self.get_candles_ws_data_mock_1()))

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(self.get_candles_ws_data_mock_2()))

        self.listening_task = asyncio.create_task(self.data_feed.listen_for_subscriptions())

        # self.mocking_assistant.run_until_all_aiohttp_messages_delivered(ws_connect_mock.return_value, timeout=2)
        all_delivered = self.mocking_assistant._all_incoming_websocket_aiohttp_delivered_event[
            ws_connect_mock.return_value]
        await asyncio.wait_for(all_delivered.wait(), 2)

        self.assertEqual(self.data_feed.candles_df.shape[0], 3, self.data_feed.candles_df.shape)
        self.assertEqual(self.data_feed.candles_df.shape[1], 10)

    def _create_exception_and_unlock_test_with_event(self, exception):
        self.resume_test_event.set()
        raise exception

    @patch.object(WebAssistantsFactory, "get_rest_assistant")
    async def test_check_network(self, mock_api_factory):
        mock_api_factory.return_value.execute_request = AsyncMock()
        result = await self.data_feed.check_network()
        mock_api_factory.return_value.execute_request.assert_called_once()
        mock_api_factory.return_value.execute_request.assert_called_once_with(
            url=self.data_feed.health_check_url,
            throttler_limit_id=CONSTANTS.HEALTH_CHECK_ENDPOINT
        )
        self.assertEqual(result, NetworkStatus.CONNECTED)
