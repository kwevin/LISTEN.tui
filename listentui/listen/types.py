from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import time
from typing import Any, Literal, NewType, Optional, Self, Type, Union

from markdownify import markdownify  # type: ignore

AlbumID = NewType("AlbumID", int)
ArtistID = NewType("ArtistID", int)
CharacterID = NewType("CharacterID", int)
SongID = NewType("SongID", int)
SourceID = NewType("SourceID", int)


@dataclass
class Socials:
    name: str
    url: str


@dataclass
class Image:
    name: str
    url: str

    @classmethod
    def from_source(
        cls: Type[Self], source: Literal["albums", "artists", "sources"], value: Optional[str] = None
    ) -> Self | None:
        if not value:
            return None

        cdn = "https://cdn.listen.moe"
        match source:
            case "albums":
                url = f"{cdn}/covers/{value}"
            case "artists":
                url = f"{cdn}/artists/{value}"
            case "sources":
                url = f"{cdn}/source/{value}"

        return cls(name=value, url=url)


@dataclass
class User:
    uuid: str
    username: str
    display_name: str
    bio: str | None
    favorites: int
    uploads: int
    requests: int
    feeds: list[SystemFeed]
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/u/{self.username}"

    @staticmethod
    def convert_to_markdown(string: str) -> str:
        return markdownify(string)  # type: ignore


@dataclass
class CurrentUser(User):
    token: str


@dataclass
class Album:
    id: AlbumID
    name: str | None
    name_romaji: str | None
    image: Image | None
    songs: list[Song] | None = None
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/albums/{self.id}"

    def format_name(self, *, romaji_first: bool = True) -> str | None:
        name = self.name_romaji or self.name if romaji_first else self.name
        return name if name else None


@dataclass
class Artist:
    id: ArtistID
    name: str | None
    name_romaji: str | None
    image: Image | None
    characters: list[Character] | None
    socials: list[Socials] | None = None
    song_count: int | None = None
    albums: list[Album] | None = None
    songs_without_album: list[Song] | None = None
    album_count: int | None = None
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/artists/{self.id}"

    def format_name(self, *, romaji_first: bool = True) -> str | None:
        name = self.name_romaji or self.name if romaji_first else self.name
        return name if name else None


@dataclass
class Character:
    id: CharacterID
    name: Optional[str] = None
    name_romaji: Optional[str] = None
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/characters/{self.id}"


@dataclass
class Source:
    id: SourceID
    name: str | None
    name_romaji: str | None
    image: Image | None
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/sources/{self.id}"


@dataclass
class Requester:
    uuid: str
    username: str
    display_name: str
    link: str = field(init=False)

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any] | None) -> Self | None:
        if not data:
            return None
        return cls(uuid=data["uuid"], username=data["username"], display_name=data["displayName"])

    def __post_init__(self):
        self.link = f"https://listen.moe/u/{self.username}"


@dataclass
class Uploader(Requester):
    pass


@dataclass
class Event:
    id: str
    name: str
    slug: str
    image: str
    presence: Optional[str] = None

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any] | None) -> Self | None:
        if not data:
            return None
        return cls(id=data["id"], name=data["name"], slug=data["slug"], image=data["image"], presence=data["presence"])


