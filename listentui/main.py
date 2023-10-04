import logging
import os
import time
from argparse import ArgumentError, ArgumentParser, Namespace
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import wraps
from math import ceil
from os import _exit  # pyright: ignore
from threading import Thread
from types import TracebackType
from typing import Any, Callable, NewType, Optional, Self, Type, Union

from graphql import Source
from psutil import pid_exists
from readchar import key, readkey
from rich.align import Align
from rich.console import (Console, ConsoleOptions, ConsoleRenderable, Group,
                          RenderableType, RenderResult)
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.pretty import pretty_repr
from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                           SpinnerColumn, Task, TextColumn)
from rich.spinner import Spinner
from rich.style import Style
from rich.table import Table
from rich.text import Text

from .config import Config
from .listen.client import Listen
from .listen.stream import StreamPlayerMPV
from .listen.types import (Album, Artist, Character, Event, ListenWsData,
                           MPVData, Requester, Song, User)
from .listen.websocket import ListenWebsocket
from .modules.baseModule import BaseModule
from .modules.presence import DiscordRichPresence

PRIMARY_COLOR = '#f92672'
QueryType = Union[Album, Artist, Song, User, Character, Source]
CommandID = NewType("commandID", int)


def threaded(func: Callable[..., Any]) -> Any:
    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        Thread(target=func, args=(self, *args,), kwargs=kwargs).start()
    return wrapper


def terminal_command(func: Callable[..., Any]) -> Any:
    @wraps(func)
    def wrapper(self: "TerminalPanel", command: str, args: Namespace) -> Any:
        Thread(target=func, args=(self, command, args,), name="terminal command").start()
    return wrapper


@dataclass
class CommandGroup:
    command: str
    output: RenderableType = field(default_factory=Text)


class TerminalCommandHistoryHandler:

    def __init__(self):
        self._data: dict[CommandID, CommandGroup] = {}
        self._command_id_count = 0

    @property
    def history_count(self):
        return len(self._data)

    def add(self, command: str, output: Optional[RenderableType] = None) -> CommandID:
        command_id = CommandID(self._command_id_count)
        if output:
            self._data[command_id] = CommandGroup(command, output)
        else:
            self._data[command_id] = CommandGroup(command)
        self._command_id_count += 1
        return command_id

    def update(self, id: CommandID, result: RenderableType) -> None:
        self._data[id].output = result

    def render(self) -> Group:
        render_objects: list[RenderableType] = []
        for group in self._data.values():
            table = Table.grid()
            prompt = Text()
            prompt.append("> ", style=PRIMARY_COLOR)
            prompt.append(group.command)
            table.add_row(prompt)
            table.add_row(group.output)
            render_objects.append(table)

        return Group(*render_objects)

    def clear(self) -> None:
        self._data.clear()


