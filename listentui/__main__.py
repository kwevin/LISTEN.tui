#!/usr/bin/env python3

import sys
from pathlib import Path

if __package__ is None and not getattr(sys, 'frozen', False):  # type: ignore
    # direct call of __main__.py
    import os.path
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))


from listentui.config import Config
from listentui.log import Logger
from listentui.main import main


def run():
    _conf = Path().resolve().joinpath('config.toml')
    if not _conf.is_file():
        Config.create_new()
    else:
        Config(_conf)
    main()


def rundev():
    Config(Path().resolve().joinpath('devconf.toml'))
    Logger.create_logger(verbose=True)
    main()


if __name__ == '__main__':
    run()
