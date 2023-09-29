# type: ignore
import asyncio
import os
import time
from json import JSONDecodeError
from string import Template
from threading import RLock
from typing import Any

from pypresence import AioPresence, DiscordNotFound
from pypresence.exceptions import ResponseTimeout
from pypresence.payloads import Payload
from rich.pretty import pretty_repr

from ..config import Config
from ..listen.types import ListenWsData, Song
from ..modules.baseModule import BaseModule
from .types import Activity, Rpc


class AioPresence(AioPresence):

    async def update(self, pid: int = os.getpid(),
                     state: str = None, details: str = None,
                     start: int = None, end: int = None,
                     large_image: str = None, large_text: str = None,
                     small_image: str = None, small_text: str = None,
                     party_id: str = None, party_size: list = None,
                     join: str = None, spectate: str = None,
                     match: str = None, buttons: list = None,
                     instance: bool = True, type: int = None) -> dict[str, Any]:
        payload = Payload.set_activity(pid=pid, state=state, details=details, start=start, end=end,
                                       large_image=large_image, large_text=large_text,
                                       small_image=small_image, small_text=small_text, party_id=party_id,
                                       party_size=party_size, join=join, spectate=spectate,
                                       match=match, buttons=buttons, instance=instance, type=type, activity=True)
        self.send_data(1, payload)
        return await self.read_output()


class Payload(Payload):

    @classmethod
    def set_activity(cls, pid: int = os.getpid(),
                     state: str = None, details: str = None,
                     start: int = None, end: int = None,
                     large_image: str = None, large_text: str = None,
                     small_image: str = None, small_text: str = None,
                     party_id: str = None, party_size: list = None,
                     join: str = None, spectate: str = None,
                     match: str = None, buttons: list = None,
                     instance: bool = True, type: int = None,
                     activity: bool | None = True, _rn: bool = True):
        if start:
            start = int(start)
        if end:
            end = int(end)

        if activity is None:
            act_details = None
            clear = True
        else:
            act_details = {
                "state": state,
                "details": details,
                "timestamps": {
                    "start": start,
                    "end": end
                },
                "assets": {
                    "large_image": large_image,
                    "large_text": large_text,
                    "small_image": small_image,
                    "small_text": small_text
                },
                "party": {
                    "id": party_id,
                    "size": party_size
                },
                "secrets": {
                    "join": join,
                    "spectate": spectate,
                    "match": match
                },
                "buttons": buttons,
                "type": type,
                "instance": instance
            }
            clear = False

        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": pid,
                "activity": act_details
            },
            "nonce": '{:.20f}'.format(cls.time())
        }
        if _rn:
            clear = _rn
        return cls(payload, clear)


