import datetime
import logging
from logging.handlers import RotatingFileHandler
from os import mkdir
from pathlib import Path


class Logger(logging.Logger):
    @staticmethod
    def create_logger(verbose: bool) -> logging.Logger:
        level = logging.DEBUG if verbose else logging.WARNING
        log_folder = Path().resolve().joinpath('logs')
        log_file = log_folder.joinpath('log').absolute()

        if not log_folder.is_dir():
            mkdir(log_folder)

        file_handler = RotatingFileHandler(
            filename=log_file,
            mode="a+",
            maxBytes=1024 * 1024 * 100,
            backupCount=5,
            encoding='utf-8'
        )

        logging.basicConfig(
            level=level,
            format="[%(levelname)s] %(module)s: %(message)s",
            handlers=[file_handler]
        )

        log = logging.getLogger("Listen_CLI")
        log.info("========== Listen RPC ==========")
        log.info(f"Started at {datetime.datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}")
        log.info("================================")
        return log
