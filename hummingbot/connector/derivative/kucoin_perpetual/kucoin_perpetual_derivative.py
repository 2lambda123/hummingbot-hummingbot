import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from bidict import ValueDuplicationError, bidict

import hummingbot.connector.derivative.kucoin_perpetual.kucoin_perpetual_constants as CONSTANTS
import hummingbot.connector.derivative.kucoin_perpetual.kucoin_perpetual_utils as kucoin_utils
from hummingbot.connector.derivative.kucoin_perpetual import kucoin_perpetual_web_utils as web_utils
from hummingbot.connector.derivative.kucoin_perpetual.kucoin_perpetual_api_order_book_data_source import (
    KucoinPerpetualAPIOrderBookDataSource,
)
from hummingbot.connector.derivative.kucoin_perpetual.kucoin_perpetual_api_user_stream_data_source import (
    KucoinPerpetualAPIUserStreamDataSource,
)
from hummingbot.connector.derivative.kucoin_perpetual.kucoin_perpetual_auth import KucoinPerpetualAuth
from hummingbot.connector.derivative.position import Position
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter

s_decimal_NaN = Decimal("nan")
s_decimal_0 = Decimal(0)


class KucoinPerpetualDerivative(PerpetualDerivativePyBase):

    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        kucoin_perpetual_api_key: str = None,
        kucoin_perpetual_secret_key: str = None,
        kucoin_perpetual_passphrase: str = None,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):

        self.kucoin_perpetual_api_key = kucoin_perpetual_api_key
        self.kucoin_perpetual_secret_key = kucoin_perpetual_secret_key
        self.kucoin_perpetual_passphrase = kucoin_perpetual_passphrase
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._domain = domain
        self._last_trade_history_timestamp = None
        self._last_order_fill_ts_s: float = 0

        super().__init__(client_config_map)

    @property
    def name(self) -> str:
        return CONSTANTS.EXCHANGE_NAME

    @property
    def authenticator(self) -> KucoinPerpetualAuth:
        return KucoinPerpetualAuth(self.kucoin_perpetual_api_key,
                                   self.kucoin_perpetual_passphrase,
                                   self.kucoin_perpetual_secret_key,
                                   time_provider=self._time_synchronizer)

    @property
    def rate_limits_rules(self) -> List[RateLimit]:
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def client_order_id_max_length(self) -> int:
        return CONSTANTS.MAX_ID_LEN

    @property
    def client_order_id_prefix(self) -> str:
        return CONSTANTS.HB_PARTNER_ID

    @property
    def trading_rules_request_path(self) -> str:
        return CONSTANTS.QUERY_SYMBOL_ENDPOINT

    @property
    def trading_pairs_request_path(self) -> str:
        return CONSTANTS.QUERY_SYMBOL_ENDPOINT

    @property
    def check_network_request_path(self) -> str:
        return CONSTANTS.SERVER_TIME_PATH_URL

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return False

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    @property
    def funding_fee_poll_interval(self) -> int:
        return 120

    def supported_order_types(self) -> List[OrderType]:
        """
        :return a list of OrderType supported by this connector
        """
        return [OrderType.LIMIT, OrderType.MARKET]

    def supported_position_modes(self):
        # KuCoin only supports ONEWAY mode for all perpetuals, no hedge mode
        return [PositionMode.ONEWAY]

    def get_buy_collateral_token(self, trading_pair: str) -> str:
        trading_rule: TradingRule = self._trading_rules[trading_pair]
        return trading_rule.buy_order_collateral_token

    def get_sell_collateral_token(self, trading_pair: str) -> str:
        trading_rule: TradingRule = self._trading_rules[trading_pair]
        return trading_rule.sell_order_collateral_token

    def get_quantity_of_contracts(self, trading_pair: str, amount: float) -> int:
        trading_rule: TradingRule = self._trading_rules[trading_pair]
        num_contracts = int(amount / trading_rule.min_base_amount_increment)
        return num_contracts

    def get_value_of_contracts(self, trading_pair: str, number: int) -> Decimal:
        if len(self._trading_rules) > 0:
            trading_rule: TradingRule = self._trading_rules[trading_pair]
            contract_value = Decimal(number * trading_rule.min_base_amount_increment)
        else:
            contract_value = Decimal(number * 0.001)
        return contract_value

    def start(self, clock: Clock, timestamp: float):
        super().start(clock, timestamp)
        self.set_position_mode(PositionMode.ONEWAY)

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        error_description = str(request_exception)
        ts_error_target_str = self._format_ret_code_for_print(ret_code=CONSTANTS.RET_CODE_AUTH_TIMESTAMP_ERROR)
        param_error_target_str = (
            "KC-API-TIMESTAMP Invalid -- Time differs from server time by more than 5 seconds"
        )
        is_time_synchronizer_related = (
            ts_error_target_str in error_description
            or param_error_target_str in error_description
        )
        return is_time_synchronizer_related

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        cancel_result = await self._api_delete(
            path_url=CONSTANTS.CANCEL_ORDER_PATH_URL.format(orderid=tracked_order.exchange_order_id),
            is_auth_required=True,
            limit_id=CONSTANTS.CANCEL_ORDER_PATH_URL,
            data={
                "order_id": tracked_order.exchange_order_id,
            }
        )
        response_code = cancel_result["code"]

        if response_code != CONSTANTS.RET_CODE_OK:
            if response_code == CONSTANTS.RET_CODE_ORDER_NOT_EXISTS:
                await self._order_tracker.process_order_not_found(order_id)
            formatted_ret_code = self._format_ret_code_for_print(response_code)
            raise IOError(f"{formatted_ret_code} - {cancel_result['msg']}")

        return True

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        position_action: PositionAction = PositionAction.NIL,
        **kwargs,
    ) -> Tuple[str, float]:
        side = trade_type.name.lower()
        order_type_str = "market" if order_type == OrderType.MARKET else "limit"
        data = {
            "size": self.get_quantity_of_contracts(trading_pair, amount),
            "clientOid": order_id,
            "side": side,
            "symbol": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
            "type": order_type_str,
            "reduceOnly": position_action == PositionAction.CLOSE,
            "leverage": str(self.get_leverage(trading_pair)),
        }
        if order_type is OrderType.LIMIT:
            data["price"] = str(price)
        elif order_type is OrderType.LIMIT_MAKER:
            data["price"] = str(price)
            data["postOnly"] = True

        exchange_order_id = await self._api_post(
            path_url=CONSTANTS.CREATE_ORDER_PATH_URL,
            data=data,
            is_auth_required=True,
            limit_id=CONSTANTS.CREATE_ORDER_PATH_URL,
        )
        return str(exchange_order_id["data"]["orderId"]), self.current_timestamp

    def _get_fee(self,
                 base_currency: str,
                 quote_currency: str,
                 order_type: OrderType,
                 order_side: TradeType,
                 position_action: PositionAction,
                 amount: Decimal,
                 price: Decimal = s_decimal_NaN,
                 is_maker: Optional[bool] = None) -> AddedToCostTradeFee:

        is_maker = is_maker or (order_type is OrderType.LIMIT_MAKER)
        trading_pair = combine_to_hb_trading_pair(base=base_currency, quote=quote_currency)
        if trading_pair in self._trading_fees:
            fees_data = self._trading_fees[trading_pair]
            fee_value = Decimal(fees_data["makerFeeRate"]) if is_maker else Decimal(fees_data["takerFeeRate"])
            fee = AddedToCostTradeFee(percent=fee_value)
        else:
            fee = build_trade_fee(
                self.name,
                is_maker,
                base_currency=base_currency,
                quote_currency=quote_currency,
                order_type=order_type,
                order_side=order_side,
                amount=amount,
                price=price,
            )
        return fee

    async def _update_trading_fees(self):
        pass

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            auth=self._auth,
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return KucoinPerpetualAPIOrderBookDataSource(
            self.trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return KucoinPerpetualAPIUserStreamDataSource(
            trading_pairs=self.trading_pairs,
            connector=self,
            auth=self._auth,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    async def _update_orders_fills(self, orders: List[InFlightOrder]):
        # This method in the base ExchangePyBase, makes an API call for each order.
        # Given the rate limit of the API method and the breadth of info provided by the method
        # the mitigation proposal is to collect all orders in one shot, then parse them
        # Note that this is limited to 500 orders (pagination)
        # An alternative for Kucoin would be to use the limit/fills that returns 24hr updates, which should
        # be sufficient, the rate limit seems better suited
        all_trades_updates: List[TradeUpdate] = []
        if len(orders) > 0:
            try:
                all_trades_updates: List[TradeUpdate] = await self._all_trades_updates(orders)
            except asyncio.CancelledError:
                raise
            except Exception as request_error:
                self.logger().warning(
                    f"Failed to fetch trade updates. Error: {request_error}")

            for trade_update in all_trades_updates:
                self._order_tracker.process_trade_update(trade_update)

    async def _all_trades_updates(self, orders: List[InFlightOrder]) -> List[TradeUpdate]:
        trade_updates: List[TradeUpdate] = []
        if len(orders) > 0:
            exchange_to_client = {o.exchange_order_id: {"client_id": o.client_order_id, "trading_pair": o.trading_pair} for o in orders}

            # We request updates from either:
            #    - The earliest order creation_timestamp in the list (first couple requests)
            #    - The last time we got a fill
            self._last_order_fill_ts_s = int(max(self._last_order_fill_ts_s, min([o.creation_timestamp for o in orders])))

            # From Kucoin https://docs.kucoin.com/#list-fills:
            # "If you only specified the start time, the system will automatically
            #  calculate the end time (end time = start time + 7 * 24 hours)"
            all_fills_response = await self._api_get(
                path_url=CONSTANTS.FILLS_PATH_URL,
                params={
                    "startAt": self._last_order_fill_ts_s * 1000,
                },
                is_auth_required=True)

            if "data" in all_fills_response and len(all_fills_response["data"]) > 0:
                for trade in all_fills_response["data"].get("items", []):
                    if str(trade["orderId"]) in exchange_to_client:
                        fee = TradeFeeBase.new_perpetual_fee(
                            fee_schema=self.trade_fee_schema(),
                            position_action=TradeType.BUY if trade["side"] == "buy" else TradeType.SELL,
                            percent_token=trade["feeCurrency"],
                            flat_fees=[TokenAmount(amount=Decimal(trade["fee"]), token=trade["feeCurrency"])]
                        )

                        client_info = exchange_to_client[str(trade["orderId"])]
                        trade_update = TradeUpdate(
                            trade_id=str(trade["tradeId"]),
                            client_order_id=client_info["client_id"],
                            trading_pair=client_info["trading_pair"],
                            exchange_order_id=str(trade["orderId"]),
                            fee=fee,
                            fill_base_amount=Decimal(trade["size"]),
                            fill_quote_amount=Decimal(trade["value"]),
                            fill_price=Decimal(trade["price"]),
                            fill_timestamp=trade["createdAt"] * 1e-3,
                        )
                        trade_updates.append(trade_update)
                        # Update the last fill timestamp with the latest one
                        self._last_order_fill_ts_s = max(self._last_order_fill_ts_s, trade["createdAt"] * 1e-3)

        return trade_updates

    async def _update_balances(self):
        """
        Calls REST API to update total and available balances
        """
        wallet_balance: Dict[str, Dict[str, Any]] = await self._api_get(
            path_url=CONSTANTS.GET_WALLET_BALANCE_PATH_URL.format(currency="USDT"),
            is_auth_required=True,
            limit_id=CONSTANTS.GET_WALLET_BALANCE_PATH_URL,
        )

        if wallet_balance["code"] != CONSTANTS.RET_CODE_OK:
            formatted_ret_code = self._format_ret_code_for_print(wallet_balance['code'])
            raise IOError(f"{formatted_ret_code} - {wallet_balance['msg']}")

        self._account_available_balances.clear()
        self._account_balances.clear()

        if wallet_balance["data"] is not None:
            if type(wallet_balance["data"]) == list:
                for balance_data in wallet_balance["data"]:
                    currency = str(balance_data["currency"])
                    self._account_balances[currency] = Decimal(str(balance_data["marginBalance"]))
                    self._account_available_balances[currency] = Decimal(str(balance_data["availableBalance"]))
            else:
                currency = str(wallet_balance["data"]["currency"])
                self._account_balances[currency] = Decimal(str(wallet_balance["data"]["marginBalance"]))
                self._account_available_balances[currency] = Decimal(str(wallet_balance["data"]["availableBalance"]))

    async def _update_positions(self):
        """
        Retrieves all positions using the REST API.
        """

        raw_responses: List[Dict[str, Any]] = await self._api_get(
            path_url=CONSTANTS.GET_POSITIONS_PATH_URL,
            is_auth_required=True,
            limit_id=CONSTANTS.GET_POSITIONS_PATH_URL,
        )

        # Initial parsing of responses. Joining all the responses
        parsed_resps: List[Dict[str, Any]] = []
        if len(raw_responses["data"]) > 0:
            for resp, trading_pair in zip(raw_responses["data"], self._trading_pairs):
                if not isinstance(resp, Exception):
                    result = resp
                    if result:
                        position_entries = result if isinstance(result, list) else [result]
                        parsed_resps.extend(position_entries)
                else:
                    self.logger().error(f"Error fetching positions for {trading_pair}. Response: {resp}")

        for position in parsed_resps:
            data = position
            ex_trading_pair = data.get("symbol")
            hb_trading_pair = await self.trading_pair_associated_to_exchange_symbol(ex_trading_pair)
            amount = self.get_value_of_contracts(hb_trading_pair, int(str(data["currentQty"])))
            position_side = PositionSide.SHORT if amount < 0 else PositionSide.LONG
            unrealized_pnl = Decimal(str(data["unrealisedPnl"]))
            entry_price = Decimal(str(data["avgEntryPrice"]))
            leverage = Decimal(str(data["realLeverage"]))
            pos_key = self._perpetual_trading.position_key(hb_trading_pair, position_side)
            if amount != s_decimal_0:
                position = Position(
                    trading_pair=hb_trading_pair,
                    position_side=position_side,
                    unrealized_pnl=unrealized_pnl,
                    entry_price=entry_price,
                    amount=amount * (Decimal("-1.0") if position_side == PositionSide.SHORT else Decimal("1.0")),
                    leverage=leverage,
                )
                self._perpetual_trading.set_position(pos_key, position)
            else:
                self._perpetual_trading.remove_position(pos_key)

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []

        if order.exchange_order_id is not None:
            try:
                all_fills_response = await self._request_order_fills(order=order)
                trades_list_key = "items"
                fills_data = all_fills_response["data"].get(trades_list_key, [])

                if fills_data is not None:
                    for fill_data in fills_data:
                        trade_update = self._parse_trade_update(trade_msg=fill_data, tracked_order=order)
                        trade_updates.append(trade_update)
            except IOError as ex:
                if not self._is_request_exception_related_to_time_synchronizer(request_exception=ex):
                    raise

        return trade_updates

    async def _request_order_fills(self, order: InFlightOrder) -> Dict[str, Any]:
        url = CONSTANTS.GET_FILL_INFO_PATH_URL.format(orderid=order.exchange_order_id)
        res = await self._api_get(
            path_url=url,
            is_auth_required=True,
            trading_pair=order.trading_pair,
            limit_id=CONSTANTS.GET_FILL_INFO_PATH_URL,
        )
        return res

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        try:
            order_status_data = await self._request_order_status_data(tracked_order=tracked_order)
            order_msg = order_status_data["data"]
            client_order_id = str(order_msg["clientOid"])
            if "cancelExist" in order_msg:
                if bool(order_msg["cancelExist"]) is True:
                    order_status = CONSTANTS.ORDER_STATE["cancelExist"]
                else:
                    order_status = CONSTANTS.ORDER_STATE[order_msg["status"]]

            order_update: OrderUpdate = OrderUpdate(
                trading_pair=tracked_order.trading_pair,
                update_timestamp=self.current_timestamp,
                new_state=order_status,
                client_order_id=client_order_id,
                exchange_order_id=order_msg["id"],
            )

            return order_update

        except IOError as ex:
            if self._is_request_exception_related_to_time_synchronizer(request_exception=ex):
                order_update = OrderUpdate(
                    client_order_id=tracked_order.client_order_id,
                    trading_pair=tracked_order.trading_pair,
                    update_timestamp=self.current_timestamp,
                    new_state=tracked_order.current_state,
                )
            else:
                raise

        return order_update

    async def _request_order_status_data(self, tracked_order: InFlightOrder) -> Dict:
        resp = await self._api_get(
            path_url=CONSTANTS.QUERY_ORDER_BY_EXCHANGE_ORDER_ID_PATH_URL.format(orderid=tracked_order.exchange_order_id),
            is_auth_required=True,
            limit_id=CONSTANTS.QUERY_ORDER_BY_EXCHANGE_ORDER_ID_PATH_URL,
        )

        return resp

    async def _user_stream_event_listener(self):
        """
        Listens to message in _user_stream_tracker.user_stream queue.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                event_type = event_message.get("type")
                event_subject = event_message.get("subject")
                execution_data = event_message.get("data")
                endpoint = web_utils.endpoint_from_message(event_message)
                payload = web_utils.payload_from_message(event_message)
                if type(execution_data) == list:
                    execution_data = execution_data[0]

                if event_type == "message" and event_subject == CONSTANTS.ORDER_CHANGE_EVENT_TYPE:
                    order_event_type = execution_data["type"]
                    client_order_id: Optional[str] = execution_data.get("clientOid")

                    fillable_order = self._order_tracker.all_fillable_orders.get(client_order_id)
                    updatable_order = self._order_tracker.all_updatable_orders.get(client_order_id)

                    event_timestamp = execution_data["ts"] * 1e-9

                    if fillable_order is not None and order_event_type in ("match", "filled"):
                        if order_event_type == "match":
                            contract_value = Decimal(self.get_value_of_contracts(fillable_order.trading_pair, int(execution_data["matchSize"])))
                            execute_price = Decimal(execution_data["matchPrice"])
                        elif order_event_type == "filled":
                            contract_value = Decimal(self.get_value_of_contracts(fillable_order.trading_pair, int(execution_data["filledSize"])))
                            execute_price = Decimal(execution_data["price"])
                        position_side = execution_data["side"]
                        position_action = (PositionAction.OPEN
                                           if (fillable_order.trade_type is TradeType.BUY and position_side == "buy"
                                               or fillable_order.trade_type is TradeType.SELL and position_side == "sell")
                                           else PositionAction.CLOSE)
                        if "type" in execution_data and execution_data["type"] in ["canceled", "filled"] and "status" in execution_data and execution_data["status"] == "done":
                            position_action = PositionAction.CLOSE

                        fee_asset = fillable_order.quote_asset
                        if "fee" in execution_data:
                            fee_amount = Decimal(execution_data["fee"])
                        else:
                            fee_amount = round(Decimal(execution_data["size"]) * Decimal(0.1), 2)
                        flat_fees = [] if fee_amount == Decimal("0") else [TokenAmount(amount=fee_amount, token=fee_asset)]

                        fee = TradeFeeBase.new_perpetual_fee(
                            fee_schema=self.trade_fee_schema(),
                            position_action=position_action,
                            percent_token=fee_asset,
                            flat_fees=flat_fees,
                        )
                        if "tradeId" in execution_data:
                            trade_update = TradeUpdate(
                                trade_id=execution_data["tradeId"],
                                client_order_id=client_order_id,
                                exchange_order_id=execution_data["orderId"],
                                trading_pair=updatable_order.trading_pair,
                                fee=fee,
                                fill_base_amount=contract_value,
                                fill_quote_amount=contract_value * execute_price,
                                fill_price=execute_price,
                                fill_timestamp=event_timestamp,
                            )
                            self._order_tracker.process_trade_update(trade_update)

                    if updatable_order is not None:
                        updated_status = CONSTANTS.ORDER_STATE.get(order_event_type)
                        order_update = OrderUpdate(
                            trading_pair=updatable_order.trading_pair,
                            update_timestamp=event_timestamp,
                            new_state=updated_status,
                            client_order_id=client_order_id,
                            exchange_order_id=execution_data["orderId"],
                        )
                        self._order_tracker.process_order_update(order_update=order_update)
                elif event_subject == CONSTANTS.BALANCE_EVENT_TYPE:
                    currency = execution_data["currency"]
                    available_balance = Decimal(execution_data["availableBalance"])
                    total_balance = Decimal(execution_data["holdBalance"]) + Decimal(execution_data["availableBalance"])
                    self._account_balances.update({currency: total_balance})
                    self._account_available_balances.update({currency: available_balance})
                elif event_subject == CONSTANTS.POSITION_CHANGE_EVENT_TYPE:
                    await self._process_account_position_event(payload)
                elif endpoint == "error":
                    self.logger().error(f"Error returned via WS: {payload}.")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error in user stream listener loop.")
                await self._sleep(5.0)

    async def _process_account_position_event(self, position_msg: Dict[str, Any]):
        """
        Updates position
        :param position_msg: The position event message payload
        """
        if position_msg["changeReason"] != "markPriceChange":
            ex_trading_pair = position_msg["symbol"]
            trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=ex_trading_pair)
            amount = Decimal(str(position_msg["currentQty"]))
            position_side = PositionSide.SHORT if amount < 0 else PositionSide.LONG
            entry_price = Decimal(str(position_msg["avgEntryPrice"]))
            leverage = Decimal(str(position_msg["realLeverage"]))
            unrealized_pnl = Decimal(str(position_msg["unrealisedPnl"]))
            pos_key = self._perpetual_trading.position_key(trading_pair, position_side)
            if amount != s_decimal_0:
                position = Position(
                    trading_pair=trading_pair,
                    position_side=position_side,
                    unrealized_pnl=unrealized_pnl,
                    entry_price=entry_price,
                    amount=amount,
                    leverage=leverage,
                )
                self._perpetual_trading.set_position(pos_key, position)
            else:
                self._perpetual_trading.remove_position(pos_key)

    def _process_trade_event_message(self, trade_msg: Dict[str, Any]):
        """
        Updates in-flight order and trigger order filled event for trade message received. Triggers order completed
        event if the total executed amount equals to the specified order amount.
        :param trade_msg: The trade event message payload
        """

        if "clientOid" in trade_msg:
            client_order_id = str(trade_msg["clientOid"])
        else:
            client_order_id = str(trade_msg["tradeId"])
        fillable_order = self._order_tracker.all_fillable_orders.get(client_order_id)

        if fillable_order is not None:
            trade_update = self._parse_trade_update(trade_msg=trade_msg, tracked_order=fillable_order)
            self._order_tracker.process_trade_update(trade_update)

        updatable_order = self._order_tracker.all_updatable_orders.get(client_order_id)
        if updatable_order is not None:
            self._process_order_event_message(order_msg=trade_msg)

    def _parse_trade_update(self, trade_msg: Dict, tracked_order: InFlightOrder) -> TradeUpdate:
        if "tradeId" in trade_msg:
            trade_id = trade_msg["tradeId"]
        elif "id" in trade_msg:
            trade_id = trade_msg["id"]
        elif "orderId" in trade_msg:
            trade_id = trade_msg["orderId"]

        if "orderId" in trade_msg:
            order_id = trade_msg["orderId"]
        elif "id" in trade_msg:
            order_id = trade_msg["id"]

        fee_asset = tracked_order.quote_asset
        if "fee" in trade_msg:
            fee_amount = Decimal(trade_msg["fee"])
        else:
            fee_amount = round(Decimal(trade_msg["size"]) * Decimal(0.1), 2)
        position_side = trade_msg["side"]
        position_action = (PositionAction.OPEN
                           if (tracked_order.trade_type is TradeType.BUY and position_side == "buy"
                               or tracked_order.trade_type is TradeType.SELL and position_side == "sell")
                           else PositionAction.CLOSE)
        if "type" in trade_msg and trade_msg["type"] in ["canceled", "filled"] and "status" in trade_msg and trade_msg["status"] == "done":
            position_action = PositionAction.CLOSE

        flat_fees = [] if fee_amount == Decimal("0") else [TokenAmount(amount=fee_amount, token=fee_asset)]

        fee = TradeFeeBase.new_perpetual_fee(
            fee_schema=self.trade_fee_schema(),
            position_action=position_action,
            percent_token=fee_asset,
            flat_fees=flat_fees,
        )

        exec_price = Decimal(trade_msg["price"])
        if "tradeTime" in trade_msg:
            exec_time = (
                trade_msg["tradeTime"]  # Time passed in nanoseconds
                if "tradeTime" in trade_msg
                else pd.Timestamp(trade_msg["tradeTime"]).timestamp()
            )
        elif "ts" in trade_msg:
            exec_time = (
                trade_msg["ts"] * 1e-9
                if "ts" in trade_msg
                else pd.Timestamp(trade_msg["ts"]).timestamp()
            )
        elif "updatedAt" in trade_msg:
            exec_time = (
                trade_msg["updatedAt"]  # Time passed in nanoseconds
                if "updatedAt" in trade_msg
                else pd.Timestamp(trade_msg["tradeTime"]).timestamp()
            )

        if int(trade_msg["filledSize"]) == 0:
            contract_value = 0
            exec_price = 0
        else:
            contract_value = Decimal(self.get_value_of_contracts(tracked_order.trading_pair, int(trade_msg["filledSize"])))
        if "type" in trade_msg and "status" in trade_msg and trade_msg["type"] == "canceled" and trade_msg["status"] == "done":
            contract_value = 0
            exec_price = 0

        trade_update: TradeUpdate = TradeUpdate(
            trade_id=trade_id,
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=order_id,
            trading_pair=tracked_order.trading_pair,
            fill_timestamp=exec_time,
            fill_price=exec_price,
            fill_base_amount=contract_value,
            fill_quote_amount=exec_price * contract_value,
            fee=fee,
        )

        return trade_update

    def _process_order_event_message(self, order_msg: Dict[str, Any]):
        """
        Updates in-flight order and triggers cancellation or failure event if needed.
        :param order_msg: The order event message payload
        """
        if "cancelExist" in order_msg:
            if bool(order_msg["cancelExist"]) is True:
                order_status = CONSTANTS.ORDER_STATE["cancelExist"]
            else:
                order_status = CONSTANTS.ORDER_STATE[order_msg["status"]]
        elif order_msg["type"] == "canceled":
            order_status = CONSTANTS.ORDER_STATE["cancelExist"]
        else:
            order_status = CONSTANTS.ORDER_STATE[order_msg["status"]]
        client_order_id = str(order_msg["clientOid"])
        updatable_order = self._order_tracker.all_updatable_orders.get(client_order_id)
        if "id" in order_msg:
            exchange_order_id = order_msg["id"]
        elif "orderId" in order_msg:
            exchange_order_id = order_msg["orderId"]

        if updatable_order is not None:
            new_order_update: OrderUpdate = OrderUpdate(
                trading_pair=updatable_order.trading_pair,
                update_timestamp=self.current_timestamp,
                new_state=order_status,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
            )
            self._order_tracker.process_order_update(new_order_update)

    def _process_wallet_event_message(self, wallet_msg: Dict[str, Any]):
        """
        Updates account balances.
        :param wallet_msg: The account balance update message payload
        """
        if "currency" in wallet_msg:
            symbol = wallet_msg["currency"]
        else:
            symbol = "USDT"

        available_balance = Decimal(str(wallet_msg["availableBalance"]))
        self._account_balances[symbol] = Decimal(available_balance + Decimal(str(wallet_msg["holdBalance"])))
        self._account_available_balances[symbol] = available_balance

    async def _format_trading_rules(self, instrument_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Converts JSON API response into a local dictionary of trading rules.
        :param instrument_info_dict: The JSON API response.
        :returns: A dictionary of trading pair to its respective TradingRule.
        """
        trading_rules = {}
        symbol_map = await self.trading_pair_symbol_map()
        for instrument in instrument_info_dict["data"]:
            try:
                exchange_symbol = instrument["symbol"]
                if exchange_symbol in symbol_map:
                    multiplier = Decimal(str(instrument["multiplier"]))
                    trading_pair = combine_to_hb_trading_pair(instrument['baseCurrency'], instrument['quoteCurrency'])
                    collateral_token = instrument["quoteCurrency"]
                    trading_rules[trading_pair] = TradingRule(
                        trading_pair=trading_pair,
                        min_order_size=Decimal(str(instrument["lotSize"])) * multiplier,
                        max_order_size =Decimal(str(instrument["maxOrderQty"])) * multiplier,
                        min_price_increment=Decimal(str(instrument["tickSize"])),
                        min_base_amount_increment=multiplier,
                        buy_order_collateral_token=collateral_token,
                        sell_order_collateral_token=collateral_token,
                    )
            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule: {instrument}. Skipping...")
        return list(trading_rules.values())

    async def _market_data_for_all_product_types(self) -> List[Dict[str, Any]]:
        all_exchange_info = []

        exchange_info = await self._api_get(
            path_url=self.trading_pairs_request_path
        )
        all_exchange_info.extend(exchange_info["data"])

        return all_exchange_info

    async def _initialize_trading_pair_symbol_map(self):
        try:
            all_exchange_info = await self._market_data_for_all_product_types()
            self._initialize_trading_pair_symbols_from_exchange_info(exchange_info=all_exchange_info)
        except Exception:
            self.logger().exception("There was an error requesting exchange info.")

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        if "data" in exchange_info:
            exchange_info = exchange_info["data"]
        for symbol_data in filter(kucoin_utils.is_exchange_information_valid, exchange_info):
            try:
                mapping[symbol_data["symbol"]] = combine_to_hb_trading_pair(base=symbol_data["baseCurrency"],
                                                                            quote=symbol_data["quoteCurrency"])
            except ValueDuplicationError:
                # We can safely ignore this, KuCoin API returns a duplicate entry for XBT-USDT
                pass
        self._set_trading_pair_symbol_map(mapping)

    def _resolve_trading_pair_symbols_duplicate(self, mapping: bidict, new_exchange_symbol: str, base: str, quote: str):
        """Resolves name conflicts provoked by futures contracts.

        If the expected BASEQUOTE combination matches one of the exchange symbols, it is the one taken, otherwise,
        the trading pair is removed from the map and an error is logged.
        """
        expected_exchange_symbol = f"{base}{quote}"
        trading_pair = combine_to_hb_trading_pair(base, quote)
        current_exchange_symbol = mapping.inverse[trading_pair]
        if current_exchange_symbol == expected_exchange_symbol:
            pass
        elif new_exchange_symbol == expected_exchange_symbol:
            mapping.pop(current_exchange_symbol)
            mapping[new_exchange_symbol] = trading_pair
        else:
            self.logger().error(f"Could not resolve the exchange symbols {new_exchange_symbol} and {current_exchange_symbol}")
            mapping.pop(current_exchange_symbol)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)

        resp_json = await self._api_get(
            path_url=CONSTANTS.LATEST_SYMBOL_INFORMATION_ENDPOINT.format(symbol=exchange_symbol),
            limit_id=CONSTANTS.LATEST_SYMBOL_INFORMATION_ENDPOINT,
        )

        if type(resp_json["data"]) == list:
            if "lastTradePrice" in resp_json["data"][0]:
                price = float(resp_json["data"][0]["lastTradePrice"])
            else:
                price = float(resp_json["data"][0]["price"])
        else:
            if "lastTradePrice" in resp_json["data"]:
                price = float(resp_json["data"]["lastTradePrice"])
            else:
                price = float(resp_json["data"]["price"])
        return price

    async def _trading_pair_position_mode_set(self, mode: PositionMode, trading_pair: str) -> Tuple[bool, str]:
        msg = ""
        success = True

        if mode == PositionMode.HEDGE:
            msg = "KuCoin Perpetuals don't allow for a position mode change."
            success = False
        else:
            msg = "Success"
            success = True

        return success, msg

    async def _set_trading_pair_leverage(self, trading_pair: str, leverage: int) -> Tuple[bool, str]:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)

        data = {
            "symbol": exchange_symbol,
            "level": leverage
        }

        resp: Dict[str, Any] = await self._api_post(
            path_url=CONSTANTS.SET_LEVERAGE_PATH_URL,
            data=data,
            is_auth_required=True,
            trading_pair=trading_pair,
        )

        success = False
        msg = ""
        if resp["code"] == CONSTANTS.RET_CODE_OK:
            success = True
        else:
            formatted_ret_code = self._format_ret_code_for_print(resp['code'])
            msg = f"{formatted_ret_code} - Some problem"

        return success, msg

    async def _fetch_last_fee_payment(self, trading_pair: str) -> Tuple[int, Decimal, Decimal]:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)

        raw_response: Dict[str, Any] = await self._api_get(
            path_url=CONSTANTS.GET_FUNDING_HISTORY_PATH_URL.format(symbol=exchange_symbol),
            limit_id=CONSTANTS.GET_FUNDING_HISTORY_PATH_URL,
            is_auth_required=True,
            trading_pair=trading_pair,
        )

        if "dataList" in raw_response and len(raw_response["dataList"][0]) == 0:
            # An empty funding fee/payment is retrieved.
            timestamp, funding_rate, payment = 0, Decimal("-1"), Decimal("-1")
        elif "data" in raw_response and len(raw_response["data"]["dataList"]) == 0:
            # An empty funding fee/payment is retrieved.
            timestamp, funding_rate, payment = 0, Decimal("-1"), Decimal("-1")
        else:
            if "dataList" in raw_response:
                data: Dict[str, Any] = raw_response["dataList"][0]
            else:
                data: Dict[str, Any] = raw_response["data"]["dataList"][0]
            funding_rate: Decimal = Decimal(str(data["fundingRate"]))
            position_size: Decimal = Decimal(str(data["positionQty"]))
            payment: Decimal = funding_rate * position_size
            if "timePoint" in data:
                timestamp: int = int(pd.Timestamp(data["timePoint"], tz="UTC").timestamp())
            else:
                timestamp: int = self.current_timestamp
        return timestamp, funding_rate, payment

    async def _api_request(self,
                           path_url,
                           method: RESTMethod = RESTMethod.GET,
                           params: Optional[Dict[str, Any]] = None,
                           data: Optional[Dict[str, Any]] = None,
                           is_auth_required: bool = False,
                           return_err: bool = False,
                           limit_id: Optional[str] = None,
                           trading_pair: Optional[str] = None,
                           currency: Optional[str] = None,
                           exchange_order_id: Optional[str] = None,
                           client_order_id: Optional[str] = None,
                           **kwargs) -> Dict[str, Any]:

        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        if limit_id is None:
            limit_id = web_utils.get_rest_api_limit_id_for_endpoint(
                endpoint=path_url,
            )
        url = web_utils.get_rest_url_for_endpoint(endpoint=path_url,
                                                  domain=self._domain)

        resp = await rest_assistant.execute_request(
            url=url,
            params=params,
            data=data,
            method=method,
            is_auth_required=is_auth_required,
            return_err=return_err,
            throttler_limit_id=limit_id if limit_id else path_url,
        )
        return resp

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        # The default implementation was added when the functionality to detect not found orders was introduced in the
        # ExchangePyBase class. Also fix the unit test test_lost_order_removed_if_not_found_during_order_status_update
        # when replacing the dummy implementation
        return False

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        # The default implementation was added when the functionality to detect not found orders was introduced in the
        # ExchangePyBase class. Also fix the unit test test_cancel_order_not_found_in_the_exchange when replacing the
        # dummy implementation
        return False

    @staticmethod
    def _format_ret_code_for_print(ret_code: Union[str, int]) -> str:
        return f"ret_code <{ret_code}>"
