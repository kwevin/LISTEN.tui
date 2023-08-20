import asyncio
import json
import time
from typing import Any, Callable

import websockets.client as websockets
from rich.pretty import pretty_repr
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from src.listen.types import ListenWsData
from src.module import Module


class ListenWebsocket(Module):
    def __init__(self) -> None:
        super().__init__()
        self._data: ListenWsData
        self.ws_data: dict[Any, Any] = dict()
        self.loop = asyncio.new_event_loop()
        self.last_heartbeat = time.time()
        self.update_able: list[Callable[[ListenWsData], Any]] = list()

    @property
    def data(self) -> ListenWsData:
        return self._data
    
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
                            self.loop.create_task(self.ws_keepalive(heartbeat))
                            self.update_status(True)
                            
                        case 1:
                            self._log.info(f"Data Received: {pretty_repr(self.ws_data)}")
                            self._data = ListenWsData.from_data(self.ws_data)
                            self._log.info(f"Data Formatted: {pretty_repr(self.data)}")
                            await self.update_update_able()
                        case 10:
                            self._data.last_heartbeat = time.time()

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
