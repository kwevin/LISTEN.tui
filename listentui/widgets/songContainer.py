from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget

from listentui.listen import Song
from listentui.screen.modal.messages import SpawnSongScreen, SpawnSourceScreen
from listentui.widgets.artistScrollableLabel import ArtistScrollableLabel
from listentui.widgets.scrollableLabel import ScrollableLabel


class SongContainer(Widget):
    DEFAULT_CSS = """
    SongContainer {
        width: 1fr;
        height: auto;
    }
    """
    song: reactive[None | Song] = reactive(None, layout=True, init=False)

    def __init__(self, song: Optional[Song] = None) -> None:
        super().__init__()
        self._optional_song = song

    def watch_song(self, song: Song) -> None:
        self.query_one(ArtistScrollableLabel).update(song)
        title = song.format_title() or ""
        source = song.format_source()
        self.query_one("#title", ScrollableLabel).update(Text.from_markup(f"{title}"))
        if source:
            self.query_one("#title", ScrollableLabel).append(Text.from_markup(f"[cyan]\\[{source}][/cyan]"))

    def update_song(self, song: Song) -> None:
        self.song = song

    def compose(self) -> ComposeResult:
        yield ArtistScrollableLabel()
        yield ScrollableLabel(id="title", sep=" ")

    def on_mount(self) -> None:
        if self._optional_song:
            self.watch_song(self._optional_song)

    async def on_scrollable_label_clicked(self, event: ScrollableLabel.Clicked) -> None:
        if not self.song:
            return
        if event.widget.id == "title":
            if event.index == 0:
                self.post_message(SpawnSongScreen(self.song.id))
            else:
                if not self.song.source:
                    return
                source_id = self.song.source.id
                self.post_message(SpawnSourceScreen(source_id))

    def set_tooltips(self, string: str | None) -> None:
        self.query_one("#title", ScrollableLabel).tooltip = string
