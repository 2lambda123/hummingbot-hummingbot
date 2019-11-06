import asyncio
import aiohttp
import pandas as pd
import mock
from mock import patch
from unittest import TestCase

from test.integration.assets.mock_data.fixture_liquid import FixtureLiquid
from hummingbot.core.data_type.order_book_tracker_entry import OrderBookTrackerEntry
from hummingbot.market.liquid.liquid_api_order_book_data_source import LiquidAPIOrderBookDataSource
from hummingbot.market.liquid.constants import Constants


PATCH_BASE_PATH = \
    'hummingbot.market.liquid.liquid_api_order_book_data_source.LiquidAPIOrderBookDataSource.{method}'


class TestLiquidOrderBookDataSource(TestCase):

    @patch(PATCH_BASE_PATH.format(method='get_exchange_markets_data'))
    def test_get_active_exchange_markets(self, mock_get_exchange_markets_data):
        """
        Test end to end flow from pinging Liquid API for markets and exchange data
        all the way to extract out needed information such as trading_pairs, 
        prices, and volume information.
        """
        loop = asyncio.get_event_loop()

        # Mock Future() object return value as the request response
        f = asyncio.Future()
        f.set_result(FixtureLiquid.EXCHANGE_MARKETS_DATA)
        mock_get_exchange_markets_data.return_value = f

        all_markets_df = loop.run_until_complete(
            LiquidAPIOrderBookDataSource.get_active_exchange_markets())
        # loop.close()

        # Check DF type
        self.assertIsInstance(all_markets_df, pd.DataFrame)

        # Check DF dimension
        self.assertEqual(all_markets_df.shape, (7, 28))  # (num of rows, num of cols)

        # Check DF indices
        self.assertListEqual(
            all_markets_df.index.to_list(),
            [
                'LCXBTC', 'STACETH', 'WLOBTC', 'ETHUSD', 'BTCUSD', 'ETHUSDC', 'BTCUSDC']
        )

        # Check DF column names
        self.assertListEqual(
            sorted(all_markets_df.columns),
            [
                'USDVolume',
                'base_currency',
                'btc_minimum_withdraw',
                'cfd_enabled',
                'code',
                'currency',
                'disabled',
                'fiat_minimum_withdraw',
                'high_market_ask',
                'id',
                'indicator',
                'last_event_timestamp',
                'last_price_24h',
                'last_traded_price',
                'last_traded_quantity',
                'low_market_bid',
                'maker_fee',
                'margin_enabled',
                'market_ask',
                'market_bid',
                'name',
                'product_type',
                'pusher_channel',
                'quoted_currency',
                'symbol',
                'taker_fee',
                'volume',
                'volume_24h'
            ]
        )

        # Check DF values
        self.assertEqual(
            all_markets_df.loc['BTCUSD'].last_traded_price, '7470.49746')

        # Check DF order, make sure it's sorted by USDVolume col in desending order
        usd_volumes = all_markets_df.loc[:, 'USDVolume'].to_list()
        self.assertListEqual(
            usd_volumes,
            sorted(usd_volumes, reverse=True),
            "The output usd volumes should remain the same after being sorted again")

    def test_filter_market_data(self):
        """
        Test the logic to parse out market data from input exchange data,
        and make sure invalid fields and payload are all filtered out in
        this process.
        """
        market_data = LiquidAPIOrderBookDataSource.filter_market_data(
                exchange_markets_data=FixtureLiquid.EXCHANGE_MARKETS_DATA)

        # Check market data type
        self.assertIsInstance(market_data, list)

        # Check market data size
        self.assertEqual(len(market_data), 7)

        # Select and compare the first item with largest id from the list
        self.assertDictEqual(
            sorted(market_data, key=lambda x: x['id'], reverse=True)[0],
            {
                'id': '538',
                'product_type': 'CurrencyPair',
                'code': 'CASH',
                'name': None,
                'market_ask': 5e-08,
                'market_bid': 3e-08,
                'indicator': -1,
                'currency': 'BTC',
                'currency_pair_code': 'LCXBTC',
                'symbol': None,
                'btc_minimum_withdraw': None,
                'fiat_minimum_withdraw': None,
                'pusher_channel': 'product_cash_lcxbtc_538',
                'taker_fee': '0.001',
                'maker_fee': '0.001',
                'low_market_bid': '3.0e-08',
                'high_market_ask': '5.0e-08',
                'volume_24h': '628660.0',
                'last_price_24h': '0.00000003',
                'last_traded_price': '0.00000004',
                'last_traded_quantity': '4867.0',
                'quoted_currency': 'BTC',
                'base_currency': 'LCX',
                'disabled': False,
                'margin_enabled': False,
                'cfd_enabled': False,
                'last_event_timestamp': '1571979656.7983565'
            }
        )
        # Check market data trading pair and their sorting order
        self.assertListEqual(
            [market['currency_pair_code'] for market in market_data],
            ['WLOBTC', 'LCXBTC', 'STACETH', 'BTCUSDC', 'BTCUSD', 'ETHUSDC', 'ETHUSD']
        )

    @patch(PATCH_BASE_PATH.format(method='get_exchange_markets_data'))
    def test_get_trading_pairs(self, mock_get_exchange_markets_data):
        """
        Test the logic where extracts trading pairs as well as the part
        symbol and id mapping is formed
        """
        loop = asyncio.get_event_loop()

        # Mock Future() object return value as the request response
        f = asyncio.Future()
        f.set_result(FixtureLiquid.EXCHANGE_MARKETS_DATA)
        mock_get_exchange_markets_data.return_value = f

        # Instantiate class instance
        liquid_data_source = LiquidAPIOrderBookDataSource()

        trading_pairs = loop.run_until_complete(
            liquid_data_source.get_trading_pairs())

        # Check trading pairs and their order
        self.assertListEqual(
            trading_pairs, ['LCXBTC', 'STACETH', 'WLOBTC', 'ETHUSD', 'BTCUSD', 'ETHUSDC', 'BTCUSDC'])

        # Check derived symbol and id conversion dict keys and their corresponding values
        self.assertDictEqual(
            liquid_data_source.symbol_id_conversion_dict,
            {
                'BTCUSD': '1',
                'BTCUSDC': '443',
                'ETHUSD': '27',
                'ETHUSDC': '444',
                'LCXBTC': '538',
                'STACETH': '206',
                'WLOBTC': '506'
            }
        )

    @patch('aiohttp.ClientResponse.json')
    def test_get_snapshot(self, mock_get):
        """
        To validate the response from aiohttp request contains the same payload
        as the final result
        """
        loop = asyncio.get_event_loop()

        # Mock aiohttp response
        f = asyncio.Future()
        f.set_result(FixtureLiquid.SNAPSHOT_1)
        mock_get.return_value = f

        # Instantiate class instance
        liquid_data_source = LiquidAPIOrderBookDataSource()

        liquid_data_source.symbol_id_conversion_dict = {'BTCETH': 27}

        snapshot = loop.run_until_complete(
            liquid_data_source.get_snapshot(client=aiohttp.ClientSession(), trading_pair='BTCETH', full=1))

        self.assertEqual(list(snapshot.keys()), ['buy_price_levels', 'sell_price_levels'])
        self.assertEqual(len(snapshot['buy_price_levels']), 2)
        self.assertEqual(len(snapshot['sell_price_levels']), 20)
        #TODO: need to test exception handling when inputs are invalid

    @patch(PATCH_BASE_PATH.format(method='get_snapshot'))
    @patch(PATCH_BASE_PATH.format(method='get_trading_pairs'))
    def test_get_tracking_pairs(self, mock_get_trading_pairs, mock_get_snapshot):
        """
        Example output of tracking pairs
        {
            'BTCUSD': OrderBookTrackerEntry(
                symbol = 'BTCUSD',
                timestamp = '1573021425.445617',
                order_book = '<hummingbot.core.data_type.order_book.OrderBook object at 0x11fa72328>'
            ),
            'ETHUSDC': OrderBookTrackerEntry(
                symbol = 'ETHUSDC',
                timestamp = '1573021426.4484851',
                order_book = '<hummingbot.core.data_type.order_book.OrderBook object at 0x11fa723c0>'
            ),
            'BTCUSDC': OrderBookTrackerEntry(
                symbol = 'BTCUSDC',
                timestamp = '1573021427.4509811',
                order_book = '<hummingbot.core.data_type.order_book.OrderBook object at 0x11fa72458>'
            )
        }
        """
        loop = asyncio.get_event_loop()

        # Mock Future() object return value as the request response
        # For this particular test, the return value from get_snapshot is not relevant, therefore
        # setting it with a random snapshot from fixture
        f = asyncio.Future()
        f.set_result(FixtureLiquid.SNAPSHOT_2)
        mock_get_snapshot.return_value = f

        # Mock get trading pairs
        mocked_trading_pairs = ['BTCUSD', 'ETHUSDC', 'BTCUSDC']

        f = asyncio.Future()
        f.set_result(mocked_trading_pairs)
        mock_get_trading_pairs.return_value = f

        # Getting returned tracking pairs
        tracking_pairs = loop.run_until_complete(
            LiquidAPIOrderBookDataSource().get_tracking_pairs())

        # Validate the number of tracking pairs is equal to the number of trading pairs received
        self.assertEqual(len(mocked_trading_pairs), len(tracking_pairs))

        # Make sure the entry key in tracking pairs matches with what's in the trading pairs
        for trading_pair, tracking_pair_obj in zip(mocked_trading_pairs, list(tracking_pairs.keys())):
            self.assertEqual(trading_pair, tracking_pair_obj)

        # Validate the data type for each tracking pair value is OrderBookTrackerEntry
        for order_book_tracker_entry in tracking_pairs.values():
            self.assertIsInstance(order_book_tracker_entry, OrderBookTrackerEntry)

        # Validate the order book tracker entry symbols are valid
        for trading_pair, order_book_tracker_entry in zip(mocked_trading_pairs, tracking_pairs.values()):
            self.assertEqual(order_book_tracker_entry.symbol, trading_pair)
