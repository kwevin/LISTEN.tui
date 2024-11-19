from __future__ import annotations

from typing import cast

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container, Grid
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static

from listentui.listen import Song
from listentui.listen.interface import Album, Artist, Source
from listentui.screen.modal.messages import SpawnAlbumScreen, SpawnSourceScreen
from listentui.widgets.artistScrollableLabel import ArtistScrollableLabel
from listentui.widgets.scrollableLabel import ScrollableLabel


class SongItem(ListItem):
    DEFAULT_CSS = """
    SongItem {
        padding: 1 0 1 0;
        border-left: thick $background-lighten-2;
    }
    SongItem ScrollableLabel, SongItem Label{
        margin-left: 1;
    }
    SongItem ArtistScrollableLabel ScrollableLabel {
        margin-left: 0;
    }

    SongItem ScrollableLabel, SongItem ArtistScrollableLabel {
        margin-left: 1;
    }

    SongItem > Container {
        width: 1fr;
        height: auto;
    }
    SongItem.favorited {
        border-left: thick red;
    }
    """

    def __init__(self, song: Song, favorited: bool = False, should_id: bool = True):
        if should_id:
            super().__init__(id=f"_song-{song.id}")
        else:
            super().__init__()
        self.song = song
        self.set_class(favorited, "favorited")
        self.title = song.format_title()

    def compose(self) -> ComposeResult:
        with Container():
            yield ScrollableLabel(
                Text.from_markup(f"{self.title}"),
                classes="item-title",
            )
            yield ArtistScrollableLabel(self.song)

    class SongChildClicked(Message):
        """For informing with the parent ListView that we were clicked"""

        def __init__(self, item: SongItem) -> None:
            super().__init__()
            self.item = item

    class SongLabelClicked(Message):
        def __init__(self, artist: Artist) -> None:
            super().__init__()
            self.artist = artist

    @on(ScrollableLabel.Clicked, ".item-title")
    def scroll_title_clicked(self, event: ScrollableLabel.Clicked) -> None:
        event.stop()
        self.post_message(self.SongChildClicked(self))

    def _on_click(self, _: events.Click) -> None:
        if not self.highlighted:
            return
        if any(label.is_currently_highlighted() for label in self.query(ScrollableLabel)):
            return
        self.post_message(self.SongChildClicked(self))

    def set_favorited_state(self, state: bool) -> None:
        self.set_class(state, "favorited")


