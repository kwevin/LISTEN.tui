from textual.app import ComposeResult
from textual.events import Key
from textual.reactive import var
from textual.screen import Screen
from textual.widgets import Footer, Placeholder, TabbedContent, TabPane

from ..data.config import Config
from ..data.theme import Theme
from ..utilities import RichLogExtended
from ..widgets import HistoryPage, ListenWebsocket, PlayerPage, SearchPage, SettingPage
from ..widgets.user import UserPage


class Main(Screen[None]):
    DEFAULT_CSS = """
    Main TabPane {
        width: 1fr;
        height: 1fr;
    }
    """
    index: var[int] = var(0, init=False)

    def __init__(self) -> None:
        super().__init__()
        self.logging = Config.get_config().advance.verbose
        self.content = ["home", "search", "history", "terminal", "user", "setting"]
        if self.logging:
            self.content.insert(len(self.content) - 1, "log")

    def watch_index(self, value: int) -> None:
        self.query_one(TabbedContent).active = self.content[value]

    def validate_index(self, value: int) -> int:
        max_idx = len(self.content) - 1
        if value == max_idx + 1:
            value = 0
        elif value == -1:
            value = max_idx

        return value

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Home", id="home"):
                yield PlayerPage()
            with TabPane("Search", id="search"):
                yield SearchPage()
            with TabPane("History", id="history"):
                yield HistoryPage()
            with TabPane("Terminal", id="terminal"):
                yield Placeholder()
            with TabPane("User", id="user"):
                yield UserPage()
            with TabPane("Setting", id="setting"):
                yield SettingPage()
        yield Footer()

    def on_mount(self) -> None:
        if self.logging:
            self.query_one(TabbedContent).add_pane(TabPane("Log", RichLogExtended(), id="log"), before="setting")
        # for widget in [self, *self.query("*")]:
        #     widget.tooltip = "\n".join(f"{node!r}" for node in widget.ancestors_with_self)

    def on_tabbed_content_tab_activated(self, tab: TabbedContent.TabActivated) -> None:
        tab_id = tab.pane.id
        if not tab_id:
            return
        self.index = self.content.index(tab_id)

    def on_key(self, event: Key) -> None:
        if event.key == "tab":
            event.prevent_default()
            self.index += 1
        elif event.key == "shift+tab":
            event.prevent_default()
            self.index -= 1

    def on_listen_websocket_updated(self, event: ListenWebsocket.Updated) -> None:
        romaji_first = Config.get_config().display.romaji_first
        title = event.data.song.format_title(romaji_first=romaji_first)
        artist = event.data.song.format_artists(romaji_first=romaji_first)
        self.notify(f"{title}" + f" by [{Theme.ACCENT}]{artist}[/]" if artist else "", title="Now Playing")
        self.query_one(HistoryPage).update_one()
