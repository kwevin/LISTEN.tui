from datetime import datetime
from typing import Any, ClassVar

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Center, Grid, Horizontal, Middle
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Markdown

from ..data.config import Config
from ..data.theme import Theme
from ..listen.client import ListenClient
from ..listen.types import CurrentUser, SystemFeed
from ..utilities import format_time_since
from .base import BasePage


class NamedStatField(Widget):
    DEFAULT_CSS = f"""
    NamedStatField {{
        align: center middle;
        width: auto;
        height: auto;
        max-width: 16;
    }}
    NamedStatField #stat {{
        color: {Theme.ACCENT};
    }}
    """

    stat: reactive[int] = reactive(0, init=False, layout=True)

    def __init__(self, label: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.label = label

    def watch_stat(self, value: int) -> None:
        self.query_one("#stat", Label).update(str(value))

    def compose(self) -> ComposeResult:
        with Center():
            yield Label(str(self.stat), id="stat")
        with Center():
            yield Label(self.label, id="label")


class UserDetails(Widget):
    DEFAULT_CSS = """
    UserDetails {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }
    UserDetails Middle {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }
    UserDetails #username {
        text-style: underline;
    }
    UserDetails Grid {
        grid-size: 2 2;
        grid-rows: 3 1fr;
    }
    UserDetails Markdown {
        row-span: 2;
        height: 1fr;
        margin: 1 3;
    }
    UserDetails Horizontal {
        width: 1fr;
        align: center middle;
    }

    """

    def compose(self) -> ComposeResult:
        with Grid():
            yield Middle(Label(id="username"))
            yield Markdown()
            with Horizontal():
                yield NamedStatField("Requested", id="requested")
                yield NamedStatField("Favorited", id="favorited")
                yield NamedStatField("Uploaded", id="uploaded")

    def update(self, user: CurrentUser) -> None:
        self.query_one("#username", Label).update(Text.from_markup(f"[link={user.link}]{user.display_name}[/link]"))
        self.query_one(Markdown).update(user.bio or "")
        self.query_one("#requested", NamedStatField).stat = user.requests
        self.query_one("#favorited", NamedStatField).stat = user.favorites
        self.query_one("#uploaded", NamedStatField).stat = user.uploads


class UserFeed(Widget):
    feeds: var[list[SystemFeed]] = var([], init=False)

    DEFAULT_CSS = f"""
    UserFeed {{
        margin: 0 4 2 4;
        height: 1fr;
    }}
    UserFeed Label {{
        padding: 0 1;
    }}
    UserFeed #time {{
        padding-bottom: 1;
    }}
    UserFeed .feed-text {{
        margin: 1 0;
    }}
    UserFeed ListItem {{
        margin: 1 0;
        background: {Theme.BACKGROUND};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Label(f"Last Updated: {datetime.now().strftime('%H:%M:%S')}", id="time")
        yield ListView()

    def watch_feeds(self, feeds: list[SystemFeed]) -> None:
        romaji_first = Config.get_config().display.romaji_first
        listview = self.query_one(ListView)
        listview.clear()
        listitems: list[ListItem] = []
        for feed in feeds:
            if not feed.song:
                continue
            title = feed.song.format_title(romaji_first=romaji_first)
            artist = feed.song.format_artists(show_character=False, romaji_first=romaji_first, embed_link=True)
            listitems.append(
                ListItem(
                    Label(
                        Text.from_markup(f"[{Theme.ACCENT}]•[/] {format_time_since(feed.created_at)}"),
                        classes="feed-time",
                    ),
                    Label(
                        Text.from_markup(f"{feed.activity} {title} by [{Theme.ACCENT}]{artist}[/]"),
                        classes="feed-text",
                        shrink=True,
                    ),
                )
            )
        listview.extend(listitems)

    def update(self, user_feeds: list[SystemFeed]) -> None:
        self.feeds = user_feeds
        self.query_one("#time", Label).update(f"Last Updated: {datetime.now().strftime('%H:%M:%S')}")


class UserPage(BasePage):
    DEFAULT_CSS = """
    UserPage UserDetails {
        height: 1fr;
        min-height: 8;
        max-height: 8;
    }
    UserPage Placeholder {
        height: 1fr;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [Binding("ctrl+r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield UserDetails()
        yield UserFeed()

    def on_mount(self) -> None:
        self.action_refresh()

    @work(group="user")
    async def action_refresh(self) -> None:
        client = ListenClient.get_instance()
        feed_amount = Config.get_config().display.user_feed_amount
        user = await client.update_current_user(0, feed_amount)
        if not user:
            return
        self.query_one(UserDetails).update(user)
        self.query_one(UserFeed).update(user.feeds)


if __name__ == "__main__":
    from textual.app import App
    from textual.widgets import Footer

    class TestApp(App[None]):
        def compose(self) -> ComposeResult:
            yield UserPage()
            yield Footer()

    app = TestApp()
    app.run()
