import webbrowser
from typing import Any, ClassVar

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.coordinate import Coordinate
from textual.message import Message
from textual.reactive import reactive, var
from textual.validation import Function
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input

from ..data.config import Config
from ..data.theme import Theme
from ..listen.client import ListenClient
from ..listen.types import Song, SongID
from ..screen.modal import ConfirmScreen, SelectionScreen


class FavoriteToggleButton(Button):
    DEFAULT_CSS = f"""
    FavoriteToggleButton {{
        background: {Theme.BUTTON_BACKGROUND};
    }}
    FavoriteToggleButton.-toggled {{
        background: {Theme.ACCENT};
    }}
    """
    is_active: reactive[bool] = reactive(False, init=False, layout=True)

    class Toggled(Message):
        def __init__(self, state: bool) -> None:
            super().__init__()
            self.state = state

    def __init__(self):
        super().__init__("Toggle Favorite Only")
        self.can_focus = False

    async def on_mount(self) -> None:
        client = ListenClient.get_instance()
        if not client.logged_in:
            self.disabled = True

    def watch_is_active(self, new: bool) -> None:
        self.add_class("-toggled") if new else self.remove_class("-toggled")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.is_active = not self.is_active
        self.post_message(self.Toggled(self.is_active))


class Search(Widget):
    DEFAULT_CSS = """
    Search Input {
        width: 1fr;
        height: auto;
    }
    Search Horizontal {
        height: auto;
    }
    Search Button {
        margin-left: 1;
    }
    Search DataTable {
        width: 1fr;
        height: 1fr;
    }
    Search DataTable > .datatable--cursor {
        text-style: bold underline;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+l", "focus_input", "Focus Input"),
        Binding("ctrl+f", "toggle_favorite", "Toggle Favorite Only"),
    ]
    search_result: var[list[Song]] = var([], init=False)
    favorites_only: var[bool] = var(False, init=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client = ListenClient.get_instance()
        self.min_search_length = 2
        self.artist_max_width = 55
        self.title_max_width = 50

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Type 2+ Characters To Search...",
            validators=Function(lambda x: len(x) >= self.min_search_length),
        )
        with Horizontal():
            yield FavoriteToggleButton()
            # yield Button("This", id="this") # TODO: requests
        yield DataTable()

    def on_show(self) -> None:
        self.query_one(Input).focus()

    def search_song(self, song_id: SongID) -> Song | None:
        for song in self.search_result:
            if song.id == song_id:
                return song
        return None

    @work(group="table")
    async def on_mount(self) -> None:
        data_table: DataTable[Any] = self.query_one(DataTable)
        data_table.add_column("Id")
        data_table.add_column("Track", width=self.title_max_width)
        data_table.add_column("Artists", width=self.artist_max_width)
        data_table.add_column("Album")
        data_table.add_column("Source")
        if not self.client.logged_in:
            self.query_one("#favorite_toggle", Button).disabled = True
        self.search_result = await self.client.songs(0, 100)

    @work(exclusive=True, group="search", exit_on_error=False)
    async def watch_favorites_only(self, value: bool) -> None:
        search_term = self.query_one(Input).value
        if len(search_term) < self.min_search_length:
            return
        self.query_one(DataTable).loading = True
        self.search_result = await self.client.search(self.query_one(Input).value, 100, favorite_only=value)
        self.query_one(DataTable).loading = False

    @work(group="table")
    async def watch_search_result(self, result: list[Song]) -> None:
        romaji_first = Config.get_config().display.romaji_first
        data_table: DataTable[Any] = self.query_one(DataTable)
        data_table.clear()
        if len(result) == 0:
            return
        favorites: dict[SongID, bool] = {}
        if self.client.logged_in:
            favorites = await self.client.check_favorite([song.id for song in result])
        for song in result:
            row = [
                Text(str(song.id), style=f"bold {Theme.ACCENT}") if favorites.get(song.id) else Text(str(song.id)),
                self.ellipses(song.format_title(romaji_first=romaji_first), self.title_max_width),
                self.ellipses(song.format_artists(romaji_first=romaji_first), self.artist_max_width),
                song.format_album(romaji_first=romaji_first),
                song.format_source(romaji_first=romaji_first),
            ]
            data_table.add_row(*row, key=f"{song.id}")
        data_table.refresh(layout=True)

    @work(group="table")
    async def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:  # noqa: PLR0912
        data_table: DataTable[Any] = self.query_one(DataTable)
        column = event.coordinate.column
        if column == 1:  # TODO: make this request the song instead
            return
        id_coord = Coordinate(event.coordinate.row, 0)
        _id: Text = data_table.get_cell_at(id_coord)
        song_id = SongID(int(_id.plain))
        song = self.search_song(song_id) or await self.client.song(song_id)
        romaji_first = Config.get_config().display.romaji_first
        if not song:
            return
        match column:
            case 0:
                if self.client.logged_in:
                    if await self.app.push_screen(ConfirmScreen(label="Favorite Song?"), wait_for_dismiss=True):
                        await self.client.favorite_song(song_id)
                        state: bool = await self.client.check_favorite(song_id)
                        data_table.update_cell_at(
                            id_coord, Text(str(song_id), style=f"bold {Theme.ACCENT}") if state else Text(str(song_id))
                        )
                        self.notify(
                            f"{'Favorited' if state else 'Unfavorited'} "
                            + f"{song.format_title(romaji_first=romaji_first)}"
                        )
                else:
                    self.notify("Must be logged in to favorite song", severity="warning")
            case 2:
                if song.artists:
                    if len(song.artists) == 1:
                        if await self.app.push_screen(ConfirmScreen(label="Open Artist Page?"), wait_for_dismiss=True):
                            webbrowser.open_new_tab(song.artists[0].link)
                    else:
                        options = song.format_artists_list()
                        if not options:
                            return
                        result = await self.app.push_screen(SelectionScreen(options), wait_for_dismiss=True)
                        if result is not None:
                            webbrowser.open_new_tab(song.artists[result].link)
            case 3:
                if song.album and await self.app.push_screen(
                    ConfirmScreen(label="Open Album Page?"), wait_for_dismiss=True
                ):
                    webbrowser.open_new_tab(song.album.link)
            case 4:
                if song.source and await self.app.push_screen(
                    ConfirmScreen(label="Open Source Page?"), wait_for_dismiss=True
                ):
                    webbrowser.open_new_tab(song.source.link)
            case _:
                pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one(DataTable).focus()

    @work(exclusive=True, group="search", exit_on_error=False)
    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.validation_result and event.validation_result.is_valid:
            self.query_one(DataTable).loading = True
            self.search_result = await self.client.search(event.value, 100, favorite_only=self.favorites_only)
            self.query_one(DataTable).loading = False
        else:
            return

    def action_focus_input(self) -> None:
        self.query_one(Input).focus()

    def action_toggle_favorite(self) -> None:
        if self.client.logged_in:
            self.favorites_only = not self.favorites_only
            self.query_one(FavoriteToggleButton).is_active = self.favorites_only
        else:
            self.notify("Must be logged in to toggle favorite only", severity="warning")

    @on(FavoriteToggleButton.Toggled)
    def on_favorite_toggle_pressed(self, event: FavoriteToggleButton.Toggled) -> None:
        self.favorites_only = event.state

    def ellipses(self, text: str | None, max_length: int) -> str:
        if not text:
            return ""
        return text if len(text) <= max_length else text[: max_length - 3] + "..."
