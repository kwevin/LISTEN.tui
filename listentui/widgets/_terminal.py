from __future__ import annotations

import asyncio
import code
import inspect
from abc import abstractmethod
from argparse import ArgumentError, ArgumentParser, Namespace
from functools import partial
from typing import Any, Awaitable, Self, TypeVar, overload

from rich.console import Console, ConsoleOptions, ConsoleRenderable, RenderResult
from rich.pretty import pprint
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.events import Key
from textual.widget import Widget
from textual.widgets import Input, Label, Pretty, Static

from listentui.data.config import Config
from listentui.listen.client import ListenClient
from listentui.listen.types import AlbumID, ArtistID

# from .base import BasePage

T = TypeVar("T")


class ParseError(Exception):
    def __init__(self, message: str, exception: ArgumentError | None = None) -> None:
        self.message = message
        self.exception = exception


class BaseCommand(Widget):
    DEFAULT_CSS = """
    BaseCommand {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(
        self,
        parser: Parser,
        args: Namespace,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__()
        self.parser = parser
        self.args = args
        self.loop = event_loop
        self.config = Config.get_config()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Return a `RenderResult` to be used in command line mode"""
        raise NotImplementedError()

    def compose(self) -> ComposeResult:
        """Return a `ComposeResult` to be used in TUI mode"""
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def run(cls, parser: Parser, args: Namespace, event_loop: asyncio.AbstractEventLoop | None = None) -> Self:
        return cls(parser, args, event_loop)

    def async_run(self, func: Awaitable[T]) -> T:
        return self.loop.run_until_complete(func) if self.loop else asyncio.new_event_loop().run_until_complete(func)

    def write_error(self, error: str) -> Table:
        table = Table.grid()
        table.add_row(f"[red]{error}[/]")
        return table


class CommandHelp(BaseCommand):
    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.get_text()

    def compose(self) -> ComposeResult:
        yield Label(self.get_text(), shrink=True)

    def get_text(self) -> Text:
        if not self.args.cmd:
            return Text(self.parser.parser.format_help())
        subcmd = self.parser.subparser.choices.get(self.args.cmd)
        if not subcmd:
            return Text(f"{self.args.cmd} is not a valid command")
        return Text(subcmd.format_help())


class CommandClear(BaseCommand):
    def compose(self) -> ComposeResult:
        yield Static()

    def on_mount(self) -> None:
        self.app.query_one(TerminalPage).clear()


class CommandEval(BaseCommand):
    def compose(self) -> ComposeResult:
        yield self.eval()

    def eval(self) -> Widget:
        try:
            compiled = code.compile_command(" ".join(self.args.expr), symbol="eval")
        except (SyntaxError, ValueError, OverflowError):
            return Pretty("Invalid python syntax")
        if not compiled:
            return Static()
        try:
            res = eval(compiled)
        except Exception as exc:
            res = exc
        return Pretty(res)


