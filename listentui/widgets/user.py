from datetime import datetime
from typing import Any

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Grid, Horizontal, Middle
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Markdown

from ..data.config import Config
from ..data.theme import Theme
from ..listen.client import ListenClient
from ..listen.types import CurrentUser, SystemFeed


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
    UserFeed .feed-text {{
        margin: 1 0;
        padding: 0 1;
    }}
    UserFeed ListItem {{
        margin: 1 0;
        background: {Theme.BACKGROUND};
    }}
    """

    def compose(self) -> ComposeResult:
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
                    Label(f"• {self.format_timespan_since(feed.created_at)}", classes="feed-time"),
                    Label(
                        Text.from_markup(f"{feed.activity} {title} by [{Theme.ACCENT}]{artist}[/]"), classes="feed-text"
                    ),
                )
            )
        listview.extend(listitems)

    def format_timespan_since(self, time: datetime) -> str:
        now = datetime.now()
        diff = now - time

        years = diff.days // 365
        if years > 0:
            return f"{years} years ago"
        months = (diff.days % 365) // 30
        if months > 0:
            return f"{months} months ago"
        days = diff.days % 30
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60

        string: list[str] = []
        if days > 0:
            string.append(f"{round(days)} days")
        if hours > 0:
            string.append(f"{round(hours)} hours")
        if minutes > 0:
            string.append(f"{round(minutes)} minutes")
        if minutes == 0:
            return "just now"
        string.append("ago")

        return " ".join(string)

    def update(self, user_feeds: list[SystemFeed]) -> None:
        self.feeds = user_feeds


class UserPage(Widget):
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

    def compose(self) -> ComposeResult:
        yield UserDetails()
        yield UserFeed()

    @work
    async def on_mount(self) -> None:
        client = ListenClient.get_instance()
        user = client.current_user
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
