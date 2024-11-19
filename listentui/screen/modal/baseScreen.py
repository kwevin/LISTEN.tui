from typing import Any, ClassVar, Coroutine, Generic, Self, Type

from textual import work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container
from textual.screen import ModalScreen
from typing_extensions import TypeVar

from listentui.screen.modal.buttons import EscButton

ScreenResultType = TypeVar("ScreenResultType")
ScreenInterfaceType = TypeVar("ScreenInterfaceType")
ScreenInterfaceID = TypeVar("ScreenInterfaceID")


class LoadingScreen(ModalScreen[ScreenInterfaceType]):
    DEFAULT_CSS = """
    LoadingScreen {
        align: center middle;
    }
    LoadingScreen #box {
        width: 11;
        height: 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, awaitable: Coroutine[None, None, ScreenInterfaceType]):
        super().__init__()
        self.awaitable = awaitable

    def compose(self) -> ComposeResult:
        yield Container(id="box")

    @work
    async def on_mount(self) -> None:
        self.query_one("#box", Container).set_loading(True)
        result = await self.awaitable
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss()


class BaseScreen(Generic[ScreenResultType, ScreenInterfaceID, ScreenInterfaceType], ModalScreen[ScreenResultType]):
    def action_cancel(self) -> None: ...

    async def on_click(self) -> None:
        first_depth = self.query("Screen > *")
        if not any(widget.is_mouse_over for widget in first_depth):
            self.action_cancel()

    @classmethod
    async def load(cls, app: App, load_id: ScreenInterfaceID) -> Self: ...
