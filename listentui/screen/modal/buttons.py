from __future__ import annotations

from typing import Any

from textual.binding import BindingType
from textual.message import Message
from textual.widgets import Button, Static

from listentui.data.theme import Theme
from listentui.listen import (
    ArtistID,
)
from listentui.listen.interface import Character
from listentui.screen.modal.messages import SpawnArtistScreen


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


class ArtistButton(Button):
    DEFAULT_CSS = f"""
    ArtistButton {{
        background: {Theme.BUTTON_BACKGROUND};
        max-width: 16;
        max-height: 3;
    }}
    """

    def __init__(self, artist_id: ArtistID, name: str):
        super().__init__(self.clamp(name))
        self.can_focus = False
        self.artist_id = artist_id

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        self.post_message(SpawnArtistScreen(self.artist_id))

    def clamp(self, text: str) -> str:
        max_length = 16
        return text if len(text) <= max_length else text[: max_length - 1] + "…"


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