class TerminalPanel(ConsoleRenderable):
    def __init__(self, main: "Main") -> None:
        self._log = logging.getLogger(__name__)
        self.main = main
        self.buffer: list[str] = []
        self.renderable = None
        self.panel = None
        self.parser, self.subparser = self.build_parser()
        self.height: int = 0
        self.scroll_offset: int = 0
        self.max_scroll_height: int = 0
        self.history = TerminalCommandHistoryHandler()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        self.height = options.max_height
        console = Console(width=width - 4, height=self.height - 2)
        with console.capture() as capture:
            console.print(self.render())
        render_list = capture.get().split('\n')
        self.max_scroll_height = len(render_list) - 2
        to_render = render_list[self.scroll_offset:]
        text = Text.from_ansi("\n".join(to_render), end="", no_wrap=True)
        yield Panel(text, height=self.height, title="Terminal")

    def __call__(self, panel: Layout) -> Self:
        self.panel = panel
        self.renderable = panel.renderable
        panel.update(self)
        return self

    def __enter__(self):
        pass

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc_value: Optional[BaseException],
                 trace: Optional[TracebackType]):
        self.buffer.clear()
        if self.panel and self.renderable:
            self.panel.update(self.renderable)

    def render(self) -> Table:
        table = Table.grid()
        if self.history.history_count != 0:
            table.add_row(self.history.render())
        field = Text()
        field.append("> ", style=PRIMARY_COLOR)
        field.append(f'{"".join(self.buffer)}|')
        table.add_row(field)
        return table

    def build_parser(self):
        parser = ArgumentParser(prog="", exit_on_error=False, add_help=False)
        subparser = parser.add_subparsers()

        # help
        help = subparser.add_parser('help',
                                    help="Print help for given command",
                                    add_help=False, exit_on_error=False)
        help.add_argument('cmd', nargs="?",
                          help="A command",
                          metavar="commmand", type=str)
        help.set_defaults(func=self.help)

        # clear
        clear = subparser.add_parser('clear',
                                     help="Clear the console output",
                                     add_help=False, exit_on_error=False)
        clear.set_defaults(func=self.clear)

        # reset
        reset = subparser.add_parser('reset',
                                     help="Reset console history, usefull when theres too much lag",
                                     add_help=False, exit_on_error=False)
        reset.set_defaults(func=self.reset)

        # eval
        eval = subparser.add_parser('eval',
                                    help="Evaluate a python expression",
                                    add_help=False, exit_on_error=False)
        eval.add_argument('expr', nargs="+",
                          help="A python expression",
                          metavar="expression")
        eval.set_defaults(func=self.eval)

        # search
        search = subparser.add_parser('search',
                                      help="Search for a song",
                                      add_help=False, exit_on_error=False)
        search.add_argument('term', nargs="+",
                            help="What to search for",
                            type=str)
        search.add_argument('-c', '--count',
                            help="The amount of result to return (default: 10)",
                            dest='count',
                            metavar="int", type=int)
        search.add_argument('-f', '--favorite-only',
                            dest='favorite',
                            help="Search favorite only",
                            action="store_true")
        search.set_defaults(func=self.search)

        # history
        history = subparser.add_parser('history',
                                       help="Show previously played history",
                                       add_help=False, exit_on_error=False)
        history.add_argument('-c', '--count',
                             help="The amount of result to return (default: 10)",
                             dest='count',
                             metavar="int", type=int)
        history.set_defaults(func=self.query_history)

        # album
        album = subparser.add_parser('album',
                                     help="Fetch info on an album",
                                     add_help=False, exit_on_error=False)
        album.add_argument("id", nargs="?",
                           help="(optional), default to current song album",
                           metavar="AlbumID", type=int)
        album.set_defaults(func=self.album)

        # artist
        artist = subparser.add_parser('artist',
                                      help="Fetch info on an artist",
                                      add_help=False, exit_on_error=False)
        artist.add_argument("id", nargs="?",
                            help="(optional), default to current song first artist",
                            metavar="AlbumID", type=int)
        artist.set_defaults(func=self.artist)

        # song
        song = subparser.add_parser('song',
                                    help="Fetch info on a song",
                                    add_help=False, exit_on_error=False)
        song.add_argument("id", nargs="?",
                          help="(optional), default to current song album",
                          metavar="SongID", type=int)
        song.set_defaults(func=self.song)

        # pv
        pv = subparser.add_parser('preview',
                                  aliases=['pv'],
                                  help="Preview a portion of the song audio",
                                  add_help=False, exit_on_error=False)
        pv.add_argument("id",
                        help="The id of the song",
                        metavar="SongID", type=int)
        pv.set_defaults(func=self.preview)

        # user
        user = subparser.add_parser('user',
                                    help="Fetch info on an user",
                                    add_help=False, exit_on_error=False)
        user.add_argument('Username',
                          help="the username of the user",
                          metavar="Username", type=str)
        user.set_defaults(func=self.user)

        # character
        character = subparser.add_parser('character',
                                         help="Fetch info on a character",
                                         add_help=False, exit_on_error=False)
        character.add_argument("id", nargs="?",
                               help="(optional), default to current song first character",
                               metavar="CharacterID", type=int)
        character.set_defaults(func=self.character)

        # source
        source = subparser.add_parser('source',
                                      help="Fetch info on a source",
                                      add_help=False, exit_on_error=False)
        source.add_argument("id", nargs="?",
                            help="(optional), default to current song source",
                            metavar="SourceID", type=int)
        source.set_defaults(func=self.source)

        # download
        download = subparser.add_parser('download',
                                        help="Download a song",
                                        add_help=False, exit_on_error=False)
        download.add_argument("id", nargs="?",
                              help="(optional), default to current playing song",
                              metavar="songID", type=int)
        download.set_defaults(func=self.download)

        if self.main.logged_in:
            # check favorite
            check_f = subparser.add_parser('check_favorite',
                                           aliases=['cf', 'check'],
                                           help="check if the song has been favorited",
                                           add_help=False, exit_on_error=False)
            check_f.add_argument("id", nargs="?",
                                 help="(optional), default to current song",
                                 metavar="SongID", type=int)
            check_f.set_defaults(func=self.check_favorite)

            # favorite
            fav = subparser.add_parser('favorite',
                                       aliases=['f'],
                                       help="Favorite a song",
                                       add_help=False, exit_on_error=False)
            fav.add_argument("id", nargs="?",
                             help="(optional), default to current song",
                             metavar="SongID", type=int)
            fav.set_defaults(func=self.favorite)
        return (parser, subparser)

    def ensure_cursor(self) -> None:
        lower_bound = self.max_scroll_height - self.height - 2
        if self.scroll_offset < lower_bound + 6:
            self.scroll_offset = lower_bound + 5

    def read(self, k: str) -> None:
        if k == key.ENTER:
            self.execute_buffer()
            return
        if k == key.BACKSPACE:
            if len(self.buffer) == 0:
                return
            self.buffer.pop()
            self.ensure_cursor()
            return
        if k == key.UP:
            if self.scroll_offset != 0:
                self.scroll_offset -= 1
            return
        if k == key.DOWN:
            if self.scroll_offset != self.max_scroll_height:
                self.scroll_offset += 1
            return
        if k in (key.LEFT, key.RIGHT):
            return
        self.ensure_cursor()
        self.buffer.append(k)

    def execute_buffer(self) -> None:
        command = "".join(self.buffer)
        # https://github.com/python/cpython/issues/103498
        the_annoying_bunch = ('eval', 'preview', 'pv', 'user', 'search')
        if command.startswith(the_annoying_bunch):
            args = command.split()
            if args[0] not in the_annoying_bunch:
                self.history.add(command, self.tablelate(f"Unknown command: {command}"))
                self.buffer.clear()
                return
            if len(args) == 1:
                self.history.add(command, self.tablelate(f"Requires an argument, run 'help {args[0]}' for more info"))
                self.buffer.clear()
                return
        try:
            if len(self.buffer) == 0:
                return
            args, others = self.parser.parse_known_args(command.split())
            if len(others) > 0:
                self.history.add(command, self.tablelate(f"Unknown argument: {' '.join(others)}"))
                self.buffer.clear()
                return
            self.buffer.clear()
            args.func(command, args)
        except ArgumentError as e:
            self.history.add(command, self.tablelate(e.message))
            self.buffer.clear()

    def tablelate(self, data: Union[list[Any], str, int, QueryType, RenderableType]) -> Table:
        table = Table.grid()
        if isinstance(data, str):
            if '\n' in data:
                for line in data.split('\n'):
                    table.add_row(line)
            else:
                table.add_row(data)
        elif isinstance(data, int):
            table.add_row(str(data))
        elif isinstance(data, list):
            for elem in data:
                table.add_row(self.tablelate(elem))
        elif isinstance(data, QueryType):
            return data  # type: ignore
        else:
            table.add_row(data)
        return table

    def help(self, command: str, args: Namespace):
        if not args.cmd:
            self.history.add(command, self.tablelate(self.parser.format_help()))
        else:
            subcmd = self.subparser.choices.get(args.cmd)
            if not subcmd:
                self.history.add(f"{command}", self.tablelate(f"{args.cmd} is not a valid command"))
            else:
                self.history.add(f"{command}", self.tablelate(subcmd.format_help()))

    def clear(self, _: str, __: Namespace):
        self.scroll_offset = self.max_scroll_height

    def reset(self, _: str, __: Namespace):
        self.history.clear()
        self.scroll_offset = 0

    def eval(self, command: str, args: Namespace):
        cmd = args.expr
        try:
            res = pretty_repr(eval(" ".join(cmd)))
        except Exception as e:
            res = pretty_repr(e)
        self.history.add(f"{command}", self.tablelate(res))

    @terminal_command
    def album(self, command: str, args: Namespace):
        if args.id:
            album_id = args.id
        else:
            if self.main.current_song.album:
                album_id = self.main.current_song.album.id
            else:
                self.history.add(command, self.tablelate("Current song have no album"))
                return
        command_id = self.history.add(command, Spinner('dots', "querying album...", style=PRIMARY_COLOR))
        res = self.main.listen.album(album_id)
        if not res:
            self.history.update(command_id, self.tablelate("No album found"))
        else:
            self.history.update(command_id, self.tablelate(res))

    @terminal_command
    def artist(self, command: str, args: Namespace):
        if args.id:
            artist_id = args.id
        else:
            if self.main.current_song.artists:
                artist_id = self.main.current_song.artists[0].id
            else:
                self.history.add(command, self.tablelate("Current song have no artist"))
                return
        command_id = self.history.add(command, Spinner('dots', "querying artist...", style=PRIMARY_COLOR))
        res = self.main.listen.artist(artist_id)
        if not res:
            self.history.update(command_id, self.tablelate("No artist found"))
        else:
            self.history.update(command_id, self.tablelate(res))

    @terminal_command
    def song(self, command: str, args: Namespace):
        if args.id:
            song_id = args.id
        else:
            song_id = self.main.current_song.id
        command_id = self.history.add(command, Spinner('dots', "querying song...", style=PRIMARY_COLOR))
        res = self.main.listen.song(song_id)
        if not res:
            self.history.update(command_id, self.tablelate("No song found"))
        else:
            self.history.update(command_id, self.tablelate(res))

    @terminal_command
    def preview(self, command: str, args: Namespace):
        song_id = args.id
        command_id = self.history.add(command, Spinner('dots', "fetching song...", style=PRIMARY_COLOR))
        res = self.main.listen.song(song_id)
        if not res:
            self.history.update(command_id, self.tablelate("No song found"))
        else:
            def progress():
                romaji_first = self.main.config.display.romaji_first
                if res:
                    if romaji_first:
                        title = res.title_romaji or res.title
                    else:
                        title = res.title
                else:
                    title = None
                progress = Progress(SpinnerColumn(),
                                    TextColumn("{task.description}"),
                                    BarColumn(),
                                    MofNTimeCompleteColumn())
                task = progress.add_task(f"Playing {title}", total=15)
                self.history.update(command_id, self.tablelate(progress))
                time.sleep(1)
                while not progress.finished:
                    progress.advance(task)
                    time.sleep(1)

            def error():
                self.history.update(command_id, self.tablelate("Unable to play snipplet :("))
                return

            if res.snippet:
                self.main.player.preview(res.snippet, on_play=progress, on_error=error)
            else:
                self.history.update(command_id, self.tablelate("Song have no playable snippet"))

    @terminal_command
    def user(self, command: str, args: Namespace):
        username = args.username
        command_id = self.history.add(command, Spinner('dots', "querying user...", style=PRIMARY_COLOR))
        res = self.main.listen.user(username)
        if not res:
            self.history.update(command_id, self.tablelate("No user found"))
        else:
            self.history.update(command_id, self.tablelate(res))

    @terminal_command
    def character(self, command: str, args: Namespace):
        if args.id:
            character_id = args.id
        else:
            if self.main.current_song.characters:
                character_id = self.main.current_song.characters[0].id
            else:
                self.history.add(command, self.tablelate("Current song have no characters"))
                return
        command_id = self.history.add(command, Spinner('dots', "querying character...", style=PRIMARY_COLOR))
        res = self.main.listen.character(character_id)
        if not res:
            self.history.update(command_id, self.tablelate("No character found"))
        else:
            self.history.update(command_id, self.tablelate(res))

    @terminal_command
    def source(self, command: str, args: Namespace):
        if args.id:
            source_id = args.id
        else:
            if self.main.current_song.source:
                source_id = self.main.current_song.source.id
            else:
                self.history.add(command, self.tablelate("Current song have no source"))
                return
        command_id = self.history.add(command, Spinner('dots', "querying source...", style=PRIMARY_COLOR))
        res = self.main.listen.source(source_id)
        if not res:
            self.history.update(command_id, self.tablelate("No source found"))
        else:
            self.history.update(command_id, self.tablelate(res))

    @terminal_command
    def check_favorite(self, command: str, args: Namespace):
        if args.id:
            song_id = args.id
        else:
            song_id = self.main.current_song.id
            status = self.main.current_song.is_favorited
            self.history.add(command, self.tablelate(f"song {song_id}: {status}"))
            return
        command_id = self.history.add(command, Spinner('dots', "checking favorite...", style=PRIMARY_COLOR))
        res = self.main.listen.check_favorite(song_id)
        if not res:
            self.history.update(command_id, self.tablelate("No song found"))
        else:
            self.history.update(command_id, self.tablelate(f"song {song_id}: {res}"))

    @terminal_command
    def favorite(self, command: str, args: Namespace):
        romaji_first = self.main.config.display.romaji_first
        sep = self.main.config.display.separator

        if args.id:
            song_id = args.id
        else:
            self.main.favorite_song()
            status = self.main.current_song.is_favorited
            song_id = self.main.current_song.id
            if romaji_first:
                title = self.main.current_song.title_romaji or self.main.current_song.title
            else:
                title = self.main.current_song.title
            artist = self.main.current_song.format_artists(1, show_character=False, romaji_first=romaji_first, sep=sep)
            if status:
                self.history.add(command, self.tablelate(f"Favoriting {title} by {artist}"))
            else:
                self.history.add(command, self.tablelate(f"Unfavoriting {title} by {artist}"))
            return

        command_id = self.history.add(command, Spinner('dots', "favoriting song...", style=PRIMARY_COLOR))
        song = self.main.listen.song(song_id)
        if not song:
            self.history.update(command_id, self.tablelate("No song found"))
        else:
            if romaji_first:
                title = song.title_romaji or song.title
            else:
                title = song.title
            artist = song.format_artists(1, show_character=False, romaji_first=romaji_first, sep=sep)
            status = self.main.listen.check_favorite(song_id)
            if not status:
                self.history.update(command_id, self.tablelate(f"Favoriting {title} by {artist}"))
            else:
                self.history.update(command_id, self.tablelate(f"Unfavoriting {title} by {artist}"))
            Thread(target=self.main.listen.favorite_song, args=(song_id, )).start()
            self.main.user_panel.update()

    @terminal_command
    def search(self, command: str, args: Namespace):
        term = " ".join(args.term)
        count = args.count or 10
        favorite_only = args.favorite
        romaji_first = self.main.config.display.romaji_first
        sep = self.main.config.display.separator
        table = Table(expand=False)
        table.add_column("id", ratio=2)
        table.add_column("song", ratio=6)
        table.add_column("artist", ratio=2)

        command_id = self.history.add(command, Spinner('dots', "searching songs...", style=PRIMARY_COLOR))
        res = self.main.listen.search(term, count, favorite_only)

        if len(res) == 0:
            self.history.update(command_id, self.tablelate("Nothing to show :("))
            return

        for song in res:
            if romaji_first:
                title = song.title_romaji or song.title
            else:
                title = song.title
            song_title = Text()
            if favorite_only:
                song_title.append(" ", Style(color=PRIMARY_COLOR, bold=True))
            song_title.append(f"{title}")
            table.add_row(f"{song.id}",
                          song_title,
                          f"{song.format_artists(1, False, romaji_first, sep)}")

        self.history.update(command_id, self.tablelate(table))

    @terminal_command
    def query_history(self, command: str, args: Namespace):
        count = args.count or 10
        romaji_first = self.main.config.display.romaji_first
        sep = self.main.config.display.separator
        table = Table(expand=False)
        table.add_column("id", ratio=2)
        table.add_column("song", ratio=4)
        table.add_column("artist", ratio=2)
        table.add_column("played at", ratio=2)

        command_id = self.history.add(command, Spinner('dots', "fetching songs history...", style=PRIMARY_COLOR))
        res = self.main.listen.play_statistic(count)

        for statistic in res:
            song = statistic.song
            if romaji_first:
                title = song.title_romaji or song.title
            else:
                title = song.title
            table.add_row(f"{song.id}",
                          f"{title}",
                          f"{song.format_artists(1, False, romaji_first, sep)}",
                          f"{statistic.created_at.strftime('%d/%m/%Y, %H:%M:%S')}")

        self.history.update(command_id, self.tablelate(table))

    @terminal_command
    def download(self, command: str, args: Namespace):
        t = Table.grid()
        e = Progress()
        t.add_row(e)
        k = e.add_task('testing', total=100)
        self.history.add(command, t)
        while not e.finished:
            e.advance(k)
            time.sleep(0.2)


