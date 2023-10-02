import asyncio
import datetime
import json
import time
from base64 import b64decode
from dataclasses import dataclass
from functools import wraps
from string import Template
from threading import Lock
from types import TracebackType
from typing import Any, Callable, Coroutine, Optional, Self, Type, Union

from gql import Client, gql
from gql.client import ReconnectingAsyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.requests import RequestsHTTPTransport
from graphql import DocumentNode

from .types import (Album, AlbumID, Artist, ArtistID, Character, CharacterID,
                    CurrentUser, Link, PlayStatistics, Song, SongID, Source,
                    SourceID, SystemFeed, User)


class NotAuthenticatedException(Exception):
    pass


def requires_auth(func: Callable[..., Coroutine[Any, Any, Any]]) -> Any:
    @wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not self._headers.get('Authorization', None):
            raise NotAuthenticatedException("Not logged in")
        return await func(self, *args, **kwargs)
    return wrapper


def requires_auth_sync(func: Callable[..., Any]) -> Any:
    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not self._headers.get('Authorization', None):
            raise NotAuthenticatedException("Not logged in")
        return func(self, *args, **kwargs)
    return wrapper


@dataclass
class Queries:
    login: DocumentNode
    user: DocumentNode
    album: DocumentNode
    artist: DocumentNode
    character: DocumentNode
    favorite_song: DocumentNode
    check_favorite: DocumentNode
    song: DocumentNode
    source: DocumentNode
    play_statistic: DocumentNode
    search: DocumentNode


class BaseClient:
    _ENDPOINT = 'https://listen.moe/graphql'
    _SYSTEM_COUNT = 10
    _SYSTEM_OFFSET = 0

    @staticmethod
    def _build_queries():
        base = {
            "user": """
                        uuid
                        username
                        displayName
                        bio
                        favorites {
                            count
                        }
                        uploads {
                            count
                        }
                        requests {
                            count
                        }
                    """,
            "song": """
                        id
                        title
                        sources {
                            id
                            name
                            nameRomaji
                            image
                        }
                        artists {
                            id
                            name
                            nameRomaji
                            image
                            characters {
                                id
                                name
                                nameRomaji
                            }
                        }
                        characters {
                            id
                            name
                            nameRomaji
                        }
                        albums {
                            id
                            name
                            nameRomaji
                            image
                        }
                        duration
                        played
                        titleRomaji
                        snippet
                    """,
            "generic": """
                        id
                        name
                        nameRomaji
                    """,
        }
        login = Template("""
            mutation login($$username: String!, $$password: String!, $$systemOffset: Int!, $$systemCount: Int!) {
                login(username: $$username, password: $$password) {
                    user {
                        ${user}
                        systemFeed(offset: $$systemOffset, count: $$systemCount) {
                            type
                            createdAt
                            song {
                                ${song}
                            }
                        }
                    }
                    token
                }
            }
        """).safe_substitute(base)
        user = Template("""
            query user($$username: String!, $$systemOffset: Int!, $$systemCount: Int!) {
                user(username: $$username) {
                    ${user}
                    systemFeed(offset: $$systemOffset, count: $$systemCount) {
                        type
                        createdAt
                        song {
                            ${song}
                        }
                    }
                }
            }
        """).safe_substitute(base)
        album = Template("""
            query album($$id: Int!) {
                album(id: $$id) {
                    ${generic}
                    image
                }
            }
        """).safe_substitute(base)
        artist = Template("""
            query artist($$id: Int!) {
                artist(id: $$id) {
                    ${generic}
                    image
                    characters {
                        ${generic}
                    }
                }
            }
        """).safe_substitute(base)
        character = Template("""
            query character($$id: Int!) {
                character(id: $$id) {
                    ${generic}
                }
            }
        """).safe_substitute(base)
        song = Template("""
            query song($$id: Int!) {
                song(id: $$id) {
                    ${song}
                }
            }
        """).safe_substitute(base)
        source = Template("""
            query source($$id: Int!) {
                source(id: $$id) {
                    ${generic}
                    image
                }
            }
        """).safe_substitute(base)
        check_favorite = """
            query checkFavorite($songs: [Int!]!) {
                checkFavorite(songs: $songs)
            }
        """
        favorite_song = """
            mutation favoriteSong($id: Int!) {
                favoriteSong(id: $id) {
                    id
                }
            }
        """
        play_statistic = Template("""
            query play_statistic($count: Int!, $offset: Int) {
                playStatistics(count: $count, offset: $offset) {
                    songs {
                        createdAt
                        song {
                            ${song}
                        }
                        requester {
                            ${user}
                        }
                    }
                }
            }
        """).safe_substitute(base)
        search = Template("""
            query search($term: ID!, $favoritesOnly: Boolean) {
                search(query: $term, favoritesOnly: $favoritesOnly) {
                    ... on Song {
                        ${song}
                    }
                }
            }
        """).safe_substitute(base)

        return Queries(
            login=gql(login),
            user=gql(user),
            album=gql(album),
            artist=gql(artist),
            character=gql(character),
            check_favorite=gql(check_favorite),
            favorite_song=gql(favorite_song),
            song=gql(song),
            source=gql(source),
            play_statistic=gql(play_statistic),
            search=gql(search)
        )
    _QUERIES = _build_queries()

    def __init__(self) -> None:
        self._user: CurrentUser | None = None
        self._headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        self.queries = self._QUERIES

    @property
    def headers(self):
        return self._headers

    @property
    def current_user(self) -> None | CurrentUser:
        if not self._user:
            return
        return self._user

    @staticmethod
    def _validate_token(token: str) -> bool:
        jwt_payload: dict[str, Any] = json.loads(b64decode(token.split('.')[1] + '=='))
        if time.time() >= jwt_payload['exp']:
            return False
        return True


