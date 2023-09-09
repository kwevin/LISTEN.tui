import logging
import os
import time
from datetime import datetime, timedelta, timezone
from math import ceil
from os import _exit  # pyright: ignore
from pathlib import Path
from threading import Thread
from typing import Optional

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
from .listen.types import CurrentUser, ListenWsData, Requester, Song
from .listen.websocket import ListenWebsocket
from .modules.baseModule import BaseModule
from .modules.presence import DiscordRichPresence


class PreviousSongPanel(ConsoleRenderable):
    def __init__(self, songs: list[Table]):
        self.songs = songs

    def __rich_console__(self, _: Console, options: ConsoleOptions) -> RenderResult:
        height = options.max_height

        render_group: list[Table] = []
        total_height = height - 2
        current_height = 0
        total_rendered = 0
        for song in self.songs:
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
    def data(self):
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
                    case 'i':
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
        self.current_song_table: Table
        self.previous_songs: list[Table] = []
        self.duration_progress = Progress(BarColumn(bar_width=None), MofNTimeCompleteColumn())
        self.duration_task = self.duration_progress.add_task('Duration', total=None)
        self.layout = self.make_layout()

    def setup(self):
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

    def check_instance_lock(self):
        instance_lock = Path().resolve().joinpath('_instance.lock')
        if instance_lock.is_file():
            with open(instance_lock, 'r') as lock:
                pid = lock.readline().rstrip()
            if pid_exists(int(pid)):
                raise Exception("Another instance is already running")

        with open(instance_lock, 'w') as lock:
            lock.write(f'{os.getpid()}')

    def free_instance_lock(self):
        os.remove(Path().resolve().joinpath('_instance.lock'))

    def favorite_song(self):
        if not self.logged_in:
            return
        self.current_song.is_favorited = not self.current_song.is_favorited
        self.update_song_table()
        Thread(target=self.listen.favorite_song, args=(self.current_song.id, )).start()
        Thread(target=self.update_user_table).start()

    def update(self, data: ListenWsData):
        # previous songs
        if self.update_counter == 0:
            for song in data.last_played:
                self.previous_songs.append(self.create_song_table(song, show_id=True))
        else:
            self.previous_songs.insert(0, self.create_song_table(self.current_song, show_id=True))
            if len(self.previous_songs) > 5:
                self.previous_songs.pop()
        self.layout['box'].update(PreviousSongPanel(self.previous_songs))
        # current song table
        self.current_song = data.song
        self.update_song_table()
        if self.logged_in:
            self.current_song.is_favorited = self.listen.check_favorite(data.song.id)
        if self.current_song.is_favorited:
            self.update_song_table()

        # tui heading
        self.layout['heading'].update(self.heading())

        self.update_counter += 1

    def calc_delay(self) -> str:
        if self.update_counter <= 1:
            return "???"
        ws_start = self.ws.data.start_time
        ws_song = self.ws.data.song.title
        if self.player.data:
            audio_start = self.player.data.start
            audio_song = self.player.data.title
            if ws_song and audio_song:
                if ws_song not in audio_song:
                    return "???"
            else:
                return "???"
        else:
            return "???"

        diff = audio_start - ws_start
        return f'{diff.total_seconds():.2f}'

    def update_song_table(self):
        self.current_song_table = self.create_song_table(self.current_song, self.ws.data.requester)
        self.current_song_table.add_row("Duration", self.duration_progress)

    def update_user_table(self):
        user = self.listen.update_current_user()
        if user:
            self.layout['user'].update(UserPanel(user))

    def heading(self) -> Panel:
        return Panel(Text(f'Listen.Moe (󰋋 {self.ws.data.listener})', justify='center'))

    def main(self) -> Panel:
        layout = Layout()
        layout.split_row(
            Layout(self.current_song_table, name='main_table', minimum_size=14, ratio=8),
            Layout(self.other_info(), name='other_info', minimum_size=4, ratio=2)
        )
        return Panel(layout)

    def create_song_table(self, song: Song,
                          requester: Optional[Requester] = None,
                          show_id: bool = False) -> Table:
        romaji_first = self.config.display.romaji_first
        separator = self.config.display.separator

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
        table.add_row("Artists", song.artists_to_string(romaji_first, separator))
        if song.sources:
            table.add_row("Source", song.sources_to_string(romaji_first, separator))
        if song.albums:
            table.add_row("Album", song.albums_to_string(romaji_first, separator))
        if show_id:
            table.caption = Text(f'ID: {song.id}', justify='right')

        return table

    def other_info(self) -> Table:
        table = Table(expand=True, show_header=False)

        if not all([i.status.running for i in self.running_modules]):
            return table

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
        table.add_row(f"󰦒  {self.calc_delay()}s",)

        table.add_section()
        last_time = round(time.time() - self.ws.data.last_heartbeat)
        heartbeat_status = "Alive" if last_time < 40 else f"Dead ({last_time})"
        table.add_row(f"  {heartbeat_status}")
        table.add_row(f"󰥔  {timedelta(seconds=round(time.time() - self.start_time))}")

        return table

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
        self.layout['main'].update(self.main())
        if self.listen.current_user:
            self.layout['user'].visible = True
            self.layout['user'].update(UserPanel(self.listen.current_user))

        refresh_per_second = 30
        with Live(self.layout, refresh_per_second=refresh_per_second, screen=True) as self.live:
            while True:
                self.layout['main'].update(self.main())
                if self.current_song.duration:
                    completed = (datetime.now(timezone.utc) - self.ws.data.start_time).total_seconds()
                else:
                    completed = round(time.time() - self.current_song.time_end)
                total = self.current_song.duration if self.current_song.duration != 0 else 0

                self.duration_progress.update(self.duration_task, completed=completed, total=total)
                time.sleep(1 / refresh_per_second)


def main():
    _main = Main()
    _main.run()
