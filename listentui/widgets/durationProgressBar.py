from datetime import datetime
from logging import getLogger

import pytz
from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import ProgressBar, Static

from listentui.data import get_song_duration
from listentui.data.config import Config
from listentui.listen import Song
from listentui.listen.interface import ListenWsData


class _DurationLabel(Static):
    current = reactive(0, layout=True)
    total = reactive(0, layout=True)

    def render(self) -> RenderableType:
        m, s = divmod(self.current, 60)
        completed = f"{m:02d}:{s:02d}"

        if self.total != 0:
            m, s = divmod(self.total, 60)
            total = f"{m:02d}:{s:02d}"
            return f"{completed}/{total}"
        return f"{completed}/--:--"


class DurationProgressBar(Widget):
    DEFAULT_CSS = """
    DurationProgressBar {
        height: 1;
        width: 1fr;
    }
    DurationProgressBar ProgressBar Bar {
        width: 1fr;
    }
    DurationProgressBar ProgressBar {
        width: 1fr;
    }
    DurationProgressBar ProgressBar Bar > .bar--indeterminate {
        color: red;
    }
    DurationProgressBar ProgressBar Bar > .bar--bar {
        color: red;
    }
    DurationProgressBar _DurationLabel {
        width: auto;
        margin-left: 2;
    }
    DurationProgressBar _DurationLabel.debug_missing {
        color: yellow;
    }
    """

    current: var[int] = var(0)
    total: var[int] = var(0)

    def __init__(self, current: int = 0, total: int = 0, stop: bool = False, pause_on_end: bool = False) -> None:
        super().__init__()
        self.timer = self.set_interval(1, self._tick, pause=stop)
        self.current = current
        self.total = total
        self.pause_on_end = pause_on_end
        self.time_end = 0
        self.progress_bar = ProgressBar(show_eta=False, show_percentage=False)
        self.progress_label = _DurationLabel()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self.progress_bar
            yield self.progress_label.data_bind(DurationProgressBar.current, DurationProgressBar.total)

    def on_mount(self) -> None:
        self.progress_bar.update(total=self.total if self.total != 0 else None, progress=self.current)

    def _tick(self) -> None:
        if self.total != 0 and self.pause_on_end and self.current >= self.total:
            self.timer.pause()
            return
        self.current += 1
        self.progress_bar.advance(1)

    def try_calculate_duration(self, data: ListenWsData):
        # the server clock is behind bruh
        self.time_end = data.song.time_end
        start = data.start_time
        now = datetime.now(tz=pytz.utc)
        current = round((now - start).total_seconds())
        locdiff = Config.get_config().persistant.locdiff
        getLogger(__name__).debug(
            f"Attempting to calculate duration:\n\tcurrent_time = {now}\n\tstarted = {start}\n\tdiff = {current}\n\tlocdiff = {locdiff}\n\tfinal_time = {current - locdiff}"  # noqa: E501
        )
        current -= locdiff
        if data.song.duration and current > data.song.duration:
            current = 0
        if not data.song.duration:
            current = 0
        current = max(current, 0)
        self.current = current
        self.total = data.song.duration or 0
        self.progress_label.total = self.total
        self.progress_bar.update(total=self.total if self.total != 0 else None, progress=self.current)

    def update_progress(self, song: Song) -> None:
        self.time_end = song.time_end
        self.current = 0
        self.total = song.duration or 0
        self.progress_label.total = self.total
        self.progress_bar.update(total=self.total if self.total != 0 else None, progress=self.current)

        if get_song_duration(song.id) is not None and Config.get_config().advance.stats_for_nerd:
            self.query_one(_DurationLabel).add_class("debug_missing")
        else:
            self.query_one(_DurationLabel).remove_class("debug_missing")

    def update_total(self, total: int) -> None:
        self.total = total
        self.progress_bar.update(total=total, progress=self.current)

    def pause(self) -> None:
        self.timer.pause()

    def resume(self) -> None:
        self.timer.resume()

    def reset(self) -> None:
        self.current = 0
        self.timer.reset()
        self.query_one(ProgressBar).update(total=self.total if self.total != 0 else None, progress=self.current)
        self.query_one(_DurationLabel).total = self.total
