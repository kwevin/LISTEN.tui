from datetime import datetime
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Grid, Horizontal
from textual.reactive import var
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, ProgressBar, RichLog

from listentui.data import _duration_lookup, _save_duration_map
from listentui.listen.client import ListenClient
from listentui.listen.interface import SongID
from listentui.widgets.minimalInput import MinimalInput


class SetScreen(ModalScreen[int]):
    DEFAULT_CSS = """
    SetScreen {
        align: center middle;
    }

    SetScreen Grid {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 60;
        height: 11;
    }
    SetScreen Label {
        width: auto;
        height: auto;
    }
    SetScreen Horizontal {
        column-span: 2;
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }

    SetScreen Button {
        width: 100%;
        column-span: 2;
    }

    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape,n,N", "cancel"),
    ]

    def __init__(self, song_id: SongID, duration: int):
        super().__init__()
        self.song_id = song_id
        self.duration = duration

    def compose(self) -> ComposeResult:
        with Grid():
            with Horizontal():
                yield Label(f"{self.song_id}: ")
                yield MinimalInput(value=str(self.duration), type="integer")
            yield Button("[N] Cancel", variant="primary", id="cancel")

    @on(MinimalInput.Submitted)
    def set_duration(self, event: MinimalInput.Submitted) -> None:
        if event.validation_result and event.validation_result.is_valid:
            self.dismiss(int(event.value))

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(self.duration)


class MyApp(App[None]):
    DEFAULT_CSS = """
    Screen #top {
        height: auto;
        width: 1fr;
    }
    Screen #bottom {
        height: 1fr;
        width: 1fr;
    }
    Screen #sid {
        width: 20;
    }
    Screen #sduration {
        width: 20;
    }
    Screen DataTable {
        height: 100%;
        width: 1fr;
    }
    Screen RichLog {
        width: 1fr;
        height: 100%;
    }
    """

    total = var[int](len(_duration_lookup) or 1)
    missing = var[int](0)
    depth = var[int](3399)  # last recorded depth 3399

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            yield Button("Get Missing", id="missing")
            yield Button("Scan", id="scan")
            yield Button("Stop Scan", id="stop-scan")
            yield Input(type="integer", id="sid")
            yield Input(type="integer", id="sduration")
            yield Button("Set", id="sset")
        yield ProgressBar()
        yield Label(id="stats")
        yield Label(id="scan-stats")
        yield Label(id="other")
        with Horizontal(id="bottom"):
            yield DataTable()
            yield RichLog(markup=True)

    def watch_total(self, new: int) -> None:
        self.query_one("#stats", Label).update(
            f"Status: {(1 - self.missing / self.total) * 100:.2f}% Missing: {self.missing} Total: {self.total}"
        )

    def watch_missing(self, new: int) -> None:
        self.query_one("#stats", Label).update(
            f"Status: {(1 - self.missing / self.total) * 100:.2f}% Missing: {self.missing} Total: {self.total}"
        )

    async def on_mount(self) -> None:
        await ListenClient.get_instance().connect()
        table = self.query_one(DataTable)
        self.keys = table.add_columns("ID", "duration")
        self.update_table()
        self.missing = len([value for value in _duration_lookup.values() if value == 0])

    def on_unmount(self) -> None:
        _save_duration_map()

    @work(exclusive=True)
    async def update_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        sus_time_threshold = 120
        # table.add_rows((key, value) for key, value in _duration_lookup.items())
        for key, value in _duration_lookup.items():
            table.add_row(key, value, label="*" if value < sus_time_threshold else None)
        table.sort(self.keys[1], self.keys[0])

    @on(Button.Pressed, "#missing")
    @work
    async def get_missing(self) -> None:
        progress = self.query_one(ProgressBar)
        client = ListenClient.get_instance()
        total_songs = await client.total_songs_count()
        offset = 0
        progress.update(total=total_songs, progress=offset)
        while offset < total_songs:
            songs = await client.songs(offset, 100)
            should_update = False
            for song in songs:
                if (song.duration is None or song.duration == 0) and _duration_lookup.get(song.id, 0) == 0:
                    _duration_lookup[song.id] = 0
                    should_update = True
            offset += len(songs)
            progress.advance(100)
            if should_update:
                self.update_table()

            self.total = len(_duration_lookup)
        _save_duration_map()

    @on(Button.Pressed, "#stop-scan")
    async def stop_scan(self) -> None:
        self.workers.cancel_group(self, "scan")
        _save_duration_map()
        self.update_table()

    @on(Button.Pressed, "#scan")
    @work(group="scan")
    async def scan_for_missing_duration(self) -> None:
        last_time: datetime | None = None
        while True:
            history = await ListenClient.get_instance().history(50, self.depth * 50)
            if len(history) == 0:
                break
            for idx, record in enumerate(history):
                if idx == 0:
                    continue
                if record.song.duration is None or record.song.duration == 0:
                    start_time = history[idx - 1].created_at
                    prev_time = record.created_at
                    duration = round((start_time - prev_time).total_seconds())
                    has_duration = _duration_lookup.get(record.song.id)
                    log = self.query_one(RichLog)
                    if has_duration is not None and has_duration != 0:
                        if duration < 120:
                            log.write(f"[red]{record.song.id:<7} !! {duration} < 120 [/]")
                        else:
                            avg = (duration + has_duration) // 2
                            _duration_lookup[record.song.id] = avg
                            log.write(
                                f"[yellow]{record.song.id:<7} => old: {has_duration:<3} new: {duration:<3} [green]avg: {avg}[/]"  # noqa: E501
                            )
                    elif has_duration is None or has_duration == 0:
                        if duration < 120:  # noqa: PLR2004
                            log.write(f"[red]{record.song.id:<7} !! {duration} < 120 [/]")
                        else:
                            _duration_lookup[record.song.id] = duration
                            log.write(f"[green]{record.song.id:<7} => {duration}[/]")
                    _save_duration_map()
                    self.missing = len([value for value in _duration_lookup.values() if value == 0])

            if (last_time and history[-1].created_at < last_time) or last_time is None:
                last_time = history[-1].created_at
            else:
                break

            self.query_one("#scan-stats", Label).update(
                f"Depth: {self.depth} Last Date: {last_time.strftime('%d/%m/%Y, %H:%M:%S')}"
            )

            if self.missing == self.total:
                break

            self.depth += 1

        _save_duration_map()
        self.missing = len([value for value in _duration_lookup.values() if value == 0])
        self.update_table()

    @on(DataTable.CellSelected)
    @work
    async def table_set_value(self, event: DataTable.CellSelected) -> None:
        table = event.control
        if event.cell_key.column_key != self.keys[1]:
            return
        duration = int(table.get_cell(event.cell_key.row_key, event.cell_key.column_key))
        song_id = SongID(int(table.get_cell_at(event.coordinate.left())))

        res = await self.app.push_screen_wait(SetScreen(song_id, duration))
        _duration_lookup[song_id] = res

        table.update_cell_at(event.coordinate, res)

    @on(Input.Changed, "#sid")
    def find_duration(self, event: Input.Changed) -> None:
        self.query_one("#sset", Button).variant = "default"
        if not event.value:
            return
        duration = _duration_lookup.get(SongID(int(event.value)))

        if duration is not None:
            self.query_one("#sduration", Input).value = str(duration)

    @on(Input.Submitted, "#sduration")
    def change_duration(self, event: Input.Submitted) -> None:
        song_id = SongID(int(self.query_one("#sid", Input).value))
        if event.validation_result and event.validation_result.is_valid:
            _duration_lookup[song_id] = int(event.value)

            self.update_table()

            _save_duration_map()

    @on(Button.Pressed, "#sset")
    def update_duration(self) -> None:
        song_id = SongID(int(self.query_one("#sid", Input).value))

        if _duration_lookup.get(song_id, None) is not None:
            value = self.query_one("#sduration", Input).value
            duration = int(value or 0)
            _duration_lookup[song_id] = duration
            self.update_table()
            _save_duration_map()
            self.query_one("#sset", Button).variant = "success"
        else:
            self.query_one("#sset", Button).variant = "error"

        def reset():
            self.query_one("#sset", Button).variant = "default"

        self.set_timer(2, reset)


if __name__ == "__main__":
    try:
        app = MyApp()
        app.run()
    except Exception:
        _save_duration_map()
