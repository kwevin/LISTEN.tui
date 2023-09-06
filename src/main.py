import os
import time
from datetime import datetime, timedelta, timezone
from os import _exit  # pyright: ignore
from pathlib import Path
from threading import Thread
from typing import Literal

from psutil import pid_exists
from readchar import key, readkey
from rich.console import (Console, ConsoleOptions, ConsoleRenderable,
                          RenderResult)
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, Task
# from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from log import Logger
from modules.baseModule import BaseModule
from src.config import Config
from src.listen.client import Listen
from src.listen.stream import StreamPlayerMPV
from src.listen.types import CurrentUser, ListenWsData
from src.listen.websocket import ListenWebsocket
from src.modules.presence import DiscordRichPresence


class UserPanel(ConsoleRenderable):
    def __init__(self, user: CurrentUser) -> None:
        self.user = user

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        def feed(count: int) -> Table:
            table = Table(expand=True, box=None, padding=(0, 0, 1, 0))
            for idx, feed in enumerate(self.user.feed):
                if idx + 1 > count:
                    break
                table.add_row(Text(f'Favorited {feed.song.title} by {feed.song.artists_to_string()}', justify='left', overflow='ellipsis'))

            return table
        width = options.max_width
        height = options.max_height
        layout = Layout()

        table = Table(expand=True, box=None)
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

        feed_height = height - 9
        count = round(feed_height / 5)
        feed_table = feed(count)

        layout.split_column(
            Layout(Padding(Text(f'{self.user.display_name}', justify='center'), (1, 0, 0, 0)), name='table', size=3),
            Layout(table, name='table', size=4),
            Layout(feed_table, name='feed_table')
        )
        yield Panel(
            layout,
            title='User',
            height=height
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
                        l: list[str] = []
                        k = ''
                        while k != key.ENTER and k != key.ESC:
                            k = readkey()
                            l.append(k)
                            self.main.cmd_input = "".join(l).rstrip()
                        # cmd = "".join(l).rstrip()
                    case _:
                        pass
            except KeyboardInterrupt:
                if self.config.system.instance_lock:
                    self.main.free_instance_lock()
                _exit(1)


class Main(Thread):

    def __init__(self) -> None:
        super().__init__()
        self.config = Config.get_config()
        if self.config.system.instance_lock:
            self.check_instance_lock()
        self.log = Logger.create_logger(self.config.system.debug)
        self.running_modules: list[BaseModule] = []
        self.start_time = time.time()
        self.update_counter: int = 0
        self.favourite_status: Literal[0, 1, 2] = 0
        self.cmd_mode: bool = False
        self.cmd_input: str = ''

        self.ws: ListenWebsocket
        self.player: StreamPlayerMPV
        self.data: ListenWsData
        self.rpc: DiscordRichPresence | None = None

        self.console = Console()
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
        if self.config.rpc.enable_rpc:
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
            Layout(name='box', ratio=8),
            Layout(name='user', ratio=2)
        )
        layout['box'].split_column(
            Layout(Panel(Text("Not a Terminal")), name='terminal', ratio=9),
            Layout(Panel(Text('> Send help')), name='input', ratio=1, size=3)
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
        self.favourite_status = 1
        res = self.listen.favorite_song(self.ws.data.song.id)
        if res:
            self.favourite_status = 2
        else:
            self.favourite_status = 0

    def update(self, data: ListenWsData):
        self.update_counter += 1
        res = self.listen.check_favorite(data.song.id)
        if res:
            self.favourite_status = 2
        else:
            self.favourite_status = 0
        self.layout['heading'].update(self.heading())
        self.layout['main'].update(self.main())

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

    def heading(self) -> Panel:
        return Panel(Text(f'Listen.Moe (󰋋 {self.ws.data.listener})', justify='center'))

    def main(self) -> Panel:
        layout = Layout()
        layout.split_row(
            Layout(self.main_table(), name='main_table', minimum_size=14, ratio=8),
            Layout(self.other_info(), name='other_info', minimum_size=4, ratio=2)
        )
        return Panel(layout)

    def main_table(self) -> Table:
        table = Table(expand=True, show_header=False)
        table.add_column(ratio=2)
        table.add_column(ratio=8)

        if self.ws.data.requester:
            table.add_row("Requested By", self.ws.data.requester.display_name)
        match self.favourite_status:
            case 0:
                star = ""
            case 1:
                star = " "
            case 2:
                star = " "
        table.add_row("Title", f'{star}{self.ws.data.song.title}')
        table.add_row("Artists", self.ws.data.song.artists_to_string(
            self.config.display.romaji_first, self.config.display.separator))
        if self.ws.data.song.sources:
            table.add_row("Source", self.ws.data.song.sources_to_string(
                self.config.display.romaji_first, self.config.display.separator))
        if self.ws.data.song.albums:
            table.add_row("Album", self.ws.data.song.albums_to_string(
                self.config.display.romaji_first, self.config.display.separator))

        if self.ws.data.song.duration:
            completed = (datetime.now(timezone.utc) - self.ws.data.start_time).total_seconds()
        else:
            completed = round(time.time() - self.ws.data.song.time_end)
        total = self.ws.data.song.duration if self.ws.data.song.duration != 0 else 0

        self.duration_progress.update(self.duration_task,
                                      completed=completed,
                                      total=total)
        table.add_row("Duration", self.duration_progress)
        # table.add_row("", self.duration_progress)
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

    def _debug(self) -> Panel:
        table = Table.grid()
        table.add_row("Ofd", f'{self.ws.data.song.title}', f'{self.player.data.title}')
        table.add_row('oft', f'{self.ws.data.start_time}', f'{self.player.data.start}')
        table.add_row('heat', f'{round(time.time() - self.ws.data.last_heartbeat)}')
        table.add_row('cmd', f'{self.cmd_input}')
        return Panel(table)

    def run(self):
        with self.console.status("Logging in...", spinner='dots'):
            if not self.config.system.token:
                if not self.config.system.username or not self.config.system.password:
                    self.listen = Listen()
                self.listen = Listen.login(self.config.system.username, self.config.system.password)
                if self.listen.current_user:
                    self.config.update('system', 'token', self.listen.current_user.token)
            else:
                self.listen = Listen.from_username_token(self.config.system.username, self.config.system.token)
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
            self.layout['user'].update(UserPanel(self.listen.current_user))

        refresh_per_second = 30
        with Live(self.layout, refresh_per_second=refresh_per_second, screen=True) as self.live:
            while True:
                self.layout['main'].update(self.main())
                time.sleep(1 / refresh_per_second)


if __name__ == "__main__":
    _dev = Path().resolve().joinpath('devconf.toml')
    if _dev.is_file():
        Config(_dev)
    else:
        Config(Path().resolve().joinpath('config.toml'))
    _main = Main()
    _main.start()
    _main.join()
