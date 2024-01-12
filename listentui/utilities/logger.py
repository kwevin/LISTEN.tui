# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false
import datetime
import logging
from logging import Handler, Logger, LogRecord
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import RichLog


class RichLogExtended(RichLog):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("c", "clear()", "Clear")]

    def action_clear(self) -> None:
        self.clear()


class RichLogHandler(Handler):
    def emit(self, record: LogRecord) -> None:
        message = self.format(record)
        if ListenLog.rich_log:
            ListenLog.rich_log.write(message)


class ListenLog(Logger):
    rich_log = RichLogExtended(highlight=True, markup=True, auto_scroll=True, wrap=True, id="_rich-log")

    @staticmethod
    def create_logger(verbose: bool) -> Logger:
        level = logging.DEBUG if verbose else logging.ERROR
        logging.basicConfig(
            level=level,
            format="(%(asctime)s)[%(levelname)s] %(name)s: %(message)s",
            handlers=[RichLogHandler()],
            datefmt="%H:%M:%S",
        )
        logger = logging.getLogger(__name__)
        logger.debug(f"Logging started at {datetime.datetime.now()}")
        return logger
