from __future__ import annotations

from threading import Event
from typing import ClassVar, Sequence

from rich.rule import Rule
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Horizontal, ScrollableContainer
from textual.message import Message
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import Button, Footer, Input, Label, Placeholder, ProgressBar, Static, TabbedContent, TabPane
from textual.worker import Worker, get_current_worker  # type: ignore

from listentui.data.config import Config
from listentui.downloader.downloader import Downloader, DownloadItem, QueueState
from listentui.listen.client import ListenClient
from listentui.listen.interface import Song, SongID
from listentui.pages.base import BasePage
from listentui.screen.modal.searchResultPicker import SearchResultPicker
from listentui.utilities import de_kuten
from listentui.widgets.downloadQueueItem import ActionInput, DownloadItemCollapsible
from listentui.widgets.pageSwitcher import PageSwitcher


class UtilityPanel(Widget):
    DEFAULT_CSS = """
    UtilityPanel { 
        height: 1fr;
        width: 1fr;

        & > Horizontal {
            height: auto;
        }

        & Input {
            width: 1fr;
            border-title-color: $text-accent;
        }

        & Button {
            margin-right: 1;
        }
    }

    UtilityPanel Grid {
        grid-size: 4 4;
        grid-gutter: 1 1;
        grid-columns: 1fr;
        grid-rows: 1fr;

        margin: 1 1;
    }
    """

    def __init__(self, parent: DownloadPage) -> None:
        super().__init__()
        self.control = parent

    def compose(self) -> ComposeResult:
        with Horizontal():
            int_put = Input(type="integer", id="manual-add")
            yield int_put
            int_put.border_title = "Manual SongID"

            yield Button("Add", id="song-add")
        yield Static(Rule("Quick Actions"))
        with Grid():
            yield Button("Add favorited", id="favorite-add")

    @on(Button.Pressed, "#song-add")
    async def add_song(self, event: Button.Pressed):
        input_widget = self.query_one(Input)

        if input_widget.value and input_widget.is_valid:
            song_id = SongID(int(input_widget.value))

            if self.control.downloader.has_song(song_id):
                self.set_button_fail(event.control)
                return

            client = ListenClient.get_instance()

            event.control.loading = True
            event.control.disabled = True
            song = await client.song(song_id)
            event.control.loading = False
            event.control.disabled = False

            if song is None:
                self.set_button_fail(event.control)
                return

            if await self.control.add_song(song):
                self.set_button_success(event.control)
                return

            self.set_button_fail(event.control)
            return

        self.set_button_fail(event.control)
        return

    @on(Button.Pressed, "#favorite-add")
    async def add_favorites(self, event: Button.Pressed):
        client = ListenClient.get_instance()
        user = client.current_user
        assert user is not None
        songs = await client.user_favorites(user.username, 0, 125)
        await self.control.batch_add_songs(songs)

    def set_button_fail(self, button: Button):
        button.variant = "error"

        def reset():
            button.variant = "default"

        self.set_timer(1, reset)

    def set_button_success(self, button: Button):
        button.variant = "success"

        def reset():
            button.variant = "default"

        self.set_timer(1, reset)


