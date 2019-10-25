class FixtureLiquid:
    """
    FixtureLiquid helps to store metadata that can be used to mimic
    API response payload returned from pinging Liquid API.

    The purpose of explcitly displaying fixtures:
    1. Make adhoc unittest mocking eaiser.
    2. Serve as a reference for future lookup the data structure passing among stages.
    """

    EXCHANGE_MARKETS_DATA = [
        {
            'id': '418',
            'product_type': 'CurrencyPair',
            'code': 'CASH',
            'name': None,
            'market_ask': None,
            'market_bid': None,
            'indicator': None,
            'currency': 'QASH',
            'currency_pair_code': 'MITHQASH',
            'symbol': 'MITH',
            'btc_minimum_withdraw': None,
            'fiat_minimum_withdraw': None,
            'pusher_channel': 'product_cash_mithqash_418',
            'taker_fee': '0.001',
            'maker_fee': '0.001',
            'low_market_bid': '0.0',
            'high_market_ask': '0.0',
            'volume_24h': '0.0',
            'last_price_24h': None,
            'last_traded_price': None,
            'last_traded_quantity': None,
            'quoted_currency': 'QASH',
            'base_currency': 'MITH',
            'disabled': True,
            'margin_enabled': False,
            'cfd_enabled': False,
            'last_event_timestamp': None
        }, {
            'id': '506',
            'product_type': 'CurrencyPair',
            'code': 'CASH',
            'name': None,
            'market_ask': 1.15e-06,
            'market_bid': 1.12e-06,
            'indicator': 1,
            'currency': 'BTC',
            'currency_pair_code': 'WLOBTC',
            'symbol': None,
            'btc_minimum_withdraw': None,
            'fiat_minimum_withdraw': None,
            'pusher_channel': 'product_cash_wlobtc_506',
            'taker_fee': '0.001',
            'maker_fee': '0.001',
            'low_market_bid': '0.00000105',
            'high_market_ask': '0.00000132',
            'volume_24h': '3147.2676282',
            'last_price_24h': '0.00000114',
            'last_traded_price': '0.00000113',
            'last_traded_quantity': '915.9778978',
            'quoted_currency': 'BTC',
            'base_currency': 'WLO',
            'disabled': False,
            'margin_enabled': False,
            'cfd_enabled': False,
            'last_event_timestamp': '1571981938.3873937'
        }, {
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
        }, {
            'id': '206',
            'product_type': 'CurrencyPair',
            'code': 'CASH',
            'name': None,
            'market_ask': 4.3e-07,
            'market_bid': 4.1e-07,
            'indicator': -1,
            'currency': 'ETH',
            'currency_pair_code': 'STACETH',
            'symbol': 'STAC',
            'btc_minimum_withdraw': None,
            'fiat_minimum_withdraw': None,
            'pusher_channel': 'product_cash_staceth_206',
            'taker_fee': '0.001',
            'maker_fee': '0.001',
            'low_market_bid': '0.00000034',
            'high_market_ask': '0.00000046',
            'volume_24h': '2092391.82350436',
            'last_price_24h': '0.00000043',
            'last_traded_price': '0.00000042',
            'last_traded_quantity': '7183.5833',
            'quoted_currency': 'ETH',
            'base_currency': 'STAC',
            'disabled': False,
            'margin_enabled': False,
            'cfd_enabled': False,
            'last_event_timestamp': '1571981852.7042925'
        }, {
            'id': '443',
            'product_type': 'CurrencyPair',
            'code': 'CASH',
            'name': None,
            'market_ask': 7491.83,
            'market_bid': 7448.43061967,
            'indicator': 1,
            'currency': 'USDC',
            'currency_pair_code': 'BTCUSDC',
            'symbol': None,
            'btc_minimum_withdraw': None,
            'fiat_minimum_withdraw': None,
            'pusher_channel': 'product_cash_btcusdc_443',
            'taker_fee': '0.001',
            'maker_fee': '0.001',
            'low_market_bid': '7357.91403631',
            'high_market_ask': '7550.41866211',
            'volume_24h': '0.177332',
            'last_price_24h': '7443.88002595',
            'last_traded_price': '7455.83',
            'last_traded_quantity': '0.038666',
            'quoted_currency': 'USDC',
            'base_currency': 'BTC',
            'disabled': False,
            'margin_enabled': False,
            'cfd_enabled': False,
            'last_event_timestamp': '1571995384.0727158'
        }, {
            'id': '1',
            'product_type': 'CurrencyPair',
            'code': 'CASH',
            'name': ' CASH Trading',
            'market_ask': 7479.253,
            'market_bid': 7473.12828,
            'indicator': 1,
            'currency': 'USD',
            'currency_pair_code': 'BTCUSD',
            'symbol': '$',
            'btc_minimum_withdraw': None,
            'fiat_minimum_withdraw': None,
            'pusher_channel': 'product_cash_btcusd_1',
            'taker_fee': '0.001',
            'maker_fee': '0.001',
            'low_market_bid': '7393.21607',
            'high_market_ask': '7523.722',
            'volume_24h': '356.45875936',
            'last_price_24h': '7468.53554',
            'last_traded_price': '7470.49746',
            'last_traded_quantity': '0.002',
            'quoted_currency': 'USD',
            'base_currency': 'BTC',
            'disabled': False,
            'margin_enabled': True,
            'cfd_enabled': True,
            'last_event_timestamp': '1571995384.0727158'
        }, {
            'id': '444',
            'product_type': 'CurrencyPair',
            'code': 'CASH',
            'name': None,
            'market_ask': 163.41541555,
            'market_bid': 162.14389286,
            'indicator': 1,
            'currency': 'USDC',
            'currency_pair_code': 'ETHUSDC',
            'symbol': None,
            'btc_minimum_withdraw': None,
            'fiat_minimum_withdraw': None,
            'pusher_channel': 'product_cash_ethusdc_444',
            'taker_fee': '0.001',
            'maker_fee': '0.001',
            'low_market_bid': '158.65627936',
            'high_market_ask': '165.33195762',
            'volume_24h': '5.10523492',
            'last_price_24h': '160.94835717',
            'last_traded_price': '162.27969704',
            'last_traded_quantity': '2.53608974',
            'quoted_currency': 'USDC',
            'base_currency': 'ETH',
            'disabled': False,
            'margin_enabled': False,
            'cfd_enabled': False,
            'last_event_timestamp': '1571995382.111739'
        }, {
            'id': '27',
            'product_type': 'CurrencyPair',
            'code': 'CASH',
            'name': ' CASH Trading',
            'market_ask': 162.88941,
            'market_bid': 162.70211,
            'indicator': 1,
            'currency': 'USD',
            'currency_pair_code': 'ETHUSD',
            'symbol': '$',
            'btc_minimum_withdraw': None,
            'fiat_minimum_withdraw': None,
            'pusher_channel': 'product_cash_ethusd_27',
            'taker_fee': '0.001',
            'maker_fee': '0.001',
            'low_market_bid': '159.8',
            'high_market_ask': '163.991',
            'volume_24h': '577.3217041',
            'last_price_24h': '161.63163',
            'last_traded_price': '162.572',
            'last_traded_quantity': '4.0',
            'quoted_currency': 'USD',
            'base_currency': 'ETH',
            'disabled': False,
            'margin_enabled': True,
            'cfd_enabled': False,
            'last_event_timestamp': '1571995382.9368947'
        }
    ]
