import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from multiprocessing import Process

from PyInstaller.__main__ import run as pyinstaller


def main():
    base = [
        '--noconfirm',
        '--clean',
        # '--upx-dir', 'upx-4.1.0',
    ]
    onedir = base.copy()
    onedir.append(r'.\onedir.spec')
    onefile = base.copy()
    onefile.append(r'.\onefile.spec')
    d = Process(target=pyinstaller, args=(onedir, ))
    f = Process(target=pyinstaller, args=(onefile, ))
    d.start()
    f.start()
    d.join()
    f.join()


if __name__ == "__main__":
    main()
