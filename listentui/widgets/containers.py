import asyncio
from typing import Optional

from rich.console import RenderableType
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import Label

from ..data import Config
from ..listen.types import Song


class ScrollableLabel(Label):
    content: var[str] = var(str())
    _scroll_content: reactive[Text] = reactive(Text(), init=False)

    def watch_content(self, new: str) -> None:
        self.set_content(new)

    def watch_mouse_over(self, value: bool) -> None:
        if Text.from_markup(self.content).cell_len > self.region.width:
            if value:
                self.scroll_worer = self.scroll()
            else:
                self.scroll_worer.cancel()
                self.set_content(self.content)

    def render(self) -> RenderableType:
        return self._scroll_content

    def set_content(self, content: str) -> None:
        self._scroll_content = Text.from_markup(content)
        self._scroll_content.no_wrap = True
        self._scroll_content.overflow = "ellipsis"

    @work(exclusive=True, group="scrollable-label")
    async def scroll(self) -> None:
        max_offset: int = self._scroll_content.cell_len - self.region.width
        speed: float = 0.1
        text_raw: str = self._scroll_content.plain
        # TODO: make this work
        # spans: list[Span] = self._scroll_content.spans.copy()
        # for i in range(max_offset + 1):
        #     new_spans: list[Span] = []
        #     for index, span in enumerate(spans):
        #         if index == 0:
        #             if span.start == 0:
        #                 new_spans.append(Span(span.start, span.end - 1, span.style))
        #             else:
        #                 new_spans.append(span.move(-1))
        #         else:
        #             new_spans.append(span.move(-1))
        #     getLogger(__name__).debug(f"text: {text_raw[i::]}\nspan: {pretty_repr(new_spans)}")
        #     self._scroll_content = Text(text_raw[i::], overflow="ellipsis", no_wrap=True, spans=new_spans)
        for i in range(max_offset + 1):
            self._scroll_content = Text(text_raw[i::], overflow="ellipsis", no_wrap=True)
            self.refresh(layout=True)
            await asyncio.sleep(speed)


class ArtistLabel(ScrollableLabel):
    DEFAULT_CSS = """
    ArtistLabel {
        width: 1fr;
        color: rgb(249,	38, 114);
    }
    """
    artist: reactive[str] = reactive("", init=False, layout=True)

    def watch_artist(self, value: str) -> None:
        self.content = value


class TitleLabel(ScrollableLabel):
    DEFAULT_CSS = """
    TitleLabel {
        width: 1fr;
    }
    """
    title: reactive[str] = reactive("", init=False, layout=True)
    source: reactive[str] = reactive("", init=False, layout=True)

    def validate_source(self, source: str) -> str:
        return "" if not source else f"[cyan]\\[{source}][/cyan]"

    def watch_title(self, value: str) -> None:
        self.content = f"{self.title} {self.source}".strip()

    def watch_source(self, value: str) -> None:
        self.content = f"{self.title} {self.source}".strip()


class SongContainer(Widget):
    DEFAULT_CSS = """
    SongContainer {
        width: auto;
        height: auto;
    }
    """
    song: reactive[None | Song] = reactive(None, layout=True, init=False)
    artist: var[str] = var(str())
    title: var[str] = var(str())
    source: var[str] = var(str())

    def __init__(self, song: Optional[Song] = None) -> None:
        super().__init__()
        if song:
            self.song = song

    def watch_song(self, song: Song) -> None:
        romaji_first = Config.get_config().display.romaji_first
        self.artist = song.format_artists(romaji_first=romaji_first, embed_link=True) or ""
        self.title = song.format_title(romaji_first=romaji_first) or ""
        self.source = song.format_source(romaji_first=romaji_first, embed_link=True) or ""
        self.query_one(TitleLabel).title = self.title
        self.query_one(TitleLabel).source = self.source
        self.query_one(ArtistLabel).artist = self.artist

    def compose(self) -> ComposeResult:
        yield ArtistLabel()
        yield TitleLabel()

    def set_tooltips(self, string: str | None) -> None:
        self.query_one(TitleLabel).tooltip = string