class PreviousSongPanel(ConsoleRenderable):
    def __init__(self):
        self.romaji_first = Config.get_config().display.romaji_first
        self.separator = Config.get_config().display.separator
        self.songs_table: list[Table] = []
        self.update_counter = 0

    def __rich_console__(self, _: Console, options: ConsoleOptions) -> RenderResult:
        height = options.max_height

        render_group: list[Table] = []
        total_height = height - 2
        current_height = 0
        total_rendered = 0
        for song in self.songs_table:
            current_height += song.row_count + 3
            if current_height > total_height:
                break
            render_group.append(song)
            total_rendered += 1

        yield Panel(
            Group(*render_group),
            title='Previous Songs',
            height=height,
            # subtitle=f'{current_height}/{total_height}={total_rendered}'
        )

    def add(self, song: Song) -> None:
        self.songs_table.insert(0, self.create_song_table(song))
        if len(self.songs_table) > 5:
            self.songs_table.pop()

    def create_song_table(self, song: Song) -> Table:
        table = Table(expand=True, show_header=False)
        table.add_column(ratio=2)
        table.add_column(ratio=8)
        title = Text()
        if song.is_favorited:
            title.append(" ", Style(color=PRIMARY_COLOR, bold=True))
        title.append(song.title or '')
        table.add_row("Title", title)
        if song.artists:
            table.add_row("Artists", song.format_artists(romaji_first=self.romaji_first, sep=self.separator))
        if song.source:
            table.add_row("Source", song.format_source(self.romaji_first))
        if song.album:
            table.add_row("Album", song.format_album(self.romaji_first))
        table.caption = Text(f"ID: {song.id}", justify='right')
        return table