@dataclass
class Song:
    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        duration = data.get("duration")
        kwargs = {
            "id": data["id"],
            "duration": duration,
            "time_end": round(time() + duration) if duration else round(time()),
            "title": Song._get_title(data),
            "source": Song._get_sources(data),
            "artists": Song._get_artists(data),
            "album": Song._get_albums(data),
            "characters": Song._get_characters(data),
            "snippet": data.get("snippet"),
        }
        if p := data.get("played"):
            kwargs.update({"played": p})
        if p := data.get("titleRomaji"):
            kwargs.update({"title_romaji": p})
        if p := data.get("lastPlayed"):
            kwargs.update({"last_played": datetime.fromtimestamp(int(p) / 1000)})
        if p := data.get("uploader"):
            kwargs.update({"uploader": Uploader.from_data(p)})

        return cls(**kwargs)  # pyright: ignore

    @staticmethod
    def _sanitise(word: str) -> str:
        # TODO: need to see if this affects Textual
        return word
        # return word.replace("\u3099", "\u309B").replace("\u309A", "\u309C").replace("\u200b", "")

    @staticmethod
    def _get_title(song: dict[str, Any]) -> str:
        title: str = song["title"]
        return title

    @staticmethod
    def _get_sources(song: dict[str, Any]) -> Source | None:
        sources = song.get("sources")
        if not sources:
            return None
        source = sources[0]
        return Source(
            id=source["id"],
            name=Song._sanitise(source["name"]) if source.get("name") else None,
            name_romaji=source.get("nameRomaji"),
            image=Image.from_source("sources", source.get("image")),
        )

    @staticmethod
    def _get_artists(song: dict[str, Any]) -> list[Artist] | None:
        artists = song.get("artists")
        if not artists:
            return None
        return [
            Artist(
                id=artist["id"],
                name=Song._sanitise(artist["name"]) if artist.get("name") else None,
                name_romaji=Song._sanitise(artist["nameRomaji"]) if artist.get("nameRomaji") else None,
                image=Image.from_source("artists", artist.get("image")),
                characters=[
                    Character(
                        character["id"],
                        name=Song._sanitise(character["name"]) if character.get("name") else None,
                        name_romaji=Song._sanitise(character["nameRomaji"]) if character.get("nameRomaji") else None,
                    )
                    for character in artist.get("characters")
                ]
                if len(artist.get("characters")) != 0
                else None,
            )
            for artist in artists
        ]

    @staticmethod
    def _get_albums(song: dict[str, Any]) -> Album | None:
        albums = song.get("albums")
        if not albums:
            return None
        album = albums[0]
        return Album(
            id=album["id"],
            name=Song._sanitise(album["name"]) if album.get("name") else None,
            name_romaji=Song._sanitise(album["nameRomaji"]) if album.get("nameRomaji") else None,
            image=Image.from_source("albums", album.get("image")),
        )

    @staticmethod
    def _get_characters(song: dict[str, Any]) -> list[Character] | None:
        characters = song.get("characters")
        if not characters:
            return None
        return [
            Character(
                id=character["id"],
                name=Song._sanitise(character["name"]) if character.get("name") else None,
                name_romaji=Song._sanitise(character["nameRomaji"]) if character.get("nameRomaji") else None,
            )
            for character in characters
        ]

    def _format_artists(
        self,
        count: Optional[int] = None,
        *,
        show_character: bool = True,
        romaji_first: bool = True,
        embed_link: bool = False,
    ) -> list[str] | None:
        if not self.artists:
            return None

        lst_string: list[str] = []
        for idx, artist in enumerate(self.artists):
            if count and idx + 1 > count:
                break
            name = (artist.name_romaji if artist.name_romaji else artist.name) if romaji_first else artist.name

            if show_character and self.characters and artist.characters:
                character_map: dict[int, Character] = {character.id: character for character in self.characters}
                char = next(
                    (
                        character_map.get(character.id)
                        for character in artist.characters
                        if character_map.get(character.id)
                    ),
                    None,
                )
                if name and char:
                    char_name = (char.name_romaji if char.name_romaji else char.name) if romaji_first else char.name
                    if embed_link:
                        e = f"[link={char.link}]{char_name}[/link]"
                        k = f"(CV: [link={artist.link}]{name}[/link])"
                        lst_string.append(f"{e} {k}")
                    else:
                        lst_string.append(f"{char_name} (CV: {name})")
            elif name:
                if embed_link:
                    lst_string.append(f"[link={artist.link}]{name}[/link]")
                else:
                    lst_string.append(name)

        return lst_string

    def format_artists_list(self, *, romaji_first: bool = True) -> list[str] | None:
        return self._format_artists(romaji_first=romaji_first)

    def format_artists(
        self,
        count: Optional[int] = None,
        *,
        show_character: bool = True,
        romaji_first: bool = True,
        embed_link: bool = False,
    ) -> str | None:
        formatted_artist = self._format_artists(
            count=count, show_character=show_character, romaji_first=romaji_first, embed_link=embed_link
        )
        if not formatted_artist:
            return None
        return ", ".join(formatted_artist)

    def artist_image(self) -> str | None:
        if not self.artists:
            return None
        if self.artists[0].image:
            return self.artists[0].image.url
        return None

    def _format(self, albs: Union[Album, Source], romaji_first: bool = True, embed_link: bool = False) -> str | None:
        name = (
            (albs.name_romaji if albs.name_romaji else albs.name)
            if romaji_first
            else albs.name
            if albs.name
            else albs.name_romaji
        )
        if not name:
            return None
        if embed_link:
            return f"[link={albs.link}]{name}[/link]"
        return name

    def format_album(self, *, romaji_first: bool = True, embed_link: bool = False) -> str | None:
        if not self.album:
            return None
        return self._format(self.album, romaji_first, embed_link)

    def format_source(self, *, romaji_first: bool = True, embed_link: bool = False) -> str | None:
        if not self.source:
            return None
        return self._format(self.source, romaji_first, embed_link)

    def format_title(self, *, romaji_first: bool = True) -> str | None:
        title = self.title_romaji or self.title if romaji_first else self.title

        if title:
            return self._sanitise(title)
        return None

    def album_image(self):
        if not self.album:
            return None
        if not self.album.image:
            return None
        return self.album.image.url

    def source_image(self):
        if not self.source:
            return None
        if not self.source.image:
            return None
        return self.source.image.url

    id: SongID
    title: str | None
    source: Source | None
    artists: list[Artist] | None
    characters: list[Character] | None
    album: Album | None
    duration: int | None
    time_end: int
    uploader: Uploader | None = None
    snippet: Optional[str] = None
    played: Optional[int] = None
    title_romaji: Optional[str] = None
    last_played: Optional[datetime] = None


