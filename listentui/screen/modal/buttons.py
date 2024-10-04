from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from listentui.data.theme import Theme
from listentui.listen import (
    ArtistID,
)
from listentui.listen.interface import Character
from listentui.screen.modal.messages import SpawnArtistScreen
from listentui.widgets.scrollableLabel import ScrollableLabel


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


class ArtistButton(Widget):
    DEFAULT_CSS = """
    ArtistButton {
        width: 16;
        height: 1;
        color: red;
    }
    """

    def __init__(self, artist_id: ArtistID, name: str):
        super().__init__()
        self.can_focus = False
        self.artist = name
        self.artist_id = artist_id

    def compose(self) -> ComposeResult:
        yield ScrollableLabel(Text.from_markup(self.artist))

    def on_scrollable_label_clicked(self) -> None:
        self.post_message(SpawnArtistScreen(self.artist_id))


class EscButton(Static):
    DEFAULT_CSS = """
    EscButton {
        dock: top;
        offset: 2 1;
        width: 7;
        padding: 0 0 !important;
        margin: 0 0 !important;
    }
    """

    def __init__(self) -> None:
        super().__init__("[@click=screen.cancel]< (Esc)[/]", id="esc")
