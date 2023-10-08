import asyncio
import functools
import logging
from collections import defaultdict
from decimal import Decimal
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    Generator,
    List,
    NamedTuple,
    Protocol,
    Tuple,
    Type,
)

from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSRequest, WSResponse
from hummingbot.logger import HummingbotLogger

from .coinbase_advanced_trade_v2_web_utils import get_timestamp_from_exchange_time
from .pipe import PipeGetPtl
from .pipeline import PipeBlock, PipesCollector
from .stream_data_source import StreamAction, StreamDataSource, StreamState, SubscriptionBuilderT
from .task_manager import TaskState


class CoinbaseAdvancedTradeV2CumulativeUpdate(NamedTuple):
    client_order_id: str
    exchange_order_id: str
    status: str
    trading_pair: str
    fill_timestamp: float  # seconds
    average_price: Decimal
    cumulative_base_amount: Decimal
    remainder_base_amount: Decimal
    cumulative_fee: Decimal
    is_taker: bool = False  # Coinbase Advanced Trade delivers trade events from the maker's perspective


async def _message_to_cumulative_update(
        event_message: Dict[str, Any],
        *,
        symbol_to_pair: Callable[[str], Coroutine[Any, Any, str]],
) -> AsyncGenerator[CoinbaseAdvancedTradeV2CumulativeUpdate, None]:
    """
    Streamline the messages for processing by the exchange.
    :param event_message: The message received from the exchange.
    """
    """
    https://docs.cloud.coinbase.com/advanced-trade-api/docs/ws-channels#user-channel
    {
      "channel": "user",
      "client_id": "",
      "timestamp": "2023-02-09T20:33:57.609931463Z",
      "sequence_num": 0,
      "events": [
        {
          "type": "snapshot",
          "orders": [
            {
              "order_id": "XXX",
              "client_order_id": "YYY",
              "cumulative_quantity": "0",
              "leaves_quantity": "0.000994",
              "avg_price": "0",
              "total_fees": "0",
              "status": "OPEN",
              "product_id": "BTC-USD",
              "creation_time": "2022-12-07T19:42:18.719312Z",
              "order_side": "BUY",
              "order_type": "Limit"
            },
          ]
        }
      ]
    }
    """
    # logging.debug(f"Cumulative handler received event {event_message}")
    # The timestamp may have been updated by the sequencer or another pipe
    if not isinstance(event_message["timestamp"], float):
        event_message["timestamp"] = get_timestamp_from_exchange_time(event_message["timestamp"], "second")

    timestamp_s: float = event_message["timestamp"]
    for event in event_message.get("events"):
        for order in event["orders"]:
            try:
                cumulative_order = CoinbaseAdvancedTradeV2CumulativeUpdate(
                    exchange_order_id=order["order_id"],
                    client_order_id=order["client_order_id"],
                    status=order["status"],
                    trading_pair=await symbol_to_pair(order["product_id"]),
                    fill_timestamp=timestamp_s,
                    average_price=Decimal(order["avg_price"]),
                    cumulative_base_amount=Decimal(order["cumulative_quantity"]),
                    remainder_base_amount=Decimal(order["leaves_quantity"]),
                    cumulative_fee=Decimal(order["total_fees"]),
                )
                yield cumulative_order
            except Exception as e:
                logging.error(f"Failed to create a CumulativeUpdate error {e}")
                logging.error(f"\n\t{order}")
                raise e


def _timestamp_filter_sequence(event_message: Dict[str, Any],
                               *,
                               sequencer: Callable[[int, str], Any]
                               ) -> Generator[CoinbaseAdvancedTradeV2CumulativeUpdate, None, None]:
    """
    Reformat the timestamp to seconds.
    Filter out heartbeat and (subscriptions?) messages.
    Call the sequencer to track the sequence number.
    :param event_message: The message received from the exchange.
    """
    """
    https://docs.cloud.coinbase.com/advanced-trade-api/docs/ws-channels#user-channel
    {
      "channel": "user",
      "client_id": "",
      "timestamp": "2023-02-09T20:33:57.609931463Z",
      "sequence_num": 0,
      "events": [...]
    }
    """
    # logging.debug(f"   DEBUG: Sequence handler {event_message}")
    if event_message["channel"] == "user":
        sequencer(event_message["sequence_num"], event_message["channel"])

        # logging.debug(f"      DEBUG: Filter {event_message}")
        if isinstance(event_message["timestamp"], str):
            event_message["timestamp"] = get_timestamp_from_exchange_time(event_message["timestamp"], "second")
        yield event_message
    # else:
    #     logging.debug(f"*** DEBUG: Filtering message {event_message} {event_message['channel']} not user")


