from concurrent.futures import Future, ThreadPoolExecutor
from enum import Enum
from typing import ClassVar, Iterable

from rich.rule import Rule
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Grid, Horizontal, ScrollableContainer
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Static
from textual.worker import Worker, get_current_worker  # type: ignore

from listentui.data.config import Config
from listentui.downloader.providers.search.baseProvider import SearchResult
from listentui.downloader.providers.search.ytm import YoutubeMusic
from listentui.listen.client import ListenClient
from listentui.listen.interface import Song, SongID
from listentui.pages.base import BasePage
from listentui.utilities import de_kuten
from listentui.widgets.removableCollapsible import RemovableCollapsible
from listentui.widgets.scrollableLabel import ScrollableLabel


class QueueState(Enum):
    QUEUED = 0
    SEARCHING = 1
    NOT_FOUND = 2
    FOUND = 3
    DOWNLOADING = 4
    DONE = 5


class SongInfo(Grid):
    DEFAULT_CSS = """
    SongInfo {
        width: 100%;
        height: 6;
        align: center middle;
        grid-size: 3 2;
        grid-gutter: 1 2;
        grid-rows: 1 3;
        
        &> Container {
            height: 3;
            width: 100%;
            align: left middle;
        }
    }
    SongInfo ScrollableLabel {
        height: 1;
    }
    
    """

    def __init__(self, song: Song) -> None:
        super().__init__()
        self.song = song

    def compose(self) -> ComposeResult:
        yield Label("Track/Artist")
        yield Label("Album")
        yield Label("Source")
        yield Container(
            ScrollableLabel(Text.from_markup(self.song.format_title() or ""), id="title"),
            ScrollableLabel(
                *[Text.from_markup(f"[red]{artist}[/]") for artist in a]
                if (a := self.song.format_artists_list())
                else [],
                id="artist",
            ),
        )
        album = self.song.format_album()
        source = self.song.format_source()
        yield Container(
            ScrollableLabel(
                Text.from_markup(f"[green]{album}[/]" if album else ""),
                id="album",
            )
        )
        yield Container(
            ScrollableLabel(
                Text.from_markup(f"[cyan]{source}[/]" if source else ""),
                id="source",
            )
        )
        yield Label(f"Duration: {self.song.duration}", id="duration")


class QueueItem(Widget):
    state: var[QueueState] = var(QueueState.QUEUED)

    DEFAULT_CSS = """
    QueueItem {
        border-left: inner $background-lighten-1;
        width: 100%;
        height: auto;
        &.searching, &.downloading {
            border-left: inner $secondary-lighten-1;
        }

        &.found {
            border-left: inner $primary-lighten-1;
        }

        &.done {
            border-left: inner $success-lighten-1;
        }
        
        &.not_found {
            border-left: inner $error-lighten-1;
        }
        & Horizontal {
            margin-top: 1;
            width: auto;
            height: auto;
        }

        & SongInfo, #url-scores {
            margin-left: 1;
        }
    }
    """

    def __init__(self, song: Song) -> None:
        super().__init__(id=f"queue-item-{song.id}")
        self.song = song
        self.border_subtitle = f"{self.song.id}"
        self.result: SearchResult | list[SearchResult] | None = None
        self.has_metadata = False

    def compose(self) -> ComposeResult:
        with RemovableCollapsible(title=f"[{self.song.id}] {de_kuten(self.song.format_title() or '')}"):
            yield SongInfo(self.song)
            yield Input(id="result-url")
            yield Label(classes="url-data", id="url-scores")
            yield Static(Rule("Metadata", style="white"))
            yield Input(id="metadata-title")
            with Horizontal():
                yield Input(id="metadata-artist")
                yield Input(id="metadata-album")

    def on_mount(self) -> None:
        url = self.query_exactly_one("#result-url", Input)
        url.border_subtitle = "[@click=focused.clear]Clear[/]   [@click=focused.autofill]Autofill[/]"
        url.border_title = "URL"

        self.query_one("#metadata-title").border_title = "Title"
        self.query_one("#metadata-artist").border_title = "Artist"
        self.query_one("#metadata-album").border_title = "Album"

        if Config.get_config().downloader.use_radio_metadata:
            self.query_exactly_one("#metadata-title", Input).value = self.song.format_title()
            self.query_exactly_one("#metadata-artist", Input).value = self.song.format_artists(show_character=False)
            self.query_exactly_one("#metadata-album", Input).value = self.song.format_album()

    def watch_state(self, old_state: QueueState, new_state: QueueState) -> None:
        self.remove_class(old_state.name.lower())
        self.add_class(new_state.name.lower())

    @work
    async def update_result(self, result: SearchResult | list[SearchResult]) -> None:
        self.result = result
        if isinstance(result, list):
            self.state = QueueState.NOT_FOUND
            return

        self.state = QueueState.FOUND
        result_input = self.query_exactly_one("#result-url", Input)
        result_input.value = result.url
        result_input.tooltip = f"[red]Title[/]: {result.title}\n[red]Artist[/]: {','.join(result.artist or [])}\n[red]Album[/]: {result.album}"  # noqa: E501

        scores = [
            f"Total: {round(result.scores.total, 2)}",
            f"TL: {round(result.scores.title, 2)}",
            f"AR: {round(result.scores.artist, 2)}",
            f"AL: {round(result.scores.album, 2)}",
            f"D: {round(result.scores.duration, 2)}",
            f"V: {round(result.scores.views, 2)}",
            f"B: {sum(result.scores.bonuses)}",
        ]

        self.query_one("#url-scores", Label).update(" ".join(scores))

        if not Config.get_config().downloader.use_radio_metadata:
            self.query_exactly_one("#metadata-title", Input).value = result.title
            self.query_exactly_one("#metadata-artist", Input).value = ",".join(result.artist or [])
            self.query_exactly_one("#metadata-album", Input).value = result.album or ""


