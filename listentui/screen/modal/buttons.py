from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from listentui.listen import (
    ArtistID,
)
from listentui.screen.modal.messages import SpawnArtistScreen
from listentui.widgets.scrollableLabel import ScrollableLabel


class OptionButton(Button, can_focus=False):
    DEFAULT_CSS = """
    OptionButton {
        align: center middle;
    }
    OptionButton > ScrollableLabel {
        margin: 0 1 0 1;
    }
    OptionButton > Label {
        width: auto;
    }
    """

    def __init__(self, text: str, index: int, **kwargs: Any) -> None:
        super().__init__("")
        self._size_known = False
        self.text = text
        self.index = index

    def compose(self) -> ComposeResult:
        if self._size_known:
            text = Text.from_markup(f"[{self.index}] {self.text}")
            if text.cell_len < self.size.width:
                yield Label(text, shrink=True)
            else:
                yield ScrollableLabel(text)

    class Selected(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    async def on_resize(self, event: events.Resize) -> None:
        self._size_known = True
        await self.recompose()

    def on_click(self, event: events.Click) -> None:
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
