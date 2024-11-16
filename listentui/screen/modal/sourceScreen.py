from typing import ClassVar, Self

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, VerticalScroll
from textual.lazy import Lazy
from textual.widgets import Collapsible, Label, ListView, Markdown

from listentui.listen import Album, AlbumID, ListenClient, Song, Source, SourceID
from listentui.screen.modal.baseScreen import BaseScreen, LoadingScreen
from listentui.screen.modal.buttons import EscButton
from listentui.screen.modal.messages import SpawnArtistScreen, SpawnSongScreen
from listentui.widgets.songListView import SongItem, SongListView


class SourceScreen(BaseScreen[None, SourceID, Source]):
    DEFAULT_CSS = """
    SourceScreen {
        align: center middle;
    }
    SourceScreen #box {
        width: 100%;
        margin: 4 4 6 4;
        height: 100%;
        border: thick $background 80%;
        background: $surface;
    }
    SourceScreen Center {
        margin-top: 1;
    }
    SourceScreen Markdown {
        margin: 1 2 0 0;
    }
    SourceScreen > * {
        padding-left: 2;
        padding-right: 2;
    }
    SourceScreen VerticalScroll {
        margin: 1 0;
    }
    SourceScreen SongListView {
        margin-right: 2;
    }
    SourceScreen CollapsibleTitle {
        width: 100%;
        margin-right: 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, source_id: SourceID, source: Source):
        super().__init__()
        self.source_id = source_id
        self.source = source

    def compose(self) -> ComposeResult:
        yield EscButton()
        with Container(id="box"):
            yield Center(Label(id="name"))
            yield (
                Collapsible(Markdown(self.source.description), title="Description")
                if self.source.description
                else Label("- No description -")
            )
            yield Label(id="links")
            with VerticalScroll():
                if self.source.songs:
                    id_to_album = self.id_to_albums(self.source.songs)
                    id_to_song = self.id_to_songs(self.source.songs)
                    for album_id, songs in id_to_song.items():
                        album = id_to_album[album_id]
                        yield Collapsible(
                            Lazy(SongListView(*[SongItem(song) for song in songs], initial_index=None)),
                            title=f"{album.format_name()}\n{len(songs)} Songs",
                        )
                if self.source.songs_without_album:
                    yield Collapsible(
                        Lazy(
                            SongListView(
                                *[SongItem(song) for song in self.source.songs_without_album], initial_index=None
                            )
                        ),
                        title=f"- No source -\n{len(self.source.songs_without_album)} Songs",
                    )

    def id_to_albums(self, songs: list[Song]) -> dict[AlbumID, Album]:
        albums: dict[AlbumID, Album] = {}
        for song in songs:
            if not song.album:
                continue
            if albums.get(song.album.id, None) is None:
                albums[song.album.id] = song.album
        return albums

    def id_to_songs(self, songs: list[Song]) -> dict[AlbumID, list[Song]]:
        albums: dict[AlbumID, list[Song]] = {}
        for song in songs:
            if not song.album:
                continue
            if albums.get(song.album.id, None) is None:
                albums[song.album.id] = []
            albums[song.album.id].append(song)
        return albums

    @on(SongListView.SongSelected)
    async def song_selected(self, event: SongListView.SongSelected) -> None:
        self.post_message(SpawnSongScreen(event.song.id))

    @on(ListView.Highlighted)
    def child_highlighed(self, event: ListView.Highlighted) -> None:
        if event.item:
            self.scroll_to_widget(event.item, center=True)

    def on_mount(self) -> None:
        self.query_one("#box", Container).loading = False
        self.query_one("#name", Label).update(self.source.format_name())
        self.query_one("#links", Label).update(
            f"{self.source.format_socials(sep=' ') or '- No links for this source yet - '}"
        )

    @classmethod
    async def load(cls, app: App, load_id: SourceID) -> Self:
        client = ListenClient.get_instance()
        res = await app.push_screen_wait(LoadingScreen(client.source(load_id)))
        assert res is not None
        return cls(load_id, res)

    def action_cancel(self) -> None:
        self.dismiss()
