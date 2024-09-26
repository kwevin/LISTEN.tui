import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from logging import getLogger

from listentui.listen.interface import Song

IGNORE_LIST: list[str] = [
    "lyric",
    "video",
    "eng",
    "jpn",
    "rom",
]


@dataclass
class Scores:
    title: float
    artist: float
    album: float
    duration: float
    views: float
    bonuses: list[float]
    total: float = field(default_factory=float)

    def __post_init__(self) -> None:
        self.total = sum([self.title, self.artist, self.album, self.duration, self.views, *self.bonuses])


@dataclass
class SearchResult:
    url: str
    title: str
    artist: list[str] | None
    album: str | None
    duration: int | None
    views: int | None
    scores: Scores
    similar: list["SearchResult"]


def strip(string: str) -> str:
    stripped = re.sub(r"[^\w]", "", string).lower()
    for item in IGNORE_LIST:
        stripped = stripped.replace(item, "")
    return stripped


class BaseSearch(ABC):
    def __init__(self, song: Song) -> None:
        super().__init__()
        self.song = song
        self._log = getLogger(__name__)

    @abstractmethod
    def find_best(self) -> SearchResult | list[SearchResult]: ...

    def get_title_variation(self) -> list[str]:
        """returns all possible variation of the song title"""
        variation = [self.song.title, self.song.title_romaji]

        return [variation for variation in variation if variation is not None]

    def get_artist_variation(self) -> list[str]:
        if not self.song.artists:
            return []

        artists: list[str | None] = []
        for artist in self.song.artists:
            artists.extend([artist.name, artist.name_romaji])

        return [artist for artist in artists if artist is not None]

    def get_character_variation(self) -> list[str]:
        if not self.song.characters:
            return []

        characters: list[str | None] = []
        for character in self.song.characters:
            characters.extend([character.name, character.name_romaji])

        return [character for character in characters if character is not None]

    def get_album_variation(self) -> list[str]:
        if not self.song.album:
            return []
        return [name for name in [self.song.album.name, self.song.album.name_romaji] if name is not None]

    def get_duration(self) -> int | None:
        return self.song.duration

    @staticmethod
    def ratio(seq1: str, seq2: str) -> float:
        return SequenceMatcher(a=strip(seq1), b=strip(seq2)).ratio()
