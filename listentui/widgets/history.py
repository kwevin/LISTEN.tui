import webbrowser
from typing import Any, ClassVar

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.coordinate import Coordinate
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import DataTable

from ..data.config import Config
from ..data.theme import Theme
from ..listen.client import ListenClient
from ..listen.types import PlayStatistics, Song, SongID
from ..screen.modal import ConfirmScreen, SelectionScreen


class HistoryPage(Widget):
    DEFAULT_CSS = """
    HistoryPage DataTable {
        width: 1fr;
        height: 1fr;
    }
    HistoryPage DataTable > .datatable--cursor {
        text-style: bold underline;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [Binding("ctrl+r", "refresh", "Refresh")]

    history_result: var[list[PlayStatistics]] = var([], init=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client = ListenClient.get_instance()

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_show(self) -> None:
        self.update_history()

    def search_song(self, song_id: SongID) -> Song | None:
        for history in self.history_result:
            if history.song.id == song_id:
                return history.song
        return None

    async def on_mount(self) -> None:
        data_table: DataTable[Any] = self.query_one(DataTable)
        data_table.add_column("Id")
        data_table.add_column("Track", width=50)
        data_table.add_column("Requested By")
        data_table.add_column("Played At")
        data_table.add_column("Artists", width=40)
        data_table.add_column("Album")
        data_table.add_column("Source")

    @work(group="table")
    async def watch_history_result(self, histories: list[PlayStatistics]) -> None:
        romaji_first = Config.get_config().display.romaji_first
        data_table: DataTable[Any] = self.query_one(DataTable)
        data_table.clear()
        favorites: dict[SongID, bool] = {}
        if self.client.logged_in:
            favorites = await self.client.check_favorite([history.song.id for history in histories])
        for history in histories:
            song = history.song
            row = [
                Text(str(song.id), style=f"bold {Theme.ACCENT}") if favorites.get(song.id) else Text(str(song.id)),
                self.ellipses(song.format_title(romaji_first=romaji_first), 50),
                Text(str(history.requester.display_name), style=f"bold {Theme.ACCENT}") if history.requester else "",
                history.created_at.strftime("%d-%m-%Y %H:%M:%S"),
                self.ellipses(song.format_artists(romaji_first=romaji_first), 40),
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
            case 4:
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
            case 5:
                if song.album and await self.app.push_screen(
                    ConfirmScreen(label="Open Album Page?"), wait_for_dismiss=True
                ):
                    webbrowser.open_new_tab(song.album.link)
            case 6:
                if song.source and await self.app.push_screen(
                    ConfirmScreen(label="Open Source Page?"), wait_for_dismiss=True
                ):
                    webbrowser.open_new_tab(song.source.link)
            case _:
                pass

    @work(group="table")
    async def update_history(self) -> None:
        self.query_one(DataTable).loading = True
        self.history_result = await self.client.history(100, 0)
        self.query_one(DataTable).loading = False
        self.query_one(DataTable).focus()

    def action_refresh(self) -> None:
        self.update_history()

    def ellipses(self, text: str | None, max_length: int) -> str:
        if not text:
            return ""
        return text if len(text) <= max_length else text[: max_length - 1] + "…"
