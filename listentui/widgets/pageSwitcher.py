from __future__ import annotations

from math import ceil
from typing import Literal, Self, cast

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import QueryError
from textual.message import Message
from textual.reactive import reactive, var
from textual.validation import Number
from textual.widget import Widget
from textual.widgets import Label, Static

from listentui.widgets.minimalInput import MinimalInput


class PageNavigationButton(Static, can_focus=True):
    DEFAULT_CSS = """
    PageNavigationButton {
        width: auto;
        height: 1;
        padding: 0 1;

        &:hover {
            tint: $surface-lighten-3 50%;
        }
    }
    """

    class PreviousSelected(Message):
        def __init__(self) -> None:
            super().__init__()

    class NextSelected(Message):
        def __init__(self) -> None:
            super().__init__()

    class InputSelected(Message):
        def __init__(self) -> None:
            super().__init__()

    def __init__(self, navigation_type: Literal["previous", "next", "input"]) -> None:
        super().__init__(
            "Prev" if navigation_type == "previous" else ("Next" if navigation_type == "next" else "…"),
            classes="page_navigator",
        )
        self.navigation_type = navigation_type

    @classmethod
    def previous(cls) -> Self:
        return cls("previous")

    @classmethod
    def next(cls) -> Self:
        return cls("next")

    @classmethod
    def input(cls) -> Self:
        return cls("input")

    def on_click(self, event: events.Click) -> None:
        event.stop()

        if self.navigation_type == "previous":
            self.post_message(self.PreviousSelected())
        elif self.navigation_type == "next":
            self.post_message(self.NextSelected())
        else:
            self.post_message(self.InputSelected())


class PageButton(Static, can_focus=True):
    DEFAULT_CSS = """
    PageButton {
        width: auto;
        height: 1;
        padding: 0 1;

        &.current {
            background: $primary-lighten-2;
        }

        &:hover {
            tint: $surface-lighten-3 50%;
        }
    }
    """

    class PageSelected(Message):
        def __init__(self, page: int) -> None:
            super().__init__()
            self.page = page

    def __init__(self, page: int, current: bool = False) -> None:
        super().__init__(f"{page}", id=f"_page_button_{page}")
        self.set_class(current, "current")
        self.page = page

    @classmethod
    def current_page(cls, page: int) -> Self:
        return cls(page, True)

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.PageSelected(self.page))


class PageInputSelector(Widget):
    # code borrowed from https://github.com/darrenburns/textual-autocomplete
    DEFAULT_CSS = """
    PageInputSelector {
        layer: page_input_selector;
        display: none;
        width: auto;
        height: 1;
        dock: top;
        background: $surface;
    }

    PageInputSelector Horizontal {
        height: 1;
        width: auto;
    }
    """

    def __init__(self, pageswitcher: PageSwitcher, limit: int) -> None:
        super().__init__()
        self.page_switcher = pageswitcher
        self.current = 1
        self.max = limit
        self.input = MinimalInput(validators=Number(minimum=1, maximum=limit))

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self.input
            yield Label(f"/{self.max}", id="lim")

    def on_mount(self) -> None:
        screen_layers = list(self.screen.styles.layers)
        if "page_input_selector" not in screen_layers:
            screen_layers.append("page_input_selector")
        self.screen.styles.layers = tuple(screen_layers)  # type: ignore

    def set_position(self) -> None:
        cursor_pos = self.app.mouse_position
        self.styles.offset = (cursor_pos.x, cursor_pos.y + 1)

    def show(self, page_switcher: PageSwitcher, current: int, limit: int) -> None:
        self.page_switcher = page_switcher
        self.styles.display = "block"
        self.set_position()
        self.max = limit
        self.query_one("#lim", Label).update(f"/{limit}")
        cast(Number, self.input.validators[0]).maximum = limit
        self.current = current
        self.input.value = f"{current}"
        self.input.focus()

    @on(events.DescendantBlur)
    def hide(self) -> None:
        self.styles.display = "none"

    @on(events.MouseScrollDown)
    def handle_down(self, _) -> None:
        self.current = max(self.current - 1, 0)
        self.input.value = f"{self.current}"

    @on(events.MouseScrollUp)
    def handle_up(self, _) -> None:
        self.current = min(self.current + 1, self.max)
        self.input.value = f"{self.current}"

    def on_input_submitted(self, event: MinimalInput.Submitted) -> None:
        if event.validation_result and event.validation_result.is_valid:
            self.page_switcher.set_page(int(event.value))
            self.page_switcher.focus()


