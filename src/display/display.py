import threading
import time
from datetime import datetime, timedelta
from logging import getLogger
from typing import Literal

from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                           SpinnerColumn, Task, TextColumn)
from rich.table import Table
from rich.text import Text

from src.listen.types import ListenWsData
from src.module.types import Status


class MofNCompletePercentageColumn(MofNCompleteColumn):
    
    def render(self, task: "Task") -> Text:
        """Show completed/total. x 100"""
        completed = int(task.completed)
        total = int(task.total) if task.total is not None else "?"
        total_width = len(str(total))
        if isinstance(total, int):
            percentage = completed / total * 100
            return Text(
                f"{percentage:.2f}%",
                style="progress.download"
            )
        else:
            return Text(
                f"{completed:{total_width}d}{self.separator}{total}",
                style="progress.download",
            )


class Controls:

    def __init__(self, keybind: dict[str, dict[str, str]] | None = None) -> None:
        keybind = {
            "Song": {
                "Play/Pause": "P",
                "Favourite": "F",
                "Source": "C",
                "Artist": "A",
                "Album": "E",
                "Search": "None",
                "History": "None",
                "Latest Additions": "None",
            },
            "User": {
                "Login": "L",
                "Sign Out": "Q",
            },
            "Other": {
                "Download": "D",

            }
        }
        self.keybind = keybind
        self._song = Layout(name='song')
        self._account = Layout(name='account')
        self._other = Layout(name='other')
    
    def song_control(self) -> Layout:
        return self._song
    
    def account_control(self) -> Layout:
        return self._account
    
    def other_control(self) -> Layout:
        return self._other
    
    def render(self) -> Layout:
        layout = Layout()
        layout.split_row(self.song_control(), self.account_control(), self.other_control())
        return layout
    
    # make func that changes the variable used for render() to switch pages and switch it back once done, refactor these functions so that they only compute once
    

class Display(threading.Thread):
    def __init__(self) -> None:
        super().__init__()
        self.data: ListenWsData | None = None
        self.progress = Progress(SpinnerColumn('simpleDotsScrolling'),
                                 TextColumn("[progress.description]{task.description}"),
                                 BarColumn(bar_width=None),
                                 MofNCompletePercentageColumn(), expand=True)
        self.duration = self.progress.add_task('Duration', total=None)
        self.console = Console()
        self.controls = Controls()
        self.modules: dict[str, Status] = {'Interface': Status(True, ''),
                                           'Websocket': Status(False, 'Initialising'),
                                           }
        self.log = getLogger(__name__)
        self.start_time = time.time()
        self.time_since = 0

    def update_status(self, module: Literal['Websocket'], status: Status):
        self.modules[module] = status

    def update_data(self, data: ListenWsData) -> None:
        self.data = data

    def _update_progress_type(self, duration: int | None) -> None:
        self.progress = Progress(SpinnerColumn('simpleDotsScrolling'),
                                 TextColumn("[progress.description]{task.description}"),
                                 BarColumn(bar_width=None),
                                 MofNCompletePercentageColumn() if duration else MofNCompleteColumn(),
                                 expand=True)
        self.duration = self.progress.add_task('Duration', total=None)

    def _info(self) -> RenderableType:
        table = Table(expand=True)
        table.add_column("Info")
        
        if not all([i.running for i in self.modules.values()]) or not self.data:
            return table
        table.add_row(f"Last heartbeat: {datetime.fromtimestamp(self.data.last_heartbeat).strftime('%H:%M:%S')}")
        table.add_row(f"Time since: {timedelta(seconds=self.time_since)}")
        table.add_row(f"Uptime: {timedelta(seconds=round(time.time() - self.start_time))}")

        if self.data.rpc:
            table.add_section()
            table.add_row(f'RPC Status: {self.data.rpc.status.running}')
            if self.data.rpc.is_arrpc:
                table.add_row('Using: ARRPC')
        
        return table

    def _table(self) -> Table | Group:
        table = Table(expand=True)
        table.add_column("Key", ratio=2)
        table.add_column("Value", ratio=8)
        
        if not all([i.running for i in self.modules.values()]) or not self.data:
            table.add_column("Status")
            table.add_row("Interface", f"{self.modules['Interface'].running}", f"{self.modules['Interface'].reason}")
            table.add_row("Websocket", f"{self.modules['Websocket'].running}", f"{self.modules['Websocket'].reason}")
            self.progress.update(self.duration, completed=0, total=None)
            return table

        self.time_since = round(time.time() - self.data.last_heartbeat)
        table.add_row("Title", self.data.song.title)
        table.add_row("Artists", self.data.song.artists_to_string())
        if self.data.song.sources:
            table.add_row("Source", self.data.song.sources_to_string())
        table.add_row("Album", self.data.song.albums_to_string())
        table.add_row("Album Image", self.data.song.album_image())
        table.add_row("Artist Image", self.data.song.artist_image())
        if self.data.song.duration:
            duration = timedelta(seconds=self.data.song.duration)
            completed = round(self.data.song.duration - (self.data.song.time_end - time.time()))
        else:
            duration = None
            completed = round(time.time() - self.data.song.time_end)

        self._update_progress_type(self.data.song.duration)

        table.add_row("Duration", f"{duration}")

        self.progress.update(self.duration,
                             completed=completed,
                             total=self.data.song.duration if self.data.song.duration else None)
        return Group(table, self.progress)
    
    def _heading(self) -> Text:
        if not self.data:
            return Text('Listen.Moe CLI', justify='center')
        else:
            return Text(f'Listen.Moe CLI ({self.data.listener})', justify='center')
     
    def _render(self) -> Layout:
        heading = self._heading()
        data_table = self._table()
        info_table = self._info()
        layout = Layout()
        info = Layout()
        layout.split_column(
            Layout(Panel(heading), size=3),
            Layout(Panel(info), size=15),
            Layout(Panel(self.controls.render(), title='Controls'), minimum_size=10)
        )

        info.split_row(
            Layout(data_table, ratio=8),
            Layout(info_table, ratio=2)
        )
        return layout

    def run(self):
        with Live(self._render(), refresh_per_second=4) as self.live:
            while True:
                self.live.update(self._render())
                time.sleep(1)