class CommandSearch(BaseCommand):
    def __init__(self, parser: Parser, args: Namespace, event_loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__(parser, args, event_loop)
        self.table = self.async_run(self.populate_table())

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.table

    async def populate_table(self) -> Table:
        client = ListenClient.get_instance()
        romaji_first = self.config.display.romaji_first
        table = Table(expand=False, show_lines=True)
        table.add_column("Id", ratio=2)
        table.add_column("Track", ratio=6)
        table.add_column("Artist", ratio=2)
        table.add_column("Album", ratio=2)
        table.add_column("Source", ratio=2)

        if self.args.favorite and not client.logged_in:
            return self.write_error("You need to be logged in to use the -f flag")

        if self.args.favorite:
            search_result = await client.search(" ".join(self.args.query), count=self.args.count, favorite_only=True)
        else:
            search_result = await client.search(" ".join(self.args.query), count=self.args.count)

        for song in search_result:
            table.add_row(
                str(song.id),
                song.format_title(romaji_first=romaji_first),
                song.format_artists(show_character=False, romaji_first=romaji_first, embed_link=True),
                song.format_album(romaji_first=romaji_first, embed_link=True),
                song.format_source(romaji_first=romaji_first, embed_link=True),
            )
        return table


class CommandHistory(BaseCommand):
    def __init__(self, parser: Parser, args: Namespace, event_loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__(parser, args, event_loop)
        self.table = self.async_run(self.populate_table())

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.table

    async def populate_table(self) -> Table:
        client = ListenClient.get_instance()
        romaji_first = self.config.display.romaji_first
        table = Table(expand=False, show_lines=True)
        table.add_column("Id", ratio=2)
        table.add_column("Track", ratio=6)
        table.add_column("Requested By", ratio=3)
        table.add_column("Played At", ratio=3)
        table.add_column("Artist", ratio=2)
        table.add_column("Album", ratio=2)
        table.add_column("Source", ratio=2)

        history_result = await client.history(self.args.count)

        for history in history_result:
            song = history.song
            table.add_row(
                str(song.id),
                song.format_title(romaji_first=romaji_first),
                history.requester.display_name if history.requester else "",
                history.created_at.strftime("%d-%m-%Y %H:%M:%S"),
                song.format_artists(show_character=False, romaji_first=romaji_first, embed_link=True),
                song.format_album(romaji_first=romaji_first, embed_link=True),
                song.format_source(romaji_first=romaji_first, embed_link=True),
            )
        return table


class CommandAlbum(BaseCommand):
    def __init__(self, parser: Parser, args: Namespace, event_loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__(parser, args, event_loop)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        for album_id in self.args.id:
            yield self.async_run(self.get_album(AlbumID(album_id)))

    async def get_album(self, album_id: AlbumID) -> Table:
        client = ListenClient.get_instance()
        album = await client.album(album_id)

        table = Table(expand=False, show_lines=True, show_header=False)
        if not album:
            table.add_row(f"Album {album_id} does not exists")
            return table

        table.add_column(ratio=2, min_width=10)
        table.add_column(ratio=8, min_width=20)

        table.title = f"[link={album.link}]{album.name}[/link]"
        table.title_justify = "center"
        table.add_row("Id", str(album.id))
        if album.name_romaji:
            table.add_row("Romaji", album.name_romaji)
        if album.image:
            table.add_row("Image Link", f"[link={album.image.url}]Link[/link]")

        return table

    def compose(self) -> ComposeResult:
        yield Container()

    async def on_mount(self) -> None:
        for album_id in self.args.id:
            self.query_one(Container).mount(Static(await self.get_album(AlbumID(album_id))))


class CommandArtist(BaseCommand):
    def __init__(self, parser: Parser, args: Namespace, event_loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__(parser, args, event_loop)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        for artist_id in self.args.id:
            yield self.async_run(self.get_artist(ArtistID(artist_id)))

    async def get_artist(self, artist_id: ArtistID) -> Table:
        client = ListenClient.get_instance()
        album = await client.artist(artist_id)

        table = Table(expand=False, show_lines=True, show_header=False)
        if not album:
            table.add_row(f"Artist {artist_id} does not exists")
            return table

        table.add_column(ratio=2, min_width=10)
        table.add_column(ratio=8, min_width=20)

        table.title = f"[link={album.link}]{album.name}[/link]"
        table.title_justify = "center"
        table.add_row("Id", str(album.id))
        if album.name_romaji:
            table.add_row("Romaji", album.name_romaji)
        if album.characters:
            character_table = Table.grid(expand=False)
            for character in album.characters:
                character_table.add_row(f"[link={character.link}]{character.name}[/link]")
            table.add_row("Character", character_table)
        if album.image:
            table.add_row("Image Link", f"[link={album.image.url}]Link[/link]")

        return table

    def compose(self) -> ComposeResult:
        yield Container()

    async def on_mount(self) -> None:
        for artist_id in self.args.id:
            self.query_one(Container).mount(Static(await self.get_artist(ArtistID(artist_id))))


class CommandSong(BaseCommand):
    def __init__(self, parser: Parser, args: Namespace, event_loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__(parser, args, event_loop)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        for artist_id in self.args.id:
            yield self.async_run(self.get_artist(ArtistID(artist_id)))

    async def get_artist(self, artist_id: ArtistID) -> Table:
        client = ListenClient.get_instance()
        album = await client.artist(artist_id)

        table = Table(expand=False, show_lines=True, show_header=False)
        if not album:
            table.add_row(f"Artist {artist_id} does not exists")
            return table

        table.add_column(ratio=2, min_width=10)
        table.add_column(ratio=8, min_width=20)

        table.title = f"[link={album.link}]{album.name}[/link]"
        table.title_justify = "center"
        table.add_row("Id", str(album.id))
        if album.name_romaji:
            table.add_row("Romaji", album.name_romaji)
        if album.characters:
            character_table = Table.grid(expand=False)
            for character in album.characters:
                character_table.add_row(f"[link={character.link}]{character.name}[/link]")
            table.add_row("Character", character_table)
        if album.image:
            table.add_row("Image Link", f"[link={album.image.url}]Link[/link]")

        return table

    def compose(self) -> ComposeResult:
        yield Container()

    async def on_mount(self) -> None:
        for artist_id in self.args.id:
            self.query_one(Container).mount(Static(await self.get_artist(ArtistID(artist_id))))


class CommandPreview(BaseCommand):
    ...


class CommandUser(BaseCommand):
    ...


class CommandCharacter(BaseCommand):
    ...


class CommandSource(BaseCommand):
    ...


class CommandDownload(BaseCommand):
    ...


class CommandCheckFavorite(BaseCommand):
    ...


class CommandFavorite(BaseCommand):
    ...


class Parser:
    def __init__(self, cli: bool = False, event_loop: asyncio.AbstractEventLoop | None = None) -> None:
        self.parser = ArgumentParser(prog="", exit_on_error=False, add_help=False)
        self.subparser = self.parser.add_subparsers()
        self.cli = cli
        self.loop = event_loop
        self._add_command = partial(self.subparser.add_parser, add_help=False, exit_on_error=False)
        self._build_parser()

    def parse(self, args: list[str]) -> Namespace:
        try:
            command, others = self.parser.parse_known_args(args)
            if len(others) > 0:
                raise ParseError(f"Unknown argument: {others[0]}")
            return command
        except ArgumentError as exc:
            raise ParseError(exc.message, exc) from exc
        except SystemExit as exc:
            raise ParseError("Missing argument") from exc

    @overload
    def parse_and_run(self, args: list[str], *, console: bool) -> ConsoleRenderable:
        ...

    @overload
    def parse_and_run(self, args: list[str]) -> Widget:
        ...

    def parse_and_run(self, args: list[str], console: bool = False) -> ConsoleRenderable | Widget:
        result = self.parse(args)
        return result.cls.run(self, result, self.loop)

    def _build_parser(self) -> Any:
        """
        you can register a command by creating a method with the name `register_<command_name>`\n
        you can register an exclusive tui or cli command by creating a method with the name `register_<tui|cli>_<command_name>`
        """  # noqa: E501
        registers = [
            method
            for name, method in inspect.getmembers(self, predicate=inspect.ismethod)
            if name.startswith("register")
            and (name.split("_")[1] != "tui" if self.cli else name.split("_")[1] != "cli")
        ]
        for register_command in registers:
            # TODO: remove
            print(f"registering {register_command.__name__}")
            register_command()

    def register_help(self) -> None:
        help = self._add_command("help", help="Print help for given command")  # noqa: A001
        help.add_argument("cmd", nargs="?", help="A command", metavar="COMMAND", type=str)
        help.set_defaults(cls=CommandHelp)

    def register_tui_clear(self) -> None:
        clear = self._add_command("clear", help="Clear the console output")
        clear.set_defaults(cls=CommandClear)

    def register_tui_eval(self) -> None:
        eval = self._add_command("eval", help="Evaluate a python expression")  # noqa: A001
        eval.add_argument("expr", nargs="*", help="A python expression", metavar="EXPRESSION")
        eval.set_defaults(cls=CommandEval)

    def register_cli_search(self) -> None:
        search = self._add_command("search", help="Search for a song")
        search.add_argument("query", nargs="+", help="The query to search for", metavar="STRING", type=str)
        search.add_argument(
            "-c",
            "--count",
            help="(default: 10) The amount of results to return",
            dest="count",
            metavar="INT",
            type=int,
            default=10,
        )
        search.add_argument(
            "-f",
            "--favorite-only",
            dest="favorite",
            help="[Requires Login] Search favorited songs only",
            action="store_true",
        )
        search.set_defaults(cls=CommandSearch)

    def register_cli_history(self) -> None:
        history = self._add_command("history", help="Show previously played history")
        history.add_argument(
            "-c",
            "--count",
            help="(default: 10) The amount of result to return",
            dest="count",
            metavar="INT",
            type=int,
            default=10,
        )
        history.set_defaults(cls=CommandHistory)

    def register_tui_album(self) -> None:
        album = self._add_command("album", help="Fetch info on an album")
        album.add_argument(
            "id", nargs="*", help="(optional) Default to current song album", metavar="AlbumID", type=int
        )
        album.set_defaults(cls=CommandAlbum)

    def register_cli_album(self) -> None:
        album = self._add_command("album", help="Fetch info on an album")
        album.add_argument("id", nargs="+", help="The ID of an album", metavar="AlbumID", type=int)
        album.set_defaults(cls=CommandAlbum)

    def register_tui_artist(self) -> None:
        artist = self._add_command("artist", help="Fetch info on an artist")
        artist.add_argument(
            "id", nargs="*", help="(optional) Default to current song first artist", metavar="ArtistID", type=int
        )
        artist.set_defaults(cls=CommandArtist)

    def register_cli_artist(self) -> None:
        artist = self._add_command("artist", help="Fetch info on an artist")
        artist.add_argument("id", nargs="+", help="The ID of an artist", metavar="ArtistID", type=int)
        artist.set_defaults(cls=CommandArtist)

    def register_tui_song(self) -> None:
        song = self._add_command("song", help="Fetch info on a song")
        song.add_argument("id", nargs="*", help="(optional) Default to current song", metavar="SongID", type=int)
        song.set_defaults(cls=CommandSong)

    def register_cli_song(self) -> None:
        song = self._add_command("song", help="Fetch info on a song")
        song.add_argument("id", nargs="+", help="The ID of a song", metavar="SongID", type=int)
        song.set_defaults(cls=CommandSong)

    def register_cli_preview(self) -> None:
        pv = self._add_command("preview", aliases=["pv"], help="Preview a portion of the song audio")
        pv.add_argument("id", help="The id of the song", metavar="SongID", type=int)
        pv.set_defaults(cls=CommandPreview)

    def register_user(self) -> None:
        user = self._add_command("user", help="Fetch info on an user")
        user.add_argument("username", help="The username of the user", metavar="USERNAME", type=str)
        user.add_argument(
            "-c",
            "--count",
            help="(default: 10) The amount of user feeds to return",
            dest="count",
            metavar="INT",
            type=int,
            default=10,
        )
        user.set_defaults(cls=CommandUser)

    def register_tui_character(self) -> None:
        character = self._add_command("character", help="Fetch info on a character")
        character.add_argument(
            "id", nargs="*", help="(optional) Default to current song first character", metavar="CharacterID", type=int
        )
        character.set_defaults(cls=CommandCharacter)

    def register_cli_character(self) -> None:
        character = self._add_command("character", help="Fetch info on a character")
        character.add_argument("id", nargs="+", help="The ID of a character", metavar="CharacterID", type=int)
        character.set_defaults(cls=CommandCharacter)

    def register_tui_source(self) -> None:
        source = self._add_command("source", help="Fetch info on a source")
        source.add_argument(
            "id", nargs="*", help="(optional) Default to current song source", metavar="SourceID", type=int
        )
        source.set_defaults(cls=CommandSource)

    def register_cli_source(self) -> None:
        source = self._add_command("source", help="Fetch info on a source")
        source.add_argument("id", nargs="+", help="The ID of a source", metavar="SourceID", type=int)
        source.set_defaults(cls=CommandSource)

    def register_tui_download(self) -> None:
        download = self._add_command("download", help="Download a song")
        download.add_argument(
            "id", nargs="*", help="(optional), default to current playing song", metavar="songID", type=int
        )
        download.set_defaults(cls=CommandDownload)

    def register_cli_download(self) -> None:
        download = self._add_command("download", help="Download a song")
        download.add_argument("id", nargs="+", help="The ID of a song", metavar="songID", type=int)
        download.set_defaults(cls=CommandDownload)

    def register_check_favorite(self) -> None:
        check_f = self._add_command("check", help="Check if the song has been favorited")
        check_f.add_argument("id", nargs="+", help="The ID of a song", metavar="SongID", type=int)
        check_f.set_defaults(cls=CommandCheckFavorite)

    def register_favorite(self) -> None:
        favorite = self._add_command("favorite", help="Favorite a song")
        favorite.add_argument("id", nargs="+", help="The ID of a song", metavar="SongID", type=int)
        favorite.set_defaults(cls=CommandFavorite)


class History:
    def __init__(self) -> None:
        self.history: list[str] = []
        self.pointer = 0
        self.max_size = 100

    def append(self, command: str) -> None:
        if len(self.history) == 0:
            self.history.append(command)
        if command != self.history[-1]:
            self.history.append(command)
        self.pointer = 0

    def previous(self) -> str:
        if self.pointer < len(self.history):
            self.pointer += 1
        return self.history[-self.pointer]

    def next(self) -> str:
        if self.pointer > 1:
            self.pointer -= 1
        return self.history[-self.pointer]


class TerminalInput(Horizontal):
    DEFAULT_CSS = """
    TerminalInput Horizontal {
        width: 1fr;
        height: auto;
    }
    TerminalInput Static {
        width: auto;
        margin-right: 1;
    }
    TerminalInput Input {
        width: 1fr;
        background: $background 0%;
        color: $text;
        padding: 0;
        border: none;
        height: 1;
    }
    TerminalInput Input:focus {
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(">")
        yield Input()

    def put(self, command: str) -> None:
        self.query_one(Input).value = command


class TerminalPage(Widget):
    DEFAULT_CSS = """
    TerminalPage VerticalScroll {
        margin: 2;
        border: round white;
    }
    TerminalPage VerticalScroll > * {
        margin-bottom: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.can_focus = False
        self.container = VerticalScroll()
        self.parser = Parser()
        self.history = History()

    def compose(self) -> ComposeResult:
        with self.container:
            yield TerminalInput()

    def on_show(self) -> None:
        self.query_one(TerminalInput).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if len(event.value) == 0:
            return
        self.history.append(event.value)
        self.container.mount(Static(f"> {event.value}"), before="TerminalInput")
        try:
            result = self.parser.parse_and_run(event.value.split())
            self.container.mount(result, before="TerminalInput")
        except ParseError as e:
            self.container.mount(Static(f"{e.message}"), before="TerminalInput")
        event.input.clear()
        event.input.scroll_visible()

    def on_key(self, event: Key) -> None:
        if event.key == "up":
            event.prevent_default()
            self.query_one(TerminalInput).put(self.history.previous())
        if event.key == "down":
            event.prevent_default()
            self.query_one(TerminalInput).put(self.history.next())

    def clear(self) -> None:
        self.container.remove_children()
        self.container.mount(TerminalInput())


if __name__ == "__main__":
    from rich.console import Console
    from textual.app import App
    from textual.widgets import Footer

    cli = False

    if cli:
        console = Console()
        loop = asyncio.new_event_loop()
        parser = Parser(cli=cli, event_loop=loop)
        while True:
            try:
                console.print(parser.parse_and_run(input().split(), console=True))
            except Exception as exc:  # noqa: PERF203
                pprint(exc)
    else:

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TerminalPage()
                yield Footer()

        app = TestApp()
        app.run()
