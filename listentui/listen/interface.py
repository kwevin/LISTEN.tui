from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import time
from typing import Any, ClassVar, Literal, NewType, Self, Type, Union

from markdownify import markdownify  # type: ignore

AlbumID = NewType("AlbumID", int)
ArtistID = NewType("ArtistID", int)
CharacterID = NewType("CharacterID", int)
SongID = NewType("SongID", int)
SourceID = NewType("SourceID", int)


class ConfigurableBase:
    prefer_romaji_first: ClassVar[bool] = False

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        raise NotImplementedError()

    @staticmethod
    def to_markdown(string: str) -> str:
        return markdownify(string)  # type: ignore

    def romaji_first(self, override: bool | None = None) -> bool:
        return override or self.prefer_romaji_first


@dataclass
class Socials(ConfigurableBase):
    name: str
    url: str

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(name=data["name"], url=data["url"])


@dataclass
class Image(ConfigurableBase):
    name: str
    url: str

    @classmethod
    def from_source(
        cls: Type[Self], source: Literal["albums", "artists", "sources"], value: str | None = None
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
class User(ConfigurableBase):
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

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(
            uuid=data["uuid"],
            username=data["username"],
            display_name=data["displayName"],
            bio=User.to_markdown(data["bio"]) if data["bio"] else None,
            favorites=data["favorites"]["count"],
            uploads=data["uploads"]["count"],
            requests=data["requests"]["count"],
            feeds=[SystemFeed.from_data(feed) for feed in data["systemFeed"]],
        )


@dataclass
class CurrentUser(User):
    token: str
    password: str

    @classmethod
    def from_data_with_password(cls: Type[Self], user: dict[str, Any], token: str, password: str) -> Self:
        return cls(
            uuid=user["uuid"],
            username=user["username"],
            display_name=user["displayName"],
            bio=CurrentUser.to_markdown(user["bio"]) if user["bio"] else None,
            favorites=user["favorites"]["count"],
            uploads=user["uploads"]["count"],
            requests=user["requests"]["count"],
            feeds=[SystemFeed.from_data(feed) for feed in user["systemFeed"]],
            token=token,
            password=password,
        )


@dataclass
class Album(ConfigurableBase):
    id: AlbumID
    name: str | None
    name_romaji: str | None
    image: Image | None
    songs: list[Song] | None = None
    artists: list[Artist] | None = None
    socials: list[Socials] | None = None
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/albums/{self.id}"

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(
            id=data["id"],
            name=data.get("name"),
            name_romaji=data.get("nameRomaji"),
            image=Image.from_source("albums", data["image"]) if data.get("image") else None,
            songs=[Song.from_data(song) for song in data["songs"]] if data.get("songs") else None,
            artists=[Artist.from_data(artist) for artist in data["artists"]] if data.get("artists") else None,
            socials=[Socials.from_data(social) for social in data["links"]] if data.get("links") else None,
        )

    def format_name(self, *, romaji_first: bool | None = None) -> str:
        name = (self.name_romaji or self.name) if self.romaji_first(romaji_first) else (self.name or self.name_romaji)
        return name or ""

    def format_socials(self, *, sep: str = ", ", use_app: bool = False) -> str:
        if not self.socials:
            return ""
        if use_app:
            return f"{sep}".join(
                [f"[@click=app.handle_url('{social.url}')]{social.name}[/]" for social in self.socials]
            )
        return f"{sep}".join([f"[link={social.url}]{social.name}[/link]" for social in self.socials])


@dataclass
class Artist(ConfigurableBase):
    id: ArtistID
    name: str | None
    name_romaji: str | None
    image: Image | None
    characters: list[Character] | None
    socials: list[Socials] | None = None
    albums: list[Album] | None = None
    songs_without_album: list[Song] | None = None
    album_count: int | None = None
    song_count: int = field(init=False)
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/artists/{self.id}"
        total = 0
        if self.albums:
            for album in self.albums:
                if album.songs:
                    total += len(album.songs)
        if self.songs_without_album:
            total += len(self.songs_without_album)
        self.song_count = total

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Artist):
            raise Exception("Not supported")
        return self.id == value.id

    def __hash__(self) -> int:
        return hash(f"{self.id}+{self.name}+{self.name_romaji}")

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(
            id=data["id"],
            name=data.get("name"),
            name_romaji=data.get("nameRomaji"),
            image=Image.from_source("artists", data["image"]),
            characters=[Character.from_data(character) for character in data["characters"]]
            if data.get("characters") and len(data["characters"]) != 0
            else None,
            socials=[Socials.from_data(social) for social in data["links"]] if data.get("links") else None,
            album_count=len(data["albums"]) if data.get("albums") else None,
            albums=[Album.from_data(album) for album in data["albums"]]
            if data.get("albums") and len(data["albums"]) != 0
            else None,
            songs_without_album=[Song.from_data(song) for song in data["songsWithoutAlbum"]]
            if data.get("songsWithoutAlbum") and len(data["songsWithoutAlbum"]) != 0
            else None,
        )

    def format_name(self, *, romaji_first: bool | None = None) -> str:
        name = (self.name_romaji or self.name) if self.romaji_first(romaji_first) else (self.name or self.name_romaji)
        return name or ""

    def format_socials(self, *, sep: str = ", ", use_app: bool = False) -> str:
        if not self.socials:
            return ""
        if use_app:
            return f"{sep}".join(
                [f"[@click=app.handle_url('{social.url}')]{social.name}[/]" for social in self.socials]
            )
        return f"{sep}".join([f"[link={social.url}]{social.name}[/link]" for social in self.socials])


