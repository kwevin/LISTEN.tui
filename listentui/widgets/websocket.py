import asyncio
import json
import time

# from datetime import datetime, timezone
from logging import getLogger
from typing import Any

import websockets.client as websockets
from textual import work
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from ..data import Theme
from ..listen.types import ListenWsData
from .custom import DurationProgressBar, SongContainer


class ListenWebsocket(Widget):
    DEFAULT_CSS = f"""
    ListenWebsocket {{
        align: left middle;
        height: 5;
        padding: 1 1 1 2;
        background: {Theme.BUTTON_BACKGROUND};
    }}
    """

    class Updated(Message):
        def __init__(self, data: ListenWsData) -> None:
            super().__init__()
            self.data = data

    class ConnectionClosed(Message):
        def __init__(self) -> None:
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self._data: ListenWsData | None = None
        self._ws_data: dict[str, Any] = {}
        self._log = getLogger(__name__)

    @property
    def data(self):
        return self._data

    def compose(self) -> ComposeResult:
        yield SongContainer()
        yield DurationProgressBar()

    def on_mount(self) -> None:
        self.loading = True
        self.websocket()

    @work(exclusive=True, group="websocket")
    async def websocket(self) -> None:
        async for self._ws in websockets.connect("wss://listen.moe/gateway_v2", ping_interval=None, ping_timeout=None):
            try:
                while True:
                    self._ws_data: dict[str, Any] = json.loads(await self._ws.recv())
                    match self._ws_data["op"]:
                        case 1:
                            self._data = ListenWsData.from_data(self._ws_data)
                            self.query_one(DurationProgressBar).update_progress(self._data.song)
                            self.post_message(self.Updated(self._data))
                            self.query_one(SongContainer).song = self._data.song
                        case 0:
                            self.loading = False
                            self.keepalive = self.ws_keepalive(self._ws_data["d"]["heartbeat"] / 1000)
                        case 10:
                            self._last_heartbeat = time.time()
                        case _:
                            pass
            except ConnectionClosedOK:
                return
            except ConnectionClosedError:
                self._log.exception("Websocket Connection Closed Unexpectedly")
                self.keepalive.cancel()
                self.post_message(self.ConnectionClosed())
                continue

    @work(exclusive=True, group="ws_keepalive")
    async def ws_keepalive(self, interval: int = 35) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await self._ws.send(json.dumps({"op": 9}))
        except (ConnectionClosedOK, ConnectionError):
            return
