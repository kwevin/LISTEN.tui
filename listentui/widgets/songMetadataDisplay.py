from __future__ import annotations

from typing import Any, Coroutine

from rich.rule import Rule
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid
from textual.events import Click, Focus
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

from listentui.downloader.baseInterface import SongMetadata
from listentui.widgets.scrollableLabel import ScrollableLabel


class SongMetadataDisplay(Widget):
    DEFAULT_CSS = """
    SongMetadataDisplay {
        height: auto;
    }
    SongMetadataDisplay Grid {
        grid-size: 3 2;
        grid-rows: 1;
        grid-columns: 1fr;
        grid-gutter: 1;
        height: auto;
        margin: 1 1;
    }
    SongMetadataDisplay #_display_scores {
        width: 1fr;
        margin-top: 1;
    }
    """

    class Clicked(Message):
        def __init__(self, metadata: SongMetadata | None, display: SongMetadataDisplay) -> None:
            super().__init__()
            self.metadata = metadata
            self.display = display

        @property
        def control(self) -> SongMetadataDisplay:
            return self.display

    def __init__(
        self,
        metadata: SongMetadata | None = None,
        show_scores: bool = False,
        show_url: bool = False,
        can_click: bool = False,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._can_click = can_click
        self._show_url = show_url
        self._initial_data = metadata
        self._show_scores = show_scores
        self._url_title = ScrollableLabel(highlight_under_mouse=False, id="_url_title")
        self._url_artists = ScrollableLabel(highlight_under_mouse=False, id="_url_artists")
        self._url_album = ScrollableLabel(highlight_under_mouse=False, id="_url_album")

    def compose(self) -> ComposeResult:
        if self._show_url:
            yield Label(id="_display_url")
        if self._show_scores:
            yield Label(id="_display_scores")
        with Grid():
            yield Label("Title")
            yield Label("Artists")
            yield Label("Album")
            yield self._url_title
            yield self._url_artists
            yield self._url_album

    def on_mount(self):
        if self._initial_data:
            self.update(self._initial_data)

    def update(self, metadata: SongMetadata):
        self._url_title.update(Text(metadata.title))
        self._url_title.tooltip = metadata.alternate_title

        self._url_artists.update(Text(", ".join(metadata.artists)))
        self._url_album.update(Text(metadata.album or ""))

        if self._show_scores:
            scores = [
                f"TL: {round(metadata.scores.title, 2)}",
                f"AR: {round(metadata.scores.artist, 2)}",
                f"AL: {round(metadata.scores.album, 2)}",
                f"B: {sum(metadata.scores.bonuses)}",
            ]
            label = self.query_one("#_display_scores", Label)
            label.update(Rule(f"{metadata.scores.total:.2f}"))
            label.tooltip = " ".join(scores)

        if self._show_url:
            self.query_one("#_display_url", Label).update(metadata.url)

    def on_click(self, event: Click):
        if self._can_click:
            self.post_message(self.Clicked(self._initial_data, self))
