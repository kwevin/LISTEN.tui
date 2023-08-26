import time
from datetime import datetime, timedelta, timezone
from os import _exit  # pyright: ignore
from pathlib import Path
from threading import Thread
from typing import Literal

from readchar import readkey
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
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
    
    @property
    def data(self):
        return None

    def run(self) -> None:
        self.update_status(True)
        while self._running:
            try:
                k = readkey()
                if k in self.config.keybind.lower_volume:
                    self.main.player.lower_volume(self.config.player.volume_step)
                if k in self.config.keybind.raise_volume:
                    self.main.player.raise_volume(self.config.player.volume_step)
                if k in self.config.keybind.lower_volume_fine:
                    self.main.player.lower_volume(1)
                if k in self.config.keybind.raise_volume_fine:
                    self.main.player.raise_volume(1)
                if k in self.config.keybind.favourite_song:
                    self.main.favourite_song()
                if k in self.config.keybind.restart_player:
                    self.main.player.restart()
                if k in self.config.keybind.play_pause:
                    self.main.player.play_pause()
            except KeyboardInterrupt:
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
        else:
            return Text(
                f"{completed:{total_width}d}{self.separator}?",
                style="progress.download",
            )


class Main(Thread):

    def __init__(self) -> None:
        super().__init__()
        self.config = Config.get_config()
        self.log = Logger.create_logger(self.config.system.debug)
        self.running_modules: list[Module] = list()
        self.start_time = time.time()
        self.update_counter: int = 0
        self.is_favorite: Literal[0, 1, 2] = 0

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

    def update(self, _: ListenWsData):
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

        self.ws.on_data_update(self.update)
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
        with Live(self.render(), refresh_per_second=refresh_per_second) as self.live:
            while True:
                self.live.update(self.render())
                time.sleep(1 / refresh_per_second)

    def terminate(self):
        for modules in self.running_modules:
            modules.terminate()

    def calc_delay(self) -> float:
        if self.update_counter <= 1:
            return 0
        ws_start = self.ws.data.start_time
        ws_song = self.ws.data.song.title
        if self.player.data:
            audio_start = self.player.data.start
            audio_song = self.player.data.title
            if ws_song != audio_song:
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
        
        self.layout = Layout(name='main')
        self.layout.split_column(
            Layout(Panel(self.header()), name='header', size=3),
            Layout(Panel(self.info()), name='info', minimum_size=14),
            Layout(Panel(self.other_info(), title='Controls'), name='info', minimum_size=10)
        )
        return self.layout

    def header(self) -> Text:
        return Text(f'Listen.Moe (󰋋 {self.ws.data.listener})', justify='center')

    def info(self) -> Layout:
        info = Layout()
        info.split_row(
            Layout(self.main_info(), ratio=8),
            Layout(self.general_info(), ratio=2)
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
        table.add_row("Duration", f"{duration}")
        
        self.duration_progress.update(self.duration,
                                      completed=completed,
                                      total=self.ws.data.song.duration if self.ws.data.song.duration != 0 else None)
        
        stream = Table(expand=False, show_header=False, box=None)
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
        # stream.add_row(f"{'󰏤 ' if self.player.paused else '󰐊 '} {'Paused' if self.player.paused else 'Playing'}")
        # stream.add_row(f"{vol_icon} {self.player.volume}")
        # stream.add_row(f"  {cache_duration:.2f}s/{cache_size}")
        # stream.add_row(Spinner(name='arc', text=Text(f" {self.player.time_remaining:.2f}")))

        offset = self.calc_delay()
        if offset == -14:
            offset = "???"
        else:
            offset = f'{offset:.2f}'
        stream.add_row(
            f"{'󰏤 ' if self.player.paused else '󰐊 '} {'Paused' if self.player.paused else 'Playing'}",
            f"{vol_icon} {self.player.volume}",
            f"  {cache_duration:.2f}s/{cache_size}",
            f"Offset: {offset}s",
        )

        e = Table(expand=True, show_header=False, box=None)
        if self.player.data:
            e.add_row('Websocket', 'Player')
            e.add_row(f'{self.ws.data.start_time}', f'{self.player.data.start}')
        return Group(table, self.duration_progress, Padding(stream, (1, 0, 0, 0)), e)

    def general_info(self) -> Table:
        table = Table(expand=True, show_header=False)
        time_since = round(time.time() - self.ws.data.last_heartbeat)
        
        if not all([i.status.running for i in self.running_modules]):
            return table

        table.add_column()
        table.add_row(f"Last heartbeat: {datetime.fromtimestamp(self.ws.data.last_heartbeat).strftime('%H:%M:%S')}")
        table.add_row(f"Time since: {timedelta(seconds=time_since)}")
        table.add_row(f"Uptime: {timedelta(seconds=round(time.time() - self.start_time))}")
        
        if self.rpc:
            table.add_section()
            table.add_row(f'RPC Status: {self.rpc.status.running}')
            if not self.rpc.data:
                return table
            if self.rpc.data.is_arrpc:
                table.add_row("Using: ARRPC")
        return table

    def other_info(self) -> Layout:
        # accounts
        # previos songs
        # stream options such as compresssion
        return Layout(name='other info')


if __name__ == "__main__":
    _dev = Path().resolve().joinpath('devconf.toml')
    if _dev:
        Config(_dev)
    else:
        Config(Path().resolve().joinpath('config.toml'))
    _main = Main()
    _main.start()
    _main.join()
