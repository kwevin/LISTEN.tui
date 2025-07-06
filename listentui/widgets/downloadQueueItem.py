from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from rich.rule import Rule
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Collapsible, Input, Static

from listentui.data.config import Config
from listentui.downloader.baseInterface import SongMetadata
from listentui.downloader.downloader import DownloadItem, QueueState
from listentui.widgets.buttons import LabelButton
from listentui.widgets.songMetadataDisplay import SongMetadataDisplay

type _MessageDefault = tuple[DownloadItemCollapsible, QueueItem, DownloadItem]


@dataclass
class _Action:
    action: str
    state: bool


class ActionInput(Input, can_focus=True):
    class Action(Enum):
        SHOW_RESULT = 0
        CLEAR = 1
        AUTOFILL = 2

    class ActionPressed(Message):
        def __init__(self, action: ActionInput.Action, inp: ActionInput) -> None:
            super().__init__()
            self.action = action
            self.inp = inp

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._actions: dict[str, _Action] = {
            "show_results": _Action("[@click=focused.show_results]Show Results[/]", False),
            "clear": _Action("[@click=focused.clear]Clear[/]", True),
            "autofill": _Action("[@click=focused.autofill]Autofill[/]", True),
        }

    def on_mount(self):
        self.border_title = "URL"
        self._build_action()

    def _build_action(self):
        actions = "   ".join((action.action for action in self._actions.values() if action.state))
        self.border_subtitle = actions

    def set_action(self, action: str, state: bool):
        self._actions[action].state = state
        self._build_action()

    def toggle_action(self, action: str):
        state = self._actions[action].state
        self._actions[action].state = not state
        self._build_action()

    def set_song(self, download_item: DownloadItem):
        if download_item.metadata is None:
            return
        self.value = download_item.metadata.url
        song = download_item.metadata
        if len(download_item.all_results) > 0:
            self.set_action("show_results", True)
        else:
            self.set_action("show_results", False)
        self.tooltip = f"Title: {song.title}\nArtists: {', '.join(song.artists)}\nAlbum: {song.album}"

    def clear_song(self):
        self.clear()
        self.tooltip = None
        self.set_action("show_results", False)

    def _action_show_results(self):
        self.post_message(self.ActionPressed(self.Action.SHOW_RESULT, self))

    def _action_clear(self):
        self.post_message(self.ActionPressed(self.Action.CLEAR, self))

    def _action_autofill(self):
        self.post_message(self.ActionPressed(self.Action.AUTOFILL, self))