@dataclass
class SystemFeed:
    type: ActivityType
    created_at: datetime
    song: Song | None
    activity: str = field(init=False)

    class ActivityType(Enum):
        FAVORITED = 2
        UPLOADED = 4

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        song = data["song"]
        return cls(
            type=cls.ActivityType.FAVORITED if int(data["type"]) == 2 else cls.ActivityType.UPLOADED,  # noqa: PLR2004
            created_at=datetime.fromtimestamp(round(int(data["createdAt"]) / 1000)),
            song=Song.from_data(song) if song else None,
        )

    def __post_init__(self) -> None:
        match self.type:
            case self.ActivityType.FAVORITED:
                self.activity = "Favorited"
            case self.ActivityType.UPLOADED:
                self.activity = "Uploaded"


@dataclass
class PlayStatistics:
    created_at: datetime
    song: Song
    requester: Requester | None


@dataclass
class ListenWsData:
    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        """
        A dataclass representation of LISTEN.moe websocket data

        Args:
            data `dict`: The websocket data
        Return:
            Self `ListenWsData`
        """
        return cls(
            _op=data["op"],
            _t=data["t"],
            start_time=datetime.fromisoformat(data["d"]["startTime"]),
            listener=data["d"]["listeners"],
            requester=Requester.from_data(data["d"].get("requester")),
            event=Event.from_data(data["d"].get("event")),
            song=Song.from_data(data["d"]["song"]),
            last_played=[Song.from_data(song) for song in data["d"]["lastPlayed"]],
        )

    _op: int
    _t: str
    song: Song
    requester: Requester | None
    start_time: datetime
    """start time in utc"""
    last_played: list[Song]
    listener: int
    event: Optional[Event] = None