class AdvSongItem(ListItem):
    DEFAULT_CSS = """
    AdvSongItem {
        padding: 1 0 1 0;
        border-left: thick $background-lighten-2;
    }
    AdvSongItem ScrollableLabel, AdvSongItem Label {
        margin-left: 1;
    }
    AdvSongItem ArtistScrollableLabel ScrollableLabel {
        margin-left: 0;
    }

    AdvSongItem ScrollableLabel, AdvSongItem ArtistScrollableLabel {
        margin-left: 1;
    }
    AdvSongItem #alb-only  {
        height: auto;
        grid-size: 2 2;
        grid-columns: 1fr 2fr;
        grid-rows: 1;
        grid-gutter: 0 1;
        margin-right: 1;
    }

    AdvSongItem #source-only  {
        height: auto;
        grid-size: 2 2;
        grid-columns: 1fr 2fr;
        grid-rows: 1;
        grid-gutter: 0 1;
        margin-right: 1;
    }

    AdvSongItem #alb-source {
        height: auto;
        grid-size: 3 2;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 1;
        grid-gutter: 0 1;
        margin-right: 1;
    }

    AdvSongItem.favorited {
        border-left: thick red;
    }

    AdvSongItem Label {
        color: grey;
    }
    AdvSongItem > Container {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(self, song: Song, favorited: bool = False, should_id: bool = True):
        if should_id:
            super().__init__(id=f"_song-{song.id}")
        else:
            super().__init__()
        self.song = song
        self.title = song.format_title()
        self.source = song.format_source()
        self.album = song.format_album()
        self.set_class(favorited, "favorited")

    def compose(self) -> ComposeResult:
        if not self.source and not self.album:
            with Container():
                yield ScrollableLabel(
                    Text.from_markup(f"{self.title}"),
                    classes="item-title",
                )
                yield ArtistScrollableLabel(self.song)
        elif self.album and not self.source:
            with Grid(id="alb-only"):
                yield ScrollableLabel(
                    Text.from_markup(f"{self.title}"),
                    classes="item-title",
                )
                yield Label("Album")
                yield ArtistScrollableLabel(self.song)
                yield (ScrollableLabel(Text.from_markup(f"[green]{self.album}[/]"), classes="item-album"))
        elif self.source and not self.album:
            with Grid(id="source-only"):
                yield ScrollableLabel(
                    Text.from_markup(f"{self.title}"),
                    classes="item-title",
                )
                yield Label("Source")
                yield ArtistScrollableLabel(self.song)
                yield (ScrollableLabel(Text.from_markup(f"[cyan]{self.source}[/]"), classes="item-source"))
        else:
            with Grid(id="alb-source"):
                yield ScrollableLabel(
                    Text.from_markup(f"{self.title}"),
                    classes="item-title",
                )
                yield Label("Album") if self.album else Static()
                yield Label("Source") if self.source else Static()
                yield ArtistScrollableLabel(self.song)
                yield (
                    ScrollableLabel(Text.from_markup(f"[green]{self.album}[/]"), classes="item-album")
                    if self.album
                    else Static()
                )
                yield (
                    ScrollableLabel(Text.from_markup(f"[cyan]{self.source}[/]"), classes="item-source")
                    if self.source
                    else Static()
                )

    class SongChildClicked(Message):
        """For informing with the parent ListView that we were clicked"""

        def __init__(self, item: AdvSongItem) -> None:
            super().__init__()
            self.item = item

    @on(ScrollableLabel.Clicked, ".item-title")
    def scroll_title_clicked(self, event: ScrollableLabel.Clicked) -> None:
        event.stop()
        self.post_message(self.SongChildClicked(self))

    @on(ScrollableLabel.Clicked, ".item-source")
    def scroll_source_clicked(self, event: ScrollableLabel.Clicked) -> None:
        event.stop()
        self.post_message(SpawnSourceScreen(cast(Source, self.song.source).id))

    @on(ScrollableLabel.Clicked, ".item-album")
    def scroll_album_clicked(self, event: ScrollableLabel.Clicked) -> None:
        event.stop()
        self.post_message(SpawnAlbumScreen(cast(Album, self.song.album).id))

    def _on_click(self, _: events.Click) -> None:
        if not self.highlighted:
            return
        if any(label.is_currently_highlighted() for label in self.query(ScrollableLabel)):
            return
        self.post_message(self.SongChildClicked(self))

    def set_favorited_state(self, state: bool) -> None:
        self.set_class(state, "favorited")


class SongListView(ListView):
    DEFAULT_CSS = """
    SongListView {
        height: auto;
        background: $background;
        &:focus-within {
            background-tint: $foreground 0%;
        }
        & > ListItem {
            margin-bottom: 1;
            # background-tint: $foreground 5%;
            background: $surface;
            &.-hovered {
                background: $background-lighten-2;
            }
            
            &.-highlight {
                # background-tint: black 30%;
                background-tint: $foreground 5%;
                background: $background-lighten-1;
            }

            &:last-of-type {
                margin-bottom: 0;
            }
        }
        &:focus > ListItem.-highlight > Widget {
            width: 1fr;
            background-tint: $foreground 5%;
            background: $background-lighten-1;
            text-style: reverse;
        }
    }
    """

    class SongSelected(Message):
        def __init__(self, song: Song) -> None:
            super().__init__()
            self.song = song

    @on(AdvSongItem.SongChildClicked)
    @on(SongItem.SongChildClicked)
    def song_clicked(self, event: SongItem.SongChildClicked) -> None:
        event.stop()
        self.post_message(self.SongSelected(event.item.song))

    def action_select_cursor(self) -> None:
        selected_child: SongItem | None = cast(SongItem | None, self.highlighted_child)
        if selected_child is None:
            return
        self.post_message(self.SongSelected(selected_child.song))
