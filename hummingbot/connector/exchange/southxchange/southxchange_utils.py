import asyncio
import aiohttp
import logging
import nest_asyncio
from typing import List, Tuple
import random
import string
import requests
import json
from typing import Dict, Any
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.config.config_methods import using_exchange
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce
from hummingbot.connector.exchange.southxchange.southxchange_constants import REST_URL
from hummingbot.connector.exchange.southxchange.southxchange_auth import SouthXchangeAuth

nest_asyncio.apply()
CENTRALIZED = True

EXAMPLE_PAIR = "BTC-USDT"

DEFAULT_FEES = [0.1, 0.1]


HBOT_BROKER_ID = "SX-HMBot"


def get_market_id(trading_pairs: List[str]) -> int:
    url = f"{REST_URL}markets"
    resp = requests.get(url)
    if resp.status_code != 200:
        return 0
    resp_text = json.loads(resp.text)
    try:
        for item in resp_text:
            if trading_pairs[0] == (f"{item[0]}-{item[1]}"):
                return item[2]
    except Exception:
        return 0
    return 0


def convert_from_exchange_trading_pair(exchange_trading_pair: str) -> str:
    return exchange_trading_pair.replace("/", "-")


def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
    return hb_trading_pair.replace("-", "/")


def get_exchange_trading_pair_from_currencies(listing_currecy: str, reference_currency: str) -> str:
    return listing_currecy + "/" + reference_currency

# get timestamp in milliseconds


# def get_ms_timestamp() -> int:
#     return get_tracking_nonce()

# get timestamp in milliseconds


def time_to_num(time_str) -> int:
    hh, mm, ss = map(int, time_str.split(':'))
    return ss + 60 * (mm + 60 * hh)


def uuid32():
    return ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(32))


def derive_order_id(cl_order_id: str, ts: int) -> str:
    """
    Server order generator based on user info and input.
    :param user_uid: user uid
    :param cl_order_id: user random digital and number id
    :param ts: order timestamp in milliseconds
    :return: order id of length 32
    """
    return (HBOT_BROKER_ID + format(ts, 'x')[-11:] + cl_order_id[-5:])[:32]


def convert_bookWebSocket_to_bookApi(t: any) -> Dict[str, list]:
    arrayBuy = []
    arraySell = []
    for item in t:
        if item.get("b") is True:
            buyOrder = {
                "Amount": item.get("a"),
                "Price": item.get("p")
            }
            arrayBuy.append(buyOrder)
        else:
            sellOrder = {
                "Amount": item.get("a"),
                "Price": item.get("p")
            }
            arraySell.append(sellOrder)
    result = {
        "BuyOrders": arrayBuy,
        "SellOrders": arraySell,
    }
    return result


def gen_exchange_order_id(client_order_id: str) -> Tuple[str, int]:
    """
    Generates the exchange order id based on user uid and client order id.
    :param user_uid: user uid,
    :param client_order_id: client order id used for local order tracking
    :return: order id of length 32
    """
    time = get_tracking_nonce()
    return [
        derive_order_id(
            client_order_id,
            time
        ),
        time
    ]


def gen_client_order_id(is_buy: bool, trading_pair: str) -> str:
    side = "B" if is_buy else "S"
    return f"{HBOT_BROKER_ID}-{side}-{trading_pair}-{get_tracking_nonce()}"


KEYS = {
    "southxchange_api_key":
        ConfigVar(key="southxchange_api_key",
                  prompt="Enter your SouthXchange API key >>> ",
                  required_if=using_exchange("southxchange"),
                  is_secure=True,
                  is_connect_key=True),
    "southxchange_secret_key":
        ConfigVar(key="southxchange_secret_key",
                  prompt="Enter your SouthXchange secret key >>> ",
                  required_if=using_exchange("southxchange"),
                  is_secure=True,
                  is_connect_key=True),
}


class SouthXchangeAPIRequest():
    def __init__(self, api_key: str, secret_key: str):
        self._shared_client = None
        self._lock = asyncio.Lock()
        self._lock2 = asyncio.Lock()
        self._southxchange_auth = SouthXchangeAuth(api_key, secret_key)

    async def _http_client(self) -> aiohttp.ClientSession:
        """
        :returns Shared client session instance
        """
        if self._shared_client is None:
            self._shared_client = aiohttp.ClientSession()
        return self._shared_client

    async def _create_api_request(self,
                                  method: str, path_url: str,
                                  params: Dict[str, Any] = {},
                                  is_auth_required: bool = False) -> Dict[str, Any]:
        with await self._lock:
            resp_result = await self._api_request_southxchange(method, path_url, params, is_auth_required)
        return resp_result

    async def _api_request_southxchange(self,
                                        method: str,
                                        path_url: str,
                                        params: Dict[str, Any] = {},
                                        is_auth_required: bool = False) -> Dict[str, Any]:
        """
        Modify - SouthXchange
        """
        url = None
        headers = None

        if is_auth_required:
            url = f"{REST_URL}{path_url}"
            headers = self._southxchange_auth.get_auth_headers(url, params)
        else:
            url = f"{REST_URL}{path_url}"
            headers = self._southxchange_auth.get_headers()

        client = await self._http_client()
        if method == "get":
            response = await client.get(url)
        elif method == "post":
            response = await client.post(
                url,
                headers= headers["header"],
                data=json.dumps(headers["data"])
            )
        else:
            raise NotImplementedError
        try:
            result = await response.text()
            if result is not None and result != "":
                parsed_response = json.loads(await response.text())
            else:
                parsed_response = "ok"
        except Exception as e:
            raise IOError(f"Error parsing data from {url}. Error: {str(e)}")
        if response.status != 200 and response.status != 204:
            raise IOError(f"Error fetching data from {url} or API call failed. HTTP status is {response.status}. "
                          f"Message: {parsed_response}")
        return parsed_response

    async def get_websoxket_token(self) -> str:
        resp_result = await self._create_api_request(
            method="post",
            path_url="GetWebSocketToken",
            params={},
            is_auth_required=True)
        return resp_result

    async def safe_wrapper_sx(self, c):
        try:
            # loop = asyncio.get_running_loop()
            # asyncio.set_event_loop(loop)
            # task = loop.create_task(c)
            # return await task
            with await self._lock2:
                loop = asyncio.get_running_loop()
                task = loop.create_task(c)
                result_taks = asyncio.run(task)
            return result_taks
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.getLogger(__name__).error(f"Unhandled error in background task: {str(e)}", exc_info=True)

    def safe_ensure_future_sx(self, coro, *args, **kwargs):
        return asyncio.ensure_future(self.safe_wrapper_sx(coro), *args, **kwargs)
