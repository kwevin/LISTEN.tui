import asyncio
import json
import threading
import time
from logging import Logger
from typing import Any

import websockets.client as websockets
from rich.pretty import pretty_repr
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from src.interface import Interface
from src.module.presence import DiscordRichPresence
from src.module.types import ListenWsData, Status


class ListenMoe(threading.Thread):
    def __init__(self, interface: Interface, log: Logger, presence: bool = True) -> None:
        super().__init__()
        self.interface = interface
        self.log = log
        self._presence: bool = presence
        self.ws_data: dict[Any, Any] = dict()
        self.status = Status(False, 'Initialising')
        self.loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self.last_heartbeat = time.time()

    def run(self) -> None:
        while True:
            try:
                self.loop.run_until_complete(self.main())
            except Exception:
                self.log.exception("Exception occured")
                continue
    
    async def update_status(self, status: bool, reason: str = ""):
        self.status.running = status
        self.status.reason = reason
        self.interface.update_status('Websocket', self.status)

    async def ws_keepalive(self, interval: int = 35) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.ws.send(json.dumps({'op': 9}))
    
    async def run_presence(self) -> None:
        await self.presence.connect()

    async def main(self) -> None:
        if self._presence:
            self.presence = DiscordRichPresence(self.log)
            self.loop.create_task(self.run_presence())
        async for self.ws in websockets.connect('wss://listen.moe/gateway_v2', ping_interval=None, ping_timeout=None):
            try:
                while True:
                    self.ws_data = json.loads(await self.ws.recv())
                    match self.ws_data['op']:
                        case 0:
                            heartbeat = self.ws_data['d']['heartbeat'] / 1000
                            self.loop.create_task(self.ws_keepalive(heartbeat))
                            await self.update_status(True)
                            
                        case 1:
                            self.log.info(f"Data Received: {pretty_repr(self.ws_data)}")
                            self.data = ListenWsData(self.ws_data)
                            if self.presence:
                                if self.presence.status.running:
                                    res = await self.presence.update(self.data.song)
                                    self.data.rpc = res
                            self.log.info(f"Data Formatted: {pretty_repr(self.data)}")
                            self.interface.update_data(self.data)

                        case 10:
                            self.data.last_heartbeat = time.time()
                            self.interface.update_data(self.data)

                        case _:
                            pass
            except ConnectionClosedOK:
                await self.update_status(False, "Websocket Connection Closed")
                return
            except ConnectionClosedError:
                await self.update_status(False, "Websocket Connection Closed Error")
                self.log.exception("Connection Closed Error")
                continue
