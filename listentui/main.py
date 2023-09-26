import logging
import os
import time
from argparse import ArgumentError, ArgumentParser, Namespace
from datetime import datetime, timedelta, timezone
from functools import wraps
from math import ceil
from os import _exit  # pyright: ignore
from pathlib import Path
from threading import Thread
from types import TracebackType
from typing import Any, Callable, Optional, Self, Type, Union

from graphql import Source
from psutil import pid_exists
from readchar import key, readkey
from rich.console import (Console, ConsoleOptions, ConsoleRenderable, Group,
                          RenderableType, RenderResult)
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.pretty import pretty_repr
from rich.progress import BarColumn, MofNCompleteColumn, Progress, Task
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

QueryType = Union[Album, Artist, Song, User, Character, Source]


def threaded(func: Callable[..., Any]) -> Any:
    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        Thread(target=func, args=(self, *args,), kwargs=kwargs).start()
    return wrapper


class TerminalPanel(ConsoleRenderable):
    def __init__(self, main: "Main") -> None:
        self.main = main
        self.buffer: list[str] = []
        self.renderable = None
        self.panel = None
        self.layout = Layout()
        self.layout.split_column(
            Layout(name='console'),
        )
        self.console_out: list[tuple[str, Table]] = []
        self.parser, self.subparser = self.build_parser()
        self.height: int = 0
        self.scroll_offset: int = 0
        self.max_scroll_height: int = 0

        pass

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        self.height = options.max_height
        console = Console(width=width - 4, height=self.height - 2)
        with console.capture() as capture:
            console.print(self.render_out())
        render_list = capture.get().split('\n')
        self.max_scroll_height = len(render_list) - 2
        to_render = render_list[self.scroll_offset:]
        self.layout['console'].update(Text.from_ansi("\n".join(to_render), end="", no_wrap=True))
        yield Panel(self.layout, height=self.height, title="Terminal")

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

    def build_parser(self):
        parser = ArgumentParser(prog="", exit_on_error=False, add_help=False)
        subparser = parser.add_subparsers()

        help = subparser.add_parser('help', help="Print help for given command", add_help=False)
        help.add_argument('cmd', nargs="?", help="A command", metavar="commmand", type=str)
        help.set_defaults(func=self.help)

        clear = subparser.add_parser('clear', help="Clear the console output", add_help=False)
        clear.set_defaults(func=self.clear)

        eval = subparser.add_parser('eval', help="Evaluate a python expression", add_help=False)
        eval.add_argument('expr', nargs="+", help="A python expression", metavar="expression")
        eval.set_defaults(func=self.eval)

        album = subparser.add_parser('album', help="Fetch info on an album", add_help=False)
        album.add_argument("id", nargs="?",
                           help="(optional), default to current song album",
                           metavar="AlbumID", type=int)
        album.set_defaults(func=self.album)

        artist = subparser.add_parser('artist', help="Fetch info on an artist", add_help=False)
        artist.add_argument("id", nargs="?",
                            help="(optional), default to current song first artist",
                            metavar="AlbumID", type=int)
        artist.set_defaults(func=self.artist)

        song = subparser.add_parser('song', help="Fetch info on a song", add_help=False)
        song.add_argument("id", nargs="?",
                          help="(optional), default to current song album",
                          metavar="SongID", type=int)
        song.set_defaults(func=self.song)

        user = subparser.add_parser('user', help="Fetch info on an user", add_help=False)
        user.add_argument('Username',
                          help="the username of the user",
                          metavar="Username", type=str)
        user.set_defaults(func=self.user)

        character = subparser.add_parser('character', help="Fetch info on a character", add_help=False)
        character.add_argument("id", nargs="?",
                               help="(optional), default to current song first character",
                               metavar="CharacterID", type=int)
        character.set_defaults(func=self.character)

        source = subparser.add_parser('source', help="Fetch info on a source", add_help=False)
        source.add_argument("id", nargs="?",
                            help="(optional), default to current song source",
                            metavar="SourceID", type=int)
        source.set_defaults(func=self.source)

        if self.main.logged_in:
            check_f = subparser.add_parser('check_favorite',
                                           help="check if the song has been favorited",
                                           add_help=False
                                           )
            check_f.add_argument("id", nargs="?",
                                 help="(optional), default to current song",
                                 metavar="SongID", type=int)
            check_f.set_defaults(func=self.check_favorite)

            fav = subparser.add_parser('favorite', help="Favorite a song", add_help=False)
            fav.add_argument("id", nargs="?",
                             help="(optional), default to current song",
                             metavar="SongID", type=int)
            fav.set_defaults(func=self.favorite)

        download = subparser.add_parser('download', help="Download a song", add_help=False)
        download.add_argument("id", nargs="?",
                              help="(optional), default to current playing song",
                              metavar="songID", type=int)
        download.set_defaults(func=self.download)
        return (parser, subparser)

    def ensure_cursor(self) -> None:
        lower_bound = self.max_scroll_height - self.height
        if self.scroll_offset < lower_bound:
            self.scroll_offset = lower_bound + 4

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
        try:
            if len(self.buffer) == 0:
                return
            args, others = self.parser.parse_known_args("".join(self.buffer).split())
            if len(others) > 0:
                self.console_out.append(("".join(self.buffer), self.tablelate(f"Invalid argument: {others[0]}")))
            args.func(args)
        except ArgumentError:
            self.console_out.append(("".join(self.buffer), self.tablelate(f"Unknown command: {''.join(self.buffer)}")))
        self.buffer.clear()

    def render_out(self) -> Table:
        table = Table.grid()
        for input, res in self.console_out:
            prompt = Text()
            prompt.append(">", style='#f92672')
            prompt.append(f" {input}")
            table.add_row(prompt)
            table.add_row(res)
        field = Text()
        field.append("> ", style='#f92672')
        field.append(f'{"".join(self.buffer)}|')
        table.add_row(field)
        return table

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

    def help(self, args: Namespace):
        if not args.cmd:
            self.console_out.append(("help", self.tablelate(self.parser.format_help())))
        else:
            subcmd = self.subparser.choices.get(args.cmd)
            if not subcmd:
                self.console_out.append((f"help {args.cmd}", self.tablelate(f"{args.cmd} is not a valid command")))
            else:
                self.console_out.append((f"help {args.cmd}", self.tablelate(subcmd.format_help())))

    def clear(self, _: Namespace):
        self.scroll_offset = self.max_scroll_height

    def eval(self, args: Namespace):
        cmd = args.expr
        try:
            res = eval("".join(cmd))
        except Exception as e:
            res = pretty_repr(e)
        self.console_out.append((f"eval {''.join(cmd)}", self.tablelate(res)))

    def album(self, args: Namespace):
        if args.id:
            album_id = args.id
        else:
            if self.main.current_song.album:
                album_id = self.main.current_song.album.id
            else:
                self.console_out.append(("album", self.tablelate("Current song have no album")))
                return
        res = self.main.listen.album(album_id)
        if not res:
            self.console_out.append((f"album {album_id}", self.tablelate("No album found")))
        else:
            self.console_out.append((f"album {album_id}", self.tablelate(res)))

    def artist(self, args: Namespace):
        if args.id:
            artist_id = args.id
        else:
            if self.main.current_song.artists:
                artist_id = self.main.current_song.artists[0].id
            else:
                self.console_out.append(("album", self.tablelate("Current song have no artist")))
                return
        res = self.main.listen.artist(artist_id)
        if not res:
            self.console_out.append((f"artist {artist_id}", self.tablelate("No artist found")))
        else:
            self.console_out.append((f"artist {artist_id}", self.tablelate(res)))

    def song(self, args: Namespace):
        if args.id:
            song_id = args.id
        else:
            song_id = self.main.current_song.id
        res = self.main.listen.song(song_id)
        if not res:
            self.console_out.append((f"song {song_id}", self.tablelate("No song found")))
        else:
            self.console_out.append((f"song {song_id}", self.tablelate(res)))

    def user(self, args: Namespace):
        username = args.username
        res = self.main.listen.user(username)
        if not res:
            self.console_out.append((f"user {username}", self.tablelate("No user found")))
        else:
            self.console_out.append((f"user {username}", self.tablelate(res)))

    def character(self, args: Namespace):
        if args.id:
            character_id = args.id
        else:
            if self.main.current_song.characters:
                character_id = self.main.current_song.characters[0].id
            else:
                self.console_out.append(("character", self.tablelate("Current song have no characters")))
                return
        res = self.main.listen.character(character_id)
        if not res:
            self.console_out.append((f"character {character_id}", self.tablelate("No character found")))
        else:
            self.console_out.append((f"character {character_id}", self.tablelate(res)))

    def source(self, args: Namespace):
        if args.id:
            source_id = args.id
        else:
            if self.main.current_song.source:
                source_id = self.main.current_song.source.id
            else:
                self.console_out.append(("character", self.tablelate("Current song have no source")))
                return
        res = self.main.listen.source(source_id)
        if not res:
            self.console_out.append((f"source {source_id}", self.tablelate("No source found")))
        else:
            self.console_out.append((f"source {source_id}", self.tablelate(res)))

    def check_favorite(self, args: Namespace):
        if args.id:
            song_id = args.id
        else:
            song_id = self.main.current_song.id
            status = self.main.current_song.is_favorited
            self.console_out.append(("check_favorite",
                                     self.tablelate(f"song {song_id}: {status}")))
            return
        res = self.main.listen.check_favorite(song_id)
        if not res:
            self.console_out.append((f"check_favorite {song_id}", self.tablelate("No song found")))
        else:
            self.console_out.append((f"check_favorite {song_id}", self.tablelate(f"song {song_id}: {res}")))

    def favorite(self, args: Namespace):
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
            artist = self.main.current_song.format_artists(0, romaji_first=romaji_first, sep=sep)
            if status:
                self.console_out.append((f"favorite {song_id}", self.tablelate(f"Favoriting {title} by {artist}")))
            else:
                self.console_out.append((f"favorite {song_id}", self.tablelate(f"Unfavoriting {title} by {artist}")))
            return

        song = self.main.listen.song(song_id)
        if not song:
            self.console_out.append((f"favorite {song_id}", self.tablelate("No song found")))
        else:
            if romaji_first:
                title = song.title_romaji or song.title
            else:
                title = song.title
            artist = song.format_artists(0, romaji_first=romaji_first, sep=sep)
            status = self.main.listen.check_favorite(song_id)
            if not status:
                self.console_out.append((f"favorite {song_id}", self.tablelate(f"Favoriting {title} by {artist}")))
            else:
                self.console_out.append((f"favorite {song_id}", self.tablelate(f"Unfavoriting {title} by {artist}")))
            Thread(self.main.listen.favorite_song, args=(song_id, )).start()
            self.main.user_panel.update()

    @threaded
    def download(self, args: Namespace):
        t = Table.grid()
        e = Progress()
        t.add_row(e)
        k = e.add_task('testing', total=100)
        self.console_out.append(("download", t))
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
            title.append(" ", Style(color='#f92672', bold=True))
        title.append(song.title or '')
        table.add_row("Title", title)
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
            feed_text.append('by ', style='#f92672')
            feed_text.append(f'{feed.song.format_artists(1, romaji_first=self.romaji_first, sep=self.sep)}')
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
        self.current_song = self.create_song_table(data.song, data.requester)
        self.layout['main_table'].update(self.current_song)
        if self.ws_data.event:
            self.update_panel(self.ws_data.event)
        else:
            self.reset_panel()

    def update_panel(self, event: Event):
        self.panel_title = f"♫♪.ılılıll {event.name} llılılı.♫♪"
        self.panel_color = '#f92672'

    def reset_panel(self):
        self.panel_title = None
        self.panel_color = "none"

    def update_song(self, song: Song) -> None:
        if not self.ws_data:
            requester = None
        else:
            requester = self.ws_data.requester
        self.current_song = self.create_song_table(song, requester)
        self.layout['main_table'].update(self.current_song)

    def create_song_table(self, song: Song, requester: Optional[Requester] = None) -> Table:
        table = Table(expand=True, show_header=False)
        table.add_column(ratio=2)
        table.add_column(ratio=8)
        title = Text()
        if song.is_favorited:
            title.append(" ", Style(color='#f92672', bold=True))
        title.append(song.title or '')

        if requester:
            table.add_row("Requested By", requester.display_name)
        table.add_row("Title", title)
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

    def __init__(self) -> None:
        self.config = Config.get_config()
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
                    case keybind.toggle_terminal:
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
        instance_lock = Path().resolve().joinpath('_instance.lock')
        if instance_lock.is_file():
            with open(instance_lock, 'r') as lock:
                pid = lock.readline().rstrip()
            if pid_exists(int(pid)):
                raise Exception("Another instance is already running")

        with open(instance_lock, 'w') as lock:
            lock.write(f'{os.getpid()}')

    def free_instance_lock(self) -> None:
        os.remove(Path().resolve().joinpath('_instance.lock'))

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
        with Live(init(), refresh_per_second=refresh_per_second, screen=False) as self.live:
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


def main():
    _main = Main()
    _main.run()
