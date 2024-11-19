from typing import Any, Coroutine

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Click
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

from listentui.listen.interface import Artist, Character, Song
from listentui.screen.modal.messages import SpawnArtistScreen, SpawnCharacterScreen
from listentui.widgets.scrollableLabel import ScrollableLabel


class ClickableLabel(Label):
    DEFAULT_CSS = """
    ClickableLabel:hover {
        text-style: bold not underline;
        background: $link-background-hover;
        color: $link-color;
    }
    """

    def __init__(self, *args: Any, index: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.index = index

    class Clicked(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def on_click(self, event: Click) -> None:
        self.post_message(self.Clicked(self.index))


class ArtistCharacterLabel(Widget, can_focus=True):
    DEFAULT_CSS = """
    ArtistCharacterLabel {
        height: 1;
        
        & Horizontal {
            width: auto;
        }
        
        & Label {
            width: auto;
            color: rgb(249, 38, 114);
        }
    }
    """

    def __init__(self, artist_list_slice: tuple[Artist, Character | None]) -> None:
        super().__init__()
        self.slice = artist_list_slice
        self._lookup_table: dict[int, Artist | Character] = {}

        artist, character = self.slice
        self._render_list: list[Text] = []
        if character:
            self._render_list.extend(
                [
                    Text.from_markup(f"{character.format_name()}"),
                    Text.from_markup(f"(CV: {artist.format_name()})"),
                ]
            )
            self._lookup_table[0] = character
            self._lookup_table[1] = artist
        else:
            self._render_list.append(Text.from_markup(f"{artist.format_name()}"))
            self._lookup_table[0] = artist

    def compose(self) -> ComposeResult:
        with Horizontal():
            for idx, item in enumerate(self._render_list):
                yield ClickableLabel(item, index=idx)

    @on(ClickableLabel.Clicked)
    def label_clicked(self, event: ClickableLabel.Clicked) -> None:
        lookup = self._lookup_table[event.index]
        if isinstance(lookup, Artist):
            self.post_message(SpawnArtistScreen(lookup.id))
        else:
            self.post_message(SpawnCharacterScreen(lookup.id))


class ArtistScrollableLabel(Widget):
    DEFAULT_CSS = """
    ArtistScrollableLabel {
        width: 100%;
        height: 1;
        color: rgb(249, 38, 114);
    }
    """

    def __init__(self, song: Song | None = None) -> None:
        super().__init__()
        self.song = song
        self._lookup_table: dict[int, Artist | Character] = {}
        self._label = ScrollableLabel(id="artist")

    def compose(self) -> ComposeResult:
        yield self._label

    def on_mount(self) -> None:
        if self.song:
            self.update(self.song)

    def update(self, song: Song) -> None:
        self.song = song
        self._lookup_table.clear()
        artist_char = song.get_artist_list()
        artist_list: list[Text | tuple[Text, Text]] = []
        idx = 0
        for artist, character in artist_char:
            if character:
                artist_list.append(
                    (Text.from_markup(character.format_name()), Text.from_markup(f"(CV: {artist.format_name()})"))
                )
                self._lookup_table[idx] = character
                self._lookup_table[idx + 1] = artist
                idx += 2
            else:
                artist_list.append(Text.from_markup(artist.format_name()))
                self._lookup_table[idx] = artist
                idx += 1

        self._label.update(*artist_list)

    async def on_scrollable_label_clicked(self, event: ScrollableLabel.Clicked) -> None:
        event.stop()
        if not self.song:
            return
        lookup = self._lookup_table[event.index]
        if isinstance(lookup, Artist):
            self.post_message(SpawnArtistScreen(lookup.id))
        else:
            self.post_message(SpawnCharacterScreen(lookup.id))
