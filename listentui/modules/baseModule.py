from abc import abstractmethod
from dataclasses import dataclass
from logging import getLogger
from threading import Thread
from typing import Any


@dataclass
class Status:
    running: bool
    reason: str = ''


class BaseModule(Thread):
    def __init__(self) -> None:
        super().__init__(name=self.__class__.__name__)
        self._data: Any
        self._log = getLogger(__name__)
        self._log.info(f'Starting: {self.__class__.__name__}')
        self._running: bool = True
        self._status = Status(False, 'Initialising')
        pass

    def update_status(self, status: bool, reason: str = ''):
        self.status.running = status
        self.status.reason = reason

    @property
    @abstractmethod
    def data(self) -> Any:
        return self._data

    @property
    def status(self) -> Status:
        return self._status

    @abstractmethod
    def run(self) -> None:
        raise NotImplementedError

    def terminate(self):
        self._running = False
