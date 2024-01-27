from typing import Any, ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Grid
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class OptionButton(Button):
    def __init__(self, *args: Any, index: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.index = index

    class Selected(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.post_message(self.Selected(self.index))


class SelectionScreen(ModalScreen[int | None]):
    """Screen for confirming actions"""

    DEFAULT_CSS = """
    SelectionScreen {
        align: center middle;
        background: $background;
    }
    SelectionScreen Container {
        width: auto;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }
    SelectionScreen Label {
        height: auto;
        width: 100%;
        content-align: center middle;
        margin-left: 1;
    }
    SelectionScreen Grid {
        grid-size: 2;
        grid-gutter: 1 2;
        padding: 1 1;
        width: 60;
        height: auto;

    }
    SelectionScreen Button {
        width: 100%;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
        ("left", "focus_previous"),
        ("right", "focus_next"),
        ("up", "focus_up"),
        ("down", "focus_down"),
    ]

    def __init__(self, options: list[str]):
        super().__init__()
        self.options = options

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Select one")
            with Grid():
                for idx, option in enumerate(self.options):
                    yield OptionButton(self.clamp(f"[{idx + 1}] {option}"), index=idx)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_focus_up(self) -> None:
        # what the fuck am i doing
        self.focus_previous()
        self.focus_previous()

    def action_focus_down(self) -> None:
        # if it works it works
        self.focus_next()
        self.focus_next()

    def on_option_button_selected(self, event: OptionButton.Selected) -> None:
        self.dismiss(event.index)

    def on_key(self, event: events.Key) -> None:
        if event.key.isdigit() and event.key != "0" and int(event.key) <= len(self.options):
            self.dismiss(int(event.key) - 1)

    def clamp(self, text: str) -> str:
        min_len = 24
        return text if len(text) <= min_len else text[: min_len - 1] + "…"


if __name__ == "__main__":
    from textual import work
    from textual.app import App
    from textual.widgets import Footer

    class TestApp(App[None]):
        BINDINGS = [("q", "options", "Options")]  # noqa: RUF012

        def compose(self) -> ComposeResult:
            yield Label()
            yield Footer()

        @work
        async def action_options(self) -> None:
            options = ["option 1", "option 2", "option 3", "option 4", "this option is too long to be displayed 5"]
            result = await self.push_screen(SelectionScreen(options), wait_for_dismiss=True)
            if result is not None:
                self.query_one(Label).update(f"{options[result]}")
                self.notify(f"{options[result]}")

    app = TestApp()
    app.run()
