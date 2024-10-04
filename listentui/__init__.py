__version__ = "2.0.0"
__NO_MPV__ = False

from os import environ

try:
    import mpv
except OSError as e:
    if not environ.get("LISTENTUI_BYPASS_MPV"):
        import sys

        print(e)
        sys.exit(-1)
    else:
        __NO_MPV__ = True
