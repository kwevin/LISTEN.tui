from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Grid, VerticalScroll
from textual.lazy import Lazy
from textual.widgets import Collapsible, Label, ListView

from listentui.listen import Album, AlbumID, ListenClient
from listentui.screen.modal.baseScreen import BaseScreen
from listentui.screen.modal.buttons import ArtistButton, EscButton
from listentui.widgets.songListView import SongItem, SongListView


class AlbumScreen(BaseScreen[None]):
    DEFAULT_CSS = """
    AlbumScreen {
        align: center middle;
    }
    AlbumScreen #box {
        width: 100%;
        margin: 4 4 6 4;
        height: 100%;
        border: thick $background 80%;
        background: $surface;
    }
    AlbumScreen Center {
        margin-top: 1;
    }
    AlbumScreen Horizontal {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    AlbumScreen Horizontal Label {
        margin-right: 1;
    }
    AlbumScreen > * {
        padding-left: 2;
        padding-right: 2;
    }
    AlbumScreen VerticalScroll {
        margin: 1 0;
    }
    AlbumScreen Collapsible {
        margin: 1 0;
    }
    AlbumScreen SongListView {
        margin-right: 2;
    }
    AlbumScreen Collapsible Grid {
        grid-size: 5;
        grid-gutter: 1 1;
        grid-rows: 3;
        height: auto;
    }
    AlbumScreen CollapsibleTitle {
        width: 100%;
        margin-right: 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, album_id: AlbumID, album: Album | None = None):
        super().__init__()
        self.album_id = album_id
        self.album: Album | None = None

    def compose(self) -> ComposeResult:
        yield EscButton()
        with Container(id="box"):
            if self.album is None:
                return
            yield Center(Label(id="name"))
            yield Label(id="links")
            with VerticalScroll():
                if self.album.artists:
                    with Collapsible(title="Contributing artists:"), Grid():
                        for artist in self.album.artists:
                            yield ArtistButton(artist.id, artist.format_name())
                if self.album.songs:
                    with VerticalScroll():
                        yield Lazy(SongListView(*[SongItem(song) for song in self.album.songs], initial_index=None))

    @on(ListView.Highlighted)
    def child_highlighed(self, event: ListView.Highlighted) -> None:
        if event.item:
            self.scroll_to_widget(event.item, center=True)

    @work
    async def on_mount(self) -> None:
        if not self.album:
            self.query_one("#box", Container).loading = True
            self.album = await ListenClient.get_instance().album(self.album_id)
            if self.album is None:
                raise Exception("album cannot be None")

            await self.recompose()
        count = len(self.album.songs) if self.album.songs else 0
        self.query_one("#name", Label).update(f"{self.album.format_name()} - {count} Songs")
        self.query_one("#links", Label).update(
            f"{self.album.format_socials(sep=' ') or '- No links for this album yet -'}"
        )
        self.query_one("#box", Container).loading = False

    def action_cancel(self) -> None:
        self.dismiss()
