import logging
import os
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from math import ceil
from os import _exit  # pyright: ignore
from pathlib import Path
from threading import Thread
from typing import Any, Callable, Optional, Union

from psutil import pid_exists
from readchar import key, readkey
from rich.console import (Console, ConsoleOptions, ConsoleRenderable, Group,
                          RenderResult)
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, Task
from rich.style import Style
from rich.table import Table
from rich.text import Text

from .config import Config
from .listen.client import Listen
from .listen.stream import StreamPlayerMPV
from .listen.types import CurrentUser, ListenWsData, MPVData, Requester, Song
from .listen.websocket import ListenWebsocket
from .modules.baseModule import BaseModule
from .modules.presence import DiscordRichPresence


def threaded(func: Callable[..., Any]) -> Any:
    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        Thread(target=func, args=(self, *args,), kwargs=kwargs).start()
    return wrapper


class TerminalPanel(ConsoleRenderable):
    def __init__(self) -> None:
        pass

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        ...

    def run(self, cmd: str) -> None:
        ...


class PreviousSongPanel(ConsoleRenderable):
    def __init__(self, songs: list[Song]):
        self.romaji_first = Config.get_config().display.romaji_first
        self.separator = Config.get_config().display.separator
        self.songs_table: list[Table] = []
        for song in songs:
            self.songs_table.append(self.create_song_table(song))

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
        table.add_row("Artists", song.artists_to_string(self.romaji_first, self.separator))
        if song.sources:
            table.add_row("Source", song.sources_to_string(self.romaji_first, self.separator))
        if song.albums:
            table.add_row("Album", song.albums_to_string(self.romaji_first, self.separator))
        table.caption = Text(f"ID: {song.id}", justify='right')
        return table


class UserPanel(ConsoleRenderable):
    def __init__(self, user: CurrentUser) -> None:
        self.conf = Config.get_config().display
        self.user = user

    def __rich_console__(self, _: Console, options: ConsoleOptions) -> RenderResult:
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
            feed_text.append(f'{feed.song.artists_to_string(self.conf.romaji_first, self.conf.separator)}')
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


class InfoPanel(ConsoleRenderable):
    def __init__(self, player: StreamPlayerMPV, websocket: ListenWebsocket) -> None:
        self.romaji_first = Config.get_config().display.romaji_first
        self.separator = Config.get_config().display.separator
        self.duration_progress = Progress(BarColumn(bar_width=None), MofNTimeCompleteColumn())
        self.duration_task = self.duration_progress.add_task('Duration', total=None)
        self.ws = websocket
        self.player = player
        self.player.on_data_update(self.calc_delay)
        self.current_song: Table
        self.ws_data: ListenWsData
        self.start_time = time.time()
        self.song_delay = 0
        self.layout = Layout()
        self.layout.split_row(
            Layout(name='main_table', minimum_size=14, ratio=8),
            Layout(name='other_info', minimum_size=4, ratio=2)
        )
        pass

    def __rich_console__(self, _: Console, __: ConsoleOptions) -> RenderResult:
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
        yield Panel(self.layout)

    def update(self, data: Union[ListenWsData, Song]) -> None:
        if isinstance(data, ListenWsData):
            self.ws_data = data
            self.current_song = self.create_song_table(data.song, data.requester)
            self.layout['main_table'].update(self.current_song)
        else:
            self.current_song = self.create_song_table(data, self.ws_data.requester)
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
        table.add_row("Artists", song.artists_to_string(self.romaji_first, self.separator))
        if song.sources:
            table.add_row("Source", song.sources_to_string(self.romaji_first, self.separator))
        if song.albums:
            table.add_row("Album", song.albums_to_string(self.romaji_first, self.separator))
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

    def calc_delay(self, data: MPVData) -> None:
        ws_start = self.ws_data.start_time
        ws_song = self.ws_data.song.title
        audio_start = data.start
        audio_song = data.title
        if ws_song and audio_song:
            if ws_song not in audio_song:
                self.song_delay = '???'
                return
        else:
            self.song_delay = '???'
            return

        diff = audio_start - ws_start
        self.song_delay = f'{diff.total_seconds():.2f}'


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


