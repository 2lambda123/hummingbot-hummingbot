# A single source of truth for constant variables related to the exchange
from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit

EXCHANGE_NAME = "southxchange"
REST_URL = "https://www.southxchange.com/api/v4/"
WS_URL = "wss://www.southxchange.com/api/v4/connect"
PUBLIC_WS_URL = WS_URL
PRIVATE_WS_URL = WS_URL + '?token={access_token}'
PONG_PAYLOAD = {"op": "pong"}

ALL_ENDPOINTS_LIMIT = "All"
RATE_LIMITS = [
    RateLimit(limit_id="SXC", limit=239, time_interval=60, linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT)]),
]
