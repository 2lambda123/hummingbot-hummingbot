from hummingbot.client.performance import PerformanceMetrics
import logging
from typing import (
    Dict,
    List,
    Optional,
    Any,
    AsyncIterable,
)
from decimal import Decimal
import asyncio
import json
import aiohttp
import time
from collections import namedtuple
import requests
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.logger import HummingbotLogger
from hummingbot.core.clock import Clock
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.limit_order import LimitOrder

from hummingbot.core.event.events import (
    MarketEvent,
    BuyOrderCompletedEvent,
    SellOrderCompletedEvent,
    OrderFilledEvent,
    OrderCancelledEvent,
    BuyOrderCreatedEvent,
    SellOrderCreatedEvent,
    MarketOrderFailureEvent,
    OrderType,
    TradeType,
    TradeFee
)
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.exchange.southxchange.southxchange_order_book_tracker import SouthxchangeOrderBookTracker
from hummingbot.connector.exchange.southxchange.southxchange_user_stream_tracker import SouthxchangeUserStreamTracker
from hummingbot.connector.exchange.southxchange.southxchange_auth import SouthXchangeAuth
from hummingbot.connector.exchange.southxchange.southxchange_in_flight_order import SouthXchangeInFlightOrder
from hummingbot.connector.exchange.southxchange import southxchange_utils
from hummingbot.connector.exchange.southxchange.southxchange_utils import SouthXchangeAPIRequest
from hummingbot.connector.exchange.southxchange.southxchange_constants import EXCHANGE_NAME, REST_URL
from hummingbot.core.data_type.common import OpenOrder
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce
ctce_logger = None
s_decimal_NaN = Decimal("nan")
s_decimal_0 = Decimal("0")

SouthxchangeOrder = namedtuple("SouthxchangeOrder", "orderId orderMarketId orderTime orderCurrencyGet orderCurrencyGive orderAmount orderOriginalAmount orderPrice orderType status")
SouthxchangeBalance = namedtuple("SouthxchangeBalance", "Currency Deposited Available Unconfirmed")


class SouthXchangeTradingRule(TradingRule):
    def __init__(self,
                 trading_pair: str,
                 min_price_increment: Decimal,
                 min_base_amount_increment: Decimal):
        super().__init__(trading_pair=trading_pair,
                         min_price_increment=min_price_increment,
                         min_base_amount_increment=min_base_amount_increment)