@dataclass
class Character(ConfigurableBase):
    id: CharacterID
    name: str | None = None
    name_romaji: str | None = None
    albums: list[Album] | None = None
    album_count: int | None = None
    song_count: int = field(init=False)
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/characters/{self.id}"
        total = 0
        if self.albums:
            for album in self.albums:
                if album.songs:
                    total += len(album.songs)
        self.song_count = total

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(
            id=data["id"],
            name=data.get("name"),
            name_romaji=data.get("nameRomaji"),
            album_count=len(data["albums"]) if data.get("albums") else None,
            albums=[Album.from_data(album) for album in data["albums"]]
            if data.get("albums") and len(data["albums"]) != 0
            else None,
        )

    def format_name(self, romaji_first: bool | None = None) -> str:
        name = (self.name_romaji or self.name) if self.romaji_first(romaji_first) else (self.name or self.name_romaji)
        return name or ""


@dataclass
class Source(ConfigurableBase):
    id: SourceID
    name: str | None
    name_romaji: str | None
    image: Image | None
    description: str | None = None
    socials: list[Socials] | None = None
    songs: list[Song] | None = None
    songs_without_album: list[Song] | None = None
    link: str = field(init=False)

    def __post_init__(self):
        self.link = f"https://listen.moe/sources/{self.id}"
        if self.description:
            self.description = self.to_markdown(self.description)

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(
            id=data["id"],
            name=data.get("name"),
            name_romaji=data.get("nameRomaji"),
            image=Image.from_source("sources", data["image"]),
            description=data.get("description"),
            socials=[Socials.from_data(social) for social in data["links"]] if data.get("links") else None,
            songs=[Song.from_data(song) for song in data["songs"]] if data.get("songs") else None,
            songs_without_album=[Song.from_data(song) for song in data["songsWithoutAlbum"]]
            if data.get("songsWithoutAlbum") and len(data["songsWithoutAlbum"]) != 0
            else None,
        )

    def format_name(self, *, romaji_first: bool | None = None) -> str:
        name = (self.name_romaji or self.name) if self.romaji_first(romaji_first) else (self.name or self.name_romaji)
        return name or ""

    def format_socials(self, *, sep: str = ", ", use_app: bool = False) -> str:
        if not self.socials:
            return ""
        if use_app:
            return f"{sep}".join(
                [f"[@click=app.handle_url('{social.url}')]{social.name}[/]" for social in self.socials]
            )
        return f"{sep}".join([f"[link={social.url}]{social.name}[/link]" for social in self.socials])


@dataclass
class Requester(ConfigurableBase):
    uuid: str
    username: str
    display_name: str
    link: str = field(init=False)

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(uuid=data["uuid"], username=data["username"], display_name=data["displayName"])

    def __post_init__(self):
        self.link = f"https://listen.moe/u/{self.username}"


@dataclass
class Uploader(Requester):
    pass


@dataclass
class Event(ConfigurableBase):
    id: str
    name: str
    slug: str
    image: str
    presence: str | None = None

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(id=data["id"], name=data["name"], slug=data["slug"], image=data["image"], presence=data["presence"])


