from enum import Enum
from typing import Tuple

from bidict import bidict

from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

DEFAULT_DOMAIN = "com"

HBOT_ORDER_ID_PREFIX = "CBAT-"
MAX_ORDER_ID_LEN = 32
HBOT_BROKER_ID = "Hummingbot"

# Base URL
SIGNIN_URL = "https://api.coinbase.{domain}/v2"
REST_URL = "https://api.coinbase.{domain}/api/v3"
WSS_URL = "wss://advanced-trade-ws.coinbase.{domain}/"

# Coinbase Signin API endpoints
SERVER_TIME_EP = "/time"
EXCHANGE_RATES_USD_EP = "/exchange-rates"
EXCHANGE_RATES_QUOTE_EP = "/exchange-rates?currency={quote_token}"
CURRENCIES_EP = "/currencies"
CRYPTO_CURRENCIES_EP = "/currencies/crypto"

SIGIN_URL_ENDPOINTS = {
    SERVER_TIME_EP,
    EXCHANGE_RATES_USD_EP,
    EXCHANGE_RATES_QUOTE_EP,
    CURRENCIES_EP,
}

# Public API endpoints or CoinbaseAdvancedTradeClient function
# Product/pair required
ALL_PAIRS_EP = "/brokerage/products"
PAIR_TICKER_EP = "/brokerage/products/{product_id}"
PAIR_TICKER_24HR_EP = "/brokerage/products/{product_id}/ticker"

# Private API endpoints or CoinbaseAdvancedTradeClient function
ORDER_EP = "/brokerage/orders"
BATCH_CANCEL_EP = "/brokerage/orders/batch_cancel"
GET_ORDER_STATUS_EP = "/brokerage/orders/historical/{order_id}"
GET_STATUS_BATCH_EP = "/brokerage/orders/historical/batch"
FILLS_EP = "/brokerage/orders/historical/fills"
TRANSACTIONS_SUMMARY_EP = "/brokerage/transaction_summary"
ACCOUNTS_LIST_EP = "/brokerage/accounts"
ACCOUNT_EP = "/brokerage/accounts/{account_uuid}"

REST_URL_ENDPOINTS = {
    ALL_PAIRS_EP,
    PAIR_TICKER_EP,
    PAIR_TICKER_24HR_EP,
    ORDER_EP,
    BATCH_CANCEL_EP,
    GET_ORDER_STATUS_EP,
    GET_STATUS_BATCH_EP,
    TRANSACTIONS_SUMMARY_EP,
    ACCOUNTS_LIST_EP,
    ACCOUNT_EP,
}

WS_HEARTBEAT_TIME_INTERVAL = 30


class WS_ACTION(Enum):
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


# https://docs.cloud.coinbase.com/advanced-trade-api/docs/ws-channels
WS_ORDER_SUBSCRIPTION_KEYS: Tuple[str, ...] = ("level2", "market_trades")
WS_ORDER_SUBSCRIPTION_CHANNELS: bidict[str, str] = bidict({k: k for k in WS_ORDER_SUBSCRIPTION_KEYS})
WS_ORDER_SUBSCRIPTION_CHANNELS["level2"] = "l2_data"

WS_USER_SUBSCRIPTION_KEYS: Tuple[str, ...] = ("user",)
WS_USER_SUBSCRIPTION_CHANNELS: bidict[str, str] = bidict({k: k for k in WS_USER_SUBSCRIPTION_KEYS})

WS_OTHERS_SUBSCRIPTION_KEYS: Tuple[str, ...] = ("ticker", "ticker_batch", "status")
WS_OTHERS_SUBSCRIPTION_CHANNELS: bidict[str, str] = bidict({k: k for k in WS_OTHERS_SUBSCRIPTION_KEYS})

# CoinbaseAdvancedTrade params
SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

# Rate Limit Type
REST_REQUESTS = "REST_REQUESTS"
MAX_REST_REQUESTS_S = 10

SIGNIN_REQUESTS = "SIGNIN_REQUESTS"
MAX_SIGNIN_REQUESTS_H = 10000

WSS_REQUESTS = "WSS_REQUESTS"
MAX_WSS_REQUESTS_S = 750

# Rate Limit time intervals
ONE_SECOND = 1
ONE_MINUTE = 60
ONE_HOUR = 3600
ONE_DAY = 86400

# Order States
ORDER_STATE = {
    "OPEN": OrderState.OPEN,
    "FILLED": OrderState.FILLED,
    "CANCELLED": OrderState.CANCELED,
    "EXPIRED": OrderState.FAILED,
    "FAILED": OrderState.FAILED,
    # Not directly from exchange
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
}
# Oddly, order can be in unknown state ???
ORDER_STATUS_NOT_FOUND_ERROR_CODE = "UNKNOWN_ORDER_STATUS"

RATE_LIMITS = [
    # Pools
    RateLimit(limit_id=REST_REQUESTS, limit=MAX_REST_REQUESTS_S, time_interval=ONE_SECOND),
    RateLimit(limit_id=SIGNIN_REQUESTS, limit=MAX_SIGNIN_REQUESTS_H, time_interval=ONE_HOUR),
    RateLimit(limit_id=WSS_REQUESTS, limit=MAX_WSS_REQUESTS_S, time_interval=ONE_SECOND),

    # Weighted Limits for REST URL endpoints
    RateLimit(limit_id=ALL_PAIRS_EP, limit=MAX_REST_REQUESTS_S, time_interval=ONE_SECOND,
              linked_limits=[LinkedLimitWeightPair(REST_REQUESTS, 1)]),

    # Weighted Limits for SIGNIN URL endpoints
    RateLimit(limit_id=SERVER_TIME_EP, limit=MAX_SIGNIN_REQUESTS_H, time_interval=ONE_HOUR,
              linked_limits=[LinkedLimitWeightPair(SIGNIN_REQUESTS, 1)]),
]
