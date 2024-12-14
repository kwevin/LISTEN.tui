from threading import Thread
from typing import Any, ClassVar, cast

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Grid, Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

from listentui.data import get_song_duration
from listentui.data.config import Config
from listentui.data.theme import Theme
from listentui.listen import ListenClient, RequestError, Song, SongID
from listentui.screen.modal.baseScreen import BaseScreen, LoadingScreen
from listentui.screen.modal.buttons import EscButton
from listentui.screen.modal.messages import SpawnAlbumScreen, SpawnSourceScreen
from listentui.utilities import format_time_since
from listentui.widgets.artistScrollableLabel import ArtistScrollableLabel
from listentui.widgets.buttons import StaticButton, ToggleButton, VolumeButton
from listentui.widgets.durationProgressBar import DurationProgressBar
from listentui.widgets.mpvThread import MPVThread, PreviewStatus, PreviewType
from listentui.widgets.scrollableLabel import ScrollableLabel


class MultiButton(Widget):
    DEFAULT_CSS = """
    MultiButton {
        min-width: 13;
        width: auto;
        height: auto;
    }
    """

    def __init__(self):
        super().__init__()
        self._volume_mode = False

    class Preview(Message):
        def __init__(self) -> None:
            super().__init__()

    def compose(self) -> ComposeResult:
        if not self._volume_mode:
            yield StaticButton("Preview", id="preview")
        else:
            yield VolumeButton(preview_mode=True)

    @on(StaticButton.Pressed, "#preview")
    async def _preview(self) -> None:
        self.post_message(self.Preview())
        self.disabled = True
        self.set_loading(True)

    @work
    async def to_volume_mode(self, volume: int) -> None:
        self._volume_mode = True
        self.disabled = False
        self.set_loading(False)
        await self.recompose()
        self.query_one(VolumeButton).volume = volume

    @work
    async def to_preview_mode(self) -> None:
        self._volume_mode = False
        await self.recompose()


