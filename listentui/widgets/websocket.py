import asyncio
import json
import time
from datetime import datetime, timezone
from logging import getLogger
from typing import Any

import websockets.client as websockets
from rich.console import RenderableType
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.message_pump import MessagePump
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ProgressBar, Static
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from ..data import Theme
from ..listen.types import ListenWsData
from .containers import SongContainer


class DurationCompleteLabel(Static):
    current = reactive(0, layout=True)
    total = reactive(0, layout=True)

    def validate_current(self, value: int | float) -> int:
        if isinstance(value, float):
            return int(value)
        return value

    def validate_total(self, value: int | float) -> int:
        if isinstance(value, float):
            return int(value)
        return value

    def render(self) -> RenderableType:
        m, s = divmod(self.current, 60)
        completed = f"{m:02d}:{s:02d}"

        if self.total != 0:
            m, s = divmod(self.total, 60)
            total = f"{m:02d}:{s:02d}"
            return f"{completed}/{total}"
        return f"{completed}/--:--"


class DurationProgressBar(Widget):
    DEFAULT_CSS = f"""
    DurationProgressBar ProgressBar Bar {{
        width: 1fr;
    }}
    DurationProgressBar ProgressBar {{
        width: 1fr;
    }}
    DurationProgressBar ProgressBar Bar > .bar--indeterminate {{
        color: {Theme.ACCENT};
    }}
    DurationProgressBar ProgressBar Bar > .bar--bar {{
        color: {Theme.ACCENT};
    }}
    DurationProgressBar DurationCompleteLabel {{
        width: auto;
        margin: 0 2 0 2;
    }}
    """

    current = reactive(0)
    total = reactive(0)

    def __init__(self) -> None:
        self.timer = MessagePump().set_interval(1, self._update_progress)
        self.time_end = 0
        super().__init__()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield ProgressBar(show_eta=False, show_percentage=False)
            yield DurationCompleteLabel()

    def on_unmount(self) -> None:
        self.timer.stop()

    def _update_progress(self) -> None:
        self.current += 1

    def update_progress(self, data: ListenWsData):
        # TODO: sometime this is inaccurate? i dont know whats wrong
        self.time_end = data.song.time_end
        if data.song.duration:
            self.current = (datetime.now(timezone.utc) - data.start_time).total_seconds()
        else:
            self.current = 0
        self.total = data.song.duration or 0

        self.query_one(ProgressBar).update(total=self.total if self.total != 0 else None, progress=self.current)

    def watch_current(self, new: int) -> None:
        self.query_one(DurationCompleteLabel).current = new
        self.query_one(ProgressBar).advance(1)

    def watch_total(self, new: int) -> None:
        self.query_one(DurationCompleteLabel).total = new


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
                            self.query_one(DurationProgressBar).update_progress(self._data)
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
                continue

    @work(exclusive=True, group="ws_keepalive")
    async def ws_keepalive(self, interval: int = 35) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await self._ws.send(json.dumps({"op": 9}))
        except (ConnectionClosedOK, ConnectionError):
            return
