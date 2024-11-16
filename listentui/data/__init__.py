import json
from logging import getLogger
from time import perf_counter

from rich.pretty import pretty_repr

from listentui.data.config import Config
from listentui.listen.interface import SongID
from listentui.utilities import get_root

_duration_lookup: dict[SongID, int] = {}
_duration_map = get_root().joinpath("duration_map.json")


def load_duration_map() -> None:
    global _duration_lookup  # noqa: PLW0603
    try:
        if _duration_map.is_file():
            perf = perf_counter()
            with open(_duration_map, "r", encoding="utf-8") as f:
                temp = json.load(f)
                _duration_lookup = {SongID(int(key)): int(value) for key, value in temp.items()}
                getLogger(__name__).debug(f"Loaded duration_map, took: {perf_counter() - perf}s")
    except json.JSONDecodeError as e:
        getLogger(__name__).warning(f"Cannot decode duration_map, reason: {e}")


def get_song_duration(song_id: SongID) -> int | None:
    return _duration_lookup.get(song_id)


def set_song_duration(song_id: SongID, duration: int) -> None:
    if duration <= 0:
        getLogger(__name__).debug(f"Invalid duration: {song_id} = {duration}")
        return
    _duration_lookup[song_id] = duration
    _save_duration_map()


def _save_duration_map() -> None:
    with open(_duration_map, "w+", encoding="utf-8") as f:
        json.dump(dict(_duration_lookup.items()), f)


load_duration_map()

__all__ = ["Config", "get_song_duration", "set_song_duration"]