class InputHandler(BaseModule):
    def __init__(self, main: "Main") -> None:
        super().__init__()
        self.main = main
        self.config = self.main.config
        self.kb = self.config.keybind
        self.pl = self.main.player

    @property
    def data(self) -> None:
        return None

    def run(self) -> None:
        self.update_status(True)
        while self._running:
            try:
                match readkey():
                    case self.kb.lower_volume:
                        self.pl.lower_volume(self.config.player.volume_step)
                    case self.kb.raise_volume:
                        self.pl.raise_volume(self.config.player.volume_step)
                    case self.kb.lower_volume_fine:
                        self.pl.lower_volume(1)
                    case self.kb.raise_volume_fine:
                        self.pl.raise_volume(1)
                    case self.kb.favourite_song:
                        self.main.favorite_song()
                    case self.kb.restart_player:
                        self.pl.restart()
                    case self.kb.play_pause:
                        self.pl.play_pause()
                    case self.kb.seek_to_end:
                        self.pl.seek_to_end()
                    case self.kb.toggle_terminal:
                        pass
                        k = ''
                        buf: list[str] = []
                        while k != key.ESC and k != key.ENTER:
                            k = readkey()
                            buf.append(k)
                    case _:
                        pass
            except KeyboardInterrupt:
                if self.config.system.instance_lock:
                    self.main.free_instance_lock()
                _exit(1)


class Main:

    def __init__(self) -> None:
        self.config = Config.get_config()
        if self.config.system.instance_lock:
            self.check_instance_lock()
        self.log = logging.getLogger(__name__)
        self.running_modules: list[BaseModule] = []
        self.start_time: float = time.time()
        self.update_counter: int = 0
        self.logged_in: bool = False

        self.ws: ListenWebsocket
        self.player: StreamPlayerMPV
        self.data: ListenWsData
        self.rpc: Optional[DiscordRichPresence] = None

        self.console = Console()
        self.current_song: Song
        self.duration_progress = Progress(BarColumn(bar_width=None), MofNTimeCompleteColumn())
        self.duration_task = self.duration_progress.add_task('Duration', total=None)
        self.layout = self.make_layout()

    def setup(self) -> None:
        self.ws = ListenWebsocket()
        self.running_modules.append(self.ws)
        self.ws.on_data_update(self.update)

        self.player = StreamPlayerMPV()
        self.running_modules.append(self.player)

        self.input_handler = InputHandler(self)
        self.running_modules.append(self.input_handler)

        # optional
        if self.config.rpc.enable:
            self.rpc = DiscordRichPresence()
            self.ws.on_data_update(self.rpc.update)
            self.running_modules.append(self.rpc)

        self.info_panel = InfoPanel(self.player, self.ws)

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
        self.info_panel.update(self.current_song)
        Thread(target=self.listen.favorite_song, args=(self.current_song.id, )).start()
        self.update_user_table()

    def update(self, data: ListenWsData) -> None:
        # previous songs
        if self.update_counter == 0:
            self.previous_panel = PreviousSongPanel(data.last_played)
        else:
            self.previous_panel.add(data.song)

        self.layout['box'].update(self.previous_panel)
        # current song table
        self.current_song = data.song
        self.info_panel.update(data)
        if self.logged_in:
            self.current_song.is_favorited = self.listen.check_favorite(data.song.id)
        if self.current_song.is_favorited:
            self.info_panel.update(self.current_song)

        # tui heading
        self.layout['heading'].update(self.heading())

        self.update_counter += 1

    @threaded
    def update_user_table(self) -> None:
        user = self.listen.update_current_user()
        if user:
            self.layout['user'].update(UserPanel(user))

    def heading(self) -> Panel:
        return Panel(Text(f'Listen.Moe (󰋋 {self.ws.data.listener})', justify='center'))

    def login(self):
        username = self.config.system.username
        password = self.config.system.password
        token = self.config.persist.token

        with self.console.status("Logging in...", spinner='dots'):
            if not token:
                if not username or not password:
                    self.listen = Listen()
                else:
                    self.listen = Listen.login(username, password)
                    self.logged_in = True
                if self.listen.current_user:
                    self.config.update('persist', 'token', self.listen.current_user.token)
            else:
                if not username or not password:
                    self.listen = Listen()
                else:
                    self.listen = Listen.login(username, password, token)
                    self.logged_in = True

    def run(self):
        self.login()
        self.setup()

        def init() -> Table:
            table = Table(expand=False)
            table.add_column("Module")
            table.add_column("Status")
            table.add_column("Reason")
            for i in self.running_modules:
                table.add_row(i.name, f'{i.status.running}', i.status.reason)
            return table

        with Live(init(), refresh_per_second=4, screen=True, transient=True) as live:
            while not all([i.status.running for i in self.running_modules]):
                live.update(init())
                time.sleep(0.1)

        self.layout['heading'].update(self.heading())
        self.layout['main'].update(self.info_panel)
        if self.listen.current_user:
            self.layout['user'].visible = True
            self.layout['user'].update(UserPanel(self.listen.current_user))

        refresh_per_second = 30
        with Live(self.layout, refresh_per_second=refresh_per_second, screen=True) as self.live:
            while True:
                self.layout['main'].update(self.info_panel)
                time.sleep(1 / refresh_per_second)


def main():
    _main = Main()
    _main.run()
