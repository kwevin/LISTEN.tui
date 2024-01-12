# pyright: reportUnknownMemberType=false, reportMissingTypeStubs=false
import asyncio
from logging import DEBUG, INFO, WARNING, getLogger
from typing import Any

import mpv
from textual import work
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from ..data import Config


class MPVStreamPlayer(Widget):
    DEFAULT_CSS = """ 
    MPVStreamPlayer {
        width: 100%;
        height: 100%;
    }
    """

    is_playing: reactive[bool] = reactive(True, init=False)
    volume: reactive[int] = reactive(100, init=False)

    class Play(Message):
        def __init__(self) -> None:
            super().__init__()

    class Paused(Message):
        def __init__(self) -> None:
            super().__init__()

    def __init__(self) -> None:
        self.mpv_options = Config.get_config().player.mpv_options.copy()
        self.mpv_options["volume"] = Config.get_config().persistant.volume
        if Config.get_config().player.dynamic_range_compression and not self.mpv_options.get("af"):
            self.mpv_options["af"] = "acompressor=ratio=4,loudnorm=I=-16:LRA=11:TP=-1.5"
        self._log = getLogger(__name__)
        self.stream_url = "https://listen.moe/stream"
        self.player = mpv.MPV(**self.mpv_options)
        super().__init__()

    @property
    def core_idle(self) -> bool:
        value = self._get_value("core_idle")
        return bool(value) if value else False

    @property
    def paused(self) -> bool:
        value = self._get_value("pause")
        return bool(value) if value else False

    def _get_value(self, value: str, *args: Any) -> Any | None:
        try:
            return getattr(self.player, value, *args)
        except (RuntimeError, mpv.ShutdownError):
            return None

    def on_mount(self) -> None:
        self.loading = True
        self.run_player()

    def on_unmount(self) -> None:
        self.player.terminate()

    def watch_is_playing(self, new: bool) -> None:
        if new:
            self.player.pause = False
            self.restart_player()
        else:
            self.player.pause = True
            self.post_message(self.Paused())

    def watch_volume(self, new: int) -> None:
        self.player.volume = new

    @work(group="run_player", name="run_player")
    async def run_player(self) -> None:
        await self.restart_player().wait()
        self.restarter()
        self.loading = False
        self.styles.display = "none"

    @work(exclusive=True, group="restart_player", name="restart_player", thread=True)
    def restart_player(self) -> None:
        self.player.play(self.stream_url)
        self.wait_until_playing()

    @work(group="restarter", name="mpv_restarter")
    async def restarter(self) -> None:
        timeout = Config.get_config().player.timeout_restart

        counter = 0
        while True:
            if self.core_idle and not self.paused:
                self._log.debug(f"idle: {self.core_idle} | paused: {self.paused} | timeout: {counter}")
                counter += 1
            else:
                counter = 0
            if counter == timeout:
                self.hard_reset()
                self._log.debug(f"Player timeout exceed: {timeout}s")
            await asyncio.sleep(1)
            # while self.core_idle and not self.paused:
            #     while counter < timeout:
            #         self._log.debug(f"Player idling detected: {counter}")
            #         self._log.debug(f"core: {self.core_idle} - paused: {self.paused}")
            #         counter += 1
            #         await asyncio.sleep(1)
            #     self.hard_reset()
            #     self._log.debug(f"Player timeout exceed: {timeout}s")
            #     break
            # await asyncio.sleep(1)

    def hard_reset(self) -> None:
        self.player.terminate()
        self.post_message(self.Paused())
        self.player = mpv.MPV(**self.mpv_options)
        self.restart_player()

    def wait_until_playing(self) -> None:
        self.player.wait_until_playing()
        self.post_message(self.Play())

    def log_handler(self, loglevel: str, component: str, message: str):
        if component == "display-tags":
            return
        match loglevel:
            case "info":
                level = INFO
            case "warn":
                level = WARNING
            case "debug":
                level = DEBUG
            case _:
                level = DEBUG
        self._log.log(level=level, msg=f"[{component}] {message}")