class UserPanel(ConsoleRenderable):
    def __init__(self, listen: Listen) -> None:
        self.romaji_first = Config.get_config().display.romaji_first
        self.sep = Config.get_config().display.separator
        self.listen = listen
        self.user = listen.current_user

    def __rich_console__(self, _: Console, options: ConsoleOptions) -> RenderResult:
        if not self.user:
            return
        width = options.max_width
        height = options.max_height
        layout = Layout(size=4)

        table = Table(expand=True, box=None, padding=(1, 0, 0, 0))
        if width > 36:
            table.add_column("Requested", justify='center')
            table.add_column("Favorited", justify='center')
            table.add_column("Uploaded", justify='center')
        else:
            table.add_column("Reqs", justify='center')
            table.add_column("Favs", justify='center')
            table.add_column("Upls", justify='center')
        table.add_row(
            Text(f'{self.user.requests}', justify='center'),
            Text(f'{self.user.favorites}', justify='center'),
            Text(f'{self.user.uploads}', justify='center')
        )

        total_height = height - 8
        current_height = 0
        total_rendered = 0
        feed_table = Table(expand=True, box=None, padding=(0, 0, 1, 0))
        for feed in self.user.feed:
            feed_text = Text(overflow='fold')
            feed_text.append('Favorited ')
            feed_text.append(f'{feed.song.title} ')
            feed_text.append('by ', style=PRIMARY_COLOR)
            artist = feed.song.format_artists(1, show_character=False, romaji_first=self.romaji_first, sep=self.sep)
            feed_text.append(f'{artist}')
            current_height += ceil(feed_text.cell_len / width) + 1
            if current_height > total_height:
                break
            feed_table.add_row(feed_text)
            total_rendered += 1

        layout.split_column(
            Layout(table, name='table', size=4),
            Layout(feed_table, name='feed_table')
        )
        yield Panel(
            layout,
            title=self.user.display_name,
            height=height,
            # subtitle=f'{current_height}/{total_height}={total_rendered}'
        )

    @threaded
    def update(self) -> None:
        self.user = self.listen.update_current_user()


