import asyncio
import logging
import signal
import sys
from contextlib import suppress
from logging import getLogger

from textual import on, work
from textual.app import App
from textual.css.query import NoMatches

from listentui.data.config import Config
from listentui.listen.client import ListenClient
from listentui.listen.interface import ConfigurableBase
from listentui.pages.setting import SettingPage
from listentui.screen.login import LoginScreen
from listentui.screen.main import MainScreen
from listentui.screen.modal.albumScreen import AlbumScreen
from listentui.screen.modal.artistScreen import ArtistScreen
from listentui.screen.modal.characterScreen import CharacterScreen
from listentui.screen.modal.messages import (
    SpawnAlbumScreen,
    SpawnArtistScreen,
    SpawnCharacterScreen,
    SpawnSongScreen,
    SpawnSourceScreen,
)
from listentui.screen.modal.songScreen import SongScreen
from listentui.screen.modal.sourceScreen import SourceScreen
from listentui.utilities import get_root
from listentui.widgets.floatingPlayer import FloatingPlayer, HideFloatingPlayer, ShowFloatingPlayer
from listentui.widgets.player import MPVThread, Player


class ListentuiApp(App[str]):
    TITLE = "LISTEN.moe"
    CSS_PATH = get_root().joinpath("testing.tcss")

    def __init__(self) -> None:
        super().__init__()
        self.player: Player | None = None

    def on_load(self) -> None:
        getLogger().setLevel(logging.DEBUG if Config.get_config().advance.stats_for_nerd else logging.WARNING)

    @work
    async def on_mount(self) -> None:
        self.login_and_load()

    @work
    async def login_and_load(self) -> None:
        config = Config.get_config()
        status = await self.push_screen_wait(LoginScreen())
        if not status:
            self.exit(return_code=1, message="Login failed, please check your username and password")
            return
        # configure the client interface
        ConfigurableBase.prefer_romaji_first = config.display.romaji_first
        self.push_screen(MainScreen())

    async def on_unmount(self) -> None:
        Config.get_config().save()
        self.exit()
        # i give up, it freezes somewhere here
        # try:
        #     async with asyncio.timeout_at(asyncio.get_event_loop().time() + 10):
        #         await self.terminate_components()
        # except asyncio.TimeoutError:
        #     sys.exit(1)

    def action_handle_url(self, url: str) -> None:
        self.open_url(url, new_tab=True)

    async def terminate_components(self) -> None:
        with suppress(AttributeError):
            await ListenClient.get_instance().close()
        if MPVThread.instance:
            MPVThread.instance.terminate()

    async def restart(self) -> None:
        self.player = None
        await self.screen.remove()
        await self.terminate_components()
        self.login_and_load()

    @on(SettingPage.RequestRestart)
    async def apply_setting(self, event: SettingPage.RequestRestart) -> None:
        await self.restart()
        # this is too unstable atm
        # if "client" in event.items or "display" in event.items:
        #     await self.restart()
        #     return
        # self.notify(f"{event.items}")

        # for item in event.items:
        #     match item:
        #         case "presense":
        #             if Config.get_config().presence.enable:
        #                 player = self.query_one(Player)
        #                 if player.ws_data and player.song:
        #                     player.update_presense(player.ws_data, player.song)
        #         case "player":
        #             if MPVThread.instance:
        #                 MPVThread.instance.hard_restart()
        #         case "advance":
        #             verbose = Config.get_config().advance.stats_for_nerd
        #             if verbose:
        #                 getLogger().setLevel(logging.DEBUG)
        #                 await self.query_one("#topbar", TabbedContent).add_pane(
        #                     TabPane("Log", RichLogExtended(), id="log"), before="setting"
        #                 )
        #             else:
        #                 getLogger().setLevel(logging.WARNING)
        #                 await self.query_one("#topbar", TabbedContent).remove_pane("#log")

        #             self.call_after_refresh(self.query_one(SettingPage).recompose)
        #         case "downloader":
        #             continue
        #         case "persistance":
        #             continue
        #         case _:
        #             getLogger(__name__).warning(f"Unhandled {item}")

    @on(Player.PlayerMounted)
    def save_player(self, event: Player.PlayerMounted) -> None:
        self.player = event.player

    @on(Player.PlayerSetVolume)
    def player_set_volume(self, event: Player.PlayerSetVolume) -> None:
        if self.player:
            self.player.player.set_volume(event.volume)

    @on(Player.PreviewSetVolume)
    def pv_set_volume(self, event: Player.PreviewSetVolume) -> None:
        if self.player:
            self.player.player.preview_set_volume(event.volume)

    @on(SpawnArtistScreen)
    @work
    async def push_screen_artist(self, event: SpawnArtistScreen) -> None:
        await self.push_screen(await ArtistScreen.load(self.app, event.artist_id))

    @on(SpawnAlbumScreen)
    @work
    async def push_album_screen(self, event: SpawnAlbumScreen) -> None:
        await self.push_screen(await AlbumScreen.load(self.app, event.album_id))

    @on(SpawnSongScreen)
    @work
    async def push_song_screen(self, event: SpawnSongScreen) -> None:
        await self.push_screen(await SongScreen.load_with_favorited(self.app, event.song_id))

    @on(SpawnSourceScreen)
    @work
    async def push_source_screen(self, event: SpawnSourceScreen) -> None:
        await self.push_screen(await SourceScreen.load(self.app, event.source_id))

    @on(SpawnCharacterScreen)
    @work
    async def push_character_screen(self, event: SpawnCharacterScreen) -> None:
        await self.push_screen(await CharacterScreen.load(self.app, event.character_id))

    # @on(ShowFloatingPlayer)
    # async def show_floating_player(self) -> None:
    #     async def mount_player():
    #         await self.screen.mount(fplayer)
    #         fplayer.show()
    #         self.player.websocket_update.subscribe(fplayer, fplayer.update)  # type: ignore

    #     if self.player is None:
    #         return

    #     try:
    #         self.screen.query_one(FloatingPlayer).show()
    #     except NoMatches:
    #         fplayer = FloatingPlayer(self.player.ws_data, self.player.song)
    #         await self.screen.mount(fplayer)
    #         fplayer.show()
    #         self.player.websocket_update.subscribe(fplayer, fplayer.update)  # type: ignore

    # @on(HideFloatingPlayer)
    # def hide_floating_player(self) -> None:
    #     try:
    #         fplayer = self.screen.query_one(FloatingPlayer)
    #         fplayer.hide()
    #     except NoMatches:
    #         return


def run() -> None:
    def sigterm_handler(signum, stack) -> None:
        app.exit(message="Terminated by SIGTERM")

    app = ListentuiApp()
    signal.signal(signal.SIGTERM, sigterm_handler)
    try:
        output = app.run()
        if output is not None:
            print(output)
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    run()