class PageSwitcher(Horizontal, can_focus=True):
    DEFAULT_CSS = """
    PageSwitcher {
        height: 1;
        width: 100%;
        align-horizontal: center;
    }
    """
    current_page: var[int] = var(1, init=False, always_update=False)
    _pages_to_render: reactive[list[Widget]] = reactive([], recompose=True)

    class PageChanged(Message):
        def __init__(self, page: int) -> None:
            super().__init__()
            self.page = page

    def __init__(self, pages: int | None = None) -> None:
        super().__init__()
        self.end_page = pages or 0

    @classmethod
    def calculate(cls, amount_per_page: int, total: int) -> Self:
        return cls(ceil(max(total / amount_per_page, 1)))

    def compose(self) -> ComposeResult:
        yield from self._pages_to_render

    def on_mount(self) -> None:
        try:
            self.screen.query_one(PageInputSelector)
        except QueryError:
            self.screen.mount(PageInputSelector(self, self.end_page))

    def on_resize(self, event: events.Resize) -> None:
        if event.size.width:
            self.create_from_width(event.size.width)

    def create_from_width(self, width: int) -> None:
        self._pages_to_render.clear()
        min_size = 12
        if width < min_size:
            return
        if self.end_page == 1:
            self._pages_to_render = self.create_pages(True)
            return
        width -= 12  # nav button
        if width - sum(self.size_of_page(page) for page in range(1, self.end_page + 1)) > 0:
            self._pages_to_render = self.create_pages(True)
        else:
            self._pages_to_render = self.create_pages()

    def create_pages(self, render_all: bool = False) -> list[Widget]:
        pages_to_render: list[Widget] = [
            self.create_prev_page(),
        ]
        if render_all:
            pages_to_render.extend([self.create_page(page) for page in range(1, self.end_page + 1)])
            pages_to_render.append(self.create_next_page())
            return pages_to_render

        per_side = 3
        # start is visible
        if self.current_page <= 2 + per_side:
            pages_to_render.extend(
                [self.create_page(page) for page in range(1, min(self.end_page - 2, per_side * 2 + 2))]
            )
            pages_to_render.extend([self.create_input_page(), self.create_page(self.end_page), self.create_next_page()])

            return pages_to_render
        # end is visible
        if self.current_page + per_side + 1 >= self.end_page:
            pages_to_render.extend([self.create_page(1), self.create_input_page()])
            pages_to_render.extend(
                [self.create_page(page) for page in range(self.end_page - per_side * 2 - 1, self.end_page + 1)]
            )
            pages_to_render.append(self.create_next_page())
            return pages_to_render

        # both start and end is not visible
        pages_to_render.extend([self.create_page(1), self.create_input_page()])
        pages_to_render.extend(
            [self.create_page(page) for page in range(self.current_page - per_side, self.current_page + per_side + 1)]
        )
        pages_to_render.extend([self.create_input_page(), self.create_page(self.end_page), self.create_next_page()])
        return pages_to_render

    def create_page(self, page: int) -> PageButton:
        if page == self.current_page:
            return PageButton.current_page(page)
        return PageButton(page)

    def size_of_page(self, page: int) -> int:
        return len(str(page)) + 2

    def create_input_page(self) -> PageNavigationButton:
        return PageNavigationButton.input()

    def create_prev_page(self) -> PageNavigationButton:
        return PageNavigationButton.previous()

    def create_next_page(self) -> PageNavigationButton:
        return PageNavigationButton.next()

    def watch_current_page(self, new_page: int) -> None:
        self.create_from_width(self.size.width)
        self.post_message(self.PageChanged(new_page))

    def on_page_navigation_button_previous_selected(self, event: PageNavigationButton.PreviousSelected) -> None:
        event.stop()
        self.current_page = max(self.current_page - 1, 1)

    def on_page_navigation_button_next_selected(self, event: PageNavigationButton.NextSelected) -> None:
        event.stop()
        self.current_page = min(self.current_page + 1, self.end_page)

    def on_page_button_page_selected(self, event: PageButton.PageSelected) -> None:
        event.stop()
        self.current_page = event.page

    def on_page_navigation_button_input_selected(self, event: PageNavigationButton.InputSelected) -> None:
        event.stop()
        self.screen.query_one(PageInputSelector).show(self, self.current_page, self.end_page)

    def set_page(self, page: int) -> None:
        self.current_page = page

    def reset(self) -> None:
        with self.prevent(self.PageChanged):
            self.set_page(1)

    def update(self, new_end_page: int) -> None:
        self.end_page = new_end_page
        self.create_from_width(self.size.width)

    def calculate_update_end_page(self, amount_per_page: int, total: int) -> None:
        self.update(ceil(max(total / amount_per_page, 1)))


if __name__ == "__main__":
    from textual.app import App

    class MyApp(App[None]):
        def compose(self) -> ComposeResult:
            yield PageSwitcher.calculate(1, 1000)

        async def on_mount(self) -> None:
            self.set_timer(5, self.query_one(PageSwitcher).reset)

        @on(PageSwitcher.PageChanged)
        def a(self) -> None:
            self.notify("kjdfgkjdf")

    app = MyApp()
    app.run()
