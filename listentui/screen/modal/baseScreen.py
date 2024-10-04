from abc import abstractmethod

from textual.screen import ModalScreen
from typing_extensions import TypeVar

ScreenResultType = TypeVar("ScreenResultType")


class BaseScreen(ModalScreen[ScreenResultType]):
    @abstractmethod
    def action_cancel(self) -> None: ...

    def on_click(self) -> None:
        first_depth = self.query("Screen > *")
        if not any(widget.is_mouse_over for widget in first_depth):
            self.action_cancel()
