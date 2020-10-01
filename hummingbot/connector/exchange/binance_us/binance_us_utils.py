import re
from typing import (
    Optional,
    Tuple)

from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.config.config_methods import using_exchange


CENTRALIZED = True


EXAMPLE_PAIR = "ZRX-ETH"


DEFAULT_FEES = [0.1, 0.1]


TRADING_PAIR_SPLITTER = re.compile(r"^(\w+)(BTC|ETH|BNB|DAI|XRP|USD|USDT|USDC|USDS|TUSD|PAX|TRX|BUSD|NGN|RUB|TRY|EUR|IDRT|ZAR|UAH|GBP|BKRW|BIDR)$")


def split_trading_pair(trading_pair: str) -> Optional[Tuple[str, str]]:
    try:
        m = TRADING_PAIR_SPLITTER.match(trading_pair)
        return m.group(1), m.group(2)
    # Exceptions are now logged as warnings in trading pair fetcher
    except Exception:
        return None


def convert_from_exchange_trading_pair(exchange_trading_pair: str) -> Optional[str]:
    if split_trading_pair(exchange_trading_pair) is None:
        return None
    # Binance.US does not split BASEQUOTE (BTCUSDT)
    base_asset, quote_asset = split_trading_pair(exchange_trading_pair)
    return f"{base_asset}-{quote_asset}"


def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
    # Binance.US does not split BASEQUOTE (BTCUSDT)
    return hb_trading_pair.replace("-", "")


KEYS = {
    "binance_us_api_key":
        ConfigVar(key="binance_us_api_key",
                  prompt="Enter your Binance.US API key >>> ",
                  required_if=using_exchange("binance_us"),
                  is_secure=True,
                  is_connect_key=True),
    "binance_us_api_secret":
        ConfigVar(key="binance_us_api_secret",
                  prompt="Enter your Binance.US API secret >>> ",
                  required_if=using_exchange("binance_us"),
                  is_secure=True,
                  is_connect_key=True),
}