class InfoPanel(ConsoleRenderable):
    def __init__(self, player: StreamPlayerMPV, websocket: ListenWebsocket) -> None:
        self.romaji_first = Config.get_config().display.romaji_first
        self.separator = Config.get_config().display.separator
        self.duration_progress = Progress(BarColumn(bar_width=None), MofNTimeCompleteColumn())
        self.duration_task = self.duration_progress.add_task('Duration', total=None)
        self.ws = websocket
        self.player = player
        self.player.on_data_update(self.calc_delay)
        self.ws_data: Optional[ListenWsData] = None
        self.current_song: Table
        self.start_time = time.time()
        self.song_delay = 0
        self.layout = Layout()
        self.layout.split_row(
            Layout(name='main_table', minimum_size=14, ratio=8),
            Layout(name='other_info', minimum_size=4, ratio=2)
        )
        self.panel_color = "none"
        self.panel_title = None
        pass

    def __rich_console__(self, _: Console, options: ConsoleOptions) -> RenderResult:
        if not self.current_song or not self.ws_data:
            yield Panel(self.layout)
            return
        if self.ws_data.song.duration:
            completed = (datetime.now(timezone.utc) - self.ws_data.start_time).total_seconds()
        else:
            completed = round(time.time() - self.ws_data.song.time_end)
        total = self.ws_data.song.duration if self.ws_data.song.duration != 0 else 0
        self.duration_progress.update(self.duration_task, completed=completed, total=total)

        self.layout['other_info'].update(self.create_info_table())
        yield Panel(self.layout, height=options.height, title=self.panel_title, border_style=self.panel_color)

    def update(self, data: ListenWsData) -> None:
        self.ws_data = data
        self.current_song = self.create_song_table(data.song)
        self.layout['main_table'].update(self.current_song)
        if data.event:
            self.update_panel(data.event)
        elif data.requester:
            self.update_panel(data.requester)
        else:
            self.reset_panel()
        if self.player.data:
            self.calc_delay(self.player.data)

    def update_panel(self, data: Union[Event, Requester]):
        if isinstance(data, Event):
            self.panel_title = f"♫♪.ılılıll {data.name} llılılı.♫♪"
        else:
            self.panel_title = f"Requested by {data.display_name}"
        self.panel_color = PRIMARY_COLOR

    def reset_panel(self):
        self.panel_title = None
        self.panel_color = "none"

    def update_song(self, song: Song) -> None:
        self.current_song = self.create_song_table(song)
        self.layout['main_table'].update(self.current_song)

    def create_song_table(self, song: Song) -> Table:
        table = Table(expand=True, show_header=False)
        table.add_column(ratio=2)
        table.add_column(ratio=8)
        title = Text()
        if song.is_favorited:
            title.append(" ", Style(color=PRIMARY_COLOR, bold=True))
        title.append(song.title or '')

        table.add_row("Title", title)
        if song.artists:
            table.add_row("Artists", song.format_artists(romaji_first=self.romaji_first, sep=self.separator))
        if song.source:
            table.add_row("Source", song.format_source(self.romaji_first))
        if song.album:
            table.add_row("Album", song.format_album(self.romaji_first))
        table.add_row("Duration", self.duration_progress)
        return table

    def create_info_table(self) -> Table:
        table = Table(expand=True, show_header=False)

        table.add_column()
        if self.player.volume > 60:
            vol_icon = '󰕾 '
        elif self.player.volume > 30:
            vol_icon = '󰖀 '
        elif self.player.volume > 0:
            vol_icon = '󰕿 '
        elif self.player.volume == 0:
            vol_icon = '󰝟 '
        else:
            vol_icon = '󰖁 '

        if self.player.cache:
            cache_duration = self.player.cache.cache_duration
            cache_size = self.player.cache.fw_byte
        else:
            cache_duration = -1
            cache_size = 0

        table.add_row(f"{'󰏤 ' if self.player.paused else '󰐊 '} {'Paused' if self.player.paused else 'Playing'}")
        table.add_row(f"{vol_icon} {self.player.volume}")
        table.add_row(f"  {cache_duration:.2f}s/{cache_size/1000:.0f}KB")
        table.add_row(f"󰦒  {self.song_delay}s",)

        table.add_section()
        last_time = round(time.time() - self.ws.last_heartbeat)
        heartbeat_status = "Alive" if last_time < 40 else f"Dead ({last_time})"
        table.add_row(f"  {heartbeat_status}")
        table.add_row(f"󰥔  {timedelta(seconds=round(time.time() - self.start_time))}")

        return table

    def calc_delay(self, _: MPVData) -> None:
        if not self.ws_data or not self.player.data:
            return
        audio_start = self.player.data.start
        audio_song = self.player.data.title
        ws_start = self.ws_data.start_time
        ws_song = self.ws_data.song.title

        if ws_song and audio_song:
            if ws_song not in audio_song:
                self.song_delay = '???'
                return
        else:
            self.song_delay = '???'
            return

        diff = audio_start - ws_start
        self.song_delay = f'{diff.total_seconds():.2f}'


