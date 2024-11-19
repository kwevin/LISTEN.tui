from typing import ClassVar

from textual import events, on
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Grid
from textual.widgets import Button, Label

from listentui.listen.interface import Song
from listentui.screen.modal.baseScreen import BaseScreen
from listentui.widgets.artistScrollableLabel import ArtistCharacterLabel


class SelectionScreen(BaseScreen[None, None, None]):
    """Screen for confirming actions"""

    DEFAULT_CSS = """
    SelectionScreen {
        align: center middle;
    }
    SelectionScreen Container {
        width: 60;
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
    SelectionScreen ArtistCharacterLabel {
        width: 1fr;
        align: center middle;
        margin: 1 1 0 1;
    }
    SelectionScreen Center {
        width: 100%;
        height: auto;
    }
    SelectionScreen #cancel {
        margin-top: 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
    ]

    def __init__(self, song: Song):
        super().__init__()
        self.song = song

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Artists")
            for artist_slice in self.song.get_artist_list():
                yield ArtistCharacterLabel(artist_slice)
            with Center():
                yield Button("[N] Cancel", variant="primary", id="cancel")

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)
