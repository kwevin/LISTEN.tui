import os
import sys
from ctypes.util import find_library
from pathlib import Path
from shutil import move
from time import perf_counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyInstaller.__main__ import run as pyinstaller
from rich.console import Console

NAME = 'listentui'
BASE = [
    '--noconfirm',
    '--clean',
    '--onefile',
    f'--name={NAME}',
    '--log-level', 'WARN',
    # '--splash', 'utils/logo.png'  # lmao dont use this
]
MAIN_PATH = "listentui/__main__.py"
PORTABLE_PATH = "listentui/__main_portable__.py"


def build_linux():
    linux = BASE.copy()
    linux.append(MAIN_PATH)
    with console.status("Building standalone"):
        pyinstaller(linux)


def generate_window_options(opts: list[str], spec: bool = False) -> list[str]:
    # use upx if it is found
    upx = Path().resolve().joinpath('upx')
    if upx.is_dir():
        console.print("Upx found, building with upx")
        opts.extend(['--upx-dir', f'{upx}'])
    else:
        console.print("Upx not found, skipping upx")

    # build using spec cannot take these arguments
    if spec:
        opts.remove("--onefile")
        opts.remove(f"--name={NAME}")
        return opts

    # embed icon
    icon = Path().resolve().joinpath('utils/logo.ico')
    if icon.is_file():
        console.print("Icon file found, building with icon")
        opts.extend(['--icon', f'{icon}'])
    else:
        console.print("No icon found, skipping icon")

    return opts


def build_window_portable():
    win = BASE.copy()
    generate_window_options(win)

    # locates mpv and bundle it with the program
    libmpv = find_library('mpv-2.dll') or find_library('mpv-1.dll')
    if libmpv is None:
        libmpv = Path('mpv-2.dll').resolve()
        if not libmpv.is_file():
            console.print("No mpv-2.dll found, unable to build standalone executable with mpv")
            return
        else:
            win.extend(['--add-binary', f'{libmpv};.'])

    win.append(PORTABLE_PATH)

    with console.status("Building window portable"):
        pyinstaller(win)
        move(Path().resolve().joinpath(f'dist/{NAME}.exe'),
             Path().resolve().joinpath(f'dist/{NAME}-portable.exe'))


def build_window_standalone():
    # build a standalone, only works if mpv is not in %PATH%
    win = BASE.copy()
    generate_window_options(win)

    win.append(MAIN_PATH)

    with console.status("Building window standalone"):
        pyinstaller(win)


def build_window_standalone_using_spec():
    # build a standalone, by modifying the specfile to remove mpv since it is in %PATH%
    win = BASE.copy()
    win = generate_window_options(win, spec=True)

    specfile = Path().resolve().joinpath(f'{NAME}.spec')
    with open(specfile, 'r') as spec:
        data = spec.readlines()

    libmpv = find_library('mpv-2.dll') or find_library('mpv-1.dll')
    if libmpv is None:
        return

    lib = Path(libmpv).name
    for idx, value in enumerate(data):
        if value.startswith('pyz'):
            insert_point = idx
            break

    for idx, line in enumerate(data):
        if "__main_portable__" in line:
            new = line.replace("__main_portable__", "__main__")
            data[idx] = new

    data.insert(insert_point, f"a.binaries -= TOC([('{lib}', None, None)])\n")  # type: ignore
    with open(specfile, 'w') as spec:
        spec.writelines(data)

    win.append(f"{specfile}")

    with console.status("Building window standalone using specfile"):
        pyinstaller(win)


def main():
    if sys.platform.startswith(("linux", "darwin", "freebsd", "openbsd")):
        build_linux()

    elif sys.platform == 'win32':
        build_window_portable()
        libmpv = find_library('mpv-2.dll') or find_library('mpv-1.dll')
        if libmpv:
            console.print("mpv.dll found in %PATH%, building standalone using specfile")
            build_window_standalone_using_spec()
        else:
            console.print("mpv.dll not found in %PATH%, building standalone normally")
            build_window_standalone()

        specfile = Path().resolve().joinpath(f'{NAME}.spec')
        if specfile.is_file():
            os.remove(specfile)


if __name__ == "__main__":
    # this will build the following
    # on linux:
    #   listentui.tui
    # on windows:
    #   listentui.exe
    #   listentui-portable.exe
    # on mac:
    #   it should build the same as linux, but i dont own a mac so idk
    console = Console(style="red")
    start = perf_counter()
    main()
    end = perf_counter()
    console.print(f"Building took {round(end - start)}s")
