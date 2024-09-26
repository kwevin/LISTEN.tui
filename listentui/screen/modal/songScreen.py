from threading import Thread
from typing import ClassVar, cast

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Grid, Horizontal
from textual.screen import Screen
from textual.widgets import Label

from listentui.data.theme import Theme
from listentui.listen import ListenClient, RequestError, Song, SongID
from listentui.screen.modal.buttons import EscButton
from listentui.screen.modal.messages import SpawnAlbumScreen, SpawnSourceScreen
from listentui.utilities import format_time_since
from listentui.widgets.artistScrollableLabel import ArtistScrollableLabel
from listentui.widgets.buttons import StaticButton, ToggleButton
from listentui.widgets.durationProgressBar import DurationProgressBar
from listentui.widgets.mpvThread import MPVThread, PreviewStatus, PreviewType
from listentui.widgets.scrollableLabel import ScrollableLabel


class SongScreen(Screen[bool]):
    """Screen for confirming actions"""

    DEFAULT_CSS = """
    SongScreen {
        align: center middle;
        background: $background;
        hatch: left $background-lighten-1 60%;
    
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
        width: 96;
        height: 14;
        border: thick $background 80%;
        background: $surface;
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
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, song_id: SongID, favorited: bool | None = None):
        super().__init__()
        self.song_id = song_id
        self.song: Song | None = None
        self.got_favorited = favorited
        self.is_favorited = False

    def compose(self) -> ComposeResult:
        yield EscButton()
        with Grid():
            if self.song is None:
                return

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
            yield Label(f"Duration: {self.song.duration}", id="duration")
            yield Label(
                f"Last played: {format_time_since(self.song.last_played, True) if self.song.last_played else None}",
                id="last_play",
            )
            yield Label(f"Time played: {self.song.played}", id="time_played")
            with Horizontal(id="horizontal"):
                yield StaticButton("Preview", id="preview")
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

    def on_mount(self) -> None:
        self.query_one(Grid).loading = True
        self.fetch_song()

    @work
    async def fetch_song(self) -> None:
        client = ListenClient.get_instance()
        song = await client.song(self.song_id)
        if song is None:
            raise Exception("Song cannot be None")
        self.song = song
        await self.recompose()
        self.query_one(ArtistScrollableLabel).update(song)
        self.query_one(Grid).border_subtitle = f"[{self.song.id}]"
        self.query_one(Grid).border_title = f"Uploader: {self.song.uploader.display_name}" if self.song.uploader else ""
        if self.got_favorited:
            self.is_favorited = self.got_favorited
        elif client.logged_in:
            self.is_favorited: bool = await client.check_favorite(song.id) or False
        self.query_one("#favorite", ToggleButton).set_toggle_state(self.is_favorited)
        self.query_one(Grid).loading = False

    def action_cancel(self) -> None:
        Thread(target=MPVThread.terminate_preview, name="terminate_preview", daemon=True).start()
        self.dismiss(self.is_favorited)

    @on(StaticButton.Pressed, "#preview")
    def preview(self) -> None:
        song = cast(Song, self.song)
        if not song.snippet:
            self.notify("No snippet to preview", severity="warning", title="Preview")
            return
        self.query_one("#preview", StaticButton).disabled = True
        MPVThread.preview(song.snippet, self.handle_preview_status)

    def handle_preview_status(self, data: PreviewStatus):  # noqa: PLR0911
        try:
            progress = self.query_one(DurationProgressBar)
            if data.state == PreviewType.LOCKED:
                self.notify("Cannot preview two songs at the same time", title="Preview", severity="warning")
                return
            if data.state == PreviewType.UNABLE:
                self.notify("Unable to play preview :(", title="Preview", severity="warning")
                return
            if data.state == PreviewType.PLAYING:
                progress.reset()
                progress.resume()
                return
            if data.state == PreviewType.DATA:
                cache = cast(MPVThread.DemuxerCacheState, data.other)
                progress.update_total(round(cache.cache_end))
                return
            if data.state == PreviewType.DONE:
                self.query_one("#preview", StaticButton).disabled = False
                return
            if data.state == PreviewType.ERROR:
                self.notify("An error has occured", title="Preview", severity="warning")
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
        res: Song | RequestError = await client.request_song(song.id, exception_on_error=False)
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