class DownloadPage(BasePage):
    # we want the data to be persistant
    # TODO: pickle and save in case of weird crash it can recover
    queue: ClassVar[dict[SongID, QueueItem]] = {}

    DEFAULT_CSS = """
    DownloadPage {
        align: center middle;

        & ScrollableContainer {
            padding: 1 1;
        }

        & Input {
            width: 1fr;
        }
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "start", "start"),
        Binding("ctrl+a", "cancel", "abort"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.client = ListenClient.get_instance()
        self.thread = 5
        self.current_page = 1
        self.pool = ThreadPoolExecutor(self.thread)

    def compose(self) -> ComposeResult:
        yield Input()
        with ScrollableContainer():
            for item in self.get_queue_item():
                yield item

    def get_queue_item(self) -> Iterable[QueueItem]:
        return self.queue.values()

    @work
    async def resort(self) -> None:
        self.query_exactly_one(ScrollableContainer).sort_children(
            key=lambda item: item.state.value if isinstance(item, QueueItem) else -1, reverse=True
        )

    @work
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user = self.client.current_user
        assert user is not None
        songs = await self.client.user_favorites(user.username, 0, 10)
        self.batch_queue(songs)

    @work
    async def batch_queue(self, songs: Iterable[Song]) -> None:
        new_items: list[QueueItem] = []
        for song in songs:
            if self.queue.get(song.id) is not None:
                continue
            queue_item = QueueItem(song)
            self.queue[song.id] = queue_item
            new_items.append(queue_item)
        await self.query_one(ScrollableContainer).mount_all(new_items)
        self.resort()

    def add_to_queue(self, song: Song) -> None:
        if self.queue.get(song.id) is None:
            self.notify("Song already in download queue")
            return

        self.batch_queue([song])

    async def remove_from_queue(self, song: Song) -> None:
        # shouldnt raise the error as the only way to remove from queue is in the queue itself
        # item = self.queue.pop(song.id)
        pass

    def action_start(self) -> None:
        self.start_searcher()

    def action_cancel(self) -> None:
        self.workers.cancel_group(self, "searcher")  # type: ignore

    @work(thread=True, group="searcher")
    def start_searcher(self) -> None:
        def update_queue_item(searcher: YoutubeMusic, item: QueueItem) -> None:
            item.state = QueueState.SEARCHING
            item.update_result(searcher.find_best())

        futures: list[Future[None]] = []
        for item in self.queue.values():
            if item.result:
                continue
            searcher = YoutubeMusic(item.song)
            futures.append(self.pool.submit(update_queue_item, searcher, item))

        worker: Worker[None] = get_current_worker()
        for future in futures:
            if worker.is_cancelled:
                break
            future.result()

        # cancel all futures that are not done
        for future in futures:
            if not future.done():
                future.cancel()

        # wait for any futures that is running to be done
        for future in futures:
            if future.running():
                future.result()

        self.resort()

    @work(thread=True)
    def start_download(self) -> None: ...


from textual.app import App, ComposeResult


class MyApp(App[None]):
    def compose(self) -> ComposeResult:
        yield DownloadPage()
        yield Footer()

    async def on_load(self) -> None:
        client = await ListenClient.login("kwevin", "^3&hcZ8q3TX&uG7s")
        assert isinstance(client, ListenClient)
        await client.connect()


app = MyApp()
app.run()


# download use a separate romaji preference setting