async def _collect_cumulative_update(
        event_message: CoinbaseAdvancedTradeV2CumulativeUpdate,
) -> AsyncGenerator[CoinbaseAdvancedTradeV2CumulativeUpdate, None]:
    # Filter-out non-CumulativeUpdate messages
    if isinstance(event_message, CoinbaseAdvancedTradeV2CumulativeUpdate):
        yield event_message
    else:
        logging.debug(f"*** DEBUG: Collect skipping {event_message} {type(event_message)}")


class WSAssistantPtl(Protocol):
    async def connect(
            self,
            ws_url: str,
            *,
            ping_timeout: float,
            message_timeout: float | None = None,
            ws_headers: Dict[str, Any] | None = None,
    ) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def send(self, request: WSRequest) -> None:
        ...

    async def ping(self) -> None:
        ...

    async def receive(self) -> WSResponse | None:
        ...

    @property
    def last_recv_time(self) -> float:
        return ...

    async def iter_messages(self) -> AsyncGenerator[WSResponse | None, None]:
        yield ...


class CoinbaseAdvancedTradeV2APIUserStreamDataSource(UserStreamTrackerDataSource):
    """
    UserStreamTrackerDataSource implementation for Coinbase Advanced Trade API.
    """

    _logger: HummingbotLogger | logging.Logger | None = None
    _indenting_logger: HummingbotLogger | logging.Logger | None = None

    @classmethod
    def logger(cls) -> HummingbotLogger | logging.Logger:
        try:
            from hummingbot.logger.indenting_logger import IndentingLogger
            if cls._indenting_logger is None:
                if cls._logger is not None:
                    cls._indenting_logger = IndentingLogger(cls._logger, cls.__name__)
                else:
                    name: str = HummingbotLogger.logger_name_for_class(cls)
                    cls._indenting_logger = IndentingLogger(logging.getLogger(name), cls.__name__)
            cls._indenting_logger.refresh_handlers()
            return cls._indenting_logger
        except ImportError:
            if cls._logger is None:
                name: str = HummingbotLogger.logger_name_for_class(cls)
                cls._logger = logging.getLogger(name)
            return cls._logger

    __slots__ = (
        "_stream_to_queue",
    )

    def __init__(
            self,
            channels: Tuple[str, ...],
            pairs: Tuple[str, ...],
            ws_factory: Callable[[], Coroutine[Any, Any, WSAssistantPtl]],
            ws_url: str,
            pair_to_symbol: Callable[[str], Coroutine[Any, Any, str]] | None,
            symbol_to_pair: Callable[[str], Coroutine[Any, Any, str]] | None,
            heartbeat_channel: str | None = None,
    ) -> None:
        """
        Initialize the Coinbase Advanced Trade API user stream data source.

        :param channels: The channels to subscribe to.
        :param pairs: The trading pairs to subscribe to.
        :param ws_factory: The factory function to create a websocket connection.
        :param ws_url: The websocket URL.
        :param pair_to_symbol: The function to convert a trading pair to a symbol.
        :param symbol_to_pair: The function to convert a symbol to a trading pair.
        :param heartbeat_channel: The channel to send heartbeat messages to.
        """
        super().__init__()
        self._stream_to_queue: _MultiStreamDataSource = _MultiStreamDataSource(
            channels=channels,
            pairs=pairs,
            ws_factory=ws_factory,
            ws_url=ws_url,
            pair_to_symbol=pair_to_symbol,
            symbol_to_pair=symbol_to_pair,
            subscription_builder=coinbase_advanced_trade_v2_subscription_builder,
            heartbeat_channel=heartbeat_channel,
        )

    async def _connected_websocket_assistant(self):
        raise NotImplementedError("This method is not implemented.")

    async def _subscribe_channels(self, websocket_assistant):
        raise NotImplementedError("This method is not implemented.")

    @property
    def last_recv_time(self) -> float:
        """
        Returns the time of the last received message

        :return: the timestamp of the last received message in seconds
        """
        return self._stream_to_queue.last_recv_time

    async def listen_for_user_stream(self, output: asyncio.Queue[CoinbaseAdvancedTradeV2CumulativeUpdate]):
        with self.logger().ctx_indentation("Listening to Coinbase Advanced Trade user stream...", bullet="["):
            await self._stream_to_queue.open()
            await self._stream_to_queue.start_stream()
            await self._stream_to_queue.subscribe()

            while True:
                message: CoinbaseAdvancedTradeV2CumulativeUpdate = await self._stream_to_queue.queue.get()
                # Filter-out non-CumulativeUpdate messages
                if isinstance(message, CoinbaseAdvancedTradeV2CumulativeUpdate):
                    await output.put(message)
                else:
                    raise ValueError(f"Invalid message type: {type(message)} {message}")


