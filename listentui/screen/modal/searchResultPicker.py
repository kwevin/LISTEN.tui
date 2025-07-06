from textwrap import indent
from typing import ClassVar

from rich.rule import Rule
from textual import events, on
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Center, Container, Grid
from textual.widgets import Button, Label, ListItem, ListView, Static

from listentui.downloader.baseInterface import SongMetadata
from listentui.downloader.downloader import DownloadItem
from listentui.listen.interface import Song
from listentui.screen.modal.baseScreen import BaseScreen
from listentui.screen.modal.buttons import EscButton
from listentui.widgets.songContainer import SongContainer
from listentui.widgets.songMetadataDisplay import SongMetadataDisplay


class SearchResultPicker(BaseScreen[SongMetadata | None, None, None]):
    """Screen for picking results from dowloader"""

    DEFAULT_CSS = """
    SearchResultPicker {
        align: center middle;

        .metadisplay_current {
            margin: 1 1;
        }
         .YoutubeMusic {
            border: tab red;
            border-title-color: white;
        }

        # &:hover {
        #     background: $block-hover-background;
        # }
    }
    SearchResultPicker #cancel {
        margin-top: 1;
    }
    SearchResultPicker ListView {
        margin: 2 2;
        height: 1fr;
    }
    SearchResultPicker #box {
        width: 100%;
        margin: 2 4;
    }
    SearchResultPicker ListItem {
        margin: 1 2;
        border: panel black;
        border-title-color: white;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
    ]

    def __init__(self, download_item: DownloadItem):
        super().__init__()
        self.download_item = download_item
        self.item_map: dict[int, SongMetadata] = {}

    def compose(self) -> ComposeResult:
        def get_display(item: SongMetadata) -> SongMetadataDisplay:
            display = SongMetadataDisplay(item, True, False, True, classes=f"{item.provider} metadisplay_current")
            display.border_title = item.provider
            return display

        def get_list(index: int, item: SongMetadata) -> ListItem:
            self.item_map[index] = item
            list_item = ListItem(SongMetadataDisplay(item, True, True), classes=item.provider)
            list_item.border_title = item.provider
            return list_item

        yield EscButton()
        with Container(id="box"):
            if self.download_item.metadata:
                yield get_display(self.download_item.metadata)
            with ListView():
                self.download_item.all_results.sort(key=lambda data: data.scores.total, reverse=True)
                filtered = self.download_item.all_results
                if self.download_item.metadata:
                    filtered = filter(lambda data: data != self.download_item.metadata, self.download_item.all_results)
                for index, item in enumerate(filtered):
                    yield get_list(index, item)

    @on(SongMetadataDisplay.Clicked)
    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(ListView.Selected)
    def selected(self, event: ListView.Selected):
        if event.control.index is None:
            return
        self.dismiss(self.item_map[event.control.index])


# TODO: make sure all ordering is right

# it should be

# top result
# ----------
# other result
# other result