class DownloadItemCollapsible(Collapsible):
    DEFAULT_CSS = """
    DownloadItemCollapsible {
        width: 1fr;
        height: auto;
        background: $boost;
        padding-left: 0;

        padding-bottom: 0;
        border-top: none;

        & Contents {
            padding: 1 0 2 1;
        }
    }

    DownloadItemCollapsible.-collapsed > Contents {
        display: none;
    }

    DownloadItemCollapsible #rc-title {
        width: 100%;
    }
    DownloadItemCollapsible #filler {
        width: 1fr;
        height: auto;
    }
    DownloadItemCollapsible > Horizontal {
        border-left: thick $background-lighten-1;
        margin-top: 0;
        height: 3;
        align: center middle;

        &.searching, &.downloading {
            border-left: thick $secondary-lighten-1;
        }

        &.found {
            border-left: thick $primary-lighten-1;
        }

        &.done {
            border-left: thick $success-lighten-1;
        }
        
        &.not_found {
            border-left: thick $error-lighten-1;
        }
        &.downloading {
            border-left: thick yellow;
        }
        &.download_failed {
            border-left: thick green;
        }
    }
    """

    class RemoveDownloadItem(Message):
        def __init__(self, defaults: _MessageDefault) -> None:
            super().__init__()
            (collapsible, queue, item) = defaults
            self.collapsible = collapsible
            self.queue_item = queue
            self.download_item = item

    class DownloadDownloadItem(Message):
        def __init__(self, defaults: _MessageDefault) -> None:
            super().__init__()
            (collapsible, queue, item) = defaults
            self.collapsible = collapsible
            self.queue_item = queue
            self.download_item = item

    class SearchDownloadItem(Message):
        def __init__(self, defaults: _MessageDefault) -> None:
            super().__init__()
            (collapsible, queue, item) = defaults
            self.collapsible = collapsible
            self.queue_item = queue
            self.download_item = item

    class FillDownloadItem(Message):
        def __init__(self, defaults: _MessageDefault, url: str) -> None:
            super().__init__()
            (collapsible, queue, item) = defaults
            self.collapsible = collapsible
            self.queue_item = queue
            self.download_item = item
            self.url = url

    class ShowDownloadItemResult(Message):
        def __init__(self, defaults: _MessageDefault) -> None:
            super().__init__()
            (collapsible, queue, item) = defaults
            self.collapsible = collapsible
            self.queue_item = queue
            self.download_item = item

    def __init__(
        self,
        item: DownloadItem,
        title: str = "Toggle",
        collapsed: bool = True,
        collapsed_symbol: str = "▶",
        expanded_symbol: str = "▼",
        name: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        self.queue_item = QueueItem(item)
        super().__init__(
            self.queue_item,
            title=title or "[This song title is blank]",
            collapsed=collapsed,
            collapsed_symbol=collapsed_symbol,
            expanded_symbol=expanded_symbol,
            name=name,
            id=f"_download_item-{item.song.id}",
            classes=classes,
            disabled=disabled,
        )
        self._state: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="rc-title"):
            yield self._title
            yield Static(id="filler")
            yield LabelButton("Download", id="_btn-download")
            yield LabelButton("Search", id="_btn-search")
            yield LabelButton("Remove", id="_btn-remove")
        yield self.Contents(*self._contents_list)

    def on_mount(self):
        self.query_one("#_btn-download", LabelButton).styles.visibility = "hidden"
        self.update_item(self.queue_item.item)

    def _get_message_default(self) -> _MessageDefault:
        return (self, self.get_queue_item(), self.get_download_item())

    @on(LabelButton.Clicked, "#_btn-remove")
    async def _remove_clicked(self, event: LabelButton.Clicked) -> None:
        self.post_message(self.RemoveDownloadItem(self._get_message_default()))

    @on(LabelButton.Clicked, "#_btn-download")
    async def _download_clicked(self, event: LabelButton.Clicked) -> None:
        if self.get_download_item().state == QueueState.FOUND:
            self.post_message(self.DownloadDownloadItem(self._get_message_default()))

    @on(LabelButton.Clicked, "#_btn-search")
    async def _search_clicked(self, event: LabelButton.Clicked) -> None:
        if self.get_download_item().state == QueueState.QUEUED:
            self.post_message(self.SearchDownloadItem(self._get_message_default()))

    def get_id(self) -> int:
        assert self.id is not None
        return int(self.id.split("-")[1])

    def get_queue_item(self) -> QueueItem:
        return self.queue_item

    def get_download_item(self) -> DownloadItem:
        return self.queue_item.item

    def update_item(self, item: DownloadItem, fill: bool = False):
        self.queue_item.update_item(item, fill)

        horizontal = self.query_one(Horizontal)
        if self._state:
            horizontal.remove_class(self._state)
        horizontal.add_class(item.state.name.lower())
        self._state = item.state.name.lower()

        match item.state:
            case QueueState.NOT_FOUND:
                self.query_one("#_btn-download", LabelButton).styles.visibility = "hidden"
            case QueueState.FOUND:
                self.query_one("#_btn-download", LabelButton).styles.visibility = "visible"
                self.query_one("#_btn-search", LabelButton).styles.display = "none"
            case QueueState.DOWNLOADING | QueueState.DONE:
                self.query_one("#_btn-download", LabelButton).styles.visibility = "hidden"
                self.query_one("#_btn-search", LabelButton).styles.display = "none"
            case QueueState.DOWNLOAD_FAILED:
                self.query_one("#_btn-download", LabelButton).styles.visibility = "visible"
                self.query_one("#_btn-search", LabelButton).styles.display = "block"

    @on(ActionInput.ActionPressed)
    def _handle_action(self, action: ActionInput.ActionPressed):
        action.stop()
        match action.action:
            case ActionInput.Action.CLEAR:
                self.update_item(self.queue_item.item)
            case ActionInput.Action.AUTOFILL:
                self.post_message(self.FillDownloadItem(self._get_message_default(), self.queue_item.get_url()))
            case ActionInput.Action.SHOW_RESULT:
                self.post_message(self.ShowDownloadItemResult(self._get_message_default()))

    # TODO: download status and progress-bar integration?