@dataclass
class Song(ConfigurableBase):
    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(
            id=data["id"],
            title=data["title"],
            title_romaji=data.get("titleRomaji"),
            source=Source.from_data(data["sources"][0]) if data.get("sources") else None,
            artists=[Artist.from_data(artist) for artist in data["artists"]] if data.get("artists") else None,
            album=Album.from_data(data["albums"][0]) if data.get("albums") else None,
            characters=[Character.from_data(chara) for chara in data["characters"]] if data.get("characters") else None,
            duration=data.get("duration"),
            time_end=round(time() + data["duration"]) if data.get("duration") else round(time()),
            snippet=data.get("snippet"),
            played=data.get("played"),
            last_played=datetime.fromtimestamp(int(date) / 1000) if (date := data.get("lastPlayed")) else None,
            uploader=Uploader.from_data(data["uploader"]) if data.get("uploader") else None,
        )

    def get_artist_list(self) -> list[tuple[Artist, Character | None]]:
        if not self.artists:
            return []

        character_map: dict[int, Character] = {}
        if self.characters:
            character_map = {character.id: character for character in self.characters}

        artist_list: list[tuple[Artist, Character | None]] = []
        for artist in self.artists:
            characters_in_songs = []
            if artist.characters:
                # should only return either an empty list or one result
                characters_in_songs = [character for character in artist.characters if character_map.get(character.id)]
            artist_list.append((artist, characters_in_songs[0] if characters_in_songs else None))

        return artist_list

    def get_artist_strings(self, *, wrap_cv: bool = True, romaji_first: bool | None = None) -> list[tuple[str, str]]:
        artist_list = self.get_artist_list()
        artist_set: list[tuple[str, str]] = []

        for artist, character in artist_list:
            artist_name = artist.format_name(romaji_first=romaji_first)
            character_name = ""
            if character:
                character_name = character.format_name(romaji_first=romaji_first)

            if wrap_cv:
                artist_set.append((character_name, f"(CV: {artist_name})"))
            else:
                artist_set.append((character_name, artist_name))

        return artist_set

    def format_artists_list(self, *, show_character: bool = True, romaji_first: bool | None = None) -> list[str]:
        artist_list = self.get_artist_list()
        artist_strings: list[str] = []

        for artist, character in artist_list:
            artist_name = artist.format_name(romaji_first=romaji_first)

            if show_character:
                character_name = character.format_name(romaji_first=romaji_first) if character else None
                artist_strings.append(f"{character_name} (CV: {artist_name})" if character_name else artist_name)
            else:
                artist_strings.append(f"{artist_name}")

        return artist_strings

    def format_artists(self, *, sep: str = ", ", show_character: bool = True, romaji_first: bool | None = None) -> str:
        formatted_artist = self.format_artists_list(show_character=show_character, romaji_first=romaji_first)
        if not formatted_artist:
            return ""
        return sep.join(formatted_artist)

    def artist_image(self) -> str | None:
        if not self.artists:
            return None
        if self.artists[0].image:
            return self.artists[0].image.url
        return None

    def _format(self, albs: Union[Album, Source], embed_link: bool = False) -> str:
        name = (albs.name_romaji or albs.name) if self.romaji_first() else (albs.name or albs.name_romaji)
        if not name:
            return ""
        if embed_link:
            return f"[link={albs.link}]{name}[/link]"
        return name

    def format_album(self, *, embed_link: bool = False) -> str:
        if not self.album:
            return ""
        return self._format(self.album, embed_link)

    def format_source(self, *, embed_link: bool = False) -> str:
        if not self.source:
            return ""
        return self._format(self.source, embed_link)

    def format_title(self) -> str:
        title = (self.title_romaji or self.title) if self.romaji_first() else (self.title or self.title_romaji)
        return title or ""

    def album_image(self):
        if self.album and self.album.image:
            return self.album.image.url
        return None

    def source_image(self):
        if self.source and self.source.image:
            return self.source.image.url
        return None

    id: SongID
    title: str | None
    source: Source | None
    artists: list[Artist] | None
    characters: list[Character] | None
    album: Album | None
    duration: int | None
    time_end: int
    uploader: Uploader | None = None
    snippet: str | None = None
    played: int | None = None
    title_romaji: str | None = None
    last_played: datetime | None = None


@dataclass
class SystemFeed(ConfigurableBase):
    type: ActivityType
    created_at: datetime
    song: Song | None
    activity: str = field(init=False)

    class ActivityType(Enum):
        # Someone commented on the user's feed.
        COMMENTED = 1
        # The user favorited a song
        FAVORITED = 2
        # The user uploaded a song
        UPLOADED = 3
        # The user approved an upload (only admins)
        APPROVEDUPLOAD = 4

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
            case _:
                self.activity = "User did something"


@dataclass
class PlayStatistics(ConfigurableBase):
    created_at: datetime
    song: Song
    requester: Requester | None

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        return cls(
            created_at=datetime.fromtimestamp(round(int(data["createdAt"]) / 1000)),
            song=Song.from_data(data["song"]),
            requester=Requester.from_data(data["requester"]) if data["requester"] else None,
        )


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
            requester=Requester.from_data(data["d"]["requester"]) if data["d"].get("requester") else None,
            event=Event.from_data(data["d"]["event"]) if data["d"].get("event") else None,
            song=Song.from_data(data["d"]["song"]),
            last_played=[Song.from_data(song) for song in data["d"]["lastPlayed"]],
        )

    _op: int
    _t: str
    song: Song
    requester: Requester | None
    start_time: datetime
    last_played: list[Song]
    listener: int
    event: Event | None = None
