from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Horizontal, VerticalScroll
from textual.lazy import Lazy
from textual.widgets import Collapsible, Label, ListView

from listentui.listen import Artist, ArtistID, ListenClient
from listentui.screen.modal.baseScreen import BaseScreen
from listentui.screen.modal.buttons import EscButton
from listentui.screen.modal.messages import SpawnSongScreen
from listentui.widgets.songListView import SongItem, SongListView


class ArtistScreen(BaseScreen[None]):
    DEFAULT_CSS = """
    ArtistScreen {
        align: center middle;
    }
    ArtistScreen #box {
        width: 100%;
        margin: 4 4 6 4;
        height: 100%;
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
    ArtistScreen VerticalScroll {
        margin: 1 0;
    }
    ArtistScreen SongListView {
        margin-right: 2;
    }
    ArtistScreen CollapsibleTitle {
        width: 100%;
        margin-right: 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, artist_id: ArtistID):
        super().__init__()
        self.artist_id = artist_id
        self.artist: Artist | None = None

    def compose(self) -> ComposeResult:
        # lazy for the win!!
        yield EscButton()
        with Container(id="box"):  # noqa: PLR1702
            if self.artist is None:
                return
            yield Center(Label(id="name"))
            with Horizontal():
                yield Label(id="albums-count")
                yield Label(id="songs-count")
            yield Label(id="links")
            with VerticalScroll():
                if self.artist.albums:
                    for album in self.artist.albums:
                        if album.songs:
                            with Collapsible(title=f"{album.format_name()}\n{len(album.songs)} Songs"), Lazy(
                                SongListView(initial_index=None)
                            ):
                                yield from [SongItem(song) for song in album.songs]

                if self.artist.songs_without_album:
                    with Collapsible(title=f"- No album -\n{len(self.artist.songs_without_album)} Songs"), Lazy(
                        SongListView(initial_index=None)
                    ):
                        yield from [SongItem(song) for song in self.artist.songs_without_album]

    @on(SongListView.SongSelected)
    async def song_selected(self, event: SongListView.SongSelected) -> None:
        client = ListenClient.get_instance()
        favorited = False
        if client.logged_in:
            favorited = await client.check_favorite(event.song.id)
        self.post_message(SpawnSongScreen(event.song.id, favorited))

    @on(ListView.Highlighted)
    def child_highlighed(self, event: ListView.Highlighted) -> None:
        if event.item:
            self.scroll_to_widget(event.item, center=True)

    async def on_mount(self) -> None:
        self.query_one("#box", Container).loading = True
        self.fetch_artist()

    @work
    async def fetch_artist(self) -> None:
        client = ListenClient.get_instance()
        artist = await client.artist(self.artist_id)
        if artist is None:
            raise Exception("Cannot be None")
        self.artist = artist
        await self.recompose()
        self.query_one("#name", Label).update(self.artist.format_name())
        self.query_one("#albums-count", Label).update(f"{self.artist.album_count or 'No'} Albums")
        self.query_one("#songs-count", Label).update(f"- {self.artist.song_count or 'No'} Songs")
        self.query_one("#links", Label).update(f"{self.artist.format_socials(sep=' ', use_app=True) or 'No Socials'}")
        self.query_one("#box", Container).loading = False

    def action_cancel(self) -> None:
        self.dismiss()
