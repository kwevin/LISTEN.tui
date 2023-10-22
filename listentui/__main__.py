#!/usr/bin/env python3
import sys
from pathlib import Path

if __package__ is None and not getattr(sys, 'frozen', False):  # type: ignore
    # direct call of __main__.py
    import os.path
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))


from argparse import ArgumentParser, Namespace

from listentui.config import Config
from listentui.log import Logger
from listentui.main import Main

VERSION = "1.2.1"
PORTABLE = False
parser = ArgumentParser(prog="Listen.tui", description="A tui for LISTEN.moe")
parser.add_argument("-v", "--version",
                    dest="version",
                    action="store_true",
                    help="Print out the program's version and exit"
                    )
parser.add_argument("--config", "-c",
                    dest="config",
                    action="store",
                    type=str,
                    help="Path to config file",
                    metavar="Path")
parser.add_argument("--debug", "-d",
                    dest="debug",
                    action="store_true",
                    help="Enable logging to file",
                    )
parser.add_argument("--log", "-l",
                    dest="log",
                    action="store",
                    type=str,
                    help="Path to log file, will be ignored if '--debug' is not passed in",
                    metavar="Path")
parser.add_argument("--bypass",
                    dest="bypass",
                    action="store_true",
                    help="Bypass and clears the instance lock"
                    )
parser.add_argument("--clean-temp",
                    dest="clean",
                    action="store_true",
                    help="Clean any temporary files created due to killing the program with task manager or x button")


def clean():
    import os
    from glob import glob
    from pathlib import Path
    from shutil import rmtree

    from rich.console import Console
    from rich.progress import track

    console = Console()
    temp_path = Path(os.environ["LOCALAPPDATA"]).joinpath("Temp")
    temp_folder = glob("_MEI*", root_dir=temp_path)

    if len(temp_folder) == 0:
        console.print(r"\^o^/ no temporary folder found")
        return

    for folder in track(temp_folder, description="Cleaning pyinstaller temporary folder"):
        rmtree(temp_path.joinpath(folder), ignore_errors=True)

    console.print(r"(✿◠‿◠) All done!")
    return


def run():
    args: Namespace = parser.parse_args()

    if args.version:
        print(VERSION)
        sys.exit()

    if args.clean:
        clean()
        sys.exit()

    if args.config:
        Config(Path(args.config).resolve(), portable=PORTABLE)
    else:
        Config(portable=PORTABLE)

    if args.debug:
        if args.log:
            log_path = Path(args.log).resolve()
        else:
            log_path = None
        Logger.create_logger(verbose=args.debug, log=log_path)

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):  # running as compiled
        from shutil import rmtree
        _mei = Path(Config.get_config().persist.meipass).resolve()
        if _mei.is_dir() and _mei != Path('').resolve():
            rmtree(_mei, ignore_errors=True)
        Config.get_config().update('persist', 'meipass', getattr(sys, '_MEIPASS'))

    _main = Main(args.debug, args.bypass)
    _main.run()


if __name__ == '__main__':
    run()
