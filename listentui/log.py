import datetime
import logging
from logging.handlers import RotatingFileHandler
from os import mkdir
from pathlib import Path
from typing import Optional


class Logger(logging.Logger):
    @staticmethod
    def create_logger(verbose: bool, log: Optional[Path] = None) -> logging.Logger:
        level = logging.DEBUG if verbose else logging.WARNING
        if log:
            log_file = log
        else:
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
            format="(%(asctime)s)[%(thread)d][%(levelname)s] %(threadName)s: %(message)s",
            handlers=[file_handler],
            datefmt="%H:%M:%S"
        )
        logger = logging.getLogger(__name__)

        logger.info('\n')
        logger.info("========== Listen RPC ==========")
        logger.info(f"Started at {datetime.datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}")
        logger.info("================================")
        return logger
