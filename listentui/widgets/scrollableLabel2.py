from __future__ import annotations

from typing import ClassVar, Iterable

from rich.pretty import pretty_repr
from textual import events, on
from textual.app import RenderResult
from textual.containers import Container
from textual.content import Content
from textual.message import Message
from textual.reactive import reactive, var
from textual.timer import Timer
from textual.widget import Widget


class TextFragment:
    def __init__(self, start: int, segment: Content, index: int, is_cell: bool = False) -> None:
        self.segment = segment
        self.start = start
        self.index = index
        self.end = start + segment.cell_length if is_cell else start + len(segment)

    def __rich_repr__(self):
        yield "Start", self.start
        yield "End", self.end
        yield "Segment", self.segment

    def __hash__(self) -> int:
        return hash((self.start, self.end))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TextFragment):
            return NotImplemented
        return (self.start, self.end) == (other.start, other.end)

    def within_range(self, value: int) -> bool:
        return value >= self.start and value < self.end


class ScrollLabel(Widget):
    COMPONENT_CLASSES: ClassVar[set[str]] = {"scroll-label--highlighted", "scroll-label--separator"}

    DEFAULT_CSS = """
    ScrollLabel {
        width: 100%;
        height: 1;
        text-wrap: nowrap;
        text-overflow: clip;

        & > .scroll-label--highlighted {
            text-style: bold not underline;
            background: $link-background-hover;
            color: $link-color;
        }

        & > .scroll-label--separator {
            color: gray;
            background: initial;
        }
    }
    """

    ALLOW_SELECT = False

    _label: reactive[Content] = reactive(Content(""), always_update=True)
    _scroll_pos: var[int] = var(0)
    _mouse_pos: var[int] = var(-1)

    class Clicked(Message):
        def __init__(self, widget: ScrollLabel, content: Content, index: int) -> None:
            super().__init__()
            self.widget = widget
            self.content = content
            self.index = index

        @property
        def control(self) -> ScrollLabel:
            return self.widget

    def __init__(
        self,
        *labels: str | Iterable[str],
        separator: str = " ",
        scroll: bool = True,
        normalise: bool = False,
        highlight: bool = True,
        scroll_interval: float = 0.1,
        auto_dock: bool = True,
        dock_delay: float = 2.5,
        dock_speed: float = 0.05,
    ):
        super().__init__()
        self.separator = separator
        self.scroll = scroll
        self.normalise = normalise
        self.highlight = highlight
        self.auto_dock = auto_dock
        self.dock_delay = dock_delay

        self._initial_labels = labels
        self._width_known = False
        self._container_width = 0
        self._range_map: dict[TextFragment, TextFragment] = {}
        self._scroll_cell_buffer: int = 0
        self._scrolled_cell = 0
        self._highlighted_range: TextFragment | None = None
        self._highlighted_text: Content = Content("")
        self._whole_text = Content("")
        self._raw_cell = 0
        self._scroller = self.set_interval(scroll_interval, self._increment_scroll_pos, pause=True)
        self._docker = self.set_interval(dock_speed, self._dock, pause=True)
        self._dock_delay_timer: Timer | None = None
        self._can_scroll = False

    def __rich_repr__(self):
        yield "range_map", [(pretty_repr(key), pretty_repr(value)) for key, value in self._range_map.items()]

    def render(self) -> RenderResult:
        return self._label

    def update(self, *labels: str | Iterable[str]):
        self._initial_labels = labels
        self._reset()
        self._generate_label()

    def _watch__scroll_pos(self):
        if self._width_known is False:
            return
        if self._mouse_pos != -1 and self.highlight:
            self._make_with_highlight()
        else:
            self._make_segment(self._whole_text)

    def _watch__mouse_pos(self):
        if self._width_known is False:
            return
        if not self.highlight:
            return
        if self._whole_text.cell_length == 0:
            return
        if self._mouse_pos == -1:
            self._remove_mouse_highlight()
            return
        self._make_with_highlight()

    def _increment_scroll_pos(self):
        if self.normalise:
            next_char = self._whole_text[self._scroll_pos % len(self._whole_text)]
            self._scroll_cell_buffer += 1
            if next_char.cell_length > self._scroll_cell_buffer:
                return
            self._scroll_cell_buffer = 0

        self._scroll_pos = (self._scroll_pos + 1) % len(self._whole_text)

    def _generate_label(self):
        # generate mapping
        last_cell = 0
        last_char = 0
        index = 0
        self._range_map.clear()

        for string in self._initial_labels:
            if isinstance(string, str):
                content = Content(string)
                cell_range = TextFragment(last_cell, content, index, is_cell=True)
                self._range_map[cell_range] = TextFragment(last_char, content, index)

                last_cell = last_cell + len(self.separator) + content.cell_length
                last_char = last_char + len(self.separator) + len(content)
                index += 1
            else:
                for fragment in string:
                    content = Content(fragment)
                    cell_range = TextFragment(last_cell, content, index, is_cell=True)
                    self._range_map[cell_range] = TextFragment(last_char, content, index)

                    # string fragment are joined using one space
                    last_cell = last_cell + 1 + content.cell_length
                    last_char = last_char + 1 + len(content)
                    index += 1

        # generate text
        flattened = [
            Content(text) if isinstance(text, str) else Content(" ").join(text) for text in self._initial_labels
        ]

        content = Content(self.separator).stylize(self.get_visual_style("scroll-label--separator")).join(flattened)
        self._raw_cell = content.cell_length
        self._whole_text = content.pad_right(self._container_width)
        self._make_segment(self._whole_text)

    def _reset(self):
        self._scroll_pos = 0

    def on_resize(self, event: events.Resize):
        self._container_width = event.container_size.width
        self._reset()
        self._generate_label()
        self._width_known = True

    def on_mouse_move(self, event: events.MouseMove) -> None:
        self._mouse_pos = event.x

        if not self._can_scroll and self.scroll and self._raw_cell > self._container_width:
            self._can_scroll = True
            self._scroller.resume()

    def on_click(self, event: events.Click) -> None:
        if self._highlighted_range:
            self.post_message(self.Clicked(self, self._highlighted_range.segment, self._highlighted_range.index))

    def on_leave(self, event: events.Leave) -> None:
        self._mouse_pos = -1
        self._can_scroll = False
        self._scroller.pause()

        if self.auto_dock:
            if self._dock_delay_timer:
                self._dock_delay_timer.reset()
            else:
                self._dock_delay_timer = self.set_timer(self.dock_delay, self._do_dock)

    def _do_dock(self):
        self._docker.resume()

    def _dock(self):
        self._dock_delay_timer = None
        if self._can_scroll:
            self._docker.pause()
            return

        if self._scroll_pos == 0:
            self._docker.pause()
            return

        # determine whether to scroll backward or forward
        length = len(self._whole_text)
        if self._scroll_pos < length // 2:
            self._scroll_pos -= 1
        else:
            self._scroll_pos = (self._scroll_pos + 1) % length

    def _make_segment(self, text: Content):
        index = self._scroll_pos
        scrolled = text[:index]
        self._scrolled_cell = scrolled.cell_length
        self._label = (text[index:] + scrolled)[: self._container_width]

    def _get_text_fragment_from_offset(self, offset: int) -> TextFragment | None:
        if offset < 0:
            return None
        for cell_range, text_range in self._range_map.items():
            if cell_range.within_range(offset):
                return text_range
        return None

    def _make_with_highlight(self):
        cell_pos = (self._scrolled_cell + self._mouse_pos) % self._whole_text.cell_length
        if self._highlighted_range and self._highlighted_range.within_range(cell_pos):
            self._make_segment(self._highlighted_text)
            return

        fragment = self._get_text_fragment_from_offset(cell_pos)
        if fragment:
            highlighted = self._whole_text.stylize(
                self.get_visual_style("scroll-label--highlighted"), fragment.start, fragment.end
            )
            self._highlighted_range = fragment
            self._highlighted_text = highlighted
            self._make_segment(highlighted)
        else:
            self._highlighted_range = None
            self._make_segment(self._whole_text)

    def _remove_mouse_highlight(self):
        self._highlighted_range = None
        self._highlighted_text = Content("")
        self._make_segment(self._whole_text)


from textual.app import App, ComposeResult


class MyApp(App[None]):
    DEFAULT_CSS = """
    Screen Container {
        width: 40;
    }
    Screen ScrollLabel {
        background: red;
    }
    """

    def compose(self) -> ComposeResult:
        yield Container(
            ScrollLabel(
                "中谷 育",
                " (CV: 原嶋あかり)",
                "天空橋朋花",
                "(CV: Koiwai Kotori)",
                separator=", ",
                scroll_interval=0.1,
                auto_dock=True,
            )
        )

    @on(ScrollLabel.Clicked)
    def clicked(self, event: ScrollLabel.Clicked):
        self.app.notify(str(event.content))


if __name__ == "__main__":
    app = MyApp()
    app.run()