class QueueItem(Widget):
    DEFAULT_CSS = """
    QueueItem {
        width: 1fr;
        height: auto;
    }

    QueueItem Horizontal {
        height: auto;

        & > Input {
            width: 1fr;
        }
    }

    QueueItem * {
        border-subtitle-color: $text-accent;
        border-title-color: $text-accent;
    }
    """

    def __init__(self, item: DownloadItem):
        super().__init__(id=f"_queue_item-{item.song.id}")
        self.item = item

    def compose(self) -> ComposeResult:
        yield UrlData()
        yield Static(Rule("Metadata", style="white"))
        yield Input(id="metadata-title", placeholder=self.item.song.format_title())
        with Horizontal():
            yield Input(id="metadata-artist", placeholder=self.item.song.format_artists(show_character=False))
            yield Input(id="metadata-album", placeholder=self.item.song.format_album())

    def on_mount(self) -> None:
        self.query_one("#metadata-title").border_title = "Title"
        self.query_one("#metadata-artist").border_title = "Artist"
        self.query_one("#metadata-album").border_title = "Album"
        if Config.get_config().downloader.use_radio_metadata:
            self.autofill_from_radio()

    def autofill_from_radio(self):
        self.query_exactly_one("#metadata-title", Input).value = self.item.song.format_title()
        self.query_exactly_one("#metadata-artist", Input).value = self.item.song.format_artists(show_character=False)
        self.query_exactly_one("#metadata-album", Input).value = self.item.song.format_album()

    def autofill_from_metadata(self, metadata: SongMetadata):
        self.query_exactly_one("#metadata-title", Input).value = metadata.title
        self.query_exactly_one("#metadata-artist", Input).value = ", ".join(metadata.artists)
        self.query_exactly_one("#metadata-album", Input).value = metadata.album or ""

        self.set_metadata_from_inputs()

    def set_metadata_from_inputs(self):
        self.item.final_title = self.query_exactly_one("#metadata-title", Input).value
        self.item.final_artists = self.query_exactly_one("#metadata-artist", Input).value
        self.item.final_album = self.query_exactly_one("#metadata-album", Input).value

    def update_item(self, item: DownloadItem, fill: bool = False):
        match item.state:
            case QueueState.FOUND:
                assert item.metadata is not None
                self.query_one(UrlData).update(item)

                if not Config.get_config().downloader.use_radio_metadata:
                    self.autofill_from_metadata(item.metadata)
            case QueueState.NOT_FOUND:
                self.query_one(UrlData).set_not_found()

        if fill:
            assert item.metadata is not None
            self.autofill_from_metadata(item.metadata)

        self.set_metadata_from_inputs()

    def get_url(self) -> str:
        return self.query_one(UrlData).get_url()

    @on(Input.Changed, "#metadata-title")
    def _update_metadata_title(self, event: Input.Changed):
        if event.value:
            self.item.final_title = event.value

    @on(Input.Changed, "#metadata-artists")
    def _update_metadata_artists(self, event: Input.Changed):
        if event.value:
            self.item.final_artists = event.value

    @on(Input.Changed, "#metadata-album")
    def _update_metadata_album(self, event: Input.Changed):
        if event.value:
            self.item.final_album = event.value

    @on(ActionInput.ActionPressed)
    def _handle_action(self, action: ActionInput.ActionPressed):
        match action.action:
            case ActionInput.Action.CLEAR:
                self.item.state = QueueState.NOT_FOUND
                self.item.metadata = None
                self.query_exactly_one("#metadata-title", Input).clear()
                self.query_exactly_one("#metadata-artist", Input).clear()
                self.query_exactly_one("#metadata-album", Input).clear()
            case ActionInput.Action.AUTOFILL:
                if (
                    self.item.state == QueueState.NOT_FOUND
                    and not self.get_url()
                    and Config.get_config().downloader.use_radio_metadata
                ):
                    self.autofill_from_radio()
            case ActionInput.Action.SHOW_RESULT:
                pass


class UrlData(Widget):
    DEFAULT_CSS = """
    UrlData {
        height: auto;

        & Collapsible {
            border: none;
            padding: 0;
            margin: 0 1;
        }
    }
    """

    def compose(self) -> ComposeResult:
        yield ActionInput(id="result-url")
        with Collapsible(id="url-data"):
            yield SongMetadataDisplay()

    def on_mount(self):
        self.query_one("#url-data", Collapsible).styles.display = "none"

    def get_url(self) -> str:
        return self.query_one("#result-url", ActionInput).value

    def update(self, download_item: DownloadItem):
        if download_item.metadata is None:
            return
        self.query_one("#url-data", Collapsible).styles.display = "block"
        self.query_one("#result-url", ActionInput).set_song(download_item)

        scores = [
            f"Total: {round(download_item.metadata.scores.total, 2)}",
            f"TL: {round(download_item.metadata.scores.title, 2)}",
            f"AR: {round(download_item.metadata.scores.artist, 2)}",
            f"AL: {round(download_item.metadata.scores.album, 2)}",
            f"B: {sum(download_item.metadata.scores.bonuses)}",
        ]

        self.query_one("#url-data", Collapsible).title = " ".join(scores)
        self.query_one(SongMetadataDisplay).update(download_item.metadata)

    def set_not_found(self):
        self.query_one("#result-url", ActionInput).set_action("show_results", True)

    @on(ActionInput.ActionPressed)
    def handle_action(self, action: ActionInput.ActionPressed):
        match action.action:
            case ActionInput.Action.CLEAR:
                self.query_one("#url-data", Collapsible).styles.display = "none"
                action.inp.clear_song()
            case ActionInput.Action.AUTOFILL:
                pass
            case ActionInput.Action.SHOW_RESULT:
                pass