CollectorT: Type = PipesCollector[Dict[str, Any], CoinbaseAdvancedTradeV2CumulativeUpdate]


async def coinbase_advanced_trade_v2_subscription_builder(
        *,
        action: StreamAction,
        channel: str,
        pair: str,
        pair_to_symbol: Callable[[str], Awaitable[str]]) -> Dict[str, Any]:
    """
    Build the subscription message for Coinbase Advanced Trade API.
    :param action: The action to perform.
    :param channel: The channel to subscribe to.
    :param pair: The trading pair to subscribe to.
    :param pair_to_symbol: The function to convert trading pair to symbol.
    :return: The subscription message.

    https://docs.cloud.coinbase.com/advanced-trade-api/docs/ws-overview
    {
        "type": "subscribe",
        "product_ids": [
            "ETH-USD",
            "ETH-EUR"
        ],
        "channel": "level2",
        "api_key": "exampleApiKey123",
        "timestamp": 1660838876,
        "signature": "00000000000000000000000000",
    }
    """

    if action == StreamAction.SUBSCRIBE:
        _type = "subscribe"
    elif action == StreamAction.UNSUBSCRIBE:
        _type = "unsubscribe"
    else:
        raise ValueError(f"Invalid action: {action}")
    return {
        "type": _type,
        "product_ids": [await pair_to_symbol(pair)],
        "channel": channel,
    }


