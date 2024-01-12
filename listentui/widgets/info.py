from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget

from ..utilities import ListenLog


class WebsocketData(Widget):
    ...


class MPVData(Widget):
    ...


class InfoWidget(Widget):
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield WebsocketData()
            yield MPVData()
        yield ListenLog.rich_log
