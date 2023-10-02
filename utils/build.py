import os
import sys
from ctypes.util import find_library
from pathlib import Path
from shutil import move

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyInstaller.__main__ import run as pyinstaller
from rich.console import Console


def main():
    base = [
        '--noconfirm',
        '--clean',
        '--onefile',
        '--name=listentui',
    ]

    if sys.platform.startswith(("linux", "darwin", "freebsd", "openbsd")):
        linux = base.copy()
        linux.append("listentui/__main__.py")
        with console.status("Building standalone"):
            pyinstaller(linux)

    elif sys.platform == 'win32':
        console.print("Building on windows")
        win = base.copy()
        script = "listentui/__main__.py"

        icon = Path().resolve().joinpath('dist/logo.ico')
        if icon.is_file():
            console.print("Icon file found, building with icon")
            win.extend(['--icon', f'{icon}'])
        else:
            console.print("No icon found, skipping icon")

        upx = Path().resolve().joinpath('upx')
        if upx.is_dir():
            console.print("Upx found, building with upx")
            win.extend(['--upx-dir', f'{upx}'])
        else:
            console.print("Upx not found, skipping upx")

        win.append(script)

        libmpv = find_library('mpv-2.dll') or find_library('mpv-1.dll')
        if libmpv is None:
            libmpv = Path('listentui/listen/mpv-2.dll').resolve()
            if not libmpv.is_file():
                # should download mpv-2.dll instead
                console.print("No mpv.dll found, unable to build standalone executable with mpv")
                return

        if libmpv:
            with console.status("Building standalone with mpv") as task:
                pyinstaller(win)
                move(Path().resolve().joinpath('dist/listentui.exe'),
                     Path().resolve().joinpath('dist/listentui_portable.exe'))

                task.update("Building standalone without mpv")
                specfile = Path().resolve().joinpath('listentui.spec')
                with open(specfile, 'r') as spec:
                    data = spec.readlines()

                lib = Path(libmpv).name
                for idx, value in enumerate(data):
                    if value.startswith('pyz'):
                        insert_point = idx
                        break

                data.insert(insert_point, f"a.binaries -= TOC([('{lib}', None, None)])\n")  # type: ignore
                with open(specfile, 'w') as spec:
                    spec.writelines(data)

                win.pop()
                win.remove("--onefile")
                win.remove("--name=listentui")
                if icon.is_file():
                    win.remove("--icon")
                    win.remove(f"{icon}")

                win.append(f"{specfile}")
                pyinstaller(win)

                os.remove(specfile)


if __name__ == "__main__":
    # this will build the following
    # on linux:
    #   listentui
    # on windows:
    #   listentui.exe
    #   listentui.exe + embedded mpv
    # on all system
    #   poetry build
    console = Console()
    main()
