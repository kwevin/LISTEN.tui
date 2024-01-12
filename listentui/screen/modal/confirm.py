from typing import ClassVar, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    """Screen for confirming actions"""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
        background: $background;
    }

    ConfirmScreen #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }

    ConfirmScreen #question {
        column-span: 2;
        height: 1fr;
        width: 1fr;
        content-align: center middle;
    }

    ConfirmScreen Button {
        width: 100%;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
        ("enter,y,Y", "confirm"),
        ("left", "focus_previous"),
        ("right", "focus_next"),
    ]

    def __init__(
        self,
        label: Optional[str] = None,
        option_true: Optional[str] = None,
        option_false: Optional[str] = None,
    ):
        super().__init__()
        self.label = label or "Are you sure you want to proceed"
        self.option_true = option_true or "Confirm"
        self.option_false = option_false or "Cancel"

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(self.label, id="question"),
            Button(f"[Y] {self.option_true}", variant="error", id="confirm"),
            Button(f"[N] {self.option_false}", variant="primary", id="cancel"),
            id="dialog",
        )

    @on(Button.Pressed, "#confirm")
    def action_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(False)