class SongScreen(BaseScreen[bool, SongID, Song]):
    """Screen for confirming actions"""

    DEFAULT_CSS = """
    SongScreen {
        align: center middle;

        #artist {
            color: rgb(249, 38, 114);
        }
    }
    SongScreen ScrollableLabel {
        height: 1;
    }
    SongScreen Grid {
        grid-size: 3 4;
        grid-gutter: 1 2;
        grid-rows: 1 3 2 1fr;
        padding: 0 2;
        width: 70%;
        height: 15;
        border: thick $background 80%;
        background: $background-lighten-1;
        border-subtitle-color: red;
        border-title-color: red;
        border-title-align: center;
    }
    SongScreen > Container {
        height: 3;
        width: 100%;
        align: left middle;
    }
    SongScreen Horizontal {
        column-span: 3;
        width: 100%;
        align: center middle;
    }
    SongScreen Horizontal > * {
        margin-right: 1;
    }
    SongScreen StaticButton {
        min-width: 13;
    }
    SongScreen #favorite {
        min-width: 14;
    }
    SongScreen .hidden {
        display: none;
    }
    SongScreen DurationProgressBar {
        offset: 0 1;
    }
    SongScreen #duration.debug_missing {
        color: yellow;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, song_id: SongID, song: Song, favorited: bool | None = None):
        super().__init__()
        self.song_id = song_id
        self.song: Song = song
        self.got_favorited = favorited
        self.is_favorited = False

    def compose(self) -> ComposeResult:
        yield EscButton()
        with Grid():
            yield Label("Track/Artist")
            yield Label("Album")
            yield Label("Source")
            yield Container(
                ScrollableLabel(Text.from_markup(self.song.format_title()), id="title"),
                ArtistScrollableLabel(),
            )
            album = self.song.format_album()
            source = self.song.format_source()
            yield Container(
                ScrollableLabel(
                    Text.from_markup(f"[green]{album}[/]"),
                    id="album",
                )
            )
            yield Container(
                ScrollableLabel(
                    Text.from_markup(f"[cyan]{source}[/]"),
                    id="source",
                )
            )
            missing_duration = get_song_duration(self.song.id)
            fetch_missing = Config.get_config().advance.stats_for_nerd
            yield Label(
                f"Duration: {missing_duration or self.song.duration}",
                id="duration",
                classes="debug_missing" if missing_duration and fetch_missing else None,
            )
            yield Label(
                f"Last played: {format_time_since(self.song.last_played, True) if self.song.last_played else None}",
                id="last_play",
            )
            yield Label(f"Time played: {self.song.played}", id="time_played")
            with Horizontal(id="horizontal"):
                yield MultiButton()
                yield DurationProgressBar(stop=True, total=0, pause_on_end=True)
                yield ToggleButton("Favorite", "Favorited", check_user=True, hidden=True, id="favorite")
                yield StaticButton("Request", check_user=True, hidden=True, id="request")

    async def on_scrollable_label_clicked(self, event: ScrollableLabel.Clicked) -> None:
        container_id = event.widget.id
        if not container_id:
            return
        if not self.song:
            return
        match container_id:
            case "album":
                if not self.song.album:
                    return
                self.post_message(SpawnAlbumScreen(self.song.album.id))
            case "source":
                if not self.song.source:
                    return
                self.post_message(SpawnSourceScreen(self.song.source.id))
            case _:
                return

    @work
    async def on_mount(self) -> None:
        client = ListenClient.get_instance()
        self.query_one(ArtistScrollableLabel).update(self.song)
        self.query_one(Grid).border_subtitle = f"[{self.song.id}]"
        self.query_one(Grid).border_title = f"Uploader: {self.song.uploader.display_name}" if self.song.uploader else ""
        if self.got_favorited:
            self.is_favorited = self.got_favorited
        elif client.logged_in:
            self.is_favorited: bool = await client.check_favorite(self.song.id) or False
        self.query_one("#favorite", ToggleButton).set_toggle_state(self.is_favorited)

    @classmethod
    async def load(cls, app: App, load_id: SongID):
        client = ListenClient.get_instance()
        res = await app.push_screen_wait(LoadingScreen(client.song(load_id)))
        assert res is not None
        return cls(load_id, res, False)

    @classmethod
    async def load_with_favorited(cls, app: App, load_id: SongID, favorited: bool = False):
        client = ListenClient.get_instance()
        res = await app.push_screen_wait(LoadingScreen(client.song(load_id)))
        assert res is not None
        return cls(load_id, res, favorited)

    def action_cancel(self) -> None:
        Thread(target=MPVThread.terminate_preview, name="terminate_preview", daemon=True).start()
        self.dismiss(self.is_favorited)

    @on(MultiButton.Preview)
    def preview(self) -> None:
        song = cast(Song, self.song)
        if not song.snippet:
            self.notify("No snippet to preview", severity="warning", title="Preview")
            return
        MPVThread.preview(song.snippet, self.handle_preview_status)

    def handle_preview_status(self, data: PreviewStatus):
        try:
            progress = self.query_one(DurationProgressBar)
            multibutton = self.query_one(MultiButton)
            if data.state == PreviewType.LOCKED:
                self.notify("Cannot preview two songs at the same time", title="Preview", severity="warning")
            elif data.state == PreviewType.UNABLE:
                self.notify("Unable to play preview :(", title="Preview", severity="warning")
            elif data.state == PreviewType.PLAYING:
                multibutton.to_volume_mode(data.other)
                progress.reset()
                progress.resume()
            elif data.state == PreviewType.DATA:
                cache = cast(MPVThread.DemuxerCacheState, data.other)
                progress.update_total(round(cache.cache_end))
            elif data.state == PreviewType.DONE:
                multibutton.to_preview_mode()
            elif data.state == PreviewType.ERROR:
                self.notify("An error has occured", title="Preview", severity="warning")
            else:
                return
        except Exception:
            return

    @on(ToggleButton.Pressed, "#favorite")
    @work
    async def favorite(self) -> None:
        song = cast(Song, self.song)
        self.is_favorited = not self.is_favorited
        self.query_one("#favorite", ToggleButton).set_toggle_state(self.is_favorited)
        client = ListenClient.get_instance()
        await client.favorite_song(song.id)

    @on(StaticButton.Pressed, "#request")
    @work
    async def request(self) -> None:
        song = cast(Song, self.song)
        client = ListenClient.get_instance()
        self.query_one("#request").set_loading(True)
        res: Song | RequestError = await client.request_song(song.id, exception_on_error=False)
        self.query_one("#request").set_loading(False)
        if isinstance(res, Song):
            title = res.format_title()
            artist = res.format_artists()
            self.notify(
                f"{title}" + f" by [{Theme.ACCENT}]{artist}[/]" if artist else "",
                title="Sent to queue",
            )
        elif res == RequestError.FULL:
            self.notify("All requests have been used up for today!", severity="warning")
        else:
            self.notify("Song is already in queue", severity="warning")
