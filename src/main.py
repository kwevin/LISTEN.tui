import os
import time
from datetime import datetime, timedelta, timezone
from os import _exit  # pyright: ignore
from pathlib import Path
from threading import Thread
from typing import Literal

from psutil import pid_exists
from readchar import key, readkey
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                           SpinnerColumn, Task, TextColumn)
# from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from log import Logger
from src.config import Config
from src.listen.client import Listen
from src.listen.stream import StreamPlayerMPV
from src.listen.types import ListenWsData
from src.listen.websocket import ListenWebsocket
from src.module import Module
from src.modules.presence import DiscordRichPresence


class InputHandler(Module):
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
                        self.main.favourite_song()
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


class MofNCompleteColumnWithPercentage(MofNCompleteColumn):
    
    def render(self, task: "Task") -> Text:
        """Show completed/total x 100"""
        completed = int(task.completed)
        total = int(task.total) if task.total is not None else None
        total_width = len(str(total))
        if isinstance(total, int):
            percentage = completed / total * 100
            return Text(
                f"{percentage:.2f}%",
                style="progress.download"
            )
        elif total is None:
            return Text(
                f"{completed:{total_width}d}{self.separator}?",
                style="progress.download",
            )
        else:
            return Text(
                f"{completed:{total_width}d}{self.separator}?",
                style="progress.download",
            )


