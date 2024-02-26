from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Grid, Horizontal
from textual.screen import Screen
from textual.widgets import Label

from ..data.config import Config
from ..data.theme import Theme
from ..listen.client import ListenClient
from ..listen.types import Song
from ..utilities import format_time_since
from ..widgets.custom import DurationProgressBar, ScrollableLabel, StaticButton, ToggleButton
from ..widgets.mpvplayer import MPVStreamPlayer


class SongScreen(Screen[None]):
    """Screen for confirming actions"""

    DEFAULT_CSS = f"""
    SongScreen {{
        align: center middle;
        background: $background;
    }}
    SongScreen ScrollableLabel {{
        height: 1;
    }}
    SongScreen #artist {{
        color: {Theme.ACCENT};
    }}
    SongScreen Grid {{
        grid-size: 3 4;
        grid-gutter: 1 2;
        grid-rows: 1 3 2 1fr;
        padding: 0 2;
        width: 96;
        height: 14;
        border: thick $background 80%;
        background: $surface;
    }}
    SongScreen > Container {{
        height: 3;
        width: 100%;
        align: left middle;
    }}
    SongScreen Horizontal {{
        column-span: 3;
        width: 100%;
        align: center middle;
    }}
    SongScreen Horizontal > * {{
        margin-right: 1;
    }}
    SongScreen StaticButton {{
        min-width: 13;
    }}
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
    ]

    def __init__(self, song: Song, player: MPVStreamPlayer, favorited: bool = False):
        super().__init__()
        self.song = song
        self.player = player
        self.is_favorited = favorited

    def compose(self) -> ComposeResult:
        with Grid():
            yield Label("Track/Artist")
            yield Label("Album")
            yield Label("Source")
            yield Container(
                ScrollableLabel(self.song.format_title() or "", id="title"),
                ScrollableLabel(self.song.format_artists() or "", id="artist"),
            )
            yield Container(ScrollableLabel(self.song.format_album() or "", id="album"))
            yield Container(ScrollableLabel(self.song.format_source() or "", id="source"))
            yield Label(f"Duration: {self.song.duration}", id="duration")
            yield Label(
                f"Last played: {format_time_since(self.song.last_played, True) if self.song.last_played else None}",
                id="last_play",
            )
            yield Label(f"Time played: {self.song.played}", id="time_played")
            with Horizontal(id="horizontal"):
                # TODO: make buttons
                yield StaticButton("Preview", id="preview")
                yield DurationProgressBar(stop=True, total=15, pause_on_end=True)
                # yield VolumeButton()
                yield ToggleButton("Fav", check_user=True, id="favorite")
                yield StaticButton("Req", id="request")

    def on_mount(self) -> None:
        self.query_one("#favorite", ToggleButton).set_state(self.is_favorited)

    def action_cancel(self) -> None:
        self.dismiss()

    @work
    async def _on_play(self) -> None:
        self.query_one(DurationProgressBar).reset()
        self.query_one(DurationProgressBar).resume()

    @work
    async def _on_error(self) -> None:
        self.notify("Unable to preview song", severity="warning", title="Preview")

    @on(StaticButton.Pressed, "#preview")
    def preview(self) -> None:
        if not self.song.snippet:
            self.notify("Unable to preview song", severity="warning", title="Preview")
            return
        self.player.preview(self.song.snippet, self._on_play, self._on_error)

    @on(ToggleButton.Pressed, "#favorite")
    async def favorite(self) -> None:
        self.query_one("#favorite", ToggleButton).toggle_state()

        client = ListenClient.get_instance()
        await client.favorite_song(self.song.id)

    @on(StaticButton.Pressed, "#request")
    async def request(self) -> None:
        client = ListenClient.get_instance()
        res: Song | None = await client.request_random_favorite(exception_on_error=False)
        romaji_first = Config.get_config().display.romaji_first

        if not res:
            self.notify("All requests have been used up for today!", severity="warning")
        else:
            title = res.format_title(romaji_first=romaji_first)
            artist = res.format_artists(romaji_first=romaji_first)
            self.notify(
                f"{title}" + f" by [{Theme.ACCENT}]{artist}[/]" if artist else "",
                title="Sent to queue",
            )

    # def on_mount(self) -> None:
    #     self.notify(f"{self.song.format_title()}")
    #     for widget in [self, *self.query("*")]:
    #         widget.tooltip = "\n".join(
    #             f"{node!r}" for node in widget.ancestors_with_self
    #         )  # + "\n\n" + widget.styles.css