class AIOListen(BaseClient):
    def __init__(self, user: CurrentUser | None = None) -> None:
        super().__init__()
        self._loop = asyncio.get_event_loop()
        self._client: Client
        self._session: ReconnectingAsyncClientSession
        if user:
            self._token = user.token
            self._user = user

    @property
    def current_user(self) -> None | CurrentUser:
        if not self._user:
            return None
        return self._user

    @classmethod
    def login(cls: Type[Self], username: str, password: str, token: Optional[str] = None) -> Self:  # type: ignore
        if token:
            if not cls._validate_token(token):
                return cls.login(username, password)
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        if token:
            headers.update({'Authorization': f'Bearer {token}'})
        transport = RequestsHTTPTransport(url=Listen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)

        if token:
            query = cls._QUERIES.user
            params = {'username': username, "systemOffset": cls._SYSTEM_OFFSET, "systemCount": cls._SYSTEM_COUNT}
            res = client.execute(document=query, variable_values=params)  # pyright: ignore
            user = res['user']
        else:
            query = cls._QUERIES.login
            params = {'username': username,
                      'password': password,
                      "systemOffset": cls._SYSTEM_OFFSET,
                      "systemCount": cls._SYSTEM_COUNT}
            res = client.execute(document=query, variable_values=params)  # pyright: ignore
            user = res['login']['user']
            token: str = res['login']['token']

        return cls(CurrentUser(
            uuid=user['uuid'],
            username=user['username'],
            display_name=user['displayName'],
            bio=user['bio'],
            favorites=user['favorites']['count'],
            uploads=user['uploads']['count'],
            requests=user['requests']['count'],
            feed=[SystemFeed.from_data(feed) for feed in user['systemFeed']],
            token=token
        ))

    async def __aenter__(self):
        if self._user:
            self._headers.update({'Authorization': f'Bearer {self._user.token}'})
        self._transport = AIOHTTPTransport(self._ENDPOINT, headers=self._headers)
        self._client = Client(transport=self._transport)
        self._session = await self._client.connect_async(reconnecting=True)  # pyright: ignore
        return self

    async def __aexit__(self,
                        exc_type: Optional[Type[BaseException]],
                        exc_value: Optional[BaseException],
                        trace: Optional[TracebackType]
                        ) -> None:
        await self._client.close_async()

    async def update_current_user(self) -> CurrentUser | None:
        if not self._user:
            return
        current_user = self._user
        user = await self.user(current_user.username)
        if not user:
            return
        self._user = CurrentUser(user.uuid,
                                 user.username,
                                 user.display_name,
                                 user.bio,
                                 user.favorites,
                                 user.uploads,
                                 user.requests,
                                 user.feed, current_user.token)
        return self._user

    # queries
    async def album(self, id: Union[AlbumID, int]) -> Album | None:
        query = self.queries.album
        params = {'id': id}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        album = res.get('album', None)
        if not album:
            return None
        return Album(
            id=album['id'],
            name=album['name'],
            name_romaji=album['nameRomaji'],
            image=Link.from_name('albums', album['image'])
        )

    async def artist(self, id: Union[ArtistID, int]) -> Artist | None:
        query = self.queries.artist
        params = {'id': id}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        artist = res.get('artist', None)
        if not artist:
            return None
        return Artist(
            id=artist['id'],
            name=artist['name'],
            name_romaji=artist['nameRomaji'],
            image=Link.from_name('artists', artist['image']),
            character=[
                Character(character['id']) for character in artist['characters']
            ] if len(artist['characters']) != 0 else None
        )

    async def character(self, id: Union[CharacterID, int]) -> Character | None:
        query = self.queries.character
        params = {'id': id}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        character = res.get('character', None)
        if not character:
            return None
        return Character(
            id=character['id'],
            name=character['name'],
            name_romaji=character['nameRomaji']
        )

    async def song(self, id: Union[SongID, int]) -> Song | None:
        query = self.queries.song
        params = {'id': id}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        song = res.get('song', None)
        if not song:
            return None
        return Song.from_data(song)

    async def source(self, id: Union[SourceID, int]) -> Source | None:
        query = self.queries.source
        params = {'id': id}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        source = res.get('source', None)
        if not source:
            return None
        return Source(
            id=source['id'],
            name=source['name'],
            name_romaji=source['nameRomaji'],
            image=Link.from_name('sources', source['image'])
        )

    async def user(self, username: str, system_offset: int = 0, system_count: int = 5) -> User | None:
        query = self.queries.user
        params = {'username': username, "systemOffset": system_offset, "systemCount": system_count}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        user = res.get('user', None)
        if not user:
            return None
        return User(
            uuid=user['uuid'],
            username=user['username'],
            display_name=user['displayName'],
            bio=user['bio'],
            favorites=user['favorites']['count'],
            uploads=user['uploads']['count'],
            requests=user['requests']['count'],
            feed=[SystemFeed.from_data(feed) for feed in user['systemFeed']]
        )

    async def play_statistic(self, count: Optional[int] = 50, offset: Optional[int] = 0) -> list[PlayStatistics]:
        query = self.queries.play_statistic
        params = {'count': count, 'offset': offset}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        songs = res['playStatistics']['songs']
        return [PlayStatistics(
            created_at=datetime.datetime.fromtimestamp(round(int(song['createdAt']) / 1000)),
            song=Song.from_data(song['song'])
        ) for song in songs]

    async def search(self, term: str, count: Optional[int] = None, favorite_only: Optional[bool] = False) -> list[Song]:
        query = self.queries.search
        params = {'term': term, 'favoritesOnly': favorite_only}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        data = [Song.from_data(data) for data in res['search']]

        if count:
            return data[:count]
        return data

    @requires_auth
    async def check_favorite(self, song: Union[SongID, int]) -> bool:
        query = self.queries.check_favorite
        params = {"songs": song}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        favorite = res['checkFavorite']
        if song in favorite:
            return True
        return False

    # mutations
    @requires_auth
    async def favorite_song(self, song: Union[SongID, int]) -> None:
        query = self.queries.favorite_song
        params = {"id": song}
        await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        return