class Main(Thread):

    def __init__(self) -> None:
        super().__init__()
        self.config = Config.get_config()
        if self.config.system.instance_lock:
            self.check_instance_lock()
        self.log = Logger.create_logger(self.config.system.debug)
        self.running: bool = True
        self.running_modules: list[Module] = list()
        self.start_time = time.time()
        self.update_counter: int = 0
        self.is_favorite: Literal[0, 1, 2] = 0
        self.last_render_time: float = 0
        self._start: float = 0
        self.cmd_mode: bool = False
        self.cmd_input: str = ''

        self.ws: ListenWebsocket
        self.player: StreamPlayerMPV
        self.data: ListenWsData
        self.rpc: DiscordRichPresence | None = None

        self.console = Console()
        self.duration_progress = Progress(SpinnerColumn('simpleDotsScrolling'),
                                          TextColumn("[progress.description]{task.description}"),
                                          BarColumn(bar_width=None),
                                          MofNCompleteColumnWithPercentage(), expand=True)
        self.duration = self.duration_progress.add_task('Duration', total=None)

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

    def increment_count(self, _: ListenWsData):
        self.update_counter += 1
    
    def check_favourite(self, data: ListenWsData):
        res = self.listen.check_favourite(data.song.id)
        if res:
            self.is_favorite = 2
        else:
            self.is_favorite = 0

    def favourite_song(self):
        self.is_favorite = 1
        res = self.listen.favourite_song(self.ws.data.song.id)
        if res:
            self.is_favorite = 2
        else:
            self.is_favorite = 0
    
    def setup(self):
        # required
        if not self.config.system.token:
            if not self.config.system.username or not self.config.system.password:
                self.listen = Listen()
            self.listen = Listen.login(self.config.system.username, self.config.system.password)
            if self.listen.current_user:
                self.config.update('system', 'token', self.listen.current_user.token)
        else:
            self.listen = Listen.from_username_token(self.config.system.username, self.config.system.token)

        self.ws = ListenWebsocket()
        self.running_modules.append(self.ws)
        
        self.player = StreamPlayerMPV()
        self.running_modules.append(self.player)

        self.ws.on_data_update(self.increment_count)
        self.ws.on_data_update(self.check_favourite)
        self.input_handler = InputHandler(self)
        self.running_modules.append(self.input_handler)

        # optional
        if self.config.rpc.enable_rpc:
            self.rpc = DiscordRichPresence()
            self.ws.on_data_update(self.rpc.update)
            self.running_modules.append(self.rpc)

        for modules in self.running_modules:
            modules.start()

    def run(self):
        self.setup()
        refresh_per_second = 8
        with Live(self.render(), refresh_per_second=refresh_per_second, screen=True) as self.live:
            while self.running:
                self.live.update(self.render())
                time.sleep(1 / refresh_per_second)
        return

    def calc_delay(self) -> float:
        if self.update_counter <= 1:
            return 0
        ws_start = self.ws.data.start_time
        ws_song = self.ws.data.song.title
        if self.player.data:
            audio_start = self.player.data.start
            audio_song = self.player.data.title
            # if ws_song != audio_song:
            #     return -14
            if ws_song and audio_song:
                if ws_song not in audio_song:
                    return -14
        else:
            return 0
        
        diff = audio_start - ws_start
        return diff.total_seconds()
    
    def render(self) -> Layout | Table:
        if not all([i.status.running for i in self.running_modules]):
            table = Table(expand=False)
            table.add_column("Module")
            table.add_column("Status")
            table.add_column("Reason")
            for i in self.running_modules:
                table.add_row(i.name, f'{i.status.running}', i.status.reason)
            return table
        self._start = time.time()
        self.layout = Layout(name='main')
        self.layout.split_column(
            Layout(Panel(self.header()), name='header', size=3),
            Layout(Panel(self.info()), name='info', minimum_size=14),
            Layout(Panel(self._debug()), minimum_size=2),
        )
        self.last_render_time = time.time() - self._start
        return self.layout

    def header(self) -> Text:
        return Text(f'Listen.Moe (󰋋 {self.ws.data.listener})', justify='center')

    def info(self) -> Layout:
        info = Layout()
        info.split_column(
            Layout(name='main', ratio=10),
            Layout(Text(f"logged in as: {self.listen.current_user.username if self.listen.current_user else ''}"), name='other', ratio=1, minimum_size=1),
        )
        info['main'].split_row(
            Layout(self.main_info(), minimum_size=14, ratio=8),
            Layout(self.general_info(), minimum_size=4, ratio=2),
        )
        return info

    def main_info(self) -> Table | Group:
        table = Table(expand=True, show_header=False)
        table.add_column(ratio=2)
        table.add_column(ratio=8)
        
        if self.ws.data.requester:
            table.add_row("Requested By", self.ws.data.requester.display_name)
        match self.is_favorite:
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
            duration = timedelta(seconds=self.ws.data.song.duration)
            # completed = round(self.ws.data.song.duration - (self.ws.data.song.time_end - time.time()))
        else:
            duration = None
            completed = round(time.time() - self.ws.data.song.time_end)
        total = self.ws.data.song.duration if self.ws.data.song.duration != 0 else None
        table.add_row("Duration", f"{duration}")
        
        self.duration_progress.update(self.duration,
                                      completed=completed,
                                      total=total)

        return Group(table, self.duration_progress)

    def general_info(self) -> Table:
        table = Table(expand=True, show_header=False)
        # time_since = round(time.time() - self.ws.data.last_heartbeat)
        
        if not all([i.status.running for i in self.running_modules]):
            return table

        table.add_column()
        if self.player.volume > 80:
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
        offset = self.calc_delay()
        if offset == -14:
            offset = "???"
        else:
            offset = f'{offset:.2f}'
        table.add_row(f"{'󰏤 ' if self.player.paused else '󰐊 '} {'Paused' if self.player.paused else 'Playing'}")
        table.add_row(f"{vol_icon} {self.player.volume}")
        table.add_row(f"  {cache_duration:.2f}s/{cache_size/1000:.0f}MB")
        table.add_row(f"󰦒  {offset}s",)

        table.add_section()
        heartbeat_status = "Alive" if round(time.time() - self.ws.data.last_heartbeat) < 40 else "Dead"
        table.add_row(f"  {heartbeat_status}")
        # table.add_row(f"Last heartbeat: {datetime.fromtimestamp(self.ws.data.last_heartbeat).strftime('%H:%M:%S')}")
        # table.add_row(f"Time since: {timedelta(seconds=time_since)}")
        table.add_row(f"󰥔  {timedelta(seconds=round(time.time() - self.start_time))}")
        
        if self.rpc and self.config.display.display_rpc_status:
            table.add_section()
            table.add_row(f'RPC Status: {self.rpc.status.running}')
            if not self.rpc.data:
                return table
            if self.rpc.data.is_arrpc:
                table.add_row("Using: ARRPC")
        return table

    def indicator(self) -> Text:
        if self.listen.current_user:
            return Text(f'logged in as: {self.listen.current_user.display_name}')
        else:
            return Text("")

    def _debug(self) -> Table:
        table = Table(expand=False, box=None)
        table.add_row("Ofd", f'{self.ws.data.song.title}', f'{self.player.data.title}')
        table.add_row('oft', f'{self.ws.data.start_time}', f'{self.player.data.start}')
        table.add_row('render time', f'{self.last_render_time*1000:.4f}ms')
        table.add_row('heat', f'{round(time.time() - self.ws.data.last_heartbeat)}')
        table.add_row('cmd', f'{self.cmd_input}')
        return table


if __name__ == "__main__":
    _dev = Path().resolve().joinpath('devconf.toml').resolve()
    if _dev.is_file():
        Config(_dev)
    else:
        Config(Path().resolve().joinpath('config.toml').resolve())
    _main = Main()
    _main.start()
    _main.join()
