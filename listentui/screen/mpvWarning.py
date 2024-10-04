import os

from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label


class MPVWarningScreen(ModalScreen[str]):
    def __init__(self, error: OSError) -> None:
        self.error = error

    def compose(self) -> ComposeResult:
        yield Label("This version of LISTEN.tui does not come shipped with libmpv")
        yield Label(str(self.error))

    def on_key(self, event: events.Key) -> None:
        self.dismiss(str(self.error))
