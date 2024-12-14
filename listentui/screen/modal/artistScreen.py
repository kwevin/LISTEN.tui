from typing import ClassVar, Self

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Horizontal, VerticalScroll
from textual.lazy import Lazy
from textual.widgets import Collapsible, Label, ListView

from listentui.listen import Artist, ArtistID, ListenClient, SongID
from listentui.screen.modal.baseScreen import BaseScreen, LoadingScreen
from listentui.screen.modal.buttons import EscButton
from listentui.screen.modal.messages import SpawnSongScreen
from listentui.screen.modal.songScreen import SongScreen
from listentui.widgets.songListView import SongItem, SongListView


class ArtistScreen(BaseScreen[None, ArtistID, Artist]):
    DEFAULT_CSS = """
    ArtistScreen {
        align: center middle;
    }
    ArtistScreen #box {
        width: 100%;
        margin: 2 4 2 4;
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
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, artist_id: ArtistID, artist: Artist, favorited: dict[SongID, bool]):
        super().__init__()
        self.artist_id = artist_id
        self.artist = artist
        self.favorited = favorited

    def compose(self) -> ComposeResult:
        # lazy for the win!!
        yield EscButton()
        with Container(id="box"):  # noqa: PLR1702
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
                                yield from [SongItem(song, self.favorited.get(song.id, False)) for song in album.songs]

                if self.artist.songs_without_album:
                    with Collapsible(title=f"- No album -\n{len(self.artist.songs_without_album)} Songs"), Lazy(
                        SongListView(initial_index=None)
                    ):
                        yield from [
                            SongItem(song, self.favorited.get(song.id, False))
                            for song in self.artist.songs_without_album
                        ]

    @on(SongListView.SongSelected)
    @work
    async def song_selected(self, event: SongListView.SongSelected) -> None:
        favorited_status = await self.app.push_screen_wait(
            await SongScreen.load_with_favorited(self.app, event.song.id, self.favorited.get(event.song.id, False))
        )

        if self.favorited.get(event.song.id, False) != favorited_status:
            self.query_one(f"#_song-{event.song.id}", SongItem).set_favorited_state(favorited_status)

    @on(ListView.Highlighted)
    def child_highlighed(self, event: ListView.Highlighted) -> None:
        if event.item:
            self.scroll_to_widget(event.item, center=True)

    async def on_mount(self) -> None:
        self.query_one("#name", Label).update(self.artist.format_name())
        self.query_one("#albums-count", Label).update(f"{self.artist.album_count or 'No'} Albums")
        self.query_one("#songs-count", Label).update(f"- {self.artist.song_count or 'No'} Songs")
        self.query_one("#links", Label).update(f"{self.artist.format_socials(sep=' ', use_app=True) or 'No Socials'}")

    @classmethod
    async def load(cls, app: App, load_id: ArtistID) -> Self:
        client = ListenClient.get_instance()
        artist = await app.push_screen_wait(LoadingScreen(client.artist(load_id)))
        assert artist is not None
        favorited = {}
        songs_id = []
        for album in artist.albums or []:
            if album.songs:
                songs_id.extend([song.id for song in album.songs])
        if artist.songs_without_album:
            songs_id.extend([song.id for song in artist.songs_without_album])
        if client.logged_in:
            favorited = await app.push_screen_wait(LoadingScreen(client.check_favorite(songs_id)))
        return cls(load_id, artist, favorited)

    def action_cancel(self) -> None:
        self.dismiss()
