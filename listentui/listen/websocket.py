import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

import websockets.client as websockets
from rich.pretty import pretty_repr
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from ..modules.baseModule import BaseModule
from .types import ListenWsData


class ListenWebsocket(BaseModule):
    def __init__(self) -> None:
        super().__init__()
        self._data: ListenWsData
        self.ws_data: dict[Any, Any] = {}
        self.loop = asyncio.new_event_loop()
        self._last_heartbeat = time.time()
        self.update_able: list[Callable[[ListenWsData], Any]] = []

    @property
    def data(self) -> ListenWsData:
        return self._data

    @property
    def last_heartbeat(self) -> float:
        return self._last_heartbeat

    def on_data_update(self, method: Callable[[ListenWsData], Any]) -> None:
        self.update_able.append(method)

    async def update_update_able(self) -> None:
        for method in self.update_able:
            method(self._data)

    def run(self) -> None:
        while self._running:
            try:
                self.loop.run_until_complete(self.main())
            except Exception:
                self._log.exception("Exception occured")
                continue

    async def ws_keepalive(self, interval: int = 35) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.ws.send(json.dumps({'op': 9}))

    async def main(self) -> None:
        async for self.ws in websockets.connect('wss://listen.moe/gateway_v2', ping_interval=None, ping_timeout=None):
            try:
                while self._running:
                    self.ws_data = json.loads(await self.ws.recv())
                    match self.ws_data['op']:
                        case 0:
                            heartbeat = self.ws_data['d']['heartbeat'] / 1000
                            asyncio.create_task(self.ws_keepalive(heartbeat), name='ws_keepalive')

                        case 1:
                            self._log.info(f"Data Received: {pretty_repr(self.ws_data)}")
                            self._data = ListenWsData.from_data(self.ws_data)
                            self._log.info(f"Data Formatted: {pretty_repr(self.data)}")
                            if not self._data.last_played[0].duration:
                                self._data.start_time = datetime.now(timezone.utc)
                            self.update_status(True)
                            asyncio.create_task(self.update_update_able())
                        case 10:
                            self._last_heartbeat = time.time()

                        case _:
                            pass
                else:
                    await self.ws.close()

            except ConnectionClosedOK:
                self.update_status(False, "Websocket Connection Closed")
                return
            except ConnectionClosedError:
                self.update_status(False, "Websocket Connection Closed Error")
                self._log.exception("Connection Closed Error")
                continue
