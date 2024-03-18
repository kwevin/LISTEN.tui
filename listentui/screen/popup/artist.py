from typing import ClassVar

from rich.text import Text
from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Collapsible, Label, ListItem, ListView

from listentui.data import Config, Theme
from listentui.listen import ListenClient
from listentui.listen.types import ArtistID, Song

# from ...widgets.mpvplayer import MPVStreamPlayer


class SongItem(ListItem):
    def __init__(self, song: Song):
        self.song = song
        romaji_first = Config.get_config().display.romaji_first
        title = song.format_title(romaji_first=romaji_first)
        artist = song.format_artists(show_character=False, romaji_first=romaji_first, embed_link=True)
        super().__init__(
            Label(
                Text.from_markup(f"{title}"),
                classes="item-title",
                shrink=True,
            ),
            Label(
                Text.from_markup(f"[{Theme.ACCENT}]{artist}[/]"),
                classes="item-artist",
            ),
        )

    class SongChildClicked(Message):
        """For informing with the parent ListView that we were clicked"""

        def __init__(self, item: "SongItem") -> None:
            self.item = item
            super().__init__()

    async def _on_click(self, _: events.Click) -> None:
        self.post_message(self.SongChildClicked(self))


class ExtendedListView(ListView):
    class SongSelected(Message):
        def __init__(self, song: Song) -> None:
            self.song = song
            super().__init__()

    @on(SongItem.SongChildClicked)
    def feed_clicked(self, event: SongItem.SongChildClicked) -> None:
        self.post_message(self.SongSelected(event.item.song))

    def action_select_cursor(self) -> None:
        """Select the current item in the list."""
        selected_child: SongItem | None = self.highlighted_child  # type: ignore
        if selected_child is None:
            return
        self.post_message(self.SongSelected(selected_child.song))


class ArtistScreen(Screen[None]):
    DEFAULT_CSS = """
    ArtistScreen {
        align: center middle;
        background: $background;
    }
    ArtistScreen #box {
        width: 124;
        height: 24;
        border: thick $background 80%;
        background: $surface;
    }
    ArtistScreen Center {
        margin-top: 1;
    }
    ArtistScreen Horizontal {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    ArtistScreen Horizontal Label {
        margin-right: 1;
    }
    ArtistScreen > * {
        padding-left: 2;
        padding-right: 2;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
    ]

    def __init__(self, artist: ArtistID):  # player: MPVStreamPlayer
        super().__init__()
        self.romaji_first = Config.get_config().display.romaji_first
        self.loading = True
        self._artist_id = artist

    def compose(self) -> ComposeResult:
        with Container(id="box"):
            yield Center(Label("Nanahira"))
            with Horizontal():
                yield Label("Amount of songs")
                yield Label("Amount of albums")
            yield Label("Socials goes here")
            yield VerticalScroll()

    @work
    async def populate_ui(self, artist_id: ArtistID) -> None:
        client = ListenClient.get_instance()
        artist = await client.artist(artist_id)
        if not artist:
            raise Exception("Artist not found")

        album_widgets: list[Collapsible] = []
        if artist.albums:
            album_widgets.extend(
                [
                    Collapsible(
                        ExtendedListView(*[SongItem(song) for song in album.songs]),
                        title=f"{album.format_name(romaji_first=self.romaji_first)}\n{len(album.songs)} Songs",
                    )
                    for album in artist.albums
                    if album.songs
                ]
            )
        if artist.songs_without_album:
            album_widgets.append(
                Collapsible(
                    ExtendedListView(*[SongItem(song) for song in artist.songs_without_album]),
                    title=f"- No album -\n{len(artist.songs_without_album)} Songs",
                )
            )
        await self.query_one(VerticalScroll).mount(*album_widgets)

        self.loading = False

    async def on_mount(self) -> None:
        self.populate_ui(self._artist_id)

        # for widget in [self, *self.query("*")]:
        #     widget.tooltip = "\n".join(
        #         f"{node!r}" for node in widget.ancestors_with_self
        #     )  # + "\n\n" + widget.styles.css


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    class MyApp(App[None]):
        async def on_mount(self) -> None:
            client = ListenClient.get_instance()
            artist = await client.artist(215)
            if artist:
                self.mount(ArtistScreen(ArtistID(215)))

    app = MyApp()
    app.run()
