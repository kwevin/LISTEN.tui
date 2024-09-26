from typing import ClassVar

from textual import events, on
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Grid
from textual.screen import Screen
from textual.widgets import Button, Label

from listentui.screen.modal.buttons import OptionButton


class SelectionScreen(Screen[int | None]):
    """Screen for confirming actions"""

    DEFAULT_CSS = """
    SelectionScreen {
        align: center middle;
        background: $background;
        hatch: left $background-lighten-1 60%;
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
    SelectionScreen OptionButton {
        width: 100%;
    }
    SelectionScreen Center {
        width: 100%;
        height: auto;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
        ("left,h", "focus_previous"),
        ("right,l", "focus_next"),
        ("up,k", "focus_up"),
        ("down,j", "focus_down"),
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
            with Center():
                yield Button("[N] Cancel", variant="primary", id="cancel")

    @on(Button.Pressed, "#cancel")
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
