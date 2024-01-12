from textual import on
from textual.app import ComposeResult
from textual.events import Key
from textual.reactive import var
from textual.screen import Screen
from textual.widgets import Button, ContentSwitcher, Footer, Placeholder

from ..data.config import Config
from ..data.theme import Theme
from ..utilities import ListenLog
from ..widgets import History, ListenWebsocket, Player, Search, Topbar


class Main(Screen[None]):
    DEFAULT_CSS = """
    Main ContentSwitcher > * {
        width: 1fr;
        height: 1fr;
    }
    """

    index: var[int] = var(0, init=False)

    def __init__(self) -> None:
        super().__init__()
        self.content = ["home", "search", "history", "terminal", "user", "setting"]
        self.content.insert(len(self.content) - 1, "_rich-log")

    def watch_index(self, value: int) -> None:
        self.query_one(ContentSwitcher).current = self.content[value]

    def validate_index(self, value: int) -> int:
        max_idx = len(self.content) - 1
        if value == max_idx + 1:
            value = 0
        elif value == -1:
            value = max_idx

        return value

    def compose(self) -> ComposeResult:
        yield Topbar()
        with ContentSwitcher(initial="home"):
            yield Player(id="home")
            yield Search(id="search")
            yield History(id="history")
            yield Placeholder(id="terminal")
            yield Placeholder(id="user")
            yield ListenLog.rich_log
            yield Placeholder(id="setting")
        yield Footer()

    @on(Button.Pressed, ".navbutton")
    def on_button_content_switcher(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id:
            index = self.content.index(button_id)
            self.index = index
        self.query_one(f"ContentSwitcher > #{event.button.id}").focus()

    async def on_key(self, event: Key) -> None:
        if event.key == "tab":
            self.index += 1
        elif event.key == "shift+tab":
            self.index -= 1

    def on_listen_websocket_websocket_updated(self, event: ListenWebsocket.WebsocketUpdated) -> None:
        romaji_first = Config.get_config().display.romaji_first
        title = event.data.song.format_title(romaji_first=romaji_first)
        artist = event.data.song.format_artists(romaji_first=romaji_first)
        self.notify(f"{title}" + f" by [{Theme.ACCENT}]{artist}[/]" if artist else "", title="Now Playing")
