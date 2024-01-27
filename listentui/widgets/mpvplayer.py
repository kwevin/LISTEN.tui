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

    class Restarted(Message):
        def __init__(self) -> None:
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self._log = getLogger(__name__)
        self.stream_url = "https://listen.moe/stream"
        self.player = mpv.MPV(**self.get_options())

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

    def get_options(self) -> dict[str, Any]:
        mpv_options = Config.get_config().player.mpv_options.copy()
        mpv_options["volume"] = Config.get_config().persistant.volume
        if Config.get_config().player.dynamic_range_compression and not mpv_options.get("af"):
            mpv_options["af"] = "acompressor=ratio=4,loudnorm=I=-16:LRA=11:TP=-1.5"

        return mpv_options

    def on_mount(self) -> None:
        self.init_player()

    def on_unmount(self) -> None:
        Config.get_config().save()
        self.player.terminate()

    @work(group="player")
    async def init_player(self) -> None:
        self.loading = True
        await self.reset().wait()
        self.restart_worker = self.restarter()
        self.loading = False
        self.styles.display = "none"

    @work(group="player")
    async def watch_is_playing(self, new: bool) -> None:
        if new:
            self.player.pause = False
            self.reset()
        else:
            self.player.pause = True

    def watch_volume(self, new: int) -> None:
        config = Config.get_config()
        config.persistant.volume = new
        self.player.volume = new

    @work(exclusive=True, group="player_reset", thread=True)
    def reset(self) -> None:
        # this needs to be a threaded method i dont know why
        self.player.play(self.stream_url)
        self.player.wait_until_playing()
        self.post_message(self.Restarted())

    @work(exclusive=True, group="player_restarter")
    async def restarter(self) -> None:
        timeout = Config.get_config().player.timeout_restart

        counter = 0
        while True:
            if self.core_idle and not self.paused:
                self._log.debug(f"idle: {self.core_idle} | paused: {self.paused} | timeout: {counter}/{timeout}")
                counter += 1
            else:
                counter = 0
            if counter == timeout:
                self.hard_restart()
                counter = 0
                self._log.debug(f"Player timeout exceed: {timeout}s")
            await asyncio.sleep(1)

    @work(group="player")
    async def hard_restart(self) -> None:
        self.player.terminate()
        self.player = mpv.MPV(**self.get_options())
        self.restarter()
        self.reset()

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