class DiscordRichPresence(BaseModule):
    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.presence = AioPresence(1042365983957975080)
        self.is_arrpc: bool = False
        self.config = Config.get_config().rpc
        self.romaji_first = Config.get_config().display.romaji_first
        self.separator = Config.get_config().display.separator
        self.song: Song
        self._lock = RLock()
        self._data: Rpc

    @property
    def data(self) -> Rpc:
        return self._data

    @staticmethod
    async def get_epoch_end_time(duration: int | None) -> int | None:
        if not duration:
            return None
        return int(round(time.time() + duration))

    async def sanitise(self, string: str) -> str:
        default: str = self.config.default_placeholder

        if len(string.strip()) < 2:
            string += default
            return string.strip()
        if len(string) >= 128:
            return f'{string[0:125]}...'.strip()
        return string.strip()

    async def get_detail(self) -> str | None:
        detail = Template(self.config.detail).substitute(self.song_dict)
        if len(detail) == 0:
            return None
        return await self.sanitise(detail)

    async def get_state(self) -> str | None:
        state = Template(self.config.state).substitute(self.song_dict)
        if len(state) == 0:
            return None
        return await self.sanitise(state)

    async def get_large_image(self) -> str | None:
        use_fallback: bool = self.config.use_fallback
        fallback: str = self.config.fallback
        use_artist: bool = self.config.use_artist

        image = self.song.album_image()
        if not image and use_artist:
            image = self.song.artist_image()
            if not image:
                return fallback if use_fallback else None
            return image
        if not image and not use_fallback:
            return image
        return image

    async def get_large_text(self) -> str | None:
        large_text = Template(self.config.large_text).substitute(self.song_dict)
        if len(large_text) == 0:
            return None
        return await self.sanitise(large_text)

    async def get_small_image(self) -> str | None:
        use_artist = self.config.show_small_image
        if not use_artist:
            return None
        return self.song.artist_image()

    async def get_small_text(self) -> str | None:
        small_text = Template(self.config.small_text).substitute(self.song_dict)
        if len(small_text.strip()) == 0:
            return None
        return await self.sanitise(small_text)

    async def get_button(self) -> list[dict[str, str]]:
        return [{"label": "Join radio", "url": "https://listen.moe/"}]

    async def create_dict(self, song: Song) -> dict[str, Any]:
        source_string = song.format_source(self.romaji_first)
        if source_string:
            source_string = f'[{source_string}]'
        song_dict = {
            "id": song.id,
            "title": song.title,
            "source": source_string,
            "source_image": song.source_image(),
            "artist": song.format_artists(romaji_first=self.romaji_first, sep=self.separator),
            "artist_image": song.artist_image(),
            "album": song.format_album(self.romaji_first),
            "album_image": song.album_image()
        }
        for k, v in song_dict.items():
            if not v:
                song_dict[k] = ''
        return song_dict

    async def connect(self):
        while self._running:
            try:
                with self._lock:
                    await self.presence.connect()
                self.update_status(True)
            except DiscordNotFound:
                self.update_status(True)
                self._log.info("Discord Not Found")
                await asyncio.sleep(120)
            except JSONDecodeError:
                continue
            while self.status.running:
                await asyncio.sleep(1)

    def run(self):
        self.loop.run_until_complete(self.connect())

    def update(self, data: ListenWsData):
        with self._lock:
            self.loop.create_task(self.aio_update(data))

    async def aio_update(self, data: ListenWsData | Rpc) -> None:
        with self._lock:
            if isinstance(data, ListenWsData):
                self.song: Song = data.song
                self.song_dict = await self.create_dict(self.song)
                self._data = Rpc(
                    is_arrpc=self.is_arrpc,
                    detail=await self.get_detail(),
                    state=await self.get_state(),
                    end=await self.get_epoch_end_time(self.song.duration),
                    large_image=await self.get_large_image(),
                    large_text=await self.get_large_text(),
                    small_image=await self.get_small_image(),
                    small_text=await self.get_small_text(),
                    buttons=await self.get_button(),
                    type=Activity.LISTENING if self.is_arrpc else Activity.PLAYING
                )
            else:
                self._data = data
            self._log.info(f'Updating presence: {pretty_repr(self.data)}')

            try:
                res = await self.presence.update(
                    details=self.data.detail,
                    state=self.data.state,
                    end=self.data.end if self.config.show_time_left else None,
                    large_image=self.data.large_image,
                    large_text=self.data.large_text,
                    small_image=self.data.small_image if self.data.small_image != self.data.large_image else None,
                    small_text=self.data.small_text,
                    buttons=self.data.buttons,
                    type=self.data.type
                )
                self._log.info(f'RPC output: {pretty_repr(res)}')

                if not res.get('data', None) and not self.is_arrpc:
                    self._log.info('arRPC detected')
                    self.is_arrpc = True
                    self.data.is_arrpc = True
                    self.data.type = Activity.LISTENING
                    await self.aio_update(self.data)
                elif res.get('data', None) and self.is_arrpc:
                    self._log.info('Using normal discord rpc')
                    self.is_arrpc = False
                    self.data.is_arrpc = False
                    self.data.type = Activity.PLAYING
                    await self.aio_update(self.data)

            except BrokenPipeError:
                self.update_status(False, "BrokenPipeError")
                self._log.info("[RPC] BrokenPipeError")
            except (ResponseTimeout, asyncio.exceptions.CancelledError, TimeoutError):
                self.update_status(False, "RPC Response Timeout")
                self._log.info("[RPC] TimeoutError")
            except Exception as exc:
                self.update_status(False, f"{exc}")
                self._log.exception("Exception has occured")
