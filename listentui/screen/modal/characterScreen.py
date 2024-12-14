from typing import ClassVar, Self

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Horizontal, VerticalScroll
from textual.lazy import Lazy
from textual.widgets import Collapsible, Label, ListView

from listentui.listen import ListenClient
from listentui.listen.interface import Character, CharacterID, SongID
from listentui.screen.modal.baseScreen import BaseScreen, LoadingScreen
from listentui.screen.modal.buttons import EscButton
from listentui.screen.modal.messages import SpawnSongScreen
from listentui.screen.modal.songScreen import SongScreen
from listentui.widgets.songListView import SongItem, SongListView


class CharacterScreen(BaseScreen[None, CharacterID, Character]):
    DEFAULT_CSS = """
    CharacterScreen {
        align: center middle;
    }
    CharacterScreen #box {
        width: 100%;
        margin: 2 4 2 4;
        height: 100%;
        border: thick $background 80%;
        background: $surface;
    }
    CharacterScreen Center {
        margin-top: 1;
    }
    CharacterScreen Horizontal {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    CharacterScreen Horizontal Label {
        margin-right: 1;
    }
    CharacterScreen > * {
        padding-left: 2;
        padding-right: 2;
    }
    CharacterScreen VerticalScroll {
        margin: 1 0;
    }
    CharacterScreen SongListView {
        margin-right: 2;
    }
    CharacterScreen CollapsibleTitle {
        width: 100%;
        margin-right: 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel"),
    ]

    def __init__(self, character_id: CharacterID, character: Character, favorited: dict[SongID, bool]):
        super().__init__()
        self.character_id = character_id
        self.character = character
        self.favorited = favorited

    def compose(self) -> ComposeResult:
        yield EscButton()
        with Container(id="box"):  # noqa: PLR1702
            yield Center(Label(id="name"))
            with Horizontal():
                yield Label(id="albums-count")
                yield Label(id="songs-count")
            with VerticalScroll():
                if self.character.albums:
                    for album in self.character.albums:
                        if album.songs:
                            with Collapsible(title=f"{album.format_name()}\n{len(album.songs)} Songs"), Lazy(
                                SongListView(initial_index=None)
                            ):
                                yield from [SongItem(song, self.favorited.get(song.id, False)) for song in album.songs]

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
        self.query_one("#name", Label).update(self.character.format_name())
        self.query_one("#albums-count", Label).update(f"{self.character.album_count or 'No'} Albums")
        self.query_one("#songs-count", Label).update(f"- {self.character.song_count or 'No'} Songs")

    @classmethod
    async def load(cls, app: App, load_id: CharacterID) -> Self:
        client = ListenClient.get_instance()
        res = await app.push_screen_wait(LoadingScreen(client.character(load_id)))
        assert res is not None
        favorited = {}
        if client.logged_in and res.albums:
            song_ids = []
            for album in res.albums:
                song_ids.extend([song.id for song in album.songs or []])
            favorited.update(await app.push_screen_wait(LoadingScreen(client.check_favorite(song_ids))))
        return cls(load_id, res, favorited)

    def action_cancel(self) -> None:
        self.dismiss()
