from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from logging import getLogger
from typing import Any, Callable

from listentui.listen.interface import Song, SongID

IGNORE_LIST: list[str] = [
    "lyric",
    "video",
    "eng",
    "jpn",
    "rom",
]

type ItemSearchCallback = Callable[[SongID, DownloadItem, tuple[int, int]], Any]
"""SongID, downloadItem (pos, total)"""

type ItemDownloadCallback = Callable[[SongID, DownloadItem, float], Any]
"""SongID, downloadItem, progress"""


@dataclass
class Scores:
    title: float
    artist: float
    album: float
    bonuses: list[float]
    total: float = field(default_factory=float)

    def __post_init__(self) -> None:
        self.total = sum([self.title, self.artist, self.album, *self.bonuses])


@dataclass
class SongMetadata:
    url: str
    provider: str
    title: str
    artists: list[str]
    scores: Scores
    album: str | None = None
    source: str | None = None
    alternate_title: str | None = None
    lyrics: str | None = None
    other: str | None = None

    def __eq__(self, value: object) -> bool:
        assert isinstance(value, SongMetadata)
        return self.url == value.url and self.provider == value.provider

    def __hash__(self) -> int:
        return hash(self.url + self.provider)

    # def __lt__(self, value: object) -> bool:
    #     assert isinstance(value, SongMetadata)
    #     return self.scores.total < value.scores.total

    # def __gt__(self, value: object) -> bool:
    #     assert isinstance(value, SongMetadata)
    #     return self.scores.total > value.scores.total


class QueueState(Enum):
    QUEUED = 0
    SEARCHING = 1
    NOT_FOUND = 2
    FOUND = 3
    DOWNLOADING = 4
    DONE = 5
    DOWNLOAD_FAILED = 6


@dataclass
class DownloadItem:
    song: Song
    metadata: SongMetadata | None
    all_results: list[SongMetadata]
    state: QueueState = QueueState.QUEUED
    final_artists: str | None = None
    final_title: str | None = None
    final_album: str | None = None
    download_err: int = 0

    def set_metadata(self, metadata: SongMetadata) -> DownloadItem:
        if metadata not in self.all_results:
            self.all_results.append(metadata)
            self.all_results.sort(key=lambda result: result.scores.total, reverse=True)

        self.metadata = metadata
        self.state = QueueState.FOUND
        return self

    def assert_final_metadata(self):
        assert self.final_title is not None
        assert self.final_artists is not None
        assert self.final_album is not None


def strip(string: str) -> str:
    stripped = re.sub(r"[^\w]", "", string).lower()
    for item in IGNORE_LIST:
        stripped = stripped.replace(item, "")
    return stripped


class SupportsURL(ABC):
    @abstractmethod
    def supported_link(self, url: str) -> bool: ...


class AutoFill(SupportsURL, ABC):
    @abstractmethod
    def autofill(self, url: str) -> SongMetadata: ...


class CustomDowloader(SupportsURL, ABC):
    @abstractmethod
    def download(self, url: str): ...


class SearchProvider(ABC):
    def __init__(self) -> None:
        super().__init__()
        self._log = getLogger(__name__)

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def find_best(self, song: Song) -> tuple[SongMetadata | None, list[SongMetadata]]: ...

    @staticmethod
    def get_title_variation(song: Song) -> list[str]:
        """returns all possible variation of the song title"""
        variation = [song.title, song.title_romaji]

        return [variation for variation in variation if variation is not None]

    @staticmethod
    def get_artist_variation(song: Song) -> list[str]:
        if not song.artists:
            return []

        artists: list[str | None] = []
        for artist in song.artists:
            artists.extend([artist.name, artist.name_romaji])

        return [artist for artist in artists if artist is not None]

    @staticmethod
    def get_character_variation(song: Song) -> list[str]:
        if not song.characters:
            return []

        characters: list[str | None] = []
        for character in song.characters:
            characters.extend([character.name, character.name_romaji])

        return [character for character in characters if character is not None]

    @staticmethod
    def get_album_variation(song: Song) -> list[str]:
        if not song.album:
            return []
        return [name for name in [song.album.name, song.album.name_romaji] if name is not None]

    @staticmethod
    def get_duration(song: Song) -> int | None:
        return song.duration

    @staticmethod
    def ratio(seq1: str, seq2: str) -> float:
        return SequenceMatcher(a=strip(seq1), b=strip(seq2)).ratio()
