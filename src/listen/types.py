from dataclasses import dataclass
from time import time
from typing import Any, Literal, Self, Type

from src.modules.types import Rpc


@dataclass
class Character:
    id: int


@dataclass
class Source:
    id: int
    name: str
    name_romaji: str | None
    image: str | None


@dataclass
class Artist:
    id: int
    name: str
    name_romaji: str | None
    image: str | None
    character: list[Character] | None


@dataclass
class Album:
    id: int
    name: str
    name_romaji: str | None
    image: str | None


@dataclass
class Requester:
    uuid: str
    username: str
    display_name: str

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any] | None) -> Self | None:
        if not data:
            return None
        return cls(
            uuid=data['uuid'],
            username=data['username'],
            display_name=data['displayName']
        )


@dataclass
class Song:

    # def __init__(self, song: dict[str, Any]) -> None:
    #     self.id = song['id']
    #     self.duration = song.get('duration', None)
    #     self.time_end = round(time() + self.duration) if self.duration else round(time())
    #     self.title = Song._get_title(song)
    #     self.sources = Song._get_sources(song)
    #     self.artists = Song._get_artists(song)
    #     self.albums = Song._get_albums(song)
    #     self.characters = Song._get_characters(song)

    #     return

    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        duration = data.get('duration', None)
        return cls(
            id=data['id'],
            duration=duration,
            time_end=round(time() + duration) if duration else round(time()),
            title=Song._get_title(data),
            sources=Song._get_sources(data),
            artists=Song._get_artists(data),
            albums=Song._get_albums(data),
            characters=Song._get_characters(data),
        )
    
    @staticmethod
    def _append_cdn(type: Literal['albums', 'artists', 'sources'], value: str | None) -> str | None:
        if not value:
            return None
        
        cdn = "https://cdn.listen.moe"
        match type:
            case 'albums':
                return f'{cdn}/covers/{value}'
            case 'artists':
                return f'{cdn}/artists/{value}'
            case 'sources':
                return f'{cdn}/source/{value}'

    @staticmethod
    def _get_title(song: dict[str, Any]) -> str:
        return song.get('title', None)
    
    @staticmethod
    def _get_sources(song: dict[str, Any]) -> list[Source] | None:
        sources = song.get('sources', None)
        if not sources:
            return None
        return [Source(
            id=source['id'],
            name=source.get('name', None),
            name_romaji=source.get('nameRomaji', None),
            image=Song._append_cdn('sources', source.get('image', None))
        ) for source in sources]

    @staticmethod
    def _get_artists(song: dict[str, Any]) -> list[Artist] | None:
        artists = song.get('artists')
        if not artists:
            return None
        return [Artist(
            id=artist['id'],
            name=artist.get('name', None),
            name_romaji=artist.get('nameRomaji', None),
            image=Song._append_cdn('artists', artist.get('image', None)),
            character=[Character(character['id']) for character in artist.get('characters')] if len(artist.get('characters')) != 0 else None
        ) for artist in artists]
    
    @staticmethod
    def _get_albums(song: dict[str, Any]) -> list[Album] | None:
        albums = song.get('albums', None)
        if not albums:
            return None
        return [Album(
            id=album['id'],
            name=album.get('name', None),
            name_romaji=album.get('nameRomaji', None),
            image=Song._append_cdn('albums', album.get('image', None))
        ) for album in albums]
    
    @staticmethod
    def _get_characters(song: dict[str, Any]) -> list[Character] | None:
        characters = song.get('characters', None)
        if not characters:
            return None
        return [Character(character['id']) for character in characters]
    
    @staticmethod
    def _list_to_string(lst: list[Artist] | list[Source] | list[Album] | None, romaji_first: bool = True, sep: str = ', ') -> str | None:
        if not lst:
            return None
        lst_string: list[str] = []
        for item in lst:
            if romaji_first:
                name = item.name_romaji if item.name_romaji else item.name
            else:
                name = item.name

            lst_string.append(name)
        return f"{sep}".join(lst_string)

    def artists_to_string(self, romaji_first: bool = True, sep: str = ', ') -> str | None:
        return self._list_to_string(self.artists, romaji_first=romaji_first, sep=sep)
    
    def sources_to_string(self, romaji_first: bool = True, sep: str = ', ') -> str | None:
        return self._list_to_string(self.sources, romaji_first=romaji_first, sep=sep)
    
    def albums_to_string(self, romji_first: bool = True, sep: str = ', ') -> str | None:
        return self._list_to_string(self.albums, romaji_first=romji_first, sep=sep)
    
    @staticmethod
    def _get_image(lst: list[Artist] | list[Source] | list[Album] | None) -> str | None:
        if not lst:
            return None
        for item in lst:
            if item.image:
                return item.image
        return None
    
    def artist_image(self) -> str | None:
        return self._get_image(self.artists)

    def source_image(self) -> str | None:
        return self._get_image(self.sources)

    def album_image(self) -> str | None:
        return self._get_image(self.albums)

    id: int
    title: str | None
    sources: list[Source] | None
    artists: list[Artist] | None
    characters: list[Character] | None
    albums: list[Album] | None
    duration: int | None
    time_end: int


@dataclass
class ListenWsData:

    # def __init__(self,
    #              data: dict[str, Any],
    #              use_artist_in_cover: bool = True,
    #              ) -> None:

    #     self._data = data
    #     self._use_artist_in_cover = use_artist_in_cover
        
    #     self._op = data['op']
    #     self._t = data['t']
    #     self.start_time = data['d']['startTime']
    #     self.listener = data['d']['listeners']
    #     self.requester = data['d'].get('requester', None)
    #     self.event = data['d'].get('event', None)

    #     self.song = Song(data['d']['song'])
    #     self.last_played: list[Song] = []
    #     for song in data['d']['lastPlayed']:
    #         self.last_played.append(Song(song))
    #     return
    
    @classmethod
    def from_data(cls: Type[Self], data: dict[str, Any]) -> Self:
        """
        A dataclass representation of listen.moe websocket data

        Args:
            data `dict`: The websocket data
        Return:
            Self `ListenWsData`
        """
        return cls(
            _op=data['op'],
            _t=data['t'],
            start_time=data['d']['startTime'],
            listener=data['d']['listeners'],
            requester=Requester.from_data(data['d'].get('requester', None)),
            event=data['d'].get('event', None),
            song=Song.from_data(data['d']['song']),
            last_played=[Song.from_data(song) for song in data['d']['lastPlayed']]
        )
        
    _op: int
    _t: str
    song: Song
    requester: Requester | None
    event: str | None
    start_time: str
    last_played: list[Song]
    listener: int
    last_heartbeat: float = time()
    rpc: Rpc | None = None


@dataclass
class MPVData:
    paused: bool | None
    core_idle: bool
    time_remaining: float | None
    volume: float
    ao_volume: float


if __name__ == "__main__":
    import asyncio
    import json

    import websockets.client as websocket
    from rich.pretty import pprint

    async def get_data():
        async for ws in websocket.connect('wss://listen.moe/gateway_v2', ping_interval=None, ping_timeout=None):
            while True:
                data = json.loads(await ws.recv())

                if data['op'] == 1:
                    await ws.close()
                    return data
    loop = asyncio.new_event_loop()
    data = loop.run_until_complete(get_data())
    e = ListenWsData.from_data(data)  # pyright: ignore[reportGeneralTypeIssues]
    pprint(e)
    pprint(e.song.sources_to_string())
    pprint(e.song.artists_to_string())
