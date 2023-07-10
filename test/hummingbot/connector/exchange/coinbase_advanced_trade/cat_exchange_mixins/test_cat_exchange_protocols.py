import unittest

from hummingbot.connector.exchange.coinbase_advanced_trade.cat_exchange_mixins.cat_exchange_protocols import (
    _exchange_mixin_protocols,
)
from hummingbot.connector.exchange.coinbase_advanced_trade.coinbase_advanced_trade_exchange import (
    CoinbaseAdvancedTradeExchange,
)


def conforms_to_protocol(obj, protocol):
    for attr in dir(protocol):
        if attr.startswith('__') and attr.endswith('__'):  # Ignore magic methods
            continue
        if attr == "_is_protocol" or attr == "_is_runtime_protocol":  # Ignore _is_protocol attribute
            continue
        if not hasattr(obj, attr):
            print(protocol, attr)
            return False
        if callable(getattr(protocol, attr)) and not callable(getattr(obj, attr)):
            print(protocol, attr)
            return False
    return True


class TestExchangeProtocols(unittest.TestCase):
    def test_conforms_to_protocol(self):
        for p in _exchange_mixin_protocols:
            self.assertTrue(conforms_to_protocol(CoinbaseAdvancedTradeExchange, p))


if __name__ == "__main__":
    unittest.main()
