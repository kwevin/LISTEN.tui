from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Collapsible, Static


class RemoveButton(Static, can_focus=True):
    DEFAULT_CSS = """
    RemoveButton {
        width: auto;
        height: auto;
        padding: 0 1 0 1;
    }

    RemoveButton:hover {
        background: $foreground 10%;
        color: $text;
    }

    RemoveButton:focus {
        background: $accent;
        color: $text;
    }
    """

    class LaunchCode(Message):
        def __init__(self) -> None:
            super().__init__()

    def on_mount(self) -> None:
        self.update("Remove")

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.LaunchCode())


class RemovableCollapsible(Collapsible):
    DEFAULT_CSS = """
    RemovableCollapsible {
        width: 1fr;
        height: auto;
        background: $boost;
        border-top: hkey $background;
        padding-bottom: 1;
        padding-left: 1;
    }

    RemovableCollapsible.-collapsed > Contents {
        display: none;
    }

    RemovableCollapsible #rc-title {
        width: 100%;
        height: auto;
    }
    RemovableCollapsible #filler {
        width: 1fr;
        height: auto;
    }
    """

    class NuclearLaunched(Message):
        def __init__(self, item: "RemovableCollapsible") -> None:
            super().__init__()
            self.item = item

    def compose(self) -> ComposeResult:
        with Horizontal(id="rc-title"):
            yield self._title
            yield Static(id="filler")
            yield RemoveButton()
        yield self.Contents(*self._contents_list)

    async def on_remove_button_launch_code(self, event: RemoveButton.LaunchCode) -> None:
        self.post_message(self.NuclearLaunched(self))
