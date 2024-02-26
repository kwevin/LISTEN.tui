import asyncio
from typing import Any, ClassVar, Literal, Optional

from rich.console import RenderableType
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label, ProgressBar, Static

from ..data import Config, Theme
from ..listen import ListenClient
from ..listen.types import Song


class ScrollableLabel(Widget):
    DEFAULT_CSS = """
    ScrollableLabel {
        height: auto;
    }
    ScrollableLabel Container {
        width: 100%;
        height: auto;
    }
    ScrollableLabel Label {
        width: auto;
        height: auto;
    }
    """
    content: var[str] = var(str())
    _scroll_content: var[Text] = var(Text(), init=False)

    def __init__(  # noqa: PLR0913
        self,
        label: str | None = None,
        *children: Widget,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(*children, name=name, id=id, classes=classes, disabled=disabled)
        self._container = Container()
        self._label = Label()
        self._label.watch_mouse_over = self.watch_mouse_over
        self.content = label or ""

    def watch_content(self, new: str) -> None:
        self._set_content(new)

    def watch__scroll_content(self, new: Text) -> None:
        self._label.update(new)

    def watch_mouse_over(self, value: bool) -> None:
        if Text.from_markup(self.content).cell_len > self._container.region.width:
            if value:
                self.scroll_worer = self.scroll()
            else:
                self.scroll_worer.cancel()
                self._set_content(self.content)

    def compose(self) -> ComposeResult:
        with self._container:
            yield self._label

    def _set_content(self, content: str) -> None:
        self._label.update(Text.from_markup(content))

    def set_tooltips(self, string: str | None) -> None:
        self._label.tooltip = string

    @work(exclusive=True, group="scrollable-label")
    async def scroll(self) -> None:
        text = Text.from_markup(self.content)
        text_raw = text.plain
        max_offset = text.cell_len - self._container.region.width
        speed = 0.1
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
            await asyncio.sleep(speed)


class SongContainer(Widget):
    DEFAULT_CSS = """
    SongContainer {
        width: 1fr;
        height: auto;
    }
    SongContainer #artist {
        color: rgb(249, 38, 114);
    }
    """
    song: reactive[None | Song] = reactive(None, layout=True, init=False)

    def __init__(self, song: Optional[Song] = None) -> None:
        super().__init__()
        if song:
            self.song = song

    def watch_song(self, song: Song) -> None:
        romaji_first = Config.get_config().display.romaji_first
        self.artist = song.format_artists(romaji_first=romaji_first, embed_link=True) or ""
        self.title = song.format_title(romaji_first=romaji_first) or ""
        self.source = song.format_source(romaji_first=romaji_first, embed_link=True)
        self.query_one("#artist", ScrollableLabel).content = self.artist
        self.query_one("#title", ScrollableLabel).content = self.format_title(self.title, self.source)

    def compose(self) -> ComposeResult:
        yield ScrollableLabel(id="artist")
        yield ScrollableLabel(id="title")

    def set_tooltips(self, string: str | None) -> None:
        self.query_one("#title", ScrollableLabel).set_tooltips(string)

    def format_title(self, title: str, source: str | None) -> str:
        source = f"[cyan]\\[{source}][/cyan]" if source else ""
        return f"{title} {source}".strip()


class _DurationCompleteLabel(Static):
    current = reactive(0, layout=True)
    total = reactive(0, layout=True)

    def validate_current(self, value: int | float) -> int:
        if isinstance(value, float):
            return int(value)
        return value

    def validate_total(self, value: int | float) -> int:
        if isinstance(value, float):
            return int(value)
        return value

    def render(self) -> RenderableType:
        m, s = divmod(self.current, 60)
        completed = f"{m:02d}:{s:02d}"

        if self.total != 0:
            m, s = divmod(self.total, 60)
            total = f"{m:02d}:{s:02d}"
            return f"{completed}/{total}"
        return f"{completed}/--:--"


class DurationProgressBar(Widget):
    DEFAULT_CSS = f"""
    DurationProgressBar {{
        width: 1fr;
    }}
    DurationProgressBar ProgressBar Bar {{
        width: 1fr;
    }}
    DurationProgressBar ProgressBar {{
        width: 1fr;
    }}
    DurationProgressBar ProgressBar Bar > .bar--indeterminate {{
        color: {Theme.ACCENT};
    }}
    DurationProgressBar ProgressBar Bar > .bar--bar {{
        color: {Theme.ACCENT};
    }}
    DurationProgressBar _DurationCompleteLabel {{
        width: auto;
        margin: 0 2 0 2;
    }}
    """

    def __init__(self, current: int = 0, total: int = 0, stop: bool = False, pause_on_end: bool = False) -> None:
        super().__init__()
        self.timer = self.set_interval(1, self._update_progress)
        if stop:
            self.timer.pause()
        self.current = current
        self.total = total
        self.pause_on_end = pause_on_end
        self.time_end = 0

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield ProgressBar(show_eta=False, show_percentage=False)
            yield _DurationCompleteLabel()

    def on_mount(self) -> None:
        self.query_one(_DurationCompleteLabel).current = self.current
        self.query_one(_DurationCompleteLabel).total = self.total
        self.query_one(ProgressBar).update(total=self.total if self.total != 0 else None, progress=self.current)

    def _update_progress(self) -> None:
        if self.total != 0 and self.pause_on_end and self.current >= self.total:
            self.timer.pause()
            return
        self.current += 1
        self.query_one(ProgressBar).advance(1)
        self.query_one(_DurationCompleteLabel).current = self.current

    # def update_progress(self, data: ListenWsData):
    #     # TODO: what in the blackmagic fuck
    #     self.time_end = data.song.time_end
    #     if data.song.duration:
    #         self.current = (datetime.now(timezone.utc) - data.start_time).total_seconds()
    #     else:
    #         self.current = 0
    #     self.total = data.song.duration or 0
    #     self.query_one(ProgressBar).update(total=self.total if self.total != 0 else None, progress=self.current)

    def update_progress(self, song: Song) -> None:
        self.time_end = song.time_end
        self.current = 0
        self.query_one(_DurationCompleteLabel).current = self.current
        self.total = song.duration or 0
        self.query_one(_DurationCompleteLabel).total = self.total
        self.query_one(ProgressBar).update(total=self.total if self.total != 0 else None, progress=self.current)

    def pause(self) -> None:
        self.timer.pause()

    def resume(self) -> None:
        self.timer.resume()

    def reset(self) -> None:
        self.current = 0
        self.query_one(ProgressBar).update(total=self.total if self.total != 0 else None, progress=self.current)


class ExtendedDataTable(DataTable[Any]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "select_cursor", "Select", show=False),
        Binding("up,k", "cursor_up", "Cursor Up", show=False),
        Binding("down,j", "cursor_down", "Cursor Down", show=False),
        Binding("right,l", "cursor_right", "Cursor Right", show=False),
        Binding("left,h", "cursor_left", "Cursor Left", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
    ]


class StaticButton(Button):
    DEFAULT_CSS = f"""
    StaticButton {{
        background: {Theme.BUTTON_BACKGROUND};
    }}
    """

    def __init__(  # noqa: PLR0913
        self,
        label: str | Text | None = None,
        variant: Literal["default", "primary", "success", "warning", "error"] = "default",
        *,
        check_user: bool = False,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ):
        super().__init__(label, variant, name=name, id=id, classes=classes, disabled=disabled)
        self.can_focus = False
        self._check_user = check_user

    async def on_mount(self) -> None:
        if self._check_user:
            client = ListenClient.get_instance()
            if not client.logged_in:
                self.disabled = True


class ToggleButton(StaticButton):
    DEFAULT_CSS = f"""
    ToggleButton.-toggled {{
        background: {Theme.ACCENT};
        text-style: bold reverse;
    }}
    """
    is_toggled: reactive[bool] = reactive(False, init=False, layout=True)

    class Toggled(Message):
        def __init__(self, state: bool) -> None:
            super().__init__()
            self.state = state

    def __init__(  # noqa: PLR0913
        self,
        label: str | Text | None = None,
        toggled_label: str | Text | None = None,
        variant: Literal["default", "primary", "success", "warning", "error"] = "default",
        *,
        check_user: bool = False,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ):
        super().__init__(label, variant, name=name, id=id, classes=classes, disabled=disabled, check_user=check_user)
        self._default = label
        self._toggled_label = toggled_label

    def watch_is_toggled(self, new: bool) -> None:
        self.toggle_class("-toggled")
        if new and self._toggled_label:
            self.label = self._toggled_label
        else:
            self.label = self._default or ""

    @on(Button.Pressed)
    def toggle_state(self) -> None:
        self.is_toggled = not self.is_toggled
        self.post_message(self.Toggled(self.is_toggled))

    def set_state(self, state: bool) -> None:
        self.is_toggled = state
