import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                           SpinnerColumn, Task, TextColumn)
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from log import Logger
from src.listen.stream import StreamPlayerMPV
from src.listen.websocket import ListenWebsocket
from src.module import Module
from src.modules.presence import DiscordRichPresence


class Configurator:
    def __init__(self, config_path: Path) -> None:
        pass


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
        self.log = Logger.create_logger(True)
        self.running_modules: list[Module] = list()
        self.start_time = time.time()

        # self.controls: Controls
        self.ws: ListenWebsocket
        self.player: StreamPlayerMPV
        self.rpc: DiscordRichPresence

        self.console = Console()
        self.duration_progress = Progress(SpinnerColumn('simpleDotsScrolling'),
                                          TextColumn("[progress.description]{task.description}"),
                                          BarColumn(bar_width=None),
                                          MofNCompleteColumnWithPercentage(), expand=True)
        self.duration = self.duration_progress.add_task('Duration', total=None)

    def setup(self):
        # core
        # self.controls = Controls(self)
        # self.running_modules.append(self.controls)

        # required
        self.ws = ListenWebsocket()
        self.running_modules.append(self.ws)
        self.player = StreamPlayerMPV()
        self.running_modules.append(self.player)
        # optional
        self.rpc = DiscordRichPresence()
        self.ws.on_data_update(self.rpc.update)
        self.running_modules.append(self.rpc)

        for modules in self.running_modules:
            modules.start()

    def end(self):
        for modules in self.running_modules:
            modules.terminate()

    def run(self):
        self.setup()
        with Live(self.render()) as self.live:
            while True:
                self.live.update(self.render())
                time.sleep(1)

    def terminate(self):
        self.end()
    
    def render(self) -> Layout | Table:
        if not all([i.status.running for i in self.running_modules]):
            table = Table(expand=True)
            for i in self.running_modules:
                table.add_row(i.name, f'{i.status.running}', i.status.reason)
            return table
        self.layout = Layout(name='main')
        self.layout.split_column(
            Layout(Panel(self.header()), name='header', size=3),
            Layout(Panel(self.info()), name='info', minimum_size=16),
            Layout(Panel(self.place_holder_controller()), name='info', minimum_size=10)
        )
        return self.layout

    def header(self) -> Text:
        return Text(f'Listen.Moe CLI ({self.ws.data.listener})', justify='center')

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
        table.add_row("Title", self.ws.data.song.title)
        table.add_row("Artists", self.ws.data.song.artists_to_string())
        if self.ws.data.song.sources:
            table.add_row("Source", self.ws.data.song.sources_to_string())
        table.add_row("Album", self.ws.data.song.albums_to_string())
        table.add_row("Album Image", self.ws.data.song.album_image())
        table.add_row("Artist Image", self.ws.data.song.artist_image())
        if self.ws.data.song.duration:
            duration = timedelta(seconds=self.ws.data.song.duration)
            completed = round(self.ws.data.song.duration - (self.ws.data.song.time_end - time.time()))
        else:
            duration = None
            completed = round(time.time() - self.ws.data.song.time_end)

        table.add_row("Duration", f"{duration}")

        self.duration_progress.update(self.duration,
                                      completed=completed,
                                      total=self.ws.data.song.duration if self.ws.data.song.duration else None)
        
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
        
        stream.add_row(f"{'󰏤 ' if self.player.paused else '󰐊 '} {'Paused' if self.player.paused else 'Playing'}")
        stream.add_row(f"{vol_icon} {self.player.volume}")
        # stream.add_row(f"  {self.player.time_remaining:.2f}")
        stream.add_row(Spinner(name='arc', text=Text(f" {self.player.time_remaining:.2f}")))
        # stream.add_row(
        #     f"{'󰏤 ' if self.player.paused else '󰐊 '} {'Paused' if self.player.paused else 'Playing'}",
        #     f"{vol_icon} {self.player.volume}",
        #     f"  {self.player.time_remaining:.2f}"
        # )

        return Group(table, self.duration_progress, Padding(stream, (1, 0, 0, 0)))

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

    def place_holder_controller(self) -> Layout:
        layout = Layout(name='Controls')
        layout.split_row(
            Layout(name='song'),
            Layout(name='account'),
            Layout(name='other')
        )
        return layout


if __name__ == "__main__":
    # load config here
    main = Main()
    main.start()
    main.join()
