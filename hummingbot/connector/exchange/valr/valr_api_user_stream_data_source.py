import asyncio

from typing import TYPE_CHECKING, List, Optional

from hummingbot.connector.exchange.valr import valr_constants as CONSTANTS, valr_web_utils as web_utils
from hummingbot.connector.exchange.valr.valr_auth import ValrAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.valr.valr_exchange import ValrExchange


class ValrAPIUserStreamDataSource(UserStreamTrackerDataSource):

    HEARTBEAT_TIME_INTERVAL = 20.0

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: ValrAuth,
                 trading_pairs: List[str],
                 connector: 'ValrExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__()
        self._auth: ValrAuth = auth
        self._current_listen_key = None
        self._domain = domain
        self._api_factory = api_factory
        self._listen_key_initialized_event: asyncio.Event = asyncio.Event()
        self._last_listen_key_ping_ts = 0
        self._last_ws_message_sent_timestamp = 0

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Creates an instance of WSAssistant connected to the exchange
        """

        ws: WSAssistant = await self._get_ws_assistant()
        url = f"{CONSTANTS.WSS_URL.format(CONSTANTS.WSS_ACCOUNT_PATH_URL)}"
        headers = self._auth.header_for_authentication("GET", CONSTANTS.WSS_ACCOUNT_PATH_URL)
        await ws.connect(ws_url=url, ws_headers=headers)
        return ws

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant, queue: asyncio.Queue):
        while True:
            try:
                seconds_until_next_ping = CONSTANTS.WSS_PING_INTERVAL - (self._time() - self._last_ws_message_sent_timestamp)
                await asyncio.wait_for(
                    super()._process_websocket_messages(
                        websocket_assistant=websocket_assistant, queue=queue),
                    timeout=seconds_until_next_ping)
            except asyncio.TimeoutError:
                payload = {
                    "type": "PING",
                }
                ping_request = WSJSONRequest(payload=payload)
                self._last_ws_message_sent_timestamp = self._time()
                await websocket_assistant.send(request=ping_request)

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.

        Valr Account WSS does not require any channel subscription.

        :param websocket_assistant: the websocket assistant used to connect to the exchange
        """
        pass

    async def _get_ws_assistant(self) -> WSAssistant:
        if self._ws_assistant is None:
            self._ws_assistant = await self._api_factory.get_ws_assistant()
        return self._ws_assistant

    async def _on_user_stream_interruption(self, websocket_assistant: Optional[WSAssistant]):
        await super()._on_user_stream_interruption(websocket_assistant=websocket_assistant)
        await self._sleep(5)
