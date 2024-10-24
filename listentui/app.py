import asyncio
import signal
import sys
from contextlib import suppress

from textual import on, work
from textual.app import App

from listentui.data.config import Config
from listentui.listen.client import ListenClient
from listentui.listen.interface import ConfigurableBase
from listentui.pages.setting import SettingPage
from listentui.screen.login import LoginScreen
from listentui.screen.main import MainScreen
from listentui.screen.modal.albumScreen import AlbumScreen
from listentui.screen.modal.artistScreen import ArtistScreen
from listentui.screen.modal.messages import SpawnAlbumScreen, SpawnArtistScreen, SpawnSongScreen, SpawnSourceScreen
from listentui.screen.modal.songScreen import SongScreen
from listentui.screen.modal.sourceScreen import SourceScreen
from listentui.screen.mpvWarning import MPVWarningScreen
from listentui.utilities.logger import create_logger
from listentui.widgets.player import MPVThread, Player


class ListentuiApp(App[str]):
    TITLE = "LISTEN.moe"

    def __init__(self) -> None:
        super().__init__()
        self.player: Player | None = None

    def on_load(self) -> None:
        create_logger(Config.get_config().advance.stats_for_nerd, self.app.console)

    @work
    async def on_mount(self) -> None:
        self.login_and_load()

    @work
    async def login_and_load(self) -> None:
        status = await self.push_screen_wait(LoginScreen())
        if not status:
            self.exit(return_code=1, message="Login failed, please check your username and password")
            return
        # configure the client interface
        ConfigurableBase.prefer_romaji_first = Config.get_config().display.romaji_first
        self.push_screen(MainScreen())

    async def on_unmount(self) -> None:
        Config.get_config().save()
        await asyncio.wait_for(self.terminate_components(), timeout=20)

    def action_handle_url(self, url: str) -> None:
        self.open_url(url, new_tab=True)

    async def terminate_components(self) -> None:
        if MPVThread.instance:
            MPVThread.instance.terminate()
        with suppress(AttributeError):
            await ListenClient.get_instance().close()
        if self.player and self.player.presense_connected:
            await self.player.presence.clear()

    async def restart(self) -> None:
        self.player = None
        await self.screen.remove()
        await self.terminate_components()
        # await self.recompose()
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

    @on(SpawnArtistScreen)
    def push_screen_artist(self, event: SpawnArtistScreen) -> None:
        self.push_screen(ArtistScreen(event.artist_id))

    @on(SpawnAlbumScreen)
    def push_album_screen(self, event: SpawnAlbumScreen) -> None:
        self.push_screen(AlbumScreen(event.album_id))

    @on(SpawnSongScreen)
    def push_song_screen(self, event: SpawnSongScreen) -> None:
        self.push_screen(SongScreen(event.song_id))

    @on(SpawnSourceScreen)
    def push_source_screen(self, event: SpawnSourceScreen) -> None:
        self.push_screen(SourceScreen(event.source_id))

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
    output = app.run()
    if output is not None:
        print(output)


if __name__ == "__main__":
    run()