class SouthxchangeExchange(ExchangePyBase):
    """
    SouthxchangeExchange connects with SouthxchangeExchange exchange and provides order book pricing, user account tracking and
    trading functionality.
    """
    API_CALL_TIMEOUT = 10.0
    SHORT_POLL_INTERVAL = 5.0
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0
    LONG_POLL_INTERVAL = 120.0

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global ctce_logger
        if ctce_logger is None:
            ctce_logger = logging.getLogger(__name__)
        return ctce_logger

    def __init__(self,
                 southxchange_api_key: str,
                 southxchange_secret_key: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True
                 ):
        super().__init__()
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        # self._markets_enabled = southxchange_utils.get_market_id(trading_pairs=trading_pairs)
        self._southxchange_auth = SouthXchangeAuth(southxchange_api_key, southxchange_secret_key)
        self._southxchange_api_request = SouthXchangeAPIRequest(southxchange_api_key, southxchange_secret_key)
        self._order_book_tracker = SouthxchangeOrderBookTracker(trading_pairs=trading_pairs)
        self._user_stream_tracker = SouthxchangeUserStreamTracker(self._southxchange_auth, self._southxchange_api_request, trading_pairs)
        self._ev_loop = asyncio.get_event_loop()
        self._shared_client = None
        self._poll_notifier = asyncio.Event()
        self._last_timestamp = 0
        self._in_flight_orders = {}  # Dict[client_order_id:str, SouthXchangeInFlightOrder]
        self._order_not_found_records = {}  # Dict[client_order_id:str, count:int]
        self._trading_rules = {}  # Dict[trading_pair:str, SouthXchangeTradingRule]
        self._status_polling_task = None
        self._user_stream_event_listener_task = None
        self._trading_rules_polling_task = None
        self._last_poll_timestamp = 0
        self._trader_level = None

    @property
    def name(self) -> str:
        return EXCHANGE_NAME

    @property
    def order_books(self) -> Dict[str, OrderBook]:
        return self._order_book_tracker.order_books

    @property
    def trading_rules(self) -> Dict[str, SouthXchangeTradingRule]:
        return self._trading_rules

    @property
    def in_flight_orders(self) -> Dict[str, SouthXchangeInFlightOrder]:
        return self._in_flight_orders

    @property
    def status_dict(self) -> Dict[str, bool]:
        """
        A dictionary of statuses of various connector's components.
        """
        return {
            "order_books_initialized": self._order_book_tracker.ready,
            "account_balance": len(self._account_balances) > 0 if self._trading_required else True,
            "trading_rule_initialized": len(self._trading_rules) > 0,
            "user_stream_initialized":
                self._user_stream_tracker.data_source.last_recv_time > 0 if self._trading_required else True,
            "trader_level": self._trader_level is not None
        }

    @property
    def ready(self) -> bool:
        """
        :return True when all statuses pass, this might take 5-10 seconds for all the connector's components and
        services to be ready.
        """
        return all(self.status_dict.values())

    @property
    def limit_orders(self) -> List[LimitOrder]:
        return [
            in_flight_order.to_limit_order()
            for in_flight_order in self._in_flight_orders.values()
        ]

    @property
    def tracking_states(self) -> Dict[str, any]:
        """
        :return active in-flight orders in json format, is used to save in sqlite db.
        """
        return {
            key: value.to_json()
            for key, value in self._in_flight_orders.items()
            if not value.is_done
        }

    def restore_tracking_states(self, saved_states: Dict[str, any]):
        """
        Restore in-flight orders from saved tracking states, this is st the connector can pick up on where it left off
        when it disconnects.
        :param saved_states: The saved tracking_states.
        """
        self._in_flight_orders.update({
            key: SouthXchangeInFlightOrder.from_json(value)
            for key, value in saved_states.items()
        })

    def supported_order_types(self) -> List[OrderType]:
        """
        :return a list of OrderType supported by this connector.
        Note that Market order type is no longer required and will not be used.
        """
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER]

    def start(self, clock: Clock, timestamp: float):
        """
        This function is called automatically by the clock.
        """
        super().start(clock, timestamp)

    def stop(self, clock: Clock):
        """
        This function is called automatically by the clock.
        """
        super().stop(clock)

    async def start_network(self):
        """
        This function is required by NetworkIterator base class and is called automatically.
        It starts tracking order book, polling trading rules,
        updating statuses and tracking user data.
        """
        self._order_book_tracker.start()
        await self._update_account_data()

        self._trading_rules_polling_task = safe_ensure_future(self._trading_rules_polling_loop())
        if self._trading_required:
            self._status_polling_task = safe_ensure_future(self._status_polling_loop())
            self._user_stream_tracker_task = safe_ensure_future(self._user_stream_tracker.start())
            self._user_stream_event_listener_task = safe_ensure_future(self._user_stream_event_listener())

    async def stop_network(self):
        """
        This function is required by NetworkIterator base class and is called automatically.
        """
        # Resets timestamps for status_polling_task
        self._last_poll_timestamp = 0
        self._last_timestamp = 0

        self._order_book_tracker.stop()
        if self._status_polling_task is not None:
            self._status_polling_task.cancel()
            self._status_polling_task = None
        if self._trading_rules_polling_task is not None:
            self._trading_rules_polling_task.cancel()
            self._trading_rules_polling_task = None
        if self._user_stream_tracker_task is not None:
            self._user_stream_tracker_task.cancel()
            self._user_stream_tracker_task = None
        if self._user_stream_event_listener_task is not None:
            self._user_stream_event_listener_task.cancel()
            self._user_stream_event_listener_task = None

    async def check_network(self) -> NetworkStatus:
        """
        This function is required by NetworkIterator base class and is called periodically to check
        the network connection. Simply ping the network (or call any light weight public API).
        """
        try:
            # since there is no ping endpoint, the lowest rate call is to get BTC-USDT ticker
            url = f"{REST_URL}markets"
            requests.get(url)
        except asyncio.CancelledError:
            raise
        except Exception:
            return NetworkStatus.NOT_CONNECTED
        return NetworkStatus.CONNECTED

    async def _http_client(self) -> aiohttp.ClientSession:
        """
        :returns Shared client session instance
        """
        if self._shared_client is None:
            self._shared_client = aiohttp.ClientSession()
        return self._shared_client

    async def _trading_rules_polling_loop(self):
        """
        Periodically update trading rule.
        """
        while True:
            try:
                await self._update_trading_rules()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().network(f"Unexpected error while fetching trading rules. Error: {str(e)}",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch new trading rules from SouthxchangeExchange. "
                                                      "Check network connection.")
                await asyncio.sleep(0.5)

    async def _update_trading_rules(self):
        """
        Modify - SouthXchange
        """
        list_fees = await self._api_request(
            method="get",
            path_url="fees")
        self._trading_rules.clear()
        self._trading_rules = self._format_trading_rules(list_fees.get("Currencies"), list_fees.get("Markets"))

    def _format_trading_rules(self, currencies: Dict[str, Any], markets: Dict[str, Any]) -> Dict[str, SouthXchangeTradingRule]:
        """
        Modify - SouthXchange
        Converts json API response into a dictionary of trading rules.
        """
        trading_rules = {}
        for a in markets:
            trading_pair = a['ListingCurrencyCode'] + "-" + a['ReferenceCurrencyCode']
            value_precision = a['PricePrecision']
            precision_rule = "0."
            dec = ""
            if value_precision is not None:
                dec = str("1").zfill(int(a['PricePrecision']))
                precision_rule = f"{precision_rule}{dec}"
            else:
                for b in currencies:
                    if(b['Code'] == a['ListingCurrencyCode']):
                        dec = str("1").zfill(int(b['Precision']))
                        precision_rule = f"{precision_rule}{dec}"
                        break
                trading_rules[trading_pair] = SouthXchangeTradingRule(
                    trading_pair,
                    min_price_increment=Decimal(precision_rule),
                    min_base_amount_increment=Decimal(precision_rule)
                )
        return trading_rules

    async def _update_account_data(self):
        """
        Modify - SouthXchange
        """
        response = await self._api_request(
            method="post",
            path_url="getUserInfo",
            is_auth_required=True
        )
        if response is not None:
            self._trader_level = "ok"

    async def _api_request(self,
                           method: str,
                           path_url: str,
                           params: Dict[str, Any] = {},
                           is_auth_required: bool = False,
                           force_auth_path_url: Optional[str] = None) -> Dict[str, Any]:
        result = await self._southxchange_api_request._create_api_request(method, path_url, params, is_auth_required)
        return result

    def get_order_price_quantum(self, trading_pair: str, price: Decimal):
        """
        Returns a price step, a minimum price increment for a given trading pair.
        """
        trading_rule = self._trading_rules[trading_pair]
        return trading_rule.min_price_increment

    def get_order_size_quantum(self, trading_pair: str, order_size: Decimal):
        """
        Returns an order amount step, a minimum amount increment for a given trading pair.
        """
        trading_rule = self._trading_rules[trading_pair]
        return Decimal(trading_rule.min_base_amount_increment)

    def get_order_book(self, trading_pair: str) -> OrderBook:
        if trading_pair not in self._order_book_tracker.order_books:
            raise ValueError(f"No order book exists for '{trading_pair}'.")
        return self._order_book_tracker.order_books[trading_pair]

    def buy(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET,
            price: Decimal = s_decimal_NaN, **kwargs) -> str:
        """
        Buys an amount of base asset (of the given trading pair). This function returns immediately.
        To see an actual order, you'll have to wait for BuyOrderCreatedEvent.
        :param trading_pair: The market (e.g. BTC-USDT) to buy from
        :param amount: The amount in base token value
        :param order_type: The order type
        :param price: The price (note: this is no longer optional)
        :returns A new internal order id
        """
        client_order_id = southxchange_utils.gen_client_order_id(True, trading_pair)
        self._southxchange_api_request.safe_ensure_future_sx(self._create_order(TradeType.BUY, client_order_id, trading_pair, amount, order_type, price))
        return client_order_id

    def sell(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET,
             price: Decimal = s_decimal_NaN, **kwargs) -> str:
        """
        Sells an amount of base asset (of the given trading pair). This function returns immediately.
        To see an actual order, you'll have to wait for SellOrderCreatedEvent.
        :param trading_pair: The market (e.g. BTC-USDT) to sell from
        :param amount: The amount in base token value
        :param order_type: The order type
        :param price: The price (note: this is no longer optional)
        :returns A new internal order id
        """
        client_order_id = southxchange_utils.gen_client_order_id(False, trading_pair)
        self._southxchange_api_request.safe_ensure_future_sx(self._create_order(TradeType.SELL, client_order_id, trading_pair, amount, order_type, price))
        return client_order_id

    def cancel(self, trading_pair: str, order_id: str):
        """
        Cancel an order. This function returns immediately.
        To get the cancellation result, you'll have to wait for OrderCancelledEvent.
        :param trading_pair: The market (e.g. BTC-USDT) of the order.
        :param order_id: The internal order id (also called client_order_id)
        """
        safe_ensure_future(self._execute_cancel(trading_pair, order_id))
        return order_id

    async def _create_order(self,
                            trade_type: TradeType,
                            order_id: str,
                            trading_pair: str,
                            amount: Decimal,
                            order_type: OrderType,
                            price: Decimal):
        """
        Calls create-order API end point to place an order, starts tracking the order and triggers order created event.
        :param trade_type: BUY or SELL
        :param order_id: Internal order id (aka client_order_id)
        :param trading_pair: The market to place order
        :param amount: The order amount (in base token value)
        :param order_type: The order type
        :param price: The order price
        """
        if not order_type.is_limit_type():
            raise Exception(f"Unsupported order type: {order_type}")
        amount = self.quantize_order_amount(trading_pair, amount)
        price = self.quantize_order_price(trading_pair, price)
        if amount <= s_decimal_0:
            raise ValueError("Order amount must be greater than zero.")
        # TODO: check balance
        pair_currencies = trading_pair.split("-")
        api_params = {
            "listingCurrency": pair_currencies[0],
            "referenceCurrency": pair_currencies[1],
            "amount": f"{amount:f}",
            "limitPrice": f"{price:f}",
            "type": trade_type.name
        }
        self.start_tracking_order(
            order_id,
            "",
            trading_pair,
            trade_type,
            price,
            amount,
            order_type
        )
        try:
            order_result = await self._api_request(
                method="post",
                path_url="placeOrder",
                params=api_params,
                is_auth_required=True,
                force_auth_path_url="order"
            )
            if order_result is not None:
                exchange_order_id = order_result
                tracked_order = self._in_flight_orders.get(order_id)
                if tracked_order is not None:
                    self.logger().info(f"Created {order_type.name} {trade_type.name} order {order_id} for "
                                       f"{amount} {trading_pair}.")
                    tracked_order.exchange_order_id = exchange_order_id

            event_tag = MarketEvent.BuyOrderCreated if trade_type is TradeType.BUY else MarketEvent.SellOrderCreated
            event_class = BuyOrderCreatedEvent if trade_type is TradeType.BUY else SellOrderCreatedEvent
            self.trigger_event(event_tag,
                               event_class(
                                   self.current_timestamp,
                                   order_type,
                                   trading_pair,
                                   amount,
                                   price,
                                   order_id,
                                   exchange_order_id=exchange_order_id
                               ))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.stop_tracking_order(order_id)
            self.logger().network(
                f"Error submitting {trade_type.name} {order_type.name} order to SouthXchange for "
                f"{amount} {trading_pair} "
                f"{price}.",
                exc_info=True,
                app_warning_msg=str(e)
            )
            self.trigger_event(MarketEvent.OrderFailure,
                               MarketOrderFailureEvent(self.current_timestamp, order_id, order_type))

    def start_tracking_order(self,
                             order_id: str,
                             exchange_order_id: str,
                             trading_pair: str,
                             trade_type: TradeType,
                             price: Decimal,
                             amount: Decimal,
                             order_type: OrderType):
        """
        Starts tracking an order by simply adding it into _in_flight_orders dictionary.
        """
        self._in_flight_orders[order_id] = SouthXchangeInFlightOrder(
            client_order_id=order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=trading_pair,
            order_type=order_type,
            trade_type=trade_type,
            price=price,
            amount=amount
        )

    def stop_tracking_order(self, order_id: str):
        """
        Stops tracking an order by simply removing it from _in_flight_orders dictionary.
        """
        if order_id in self._in_flight_orders:
            del self._in_flight_orders[order_id]

    async def _execute_cancel(self, trading_pair: str, order_id: str) -> str:
        """
        Executes order cancellation process by first calling cancel-order API. The API result doesn't confirm whether
        the cancellation is successful, it simply states it receives the request.
        :param trading_pair: The market trading pair
        :param order_id: The internal order id
        order.last_state to change to CANCELED
        """
        order_was_cancelled = False
        try:
            tracked_order = self._in_flight_orders.get(order_id)
            if tracked_order is None:
                raise ValueError(f"Failed to cancel order - {order_id}. Order not found.")
            if tracked_order.exchange_order_id is None:
                await tracked_order.get_exchange_order_id()
            ex_order_id = tracked_order.exchange_order_id

            api_params = {
                "orderCode": ex_order_id,
            }
            await self._api_request(
                method="post",
                path_url="cancelOrder",
                params=api_params,
                is_auth_required=True,
                force_auth_path_url="order"
            )

            order_was_cancelled = True
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if str(e).find("Order not found") != -1:
                self.stop_tracking_order(order_id)
                return
        if order_was_cancelled:
            self.logger().info(f"Successfully cancelled order {order_id}.")
            self.stop_tracking_order(order_id)
            self.trigger_event(MarketEvent.OrderCancelled,
                               OrderCancelledEvent(self.current_timestamp, order_id, ex_order_id))
            tracked_order.cancelled_event.set()
            return CancellationResult(order_id, True)
        else:
            if not tracked_order.is_local:
                self.logger().network(
                    "Failed to cancel all orders.",
                    exc_info=True,
                    app_warning_msg="Failed to cancel all orders on SouthxchangeExchange. Check API key and network connection.")
            return CancellationResult(order_id, False)

    async def _status_polling_loop(self):
        """
        Periodically update user balances and order status via REST API. This serves as a fallback measure for web
        socket API updates.
        """
        while True:
            try:
                await self._poll_notifier.wait()
                await safe_gather(
                    self._update_balances(),
                    self._update_order_status(),
                )
                self._last_poll_timestamp = self.current_timestamp
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(str(e), exc_info=True)
                self.logger().network("Unexpected error while fetching account updates.",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch account updates from SouthxchangeExchange. "
                                                      "Check API key and network connection.")
                await asyncio.sleep(0.5)
            finally:
                self._poll_notifier = asyncio.Event()

    async def _update_balances(self):
        """
        Modify - SouthXchange
        Calls REST API to update total and available balances.
        """
        response = await self._api_request(
            method="post",
            path_url="listBalances",
            is_auth_required=True)
        balances = list(map(
            lambda balance: SouthxchangeBalance(
                balance["Currency"],
                balance["Deposited"],
                balance["Available"],
                balance["Unconfirmed"]
            ),
            response
        ))
        self._process_balances(balances)

    async def _update_order_status(self):
        """
        Calls REST API to get status update for each in-flight order.
        """
        last_tick = int(self._last_poll_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL)
        current_tick = int(self.current_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL)
        if current_tick > last_tick and len(self._in_flight_orders) > 0:
            tracked_orders = list(self._in_flight_orders.values())
            tasks = []
            for tracked_order in tracked_orders:
                order_id = await tracked_order.get_exchange_order_id()
                api_params = {
                    "code": order_id,
                }
                tasks.append(self._api_request(
                    method="post",
                    path_url="getOrder",
                    params=api_params,
                    is_auth_required=True)
                )
            self.logger().debug(f"Polling for order status updates of {len(tasks)} orders.")
            responses = await safe_gather(*tasks, return_exceptions=True)
            for response in responses:
                if isinstance(response, Exception):
                    raise response
                if response is None:
                    self.logger().info(f"_update_order_status result not in resp: {response}")
                    continue
                order_process = SouthxchangeOrder(
                    str(response["Code"]),
                    0,
                    response["DateAdded"],
                    response["ListingCurrency"],
                    response["ReferenceCurrency"],
                    str(response["Amount"]),
                    0,
                    str(response["LimitPrice"]),
                    response["Type"],
                    response["Status"]
                )
                self._process_order_message(order_process)

    async def cancel_all(self, timeout_seconds: float):
        """
        Cancels all in-flight orders and waits for cancellation results.
        Used by bot's top level stop and exit commands (cancelling outstanding orders on exit)
        :param timeout_seconds: The timeout at which the operation will be canceled.
        :returns List of CancellationResult which indicates whether each order is successfully cancelled.
        """
        open_orders = [o for o in self._in_flight_orders.values() if not o.is_done]
        if len(open_orders) == 0:
            return []
        tasks = [self._execute_cancel(o.trading_pair, o.client_order_id) for o in open_orders]
        cancellation_results = []
        try:
            cancellation_results = await safe_gather(*tasks, return_exceptions=False)
        except Exception:
            self.logger().network(
                "Unexpected error cancelling orders.",
                exc_info=True,
                app_warning_msg = "Failed to cancel all orders on SouthXchange. Check API key and network connection."
            )
        return cancellation_results

    def tick(self, timestamp: float):
        """
        Is called automatically by the clock for each clock's tick (1 second by default).
        It checks if status polling task is due for execution.
        """
        now = time.time()
        poll_interval = (self.SHORT_POLL_INTERVAL
                         if now - self._user_stream_tracker.last_recv_time > 60.0
                         else self.LONG_POLL_INTERVAL)
        last_tick = int(self._last_timestamp / poll_interval)
        current_tick = int(timestamp / poll_interval)
        if current_tick > last_tick:
            if not self._poll_notifier.is_set():
                self._poll_notifier.set()
        self._last_timestamp = timestamp

    def get_fee(self,
                base_currency: str,
                quote_currency: str,
                order_type: OrderType,
                order_side: TradeType,
                amount: Decimal,
                price: Decimal = s_decimal_NaN) -> TradeFee:
        """
        To get trading fee, this function is simplified by using fee override configuration. Most parameters to this
        function are ignore except order_type. Use OrderType.LIMIT_MAKER to specify you want trading fee for
        maker order.
        """
        is_maker = order_type is OrderType.LIMIT_MAKER
        return TradeFee(percent=self.estimate_fee_pct(is_maker))

    async def _iter_user_event_queue(self) -> AsyncIterable[Dict[str, any]]:
        while True:
            try:
                yield await self._user_stream_tracker.user_stream.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unknown error. Retrying after 1 seconds.",
                    exc_info=True,
                    app_warning_msg="Could not fetch user events from SouthxchangeExchange. Check API key and network connection."
                )
                await asyncio.sleep(1.0)

    async def _user_stream_event_listener(self):
        """
        Listens to message in _user_stream_tracker.user_stream queue. The messages are put in by
        SouthxchangeAPIUserStreamDataSource
        """
        async for event_message in self._iter_user_event_queue():
            try:
                if event_message.get("k") == "order":
                    list_orders_to_process = event_message.get("v")
                    for order_data in list_orders_to_process:
                        params = {
                            "code": order_data["c"],
                        }
                        order = await self._api_request(
                            method="post",
                            path_url="getOrder",
                            params=params,
                            is_auth_required=True)
                        if(order_data["b"] is True):
                            orderType = "buy"
                        else:
                            orderType = "sell"
                        order_process = SouthxchangeOrder(
                            str(order_data["c"]),
                            order_data["m"],
                            order_data["d"],
                            order_data["get"],
                            order_data["giv"],
                            str(order_data["a"]),
                            str(order_data["oa"]),
                            str(order_data["p"]),
                            orderType,
                            order["Status"]
                        )
                        if order["Status"] in {"executed", "partiallyexecuted", "partiallyexecutedbutnotenoughbalance"}:
                            self._process_trade_message(order_process)
                        else:
                            self._process_order_message(order_process)
                elif event_message.get("k") == "balance":
                    await self._update_balances()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await asyncio.sleep(15.0)

    async def get_open_orders(self) -> List[OpenOrder]:
        result = await self._api_request(
            method="post",
            path_url="listOrders",
            is_auth_required=True,
        )
        ret_val = []
        for order in result:
            exchange_order_id = order["Code"]
            client_order_id = None
            for in_flight_order in self._in_flight_orders.values():
                if in_flight_order.exchange_order_id == exchange_order_id:
                    client_order_id = in_flight_order.client_order_id
            if client_order_id is None:
                self.logger().debug(f"Unrecognized Order {exchange_order_id}: {order}")
                continue
            ret_val.append(
                OpenOrder(
                    client_order_id=client_order_id,
                    trading_pair= order["ListingCurrency"] + "-" + order["ListingCurrency"],
                    price=Decimal(str(order["LimitPrice"])),
                    amount=Decimal(str(order["OriginalAmount"])),
                    executed_amount=Decimal(str(order["OriginalAmount"])) - Decimal(str(order["Amount"])),
                    status="Pending",
                    order_type=OrderType.LIMIT,
                    is_buy=True if order["Type"].lower() == "buy" else False,
                    time=get_tracking_nonce(),
                    exchange_order_id=exchange_order_id
                )
            )
        return ret_val

    def _process_order_message(self, order_msg: SouthxchangeOrder):
        """
        Updates in-flight order and triggers cancellation or failure event if needed.
        :param order_msg: The order response from either REST or web socket API (they are of the same format)
        """
        client_order_id = None
        # for order_msg in list_order_msg:
        exchange_order_id = order_msg.orderId
        for in_flight_order in self._in_flight_orders.values():
            if in_flight_order.exchange_order_id == exchange_order_id:
                client_order_id = in_flight_order.client_order_id

        if client_order_id is None:
            return

        tracked_order = self._in_flight_orders[client_order_id]
        tracked_order.last_state = order_msg.status
        if tracked_order.is_cancelled:
            self.logger().info(f"Successfully cancelled order {client_order_id}.")
            self.trigger_event(MarketEvent.OrderCancelled,
                               OrderCancelledEvent(self.current_timestamp, client_order_id, exchange_order_id))
            tracked_order.cancelled_event.set()
            self.stop_tracking_order(client_order_id)
            # return
        elif tracked_order.is_failure:
            self.logger().info(f"The market order {client_order_id} has failed according to order status API. "
                               f"Reason: {southxchange_utils.get_api_reason(order_msg.errorCode)}")
            self.trigger_event(MarketEvent.OrderFailure,
                               MarketOrderFailureEvent(self.current_timestamp, client_order_id, tracked_order.order_type))
            self.stop_tracking_order(client_order_id)
            # return
        elif tracked_order.is_done:
            event_tag = MarketEvent.BuyOrderCompleted if tracked_order.trade_type is TradeType.BUY else MarketEvent.SellOrderCompleted
            event_class = BuyOrderCompletedEvent if tracked_order.trade_type is TradeType.BUY else SellOrderCompletedEvent
            self.trigger_event(
                event_tag,
                event_class(
                    self.current_timestamp,
                    client_order_id,
                    tracked_order.base_asset,
                    tracked_order.quote_asset,
                    tracked_order.fee_asset,
                    tracked_order.executed_amount_base,
                    tracked_order.executed_amount_quote,
                    tracked_order.fee_paid,
                    tracked_order.order_type,
                    exchange_order_id
                )
            )
            self.stop_tracking_order(client_order_id)
            # return

    def _process_trade_message(self, order_msg: SouthxchangeOrder):
        client_order_id = None
        exchange_order_id = order_msg.orderId
        for in_flight_order in self._in_flight_orders.values():
            if in_flight_order.exchange_order_id == exchange_order_id:
                client_order_id = in_flight_order.client_order_id

        if client_order_id is None:
            return
        tracked_order = self._in_flight_orders[client_order_id]
        trasanctionsOrder: Dict[any, any]
        try:
            params = {
                "transactionType": "tradesbyordercode",
                "optionalFilter": int(exchange_order_id),
                "pageSize": 50,
            }
            url = f"{REST_URL}listTransactions"
            headers = self._southxchange_auth.get_auth_headers(url, params)
            resp = requests.post(url, headers= headers["header"], data=json.dumps(params))
            if resp.status_code == 200:
                trasanctionsOrder = json.loads(resp.text)
        except Exception:
            return

        acumalatesFee = Decimal("0.0")
        feeAsset: str = ""
        for transOrder in trasanctionsOrder.get('Result'):
            if(transOrder["Type"] == "tradefee"):
                acumalatesFee = acumalatesFee + Decimal(transOrder["Amount"] * (-1))
                feeAsset = transOrder["CurrencyCode"]

        cumFilledQty = Decimal("0.0")
        cumFilledQty = Decimal(order_msg.orderOriginalAmount) - Decimal(order_msg.orderAmount)
        if cumFilledQty == 0:
            cumFilledQty = Decimal(tracked_order.amount)
        if tracked_order.executed_amount_base != cumFilledQty:
            # Update the relevant order information when there is fill event
            new_filled_amount = cumFilledQty - tracked_order.executed_amount_base
            new_fee_paid = acumalatesFee - tracked_order.fee_paid
            tracked_order.executed_amount_base = cumFilledQty
            tracked_order.executed_amount_quote = Decimal(order_msg.orderPrice) * tracked_order.executed_amount_base
            tracked_order.fee_paid = Decimal(acumalatesFee)
            tracked_order.fee_asset = feeAsset

            self.trigger_event(
                MarketEvent.OrderFilled,
                OrderFilledEvent(
                    self.current_timestamp,
                    client_order_id,
                    tracked_order.trading_pair,
                    tracked_order.trade_type,
                    tracked_order.order_type,
                    Decimal(order_msg.orderPrice),
                    new_filled_amount,
                    TradeFee(0.0, [(tracked_order.fee_asset, new_fee_paid)]),
                    exchange_order_id
                )
            )

        # update order status
        tracked_order.last_state = order_msg.status
        if tracked_order.is_done:
            event_tag = MarketEvent.BuyOrderCompleted if tracked_order.trade_type is TradeType.BUY else MarketEvent.SellOrderCompleted
            event_class = BuyOrderCompletedEvent if tracked_order.trade_type is TradeType.BUY else SellOrderCompletedEvent
            self.trigger_event(
                event_tag,
                event_class(
                    self.current_timestamp,
                    client_order_id,
                    tracked_order.base_asset,
                    tracked_order.quote_asset,
                    tracked_order.fee_asset,
                    tracked_order.executed_amount_base,
                    tracked_order.executed_amount_quote,
                    tracked_order.fee_paid,
                    tracked_order.order_type,
                    exchange_order_id
                )
            )

    def _process_balances(self, balances: List[SouthxchangeBalance], is_complete_list: bool = True):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()
        for balance in balances:
            asset_name = balance.Currency
            self._account_available_balances[asset_name] = PerformanceMetrics.smart_round(Decimal(balance.Available))
            self._account_balances[asset_name] = PerformanceMetrics.smart_round(Decimal(balance.Deposited))
            remote_asset_names.add(asset_name)
        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def quantize_order_amount(self, trading_pair: str, amount: Decimal, ) -> Decimal:
        quantized_amount: Decimal = super().quantize_order_amount(trading_pair, amount)
        return quantized_amount

    def quantize_order_price(self, trading_pair: str, price: Decimal = s_decimal_0) -> Decimal:
        quantized_price: Decimal = super().quantize_order_price(trading_pair, price)
        return quantized_price
