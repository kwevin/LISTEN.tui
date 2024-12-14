# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from enum import Enum
from logging import getLogger
from math import ceil
from string import Template
from typing import Any, cast

import pytz
import websockets.asyncio.client as websockets
from pypresence import AioPresence, DiscordNotFound  # type: ignore
from pypresence.exceptions import PipeClosed, ResponseTimeout
from pypresence.payloads import Payload  # type: ignore
from rich.pretty import pretty_repr
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.signal import Signal
from textual.widget import Widget
from textual.widgets import Label
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from listentui import __NO_MPV__
from listentui.data.config import Config
from listentui.listen.client import ListenClient
from listentui.listen.interface import ListenWsData, Song, SongID
from listentui.widgets.durationProgressBar import DurationProgressBar
from listentui.widgets.floatingPlayer import HideFloatingPlayer, ShowFloatingPlayer
from listentui.widgets.mpvThread import MPVThread
from listentui.widgets.songContainer import SongContainer
from listentui.widgets.vanityBar import VanityBar

PRESENSE_APPLICATION_ID = 1042365983957975080


class Activity(Enum):
    PLAYING = 0
    _STREAMING = 1
    LISTENING = 2
    WATCHING = 3
    _CUSTOM = 4
    COMPETING = 5


class AioPresence(AioPresence):
    async def update(
        self,
        pid: int = os.getpid(),
        state: str | None = None,
        details: str | None = None,
        start: int | None = None,
        end: int | None = None,
        large_image: str | None = None,
        large_text: str | None = None,
        small_image: str | None = None,
        small_text: str | None = None,
        party_id: str | None = None,
        party_size: list[int] | None = None,
        join: str | None = None,
        spectate: str | None = None,
        match: str | None = None,
        buttons: list[dict[str, str]] | None = None,
        instance: bool = True,
        type: int | None = None,  # noqa: A002
    ) -> dict[str, Any]:
        payload = Payload.set_activity_with_type(
            pid=pid,
            state=state,
            details=details,
            start=start,
            end=end,
            large_image=large_image,
            large_text=large_text,
            small_image=small_image,
            small_text=small_text,
            party_id=party_id,
            party_size=party_size,
            join=join,
            spectate=spectate,
            match=match,
            buttons=buttons,
            instance=instance,
            type=type,
            activity=True,
        )
        self.send_data(1, payload)  # type: ignore
        return await self.read_output()


class Payload(Payload):
    @classmethod
    def set_activity_with_type(
        cls,
        pid: int = os.getpid(),
        state: str | None = None,
        details: str | None = None,
        start: int | None = None,
        end: int | None = None,
        large_image: str | None = None,
        large_text: str | None = None,
        small_image: str | None = None,
        small_text: str | None = None,
        party_id: str | None = None,
        party_size: list[int] | None = None,
        join: str | None = None,
        spectate: str | None = None,
        match: str | None = None,
        buttons: list[dict[str, str]] | None = None,
        instance: bool = True,
        type: int | None = None,  # noqa: A002
        activity: bool | None = True,
        _rn: bool = True,
    ):
        if start:
            start = int(start)
        if end:
            end = int(end)

        if activity is None:
            act_details = None
            clear = True
        else:
            act_details = {  # type: ignore
                "type": type,
                "state": state,
                "details": details,
                "timestamps": {"start": start, "end": end},
                "assets": {
                    "large_image": large_image,
                    "large_text": large_text,
                    "small_image": small_image,
                    "small_text": small_text,
                },
                "party": {"id": party_id, "size": party_size},
                "secrets": {"join": join, "spectate": spectate, "match": match},
                "buttons": buttons,
                "instance": instance,
            }
            clear = False

        payload = {  # type: ignore
            "cmd": "SET_ACTIVITY",
            "args": {"pid": pid, "activity": act_details},
            "nonce": "{:.20f}".format(cls.time()),
        }
        if _rn:
            clear = _rn
        return cls(payload, clear)  # type: ignore


