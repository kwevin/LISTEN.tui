from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget

from listentui.listen.interface import Artist, Character, Song
from listentui.screen.modal.messages import SpawnArtistScreen, SpawnCharacterScreen
from listentui.widgets.scrollableLabel import ScrollableLabel


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
