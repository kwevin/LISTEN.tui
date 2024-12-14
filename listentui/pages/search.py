# import webbrowser
from random import choice as random_choice
from typing import ClassVar, cast

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Center, Horizontal, ScrollableContainer
from textual.reactive import var
from textual.validation import Function
from textual.widgets import Input, Label, Select, SelectionList

from listentui.listen.client import ListenClient, RequestError
from listentui.listen.interface import Song, SongID
from listentui.pages.base import BasePage
from listentui.screen.modal.songScreen import SongScreen
from listentui.widgets.pageSwitcher import PageSwitcher
from listentui.widgets.songListView import AdvSongItem, SongListView


class SearchPage(BasePage):
    DEFAULT_CSS = """
    SearchPage {
        align: center middle;

        & SongListView {
            margin: 1 1 1 1;
        }
        
        & PageSwitcher {
            margin-bottom: 1;
        }
        
        & Horizontal {
            height: auto;
            width: 100%;
        }

        & Input {
            height: auto;
            width: 1fr;
        }

        #svalue {
            width: 11;
        }
        #sfilter {
            min-width: 17;
            max-width: 24;
            overflow: hidden hidden;
        }
    }
    OptionList {
        & > .option-list--option-highlighted {
            background: $surface;
        }
        &:focus > .option-list--option-highlighted {
            background: $surface;
            background-tint: $foreground 5%;
        }
    }
    """
    search_result: var[list[Song]] = var([], init=False, always_update=True)
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+q", "random", "Request A Random Searched Song"),
        Binding("ctrl+r", "random_favorited", "Request A Random Favorited Song"),
        Binding("ctrl+t", "toggle_filter", "Toggle Favorite Filter"),
        Binding("ctrl+s", "force_search", "Force Search", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.list_view = SongListView()
        self.default_songs: list[Song] = []
        self.song_count: int = -1
        self.client = ListenClient.get_instance()
        self.min_search_length = 3
        self.amount_per_page: int = 20
        self.amount_selection: Select[int] = Select(
            [("20", 20), ("50", 50), ("100", 100), ("200", 200)], allow_blank=False, value=20, id="svalue"
        )
        self.filter: SelectionList[bool] = SelectionList(*[("Favorited Only", True)], id="sfilter")
        # self.filter.can_focus = False
        self.search_result_copy: list[SongID] = []
        self.favorited: dict[SongID, bool] = {}

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Input(
                placeholder="Press Enter To Search...",
                validators=Function(lambda x: len(x) >= self.min_search_length),
                valid_empty=True,
            )
            yield self.amount_selection
            yield self.filter
        yield Center(Label(id="counter"))
        with ScrollableContainer(id="list_view_main"):
            yield self.list_view
            yield PageSwitcher()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"random", "random_favorited", "toggle_filter"}:
            return ListenClient.get_instance().logged_in
        return True

    def action_toggle_filter(self) -> None:
        selection = self.filter.get_option_at_index(0)
        self.filter.toggle(selection)

    @work
    async def action_random(self) -> None:
        if len(self.search_result_copy) > 0:
            random = random_choice(self.search_result_copy)
            self.search_result_copy.remove(random)
        else:
            self.notify("No more songs to request!", severity="warning")
            return

        res: Song | RequestError = await self.client.request_song(random, exception_on_error=False)
        if isinstance(res, Song):
            title = res.format_title()
            artist = res.format_artists()
            self.notify(
                f"{title}" + f" by [red]{artist}[/]" if artist else "",
                title="Sent to queue",
            )
        elif res == RequestError.FULL:
            self.notify("All requests have been used up for today!", severity="warning")
        else:
            self.notify("No more songs to request!", severity="warning")

    @work
    async def action_random_favorited(self) -> None:
        res: Song | RequestError = await self.client.request_random_favorite(exception_on_error=False)
        if isinstance(res, Song):
            title = res.format_title()
            artist = res.format_artists()
            self.notify(
                f"{title}" + f" by [red]{artist}[/]" if artist else "",
                title="Sent to queue",
            )
        else:
            self.notify("All requests have been used up for today!", severity="warning")

    def watch_search_result(self, new_value: list[Song]) -> None:
        self.enable_loading()
        self.update_list_view(new_value)

    @work
    async def update_list_view(self, new_value: list[Song]) -> None:
        self.favorited = {}
        if self.client.logged_in and not self.is_filter_selected() and len(new_value) != 0:
            self.favorited = await self.client.check_favorite([s.id for s in new_value])

        self.populate_list_view(1)
        if not self.query_one(Input).value and not self.is_filter_selected():
            self.query_one("#counter", Label).update(f"{self.song_count} Total Songs")
        else:
            self.query_one("#counter", Label).update(
                f"{len(new_value)} Results Found" if len(new_value) > 0 else "No Result Found"
            )
            self.query_one(PageSwitcher).calculate_update_end_page(self.amount_per_page, len(new_value))
        self.search_result_copy = [s.id for s in new_value]

    @work
    async def populate_list_view(self, page: int) -> None:
        await self.list_view.clear()
        if self.search_result:
            await self.list_view.extend(
                AdvSongItem(song, self.favorited.get(song.id, self.is_filter_selected()))
                for song in list(self.search_result)[
                    (page - 1) * self.amount_per_page : min(page * self.amount_per_page, len(self.search_result))
                ]
            )
        self.remove_loading()

    @work
    async def on_mount(self) -> None:
        if not self.client.logged_in:
            self.filter.styles.display = "none"
        self.default_songs = await self.get_songs(0, self.amount_per_page)
        self.song_count = await self.client.total_songs_count()
        self.set_default_state()

    @work
    async def set_default_state(self) -> None:
        self.search_result = self.default_songs
        pager = self.query_one(PageSwitcher)
        pager.calculate_update_end_page(self.amount_per_page, self.song_count)
        pager.reset()

    @on(Select.Changed, "#svalue")
    def search_value_changed(self, event: Select.Changed) -> None:
        self.amount_per_page = cast(int, event.value)
        if self.is_filter_selected():
            self.search(True)
        elif self.is_input_empty():
            self.extend_search_result(self.query_one(PageSwitcher).current_page)
            self.query_one(PageSwitcher).calculate_update_end_page(self.amount_per_page, self.song_count)
        else:
            self.search()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not event.value:
            self.set_default_state()
        if event.validation_result and event.validation_result.is_valid:
            self.search(True)

    @on(SelectionList.SelectedChanged, "#sfilter")
    def on_filter_changed(self, event: SelectionList.SelectedChanged[bool]) -> None:
        if not self.is_filter_selected() and not self.query_one(Input).value:
            self.search_result = self.default_songs
        else:
            self.search(True)

    @on(PageSwitcher.PageChanged)
    def on_page_changed(self, event: PageSwitcher.PageChanged) -> None:
        if not self.query_one(Input).value and not self.is_filter_selected():
            self.extend_search_result(event.page)
        else:
            self.populate_list_view(event.page)

    @work
    async def extend_search_result(self, page: int) -> None:
        self.enable_loading()
        self.search_result = await self.get_songs((page - 1) * self.amount_per_page, self.amount_per_page)

    @work
    async def search(self, valid: bool = False) -> None:
        inp = self.query_one(Input)
        search = inp.value
        pager = self.query_one(PageSwitcher)
        if valid:
            if pager.current_page != 1:
                pager.reset()
            self.enable_loading()
            self.search_result = await self.get_search(search)
            return

        validation = inp.validate(search)
        if validation and validation.is_valid:
            if pager.current_page != 1:
                pager.reset()
            self.enable_loading()
            self.search_result = await self.get_search(search)

    async def get_songs(self, offset: int, count: int) -> list[Song]:
        return await self.client.songs(offset, count)

    async def get_search(self, search_string: str) -> list[Song]:
        return await self.client.search(search_string, favorite_only=self.is_filter_selected())

    @on(SongListView.SongSelected)
    @work
    async def song_selected(self, event: SongListView.SongSelected) -> None:
        filtr = self.is_filter_selected()
        favorited_status = await self.app.push_screen_wait(
            await SongScreen.load_with_favorited(self.app, event.song.id, self.favorited.get(event.song.id, filtr))
        )
        self.query_one(f"#_song-{event.song.id}", AdvSongItem).set_favorited_state(favorited_status)

    def is_filter_selected(self) -> bool:
        return len(self.filter.selected) == 1

    def is_input_empty(self) -> bool:
        return not self.query_one(Input).value

    def enable_loading(self) -> None:
        self.query_one("#list_view_main").set_loading(True)

    def remove_loading(self) -> None:
        self.query_one("#list_view_main").set_loading(False)

    def action_force_search(self) -> None:
        self.search(True)
