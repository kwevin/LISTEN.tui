from typing import ClassVar, Self

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Grid, VerticalScroll
from textual.lazy import Lazy
from textual.widgets import Collapsible, Label, ListView

from listentui.listen import Album, AlbumID, ListenClient
from listentui.screen.modal.baseScreen import BaseScreen, LoadingScreen
from listentui.screen.modal.buttons import ArtistButton, EscButton
from listentui.screen.modal.messages import SpawnSongScreen
from listentui.screen.modal.songScreen import SongScreen
from listentui.widgets.songListView import AdvSongItem, SongItem, SongListView


class AlbumScreen(BaseScreen[None, AlbumID, Album]):
    DEFAULT_CSS = """
    AlbumScreen {
        align: center middle;
    }
    AlbumScreen #box {
        width: 100%;
        margin: 2 4 2 4;
        height: 100%;
        border: thick $background 80%;
        background: $background-lighten-1;
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
        background: $background;
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
    AlbumScreen SongListView {
        margin: 1 1 0 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, album_id: AlbumID, album: Album, favorited: dict[int, bool]):
        super().__init__()
        self.album_id = album_id
        self.album = album
        self.favorited = favorited

    def compose(self) -> ComposeResult:
        yield EscButton()
        with Container(id="box"):
            yield Center(Label(id="name"))
            yield Label(id="links")
            if self.album.artists:
                with Collapsible(title="Contributing artists:"), Grid():
                    for artist in self.album.artists:
                        yield ArtistButton(artist.id, artist.format_name())
            with VerticalScroll():
                if self.album.songs:
                    with VerticalScroll():
                        yield Lazy(
                            SongListView(
                                *[SongItem(song, self.favorited.get(song.id, False)) for song in self.album.songs],
                                initial_index=None,
                            )
                        )

    @on(ListView.Highlighted)
    def child_highlighed(self, event: ListView.Highlighted) -> None:
        if event.item:
            self.scroll_to_widget(event.item, center=True)

    @on(SongListView.SongSelected)
    @work
    async def song_selected(self, event: SongListView.SongSelected) -> None:
        favorited_status = await self.app.push_screen_wait(
            await SongScreen.load_with_favorited(self.app, event.song.id, self.favorited.get(event.song.id, False))
        )

        if self.favorited.get(event.song.id, False) != favorited_status:
            self.query_one(f"#_song-{event.song.id}", SongItem).set_favorited_state(favorited_status)

    @classmethod
    async def load(cls, app: App, load_id: AlbumID) -> Self:
        client = ListenClient.get_instance()
        res = await app.push_screen_wait(LoadingScreen(client.album(load_id)))
        assert res is not None
        favorited = {}
        if client.logged_in and res.songs:
            favorited.update(
                await app.push_screen_wait(LoadingScreen(client.check_favorite([song.id for song in res.songs])))
            )
        return cls(load_id, res, favorited)

    def on_mount(self) -> None:
        count = len(self.album.songs) if self.album.songs else 0
        self.query_one("#name", Label).update(f"{self.album.format_name()} - {count} Songs")
        self.query_one("#links", Label).update(
            f"{self.album.format_socials(sep=' ') or '- No links for this album yet -'}"
        )

    def action_cancel(self) -> None:
        self.dismiss()