class Listen(BaseClient):
    def __init__(self, user: CurrentUser | None = None) -> None:
        super().__init__()
        if user:
            self._token = user.token
            self._update_header({'Authorization': f'Bearer {user.token}'})
            self._user = user
        self._transport = RequestsHTTPTransport(url=self._ENDPOINT, headers=self._headers, retries=3)
        self._client = Client(transport=self._transport)
        self._lock = Lock()

    @classmethod
    def login(cls: Type[Self], username: str, password: str, token: Optional[str] = None) -> Self:  # type: ignore
        if token:
            if not cls._validate_token(token):
                return cls.login(username, password)
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        if token:
            headers.update({'Authorization': f'Bearer {token}'})
        transport = RequestsHTTPTransport(url=Listen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)

        if token:
            query = cls._QUERIES.user
            params = {'username': username, "systemOffset": cls._SYSTEM_OFFSET, "systemCount": cls._SYSTEM_COUNT}
            res = client.execute(document=query, variable_values=params)  # pyright: ignore
            user = res['user']
        else:
            query = cls._QUERIES.login
            params = {'username': username,
                      'password': password,
                      "systemOffset": cls._SYSTEM_OFFSET,
                      "systemCount": cls._SYSTEM_COUNT}
            res = client.execute(document=query, variable_values=params)  # pyright: ignore
            user = res['login']['user']
            token: str = res['login']['token']

        return cls(CurrentUser(
            uuid=user['uuid'],
            username=user['username'],
            display_name=user['displayName'],
            bio=user['bio'],
            favorites=user['favorites']['count'],
            uploads=user['uploads']['count'],
            requests=user['requests']['count'],
            feed=[SystemFeed.from_data(feed) for feed in user['systemFeed']],
            token=token
        ))

    def _update_header(self, header: dict[str, Any]):
        self._headers.update(header)
        self._transport = RequestsHTTPTransport(url=self._ENDPOINT, headers=self._headers, retries=3)
        self._client = Client(transport=self._transport)

    def update_current_user(self) -> None | CurrentUser:
        if not self._user:
            return
        current_user = self._user
        user = self.user(current_user.username)
        if not user:
            return
        self._user = CurrentUser(user.uuid,
                                 user.username,
                                 user.display_name,
                                 user.bio,
                                 user.favorites,
                                 user.uploads,
                                 user.requests,
                                 user.feed, current_user.token)
        return self._user

    # queries
    def album(self, id: Union[AlbumID, int]) -> Album | None:
        with self._lock:
            query = self.queries.album
            params = {'id': id}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            album = res.get('album', None)
            if not album:
                return None
            return Album(
                id=album['id'],
                name=album['name'],
                name_romaji=album['nameRomaji'],
                image=Link.from_name('albums', album['image'])
            )

    def artist(self, id: Union[ArtistID, int]) -> Artist | None:
        with self._lock:
            query = self.queries.artist
            params = {'id': id}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            artist = res.get('artist', None)
            if not artist:
                return None
            return Artist(
                id=artist['id'],
                name=artist['name'],
                name_romaji=artist['nameRomaji'],
                image=Link.from_name('artists', artist['image']),
                character=[
                    Character(character['id'],
                              character['name'],
                              character['nameRomaji']) for character in artist['characters']
                ] if len(artist['characters']) != 0 else None
            )

    def character(self, id: Union[CharacterID, int]) -> Character | None:
        with self._lock:
            query = self.queries.character
            params = {'id': id}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            character = res.get('character', None)
            if not character:
                return None
            return Character(
                id=character['id'],
                name=character['name'],
                name_romaji=character['nameRomaji']
            )

    def song(self, id: Union[SongID, int]) -> Song | None:
        with self._lock:
            query = self.queries.song
            params = {'id': id}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            song = res.get('song', None)
            if not song:
                return None
            return Song.from_data(song)

    def source(self, id: Union[SourceID, int]) -> Source | None:
        with self._lock:
            query = self.queries.source
            params = {'id': id}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            source = res.get('source', None)
            if not source:
                return None
            return Source(
                id=source['id'],
                name=source['name'],
                name_romaji=source['nameRomaji'],
                image=Link.from_name('sources', source['image'])
            )

    def user(self, username: str, system_offset: int = 0, system_count: int = 5) -> User | None:
        with self._lock:
            query = self.queries.user
            params = {'username': username, "systemOffset": system_offset, "systemCount": system_count}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            user = res.get('user', None)
            if not user:
                return None
            return User(
                uuid=user['uuid'],
                username=user['username'],
                display_name=user['displayName'],
                bio=user['bio'],
                favorites=user['favorites']['count'],
                uploads=user['uploads']['count'],
                requests=user['requests']['count'],
                feed=[SystemFeed.from_data(feed) for feed in user['systemFeed']]
            )

    def play_statistic(self, count: Optional[int] = 50, offset: Optional[int] = 0) -> list[PlayStatistics]:
        with self._lock:
            query = self.queries.play_statistic
            params = {'count': count, 'offset': offset}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            songs = res['playStatistics']['songs']
            return [PlayStatistics(
                created_at=datetime.datetime.fromtimestamp(round(int(song['createdAt']) / 1000)),
                song=Song.from_data(song['song'])
            ) for song in songs]

    def search(self, term: str, count: Optional[int] = None, favorite_only: Optional[bool] = False) -> list[Song]:
        with self._lock:
            query = self.queries.search
            params = {'term': term, 'favoritesOnly': favorite_only}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            data = [Song.from_data(data) for data in res['search']]

            if count:
                return data[:count]
            return data

    @requires_auth_sync
    def check_favorite(self, song: Union[SongID, int]) -> bool:
        with self._lock:
            query = self.queries.check_favorite
            params = {"songs": song}
            res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
            favorite = res['checkFavorite']
            if song in favorite:
                return True
            return False

    # mutation
    @requires_auth_sync
    def favorite_song(self, song: Union[SongID, int]) -> None:
        with self._lock:
            query = self.queries.favorite_song
            params = {"id": song}
            self._client.execute(document=query, variable_values=params)  # pyright: ignore
            return


if __name__ == "__main__":
    from rich.pretty import pprint

    async def main():
        async with AIOListen() as listen:
            pprint(await listen.search("nanahira", 2, favorite_only=True))
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