class _MultiStreamDataSource:
    """
    _MultiStreamDataSource implementation for Coinbase Advanced Trade API.
    """
    _logger: HummingbotLogger | logging.Logger | None = None
    _indenting_logger: HummingbotLogger | logging.Logger | None = None

    @classmethod
    def logger(cls) -> HummingbotLogger | logging.Logger:
        try:
            from hummingbot.logger.indenting_logger import IndentingLogger
            if cls._indenting_logger is None:
                if cls._logger is not None:
                    cls._indenting_logger = IndentingLogger(cls._logger, cls.__name__)
                else:
                    name: str = HummingbotLogger.logger_name_for_class(cls)
                    cls._indenting_logger = IndentingLogger(logging.getLogger(name), cls.__name__)
            cls._indenting_logger.refresh_handlers()
            return cls._indenting_logger
        except ImportError:
            if cls._logger is None:
                name: str = HummingbotLogger.logger_name_for_class(cls)
                cls._logger = logging.getLogger(name)
            return cls._logger

    __slots__ = (
        "_streams",
        "_sequences",
        "_transformers",
        "_collector",
        "_ws_factory",
        "_pair_to_symbol",
        "_last_recv_time",
        "_stream_state",
    )

    def __init__(self,
                 *,
                 channels: Tuple[str, ...],
                 pairs: Tuple[str, ...],
                 ws_factory: Callable[[], Coroutine[Any, Any, WSAssistantPtl]],
                 ws_url: str,
                 pair_to_symbol: Callable[[str], Coroutine[Any, Any, str]],
                 symbol_to_pair: Callable[[str], Coroutine[Any, Any, str]],
                 subscription_builder: SubscriptionBuilderT,
                 heartbeat_channel: str | None = None) -> None:
        """
        Initialize the CoinbaseAdvancedTradeAPIUserStreamDataSource.

        :param Tuple channels: Channel to subscribe to.
        :param Tuple pairs: symbol to subscribe to.
        :param ws_factory: The method for creating the WSAssistant.
        :param pair_to_symbol: Async function to convert the pair to symbol.
        """

        def sequencer(s: int, c: str, sequences: Dict[str, int], key: str) -> None:
            """
            Check the sequence number and increment it.
            """
            assert isinstance(s, int), f"Sequence number should be int, not {type(s)}"
            assert isinstance(c, str), f"Channel should be str, not {type(c)}"
            assert isinstance(sequences, dict), f"Sequences should be dict, not {type(sequences)}"
            assert isinstance(key, str), f"Key should be str, not {type(key)}"

            if s != sequences[key] + 1:
                self.logger().warning(
                    f"Sequence number mismatch. Expected {sequences[key] + 1}, received {s} for {key}"
                    f"\n      channel: {c}")
                # This should never occur, it indicates a flaw in the code
                if s < sequences[key]:
                    raise ValueError(
                        f"Sequence number lower than expected {sequences[key] + 1}, received {s} for {key}")
            sequences[key] = s

        self._streams: Dict[str, StreamDataSource] = {}
        self._transformers: Dict[str, List[PipeBlock]] = {}
        self._sequences: defaultdict[str, int] = defaultdict(int)

        for channel in channels:
            for pair in pairs:
                channel_pair = self._stream_key(channel=channel, pair=pair)

                # Create the StreamDataSource, websocket to queue
                self._streams[channel_pair] = StreamDataSource(
                    channel=channel,
                    pair=pair,
                    ws_factory=ws_factory,
                    ws_url=ws_url,
                    pair_to_symbol=pair_to_symbol,
                    subscription_builder=subscription_builder,
                    heartbeat_channel=heartbeat_channel,
                )

                # Create the PipeBlocks that transform the messages
                self._transformers[channel_pair]: List[PipeBlock] = []

                # Create the sequencer: How to verify the sequence number and update it
                sequencer = functools.partial(sequencer, sequences=self._sequences, key=channel_pair)

                # Create the callable to pass as a handler to the PipeBlock
                timestamp_filter_sequence = functools.partial(_timestamp_filter_sequence, sequencer=sequencer)

                # Create the callable to pass as a handler to the PipeBlock
                message_to_cumulative_update = functools.partial(
                    _message_to_cumulative_update,
                    symbol_to_pair=symbol_to_pair)

                # Create the PipeBlocks that transforms the messages
                self._transformers[channel_pair].append(
                    PipeBlock[Dict[str, Any], Dict[str, Any]](
                        self._streams[channel_pair].destination,
                        timestamp_filter_sequence))

                self._transformers[channel_pair].append(
                    PipeBlock[Dict[str, Any], CoinbaseAdvancedTradeV2CumulativeUpdate](
                        self._transformers[channel_pair][-1].destination,
                        message_to_cumulative_update,
                    ))

        self._collector: CollectorT = CollectorT(
            sources=tuple(self._transformers[t][-1].destination for t in self._transformers),
            handler=_collect_cumulative_update,
        )

    @staticmethod
    def _stream_key(*, channel: str, pair: str) -> str:
        return f"{channel}:{pair}"

    @property
    def queue(self) -> PipeGetPtl[CoinbaseAdvancedTradeV2CumulativeUpdate]:
        return self._collector.destination

    @property
    def states(self) -> List[Tuple[StreamState, TaskState]]:
        return [self._streams[t].state for t in self._streams]

    @property
    def last_recv_time(self) -> float:
        """
        Returns the time of the last received message

        :return: the timestamp of the last received message in seconds
        """
        self.logger().debug(
            f"Last recv time: {min((self._streams[t].last_recv_time for t in self._streams))} {max((self._streams[t].last_recv_time for t in self._streams))}")
        return min((self._streams[t].last_recv_time for t in self._streams))

    async def open(self) -> None:
        """Initialize all the streams, subscribe to heartbeats channels"""
        stream: StreamDataSource
        self.logger().debug("Opening User stream (gather)")
        # await asyncio.gather(*[stream.open_connection() for stream in self._streams.values()])
        for stream in list(self._streams.values()):
            await stream.open_connection()
            if stream.state[0] != StreamState.OPENED:
                self.logger().warning(f"Stream {stream.channel}:{stream.pair} failed to open.")
                await stream.close_connection()
                self._streams.pop(self._stream_key(channel=stream.channel, pair=stream.pair), None)
        self.logger().debug("Done opening")

    async def close(self) -> None:
        """Close all the streams"""
        for stream in list(self._streams.values()):
            await stream.close_connection()

    async def subscribe(self) -> None:
        """Subscribe to all the streams"""
        self.logger().debug("Subscribing User stream (gather)")
        # await asyncio.gather(*[stream.subscribe() for stream in self._streams.values()])
        for stream in list(self._streams.values()):
            await stream.subscribe()
            if stream.state[0] != StreamState.SUBSCRIBED:
                self.logger().warning(f"Stream {stream.channel}:{stream.pair} failed to subscribe.")
                await stream.close_connection()
                self._streams.pop(self._stream_key(channel=stream.channel, pair=stream.pair), None)
            self.logger().info(f"'->Subscribed User stream {stream.channel}:{stream.pair} opening.")
        self.logger().debug("Done subscribing")

    async def unsubscribe(self) -> None:
        """Unsubscribe to all the streams"""
        for stream in list(self._streams.values()):
            await stream.unsubscribe()
            if stream.state[0] != StreamState.UNSUBSCRIBED:
                self.logger().warning(f"Stream {stream.channel}:{stream.pair} failed to unsubscribe.")
                await stream.close_connection()

    async def start_stream(self) -> None:
        """Listen to all the streams and put the messages to the output queue."""
        await self._collector.start_task()
        for key in self._streams:
            for transformer in reversed(self._transformers[key]):
                await transformer.start_task()
            await self._streams[key].open_connection()
            await self._streams[key].start_task()

    async def stop_stream(self) -> None:
        """Listen to all the streams and put the messages to the output queue."""
        for key in self._streams:
            await self._streams[key].close_connection()
            await self._streams[key].stop_stream()
        await self._collector.stop_task()