class DownloadPage(BasePage):
    DEFAULT_CSS = """
    DownloadPage #_dl_btn {
        dock: bottom;
        grid-size: 4 2;
        grid-columns: 1fr 18 18 18;
        grid-rows: 1 1;
        grid-gutter: 1 0;
        height: 5;
        width: 100%;
        height: auto;

        & Button {
            row-span: 2;
        }

        #stats-label, ProgressBar {
            margin-left: 1;
        }

    }
    DownloadPage DownloadItemCollapsible {
        margin: 0 1 0 1;
    }
    """

    downloader = Downloader()

    class SearchUpdate(Message):
        def __init__(self, song_id: SongID, dowload_item: DownloadItem, progress: tuple[int, int]) -> None:
            super().__init__()
            self.song_id = song_id
            self.dowload_item = dowload_item
            self.progress = progress

    class DownloadUpdate(Message):
        def __init__(self, song_id: SongID, dowload_item: DownloadItem, progress: float) -> None:
            super().__init__()
            self.song_id = song_id
            self.dowload_item = dowload_item
            self.progress = progress

    def __init__(self):
        super().__init__()
        self._per_page_count = 20
        self._searching = Event()
        self._downloading = Event()
        self._queue_items: dict[SongID, DownloadItemCollapsible] = {}
        self._pager = PageSwitcher()
        self._progress = ProgressBar()
        self._stat_label = Label(id="stats-label")

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Queue"):
                yield ScrollableContainer(id="queue-container")
                yield self._pager
                with Grid(id="_dl_btn"):
                    yield self._stat_label  # global stats, object and progress bar goes here
                    yield Button("Clear", id="btn-clear")
                    yield Button("Search", id="btn-search")
                    yield Button("Download", id="btn-download")
                    yield self._progress
            with TabPane("Done"):
                yield Placeholder()
            with TabPane("Utilities"):
                yield UtilityPanel(self)

    def on_mount(self):
        self.get_page(1)

    def update_stat_label(self):
        current_item = self.downloader.get_queue()
        found = [item for item in current_item if item.state == QueueState.FOUND]
        self.set_stat_label(len(found), len(current_item))

    def set_stat_label(self, found_progress: int, total: int):
        self._stat_label.update(f"Item: {total} | Found: {found_progress} | {found_progress / total:.2f}%")

    @on(PageSwitcher.PageChanged)
    def page_changed(self, event: PageSwitcher.PageChanged):
        self.get_page(event.page)

    @work(exclusive=True, group="downloadpage")
    async def get_page(self, page: int):
        queue = self.query_one("#queue-container", ScrollableContainer)
        await queue.remove_children()
        self._clear_item()
        start = (page - 1) * self._per_page_count
        stop = start + self._per_page_count
        items = self.downloader.get_queue()
        items.sort(key=lambda item: item.state.value, reverse=True)
        widgets = [self._new_item(item) for item in items[start:stop]]
        await queue.mount_all(widgets)

        # self.sort_items()

    def _new_item(self, item: DownloadItem) -> DownloadItemCollapsible:
        queue_item = DownloadItemCollapsible(item, title=item.song.format_title())
        self._queue_items[item.song.id] = queue_item

        return queue_item

    def _remove_item(self, song_id: SongID):
        self._queue_items.pop(song_id)

    def _get_item(self, song_id: SongID) -> DownloadItemCollapsible | None:
        return self._queue_items.get(song_id, None)

    def _clear_item(self):
        self._queue_items = {}

    @on(DownloadItemCollapsible.RemoveDownloadItem)
    async def _remove_from_queue(self, event: DownloadItemCollapsible.RemoveDownloadItem):
        assert event.collapsible.id is not None
        song_id = SongID(event.collapsible.get_id())

        self.downloader.remove_from_queue(song_id)
        self._remove_item(song_id)
        queue = self.query_one("#queue-container", ScrollableContainer)
        await queue.remove_children(f"#{event.collapsible.id}")

    async def add_song(self, song: Song) -> bool:
        result = self.downloader.add_to_queue(song)
        if result is None:
            return False

        title = result.song.format_title()
        self.get_page(self._pager.current_page)

        self.notify(f"Added: {title}", title="Download Queue")

        self._pager.calculate_update_end_page(self._per_page_count, len(self.downloader.get_queue()))
        return True

    async def batch_add_songs(self, songs: Sequence[Song]):
        items = self.downloader.batch_to_queue(songs)

        self.get_page(self._pager.current_page)
        self._pager.calculate_update_end_page(self._per_page_count, len(self.downloader.get_queue()))
        self.notify(f"Added {len(items)}/{len(songs)} songs", title="Download Queue")

    def sort_items(self):
        self.get_page(self._pager.current_page)
        # queue = self.query_one("#queue-container", ScrollableContainer)

        # def sort(widget: Widget):
        #     if isinstance(widget, DownloadItemCollapsible):
        #         return widget.get_item().item.state.value
        #     return 0

        # queue.sort_children(key=sort, reverse=True)

    @on(SearchUpdate)
    async def search_update_item(self, event: SearchUpdate):
        widget = self._get_item(event.song_id)
        if widget:
            widget.update_item(event.dowload_item)

        self._progress.update(progress=event.progress[0], total=event.progress[1])
        self.update_stat_label()

    @on(DownloadUpdate)
    async def download_update_item(self, event: DownloadUpdate):
        widget = self._get_item(event.song_id)
        if widget:
            widget.update_item(event.dowload_item)

        # TODO: stats and progress

    @on(Button.Pressed, "#btn-search")
    def manual_search_all(self, event: Button.Pressed):
        if self._searching.is_set():
            self._cancel_search(event)
        elif self.downloader.has_searchable():
            self._start_search(event)

    @work(thread=True)
    def _start_search(self, event: Button.Pressed):
        def handle_callback(song_id: SongID, queue_item: DownloadItem, progress: tuple[int, int]):
            self.post_message(self.SearchUpdate(song_id, queue_item, progress))

        def set_button():
            self._searching.set()
            button = event.control
            button.label = "Cancel Search"

        def set_done():
            self._searching.clear()
            button = event.control
            button.label = "Search"
            button.set_loading(False)
            button.disabled = False

        self.app.call_from_thread(set_button)
        self.downloader.batch_search_all(handle_callback)
        self.app.call_from_thread(set_done)
        self.app.call_from_thread(self.sort_items)

    @work(thread=True)
    def _cancel_search(self, event: Button.Pressed):
        def set_button():
            self._searching.clear()
            button = event.control
            button.label = "Search"
            button.set_loading(False)
            button.disabled = False

        def set_loading():
            button = event.control
            button.set_loading(True)
            button.disabled = True

        self.app.call_from_thread(set_loading)
        self.downloader.cancel_batch_search()
        self.app.call_from_thread(set_button)
        self.app.call_from_thread(self.sort_items)

    @on(DownloadItemCollapsible.FillDownloadItem)
    @work(thread=True)
    def _autofill_item(self, event: DownloadItemCollapsible.FillDownloadItem):
        # TODO: thread safety
        metadata = event.collapsible.get_download_item().metadata
        if metadata and metadata.url == event.url:
            event.download_item.state = QueueState.FOUND
            event.collapsible.update_item(event.download_item.set_metadata(metadata), True)
            return

        result = self.downloader.get_from_link(event.url)

        if result:
            event.download_item.state = QueueState.FOUND
            event.collapsible.update_item(event.download_item.set_metadata(result), True)

    @on(DownloadItemCollapsible.ShowDownloadItemResult)
    @work
    async def _show_results_screen(self, event: DownloadItemCollapsible.ShowDownloadItemResult):
        result = await self.app.push_screen_wait(SearchResultPicker(event.download_item))

        if result is None:
            return

        event.download_item.state = QueueState.FOUND
        event.collapsible.update_item(event.download_item.set_metadata(result))

    @on(DownloadItemCollapsible.SearchDownloadItem)
    @work(thread=True)
    def _search_item(self, event: DownloadItemCollapsible.SearchDownloadItem):
        def handle_callback(song_id: SongID, download_item: DownloadItem, progress: tuple[int, int]):
            self.post_message(self.SearchUpdate(song_id, download_item, progress))

        download_item = event.download_item
        self.downloader.search(download_item.song.id, handle_callback)

    @on(DownloadItemCollapsible.DownloadDownloadItem)
    @work(thread=True)
    def _download_item(self, event: DownloadItemCollapsible.DownloadDownloadItem):
        def handle_callback(song_id: SongID, download_item: DownloadItem, progress: float):
            self.post_message(self.DownloadUpdate(song_id, download_item, progress))

        self.notify(f"{event.download_item.final_title}")

        ret = self.downloader.download(event.download_item.song.id, handle_callback)

        if ret:
            self._log.exception("Download Error", ret)

    @on(Button.Pressed, "#btn-clear")
    @work
    async def clear_queue(self):
        # TODO: make this confirm
        self.downloader.clear_queue()
        self._clear_item()
        queue = self.query_one("#queue-container", ScrollableContainer)
        await queue.remove_children()


from textual.app import App


class MyApp(App[None]):
    CSS_PATH = "../../testing.tcss"

    def compose(self) -> ComposeResult:
        yield DownloadPage()
        yield Footer()

    async def on_load(self) -> None:
        config = Config.get_config()
        client = await ListenClient.login(config.client.username, config.client.password)
        assert isinstance(client, ListenClient)
        # await client.connect()


app = MyApp()
app.run()


# download use a separate romaji preference setting

# widget[DownloadQueueItem -> QueueItem] -> actualData[DownloadItem]

# TODO: disable batch download when searching, likewise, disable batch search when downloading
# or think of a better solution, the current system should be able to handle both, its just that
# there is no locks to continue either one