class HeadingPanel(ConsoleRenderable):
    def __init__(self) -> None:
        self.listener = 0
        pass

    def __rich_console__(self, _: Console, __: ConsoleOptions) -> RenderResult:
        yield Panel(Text(f'Listen.Moe (󰋋 {self.listener})', justify='center'))

    def update(self, listener: int) -> None:
        self.listener = listener


class MofNTimeCompleteColumn(MofNCompleteColumn):
    def render(self, task: "Task") -> Text:
        """Show 00:01/04:28"""
        m, s = divmod(int(task.completed), 60)
        completed = f'{m:02d}:{s:02d}'
        total = int(task.total) if task.total is not None else None
        if isinstance(task.total, int) and task.total != 0:
            m, s = divmod(task.total, 60)
            total = f'{m:02d}:{s:02d}'
            return Text(
                f"{completed}{self.separator}{total}",
                style="white",
            )
        else:
            return Text(
                f"{completed}{self.separator}?",
                style="white",
            )


class Main:

    def __init__(self, debug: bool = False, bypass: bool = False) -> None:
        self.debug = debug
        self.config = Config.get_config()
        if bypass:
            self.free_instance_lock()
        if self.config.system.instance_lock:
            self.check_instance_lock()
        self.log = logging.getLogger(__name__)
        self.running_modules: list[BaseModule] = []
        self.start_time: float = time.time()
        self.logged_in: bool = False
        self.update_counter = 0

        self.ws: ListenWebsocket
        self.player: StreamPlayerMPV
        self.data: ListenWsData
        self.rpc: Optional[DiscordRichPresence] = None

        self.console = Console()
        self.current_song: Song
        self.duration_progress = Progress(BarColumn(bar_width=None), MofNTimeCompleteColumn())
        self.duration_task = self.duration_progress.add_task('Duration', total=None)
        self.layout = self.make_layout()

    def input_handler(self) -> None:
        keybind = self.config.keybind
        player = self.player
        while True:
            try:
                match readkey():
                    case keybind.lower_volume:
                        player.lower_volume(self.config.player.volume_step)
                    case keybind.raise_volume:
                        player.raise_volume(self.config.player.volume_step)
                    case keybind.lower_volume_fine:
                        player.lower_volume(1)
                    case keybind.raise_volume_fine:
                        player.raise_volume(1)
                    case keybind.favourite_song:
                        self.favorite_song()
                    case keybind.restart_player:
                        player.restart()
                    case keybind.play_pause:
                        player.play_pause()
                    case keybind.open_terminal:
                        k = ''
                        term = self.terminal_panel
                        box = self.layout['box']
                        with term(box):
                            while k != key.ESC:
                                k = readkey()
                                term.read(k)
                    case _:
                        pass
            except KeyboardInterrupt:
                if self.config.system.instance_lock:
                    self.free_instance_lock()
                _exit(1)

    def setup(self) -> None:
        self.ws = ListenWebsocket()
        self.running_modules.append(self.ws)
        self.ws.on_data_update(self.update)

        self.player = StreamPlayerMPV()
        self.running_modules.append(self.player)

        # optional
        if self.config.rpc.enable:
            self.rpc = DiscordRichPresence()
            self.ws.on_data_update(self.rpc.update)
            self.running_modules.append(self.rpc)

        self.heading_panel = HeadingPanel()
        self.info_panel = InfoPanel(self.player, self.ws)
        self.previous_panel = PreviousSongPanel()
        self.user_panel = UserPanel(self.listen)
        self.terminal_panel = TerminalPanel(self)

        for modules in self.running_modules:
            modules.start()

    def make_layout(self) -> Layout:
        layout = Layout(name='root')
        layout.split_column(
            Layout(name="heading", size=3),
            Layout(name='main', size=12),
            Layout(name='other', minimum_size=2)
        )
        layout['other'].split_row(
            Layout(Panel(Text('')), name='box', ratio=8),
            Layout(name='user', ratio=2, visible=False)
        )
        return layout

    def check_instance_lock(self) -> None:
        instance_lock = Config.get_config().config_root.joinpath('_instance.lock')
        if instance_lock.is_file():
            with open(instance_lock, 'r') as lock:
                pid = lock.readline().rstrip()
            if pid_exists(int(pid)):
                console = Console()
                height = round(console.options.max_height * 0.60)
                width = round(console.options.max_width * 0.60)
                warning = Align(Text("Another Instance of Listen.tui is Currently Running"),
                                vertical='middle', align='center')
                info = Align(Text("If this isn't the case, please run with '--bypass' once"), align='center')
                mini_terminal = Layout()
                mini_terminal.split_column(
                    Layout(Panel(Text()), ratio=2),
                    Layout(Align(Text(f"pid: {pid}"), vertical='middle', align='center'), ratio=8)
                )
                terminal = Align(Group(Panel(mini_terminal, height=height, style='white'), info),
                                 width=width, height=height, vertical='middle', align='center')
                layout = Layout()
                layout.split_column(
                    Layout(warning, ratio=2),
                    Layout(terminal, ratio=8),
                )
                finale = Panel(layout, style='red', height=console.height)
                with Live(finale, screen=True):
                    input()
                raise Exception("Another instance is running")

        with open(instance_lock, 'w') as lock:
            lock.write(f'{os.getpid()}')

    def free_instance_lock(self) -> None:
        instance_lock = Config.get_config().config_root.joinpath('_instance.lock')
        if instance_lock.is_file():
            os.remove(instance_lock)

    def favorite_song(self) -> None:
        if not self.logged_in:
            return
        self.current_song.is_favorited = not self.current_song.is_favorited
        Thread(target=self.listen.favorite_song, args=(self.current_song.id, )).start()
        self.info_panel.update_song(self.current_song)
        self.user_panel.update()

    def update(self, data: ListenWsData) -> None:
        # header
        self.heading_panel.update(data.listener)

        # previous song
        if self.update_counter == 0:
            for song in data.last_played:
                self.previous_panel.add(song)
        else:
            self.previous_panel.add(self.current_song)

        # current song table
        self.current_song = data.song
        self.info_panel.update(data)
        if self.logged_in:
            self.current_song.is_favorited = self.listen.check_favorite(data.song.id)
        if self.current_song.is_favorited:
            self.info_panel.update_song(self.current_song)

        self.update_counter += 1

    def login(self):
        username = self.config.system.username
        password = self.config.system.password
        token = self.config.persist.token

        with self.console.status("Logging in...", spinner='dots'):
            if not username and not password:
                self.listen = Listen()
            else:
                if not token:
                    self.listen = Listen.login(username, password)
                else:
                    self.listen = Listen.login(username, password, token)
                self.logged_in = True
                if self.listen.current_user:
                    self.config.update('persist', 'token', self.listen.current_user.token)

    def run(self):
        self.login()
        self.setup()
        Thread(target=self.input_handler).start()

        def init() -> Table:
            table = Table(expand=False)
            table.add_column("Module")
            table.add_column("Status")
            table.add_column("Reason")
            for i in self.running_modules:
                table.add_row(i.name, f'{i.status.running}', i.status.reason)
            return table

        refresh_per_second = 30
        screen = not self.debug
        with Live(init(), refresh_per_second=refresh_per_second, screen=screen) as self.live:
            while not all([i.status.running for i in self.running_modules]):
                self.live.update(init())
            self.live.update(self.layout)

            self.layout['heading'].update(self.heading_panel)
            self.layout['main'].update(self.info_panel)
            self.layout['box'].update(self.previous_panel)

            if self.listen.current_user:
                self.layout['user'].visible = True
                self.layout['user'].update(self.user_panel)

            while True:
                self.layout['main'].update(self.info_panel)
                time.sleep(1 / refresh_per_second)