class Player(Widget):
    DEFAULT_CSS = """
    Player {
        align: left middle;
        width: 1fr;
        height: 8;
        padding: 0 1;

        #debug {
            width: 100%;
            height: 1;
            align-horizontal: center;

            & Label {
                padding-left: 2;
            }
        
        
            #retries {
                color: red;
            }


            #retries {
                color: red;
            }

        }
    }
    """

    class PlayerMounted(Message):
        def __init__(self, player: Player) -> None:
            super().__init__()
            self.player = player

    class WebsocketUpdated(Message):
        def __init__(self, data: ListenWsData) -> None:
            super().__init__()
            self.data = data

    class WebsocketStatus(Message):
        def __init__(self, state: bool, last_heartbeat: datetime) -> None:
            super().__init__()
            self.is_alive = state
            self.last_heartbeat = last_heartbeat

    class PlayerSetVolume(Message):
        def __init__(self, volume: int) -> None:
            super().__init__()
            self.volume = volume

    class PreviewSetVolume(Message):
        def __init__(self, volume: int) -> None:
            super().__init__()
            self.volume = volume

    def __init__(self) -> None:
        super().__init__()
        self._log = getLogger(__name__)
        self.ws_data: ListenWsData | None = None
        self.song: Song | None = None
        self.is_first_song = True
        self._song_count = 0  # use for calculating first song only
        self.progress_bar = DurationProgressBar(stop=True, pause_on_end=False)
        self.player = MPVThread(self)
        self.retries = 0
        self.websocket_time = 0
        self.mpv_time = 0
        self.start_time = time.time()
        self.on_display = False
        self.mpv_cache: MPVThread.DemuxerCacheState | None = None
        self.presence = AioPresence(PRESENSE_APPLICATION_ID)
        self.presense_connected = False
        self.set_interval(1, self.update_time_elapsed)
        self.set_interval(1, self.update_cache)
        self.websocket_update = Signal[tuple[ListenWsData, Song]](self, "ws_update")

    def compose(self) -> ComposeResult:
        yield VanityBar()
        yield SongContainer()
        yield self.progress_bar
        with Horizontal(id="debug"):
            yield Label(id="retries")
            yield Label(id="heartbeat")
            yield Label(id="rpc")
            yield Label(id="delay")
            yield Label(id="cache")
            yield Label(id="time")

    async def on_mount(self) -> None:
        self.post_message(self.PlayerMounted(self))
        self.set_loading(True)
        self.websocket()
        if not __NO_MPV__:
            self.player.start()

        if Config.get_config().presence.enable:
            await self.connect_presense()
        else:
            self.query_one("#rpc", Label).styles.display = "none"

        if not Config.get_config().advance.stats_for_nerd:
            self.query_one("#debug").styles.display = "none"

        self.query_one("#delay", Label).tooltip = "Delay"
        self.query_one("#cache", Label).tooltip = "Cache"
        self.query_one("#time", Label).tooltip = "Uptime"

    def update_retries(self, retry: int, soft_cap: int, timeout: int) -> None:
        retries = self.query_one("#retries", Label)
        if retry > 0:
            retries.update(f"{retry}!")
            if retry > soft_cap:
                retries.styles.color = "red"
            else:
                retries.styles.color = "yellow"

            retries.tooltip = f"timeout: {timeout}s"
        else:
            retries.update("")

    def update_cache(self) -> None:
        if not self.player.cache:
            return
        self.query_one("#cache", Label).update(
            f"{self.player.cache.cache_duration:.2f}s/{self.player.cache.fw_byte / 1000:.0f}KB"
        )

    def update_delay(self) -> None:
        if self.mpv_time == 0 and self.websocket_time == 0:
            return
        if self.mpv_time == 0 or self.websocket_time == 0:
            self.query_one("#delay", Label).update("-s")
            return

        self.query_one("#delay", Label).update(f"{round(self.mpv_time - self.websocket_time)}s")

    def update_time_elapsed(self) -> None:
        self.query_one("#time", Label).update(f"{timedelta(seconds=round(time.time() - self.start_time))}")

    @on(WebsocketStatus)
    def update_heartbeat(self, status: WebsocketStatus) -> None:
        label = self.query_one("#heartbeat", Label)
        if status.is_alive:
            label.update("[green]OK[/]")
        else:
            label.update("[red]DEAD[/]")
        label.tooltip = f"Last: {status.last_heartbeat.strftime('%H:%M:%S')}"

    @on(WebsocketUpdated)
    def update_websocket_time(self, event: WebsocketUpdated) -> None:
        self.websocket_time = time.time()
        self.update_delay()

        # attemps to calculate the difference between localtime and server time (i believe their clock is behind)
        if not self.is_first_song:
            current_time = datetime.now(tz=pytz.utc)
            server_time = event.data.start_time
            diff = current_time - server_time
            self._log.debug(f"local/server difference = {diff}")
            Config.get_config().persistant.locdiff = round(diff.total_seconds())

    # @on(WebsocketUpdated)
    # def show_toast(self, event: WebsocketUpdated) -> None:
    #     if self.visible:
    #         return
    #     title = event.data.song.format_title()
    #     artist = event.data.song.format_artists()
    #     self.notify(f"{title}" + f"\n[red]{artist}[/]" if artist else "", title="Now Playing")

    @on(MPVThread.NewSong)
    @on(MPVThread.Metadata)
    def update_mpv_time(self) -> None:
        self.update_retries(0, 0, 0)
        self.mpv_time = time.time()
        self.update_delay()

    @work
    async def update_container(self, data: ListenWsData) -> None:
        self.progress_bar.resume()
        self.song = cast(Song, await ListenClient.get_instance().song(data.song.id))
        self.websocket_update.publish((data, self.song))

        self.query_one(SongContainer).update_song(self.song)
        self.query_one(VanityBar).update_vanity(data)
        self.set_loading(False)

        if Config.get_config().presence.enable:
            self.update_presense(data, self.song)

    @on(MPVThread.FailedRestart)
    def player_failed_restart(self, event: MPVThread.FailedRestart) -> None:
        self.retries = event.retry_no
        self.update_retries(event.retry_no, event.soft_cap, event.timeout)

    @on(MPVThread.SuccessfulRestart)
    def player_sucessful_restart(self, event: MPVThread.SuccessfulRestart) -> None:
        self.retries = 0
        self.update_retries(0, 0, 0)

    @on(MPVThread.Fail)
    def player_failed(self, event: MPVThread.Fail) -> None:
        self.app.exit(return_code=1, message="Player failed to connect / regain connection")

    @work(exclusive=True, group="websocket")
    async def websocket(self) -> None:
        last_heartbeat: datetime = datetime.now()
        async for self._ws in websockets.connect("wss://listen.moe/gateway_v2", ping_interval=None, ping_timeout=None):
            try:
                while True:
                    res: dict[str, Any] = json.loads(await self._ws.recv())
                    match res["op"]:
                        case 1:
                            new_data = ListenWsData.from_data(res)
                            # new_data.song.duration = get_song_duration(new_data.song.id) or new_data.song.duration
                            # TODO: remove once they fix the bug
                            if new_data.song.duration is None or new_data.song.duration == 0:
                                new_data.song.duration = await self.get_missing_duration(new_data.song)

                            self.ws_data = new_data
                            self.post_message(self.WebsocketUpdated(self.ws_data))
                            if not self._song_count and self.is_first_song:
                                self.progress_bar.try_calculate_duration(self.ws_data)
                                self._song_count += 1
                            elif self._song_count and self.is_first_song:
                                self.is_first_song = False
                                self.progress_bar.update_progress(self.ws_data.song)
                            else:
                                self.progress_bar.update_progress(self.ws_data.song)
                            self.update_container(self.ws_data)
                        case 0:
                            self.post_message(self.WebsocketStatus(True, last_heartbeat))
                            self.keepalive = self.ws_keepalive(res["d"]["heartbeat"] / 1000)
                        case 10:
                            last_heartbeat = datetime.now()
                            self.post_message(self.WebsocketStatus(True, last_heartbeat))
                        case _:
                            pass
            except ConnectionClosedOK:
                return
            except ConnectionClosedError:
                self.post_message(self.WebsocketStatus(False, last_heartbeat))
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

    async def connect_presense(self) -> None:
        try:
            async with asyncio.timeout(5):
                await self.presence.connect()
            self.presense_connected = True
            self.query_one("#rpc", Label).update("[green]RPC[/]")
        except DiscordNotFound:
            self.query_one("#rpc", Label).update("[red]RPC[/]")
            self.query_one("#rpc", Label).tooltip = "Discord Not Found"
            return
        except TimeoutError:
            self.query_one("#rpc", Label).update("[red]RPC[/]")
            self.query_one("#rpc", Label).tooltip = "Timed out connecting to discord"
            return
        except Exception as exc:
            self.query_one("#rpc", Label).update("[red]RPC[/]")
            self.query_one("#rpc", Label).tooltip = f"{exc}"
            return

    def sanitise(self, string: str) -> str:
        default = Config.get_config().presence.default_placeholder
        # discord limit
        min_length = 2
        max_length = 128

        if len(string.strip()) < min_length:
            string += default
            return string.strip()
        if len(string) >= max_length:
            return f"{string[0:125]}..."
        return string

    def substitute(self, string: str, substitution: dict[str, str]) -> str | None:
        subbed = Template(string).safe_substitute(substitution)
        return self.sanitise(final) if (final := subbed.strip()) else None

    def get_large_image(self, song: Song) -> str | None:
        config = Config.get_config().presence
        use_fallback = config.use_fallback
        fallback = config.fallback
        use_artist = config.use_artist

        album = song.album_image()
        if album:
            return album

        artist_image = song.artist_image()
        if use_artist and artist_image:
            return artist_image

        return fallback if use_fallback else None

    def get_small_image(self, song: Song) -> str | None:
        config = Config.get_config().presence
        return song.artist_image() if config.show_artist_as_small_icon else None

    def get_epoch_end_time(self, song: Song) -> int | None:
        return song.time_end if song.duration else None

    @work
    async def update_presense(self, data: ListenWsData, song: Song) -> None:
        if not self.presense_connected:
            await self.connect_presense()
        config = Config.get_config().presence

        substitution_dict: dict[str, str] = {
            "id": str(song.id),
            "title": song.format_title(),
            "title_romaji": song.title_romaji or "",
            "title_original": song.title or "",
            "artist": song.format_artists(),
            "artist_romaji": song.format_artists(romaji_first=True),
            "artist_original": song.format_artists(romaji_first=False),
            "artist_no_character": song.format_artists(show_character=False) or "",
            "artist_image": song.artist_image() or "",
            "album": song.format_album(),
            "album_image": song.album_image() or "",
            "source": song.format_source() or "",
            "source_wrapped": f"[{source}]" if (source := song.format_source()) else "",
            "source_image": song.source_image() or "",
            "requester": data.requester.display_name if data.requester else "",
            "event": data.event.name if data.event else "",
            "listener": str(data.listener),
        }

        presense_type = Activity(config.type)
        large_image = self.get_large_image(song)
        small_image = self.get_small_image(song)

        try:
            res = await self.presence.update(
                details=self.substitute(config.detail, substitution_dict),
                state=self.substitute(config.state, substitution_dict),
                end=self.get_epoch_end_time(song) if config.show_time_left else None,
                large_image=self.get_large_image(song),
                large_text=self.substitute(config.large_text, substitution_dict),
                small_image=small_image if large_image != small_image else None,
                small_text=self.substitute(config.small_text, substitution_dict),
                # seems like discord deprecated buttons from rpc
                # (or smth changed and this stopped working)
                buttons=[{"label": "Join radio", "url": "https://listen.moe/"}],
                type=presense_type.value,
            )
            self._log.debug(pretty_repr(res))
            self.query_one("#rpc", Label).update("[green]RPC[/]")
        except (PipeClosed, BrokenPipeError, ResponseTimeout, asyncio.CancelledError, TimeoutError):
            self.presense_connected = False
            self.query_one("#rpc", Label).update("[red]RPC[/]")
            self._log.info("Unable to update presense")
        except Exception:
            self.query_one("#rpc", Label).update("[red]RPC[/]")
            self._log.exception("Something went wrong with updating discord presense")

    async def on_unmount(self) -> None:
        if self.presense_connected:
            try:
                async with asyncio.timeout_at(asyncio.get_event_loop().time() + 5):
                    await self.presence.clear()
            except TimeoutError:
                return

    def on_hide(self) -> None:
        self.on_display = False
        self.post_message(ShowFloatingPlayer())

    def on_show(self) -> None:
        self.on_display = True
        self.post_message(HideFloatingPlayer())

    async def get_missing_duration(self, song: Song) -> int:
        """
        This works because of a bug, will be removed
        for duration_map once fixed (if ever)
        """

        client = ListenClient.get_instance()

        history = await client.history(2, 0)

        if history[1].song.id == song.id:
            return ceil((history[0].created_at - history[1].created_at).total_seconds())
        return 0
