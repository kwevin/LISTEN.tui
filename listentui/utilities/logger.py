# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false
from datetime import datetime
from logging import Formatter, LogRecord
from queue import Queue
from threading import Event, Thread
from time import sleep
from typing import Any, ClassVar

from rich.console import ConsoleRenderable
from rich.logging import RichHandler
from rich.traceback import Traceback
from textual.app import _NullFile  # noqa: PLC2701
from textual.binding import Binding, BindingType
from textual.widgets import RichLog


class RichLogExtended(RichLog):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "clear", "Clear"),
        Binding("d", "toggle_autoscroll", "Toggle Autoscroll"),
        Binding("ctrl+d", "dump", "Dump Logs"),
    ]
    queue: Queue[tuple[LogRecord | str, ConsoleRenderable | str]] = Queue(maxsize=-1)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, max_lines=1000, highlight=True, markup=True, wrap=True, **kwargs)
        self.raw: list[str] = []
        self.formatter = Formatter("(%(asctime)s)[%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
        self.thread = Thread(target=self.empty_queue, daemon=True)
        self.stopped = Event()

    def action_clear(self) -> None:
        self.clear()

    def on_mount(self) -> None:
        self.thread.start()

    def on_unmount(self) -> None:
        self.stopped.set()
        RichLogExtended.queue.put_nowait(("STOPPED", "STOPPED"))
        self.thread.join(1)

    def action_toggle_autoscroll(self) -> None:
        self.auto_scroll = not self.auto_scroll
        if self.auto_scroll:
            self.scroll_end()
        self.notify(f"Autoscroll {'enabled' if self.auto_scroll else 'disabled'}")

    def empty_queue(self) -> None:
        while not self.stopped.is_set():
            raw, renderable = RichLogExtended.queue.get()
            if isinstance(raw, str):
                self.raw.append(raw)
            else:
                self.raw.append(self.formatter.format(raw))
            self.app.call_from_thread(self.write, renderable, expand=True)

    def action_dump(self) -> None:
        with open(f"{datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.log", "w+", encoding="utf-8") as f:
            f.writelines([line + "\n" for line in self.raw])


class RichLogHandler(RichHandler):
    def emit(self, record: LogRecord) -> None:
        """Invoked by logging."""
        message = self.format(record)
        traceback = None
        if self.rich_tracebacks and record.exc_info and record.exc_info != (None, None, None):
            exc_type, exc_value, exc_traceback = record.exc_info
            assert exc_type is not None
            assert exc_value is not None
            traceback = Traceback.from_exception(
                exc_type,
                exc_value,
                exc_traceback,
                width=self.tracebacks_width,
                code_width=self.tracebacks_code_width,
                extra_lines=self.tracebacks_extra_lines,
                theme=self.tracebacks_theme,
                word_wrap=self.tracebacks_word_wrap,
                show_locals=self.tracebacks_show_locals,
                locals_max_length=self.locals_max_length,
                locals_max_string=self.locals_max_string,
                suppress=self.tracebacks_suppress,
                max_frames=self.tracebacks_max_frames,
            )
            message = record.getMessage()
            if self.formatter:
                record.message = record.getMessage()
                formatter = self.formatter
                if hasattr(formatter, "usesTime") and formatter.usesTime():
                    record.asctime = formatter.formatTime(record, formatter.datefmt)
                message = formatter.formatMessage(record)

        message_renderable = self.render_message(record, message)
        log_renderable = self.render(record=record, traceback=traceback, message_renderable=message_renderable)
        if isinstance(self.console.file, _NullFile):
            # Handles pythonw, where stdout/stderr are null, and we return NullFile
            # instance from Console.file. In this case, we still want to make a log record
            # even though we won't be writing anything to a file.
            self.handleError(record)
        else:
            try:
                RichLogExtended.queue.put_nowait((record, log_renderable))
            except Exception:
                self.handleError(record)
