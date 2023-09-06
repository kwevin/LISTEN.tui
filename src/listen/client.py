import asyncio
from dataclasses import dataclass
from functools import wraps
from string import Template
from types import TracebackType
from typing import Any, Callable, Coroutine, Optional, Self, Type

from gql import Client, gql
from gql.client import ReconnectingAsyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.requests import RequestsHTTPTransport
from graphql import DocumentNode

from src.listen.types import (Album, Artist, Character, CurrentUser, Link,
                              Song, Source, SystemFeed, User)


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


class BaseClient:
    _ENDPOINT = 'https://listen.moe/graphql'
    _SYSTEM_COUNT = 5
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
                    """,
            "generic": """
                        id
                        name
                        nameRomaji
                    """,
            "next": """""",
        }
        login = Template("""
            mutation login($$username: String!, $$password: String!, $$systemOffset: Int!, $$systemCount: Int!) {
                login(username: $$username, password: $$password) {
                    user {
                        ${user}
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
        return Queries(
            login=gql(login),
            user=gql(user),
            album=gql(album),
            artist=gql(artist),
            character=gql(character),
            check_favorite=gql(check_favorite),
            favorite_song=gql(favorite_song),
            song=gql(song),
            source=gql(source)
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
    def current_user(self):
        if not self._user:
            return None
        return self._user
    

class AIOListen(BaseClient):
    def __init__(self, user: CurrentUser | None = None) -> None:
        super().__init__()
        self._loop = asyncio.get_event_loop()
        self._client: Client
        self._session: ReconnectingAsyncClientSession
        if user:
            self._token = user.token
            self._user = user

    @classmethod
    def login(cls: Type[Self], username: str, password: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        transport = RequestsHTTPTransport(url=AIOListen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = cls._QUERIES.login
        params = {'username': username, 'password': password, "systemOffset": cls._SYSTEM_OFFSET, "systemCount": cls._SYSTEM_COUNT}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        login = res['login']
        user = res['login']['user']
        return cls(CurrentUser(
            uuid=user['uuid'],
            username=user['username'],
            display_name=user['displayName'],
            bio=user['bio'],
            favorites=user['favorites']['count'],
            uploads=user['uploads']['count'],
            requests=user['requests']['count'],
            feed=[SystemFeed.from_data(feed) for feed in user['systemFeed']],
            token=login['token']
        ))

    @classmethod
    def from_username_token(cls: Type[Self], username: str, token: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        transport = RequestsHTTPTransport(url=AIOListen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = cls._QUERIES.user
        params = {'username': username, "systemOffset": cls._SYSTEM_OFFSET, "systemCount": cls._SYSTEM_COUNT}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        user = res.get('user', None)
        if not user:
            raise Exception("What the")
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

    # queries
    async def album(self, id: int) -> Album | None:
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

    async def artist(self, id: int) -> Artist | None:
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
            character=[Character(character['id']) for character in artist['character']] if len(artist['characters']) != 0 else None
        )

    async def character(self, id: int) -> Character | None:
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
    
    async def song(self, id: int) -> Song | None:
        query = self.queries.song
        params = {'id': id}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        song = res.get('song', None)
        if not song:
            return None
        return Song.from_data(song)

    async def source(self, id: int) -> Source | None:
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

    @requires_auth
    async def check_favorite(self, song: int) -> bool:
        query = self.queries.check_favorite
        params = {"songs": song}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        favorite = res['checkFavorite']
        if song in favorite:
            return True
        return False
    
    # mutations
    @requires_auth
    async def favorite_song(self, song: int):
        query = self.queries.favorite_song
        params = {"id": song}
        await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        return await self.check_favorite(song)


class Listen(BaseClient):
    def __init__(self, user: CurrentUser | None = None) -> None:
        super().__init__()
        if user:
            self._token = user.token
            self._update_header({'Authorization': f'Bearer {user.token}'})
            self._user = user
        self._transport = RequestsHTTPTransport(url=self._ENDPOINT, headers=self._headers, retries=3)
        self._client = Client(transport=self._transport)

    @classmethod
    def login(cls: Type[Self], username: str, password: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        transport = RequestsHTTPTransport(url=Listen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = cls._QUERIES.login
        params = {'username': username, 'password': password, "systemOffset": cls._SYSTEM_OFFSET, "systemCount": cls._SYSTEM_COUNT}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        login = res['login']
        user = res['login']['user']
        return cls(CurrentUser(
            uuid=user['uuid'],
            username=user['username'],
            display_name=user['displayName'],
            bio=user['bio'],
            favorites=user['favorites']['count'],
            uploads=user['uploads']['count'],
            requests=user['requests']['count'],
            feed=[SystemFeed.from_data(feed) for feed in user['systemFeed']],
            token=login['token']
        ))
    
    @classmethod
    def from_username_token(cls: Type[Self], username: str, token: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        transport = RequestsHTTPTransport(url=Listen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = cls._QUERIES.user
        params = {'username': username, "systemOffset": cls._SYSTEM_OFFSET, "systemCount": cls._SYSTEM_COUNT}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        user = res.get('user', None)
        if not user:
            raise Exception("What the")
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
    
    # queries
    def album(self, id: int) -> Album | None:
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

    def artist(self, id: int) -> Artist | None:
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
            character=[Character(character['id'],
                                 character['name'],
                                 character['nameRomaji']) for character in artist['characters']] if len(artist['characters']) != 0 else None
        )

    def character(self, id: int) -> Character | None:
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
    
    def song(self, id: int) -> Song | None:
        query = self.queries.song
        params = {'id': id}
        res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
        song = res.get('song', None)
        if not song:
            return None
        return Song.from_data(song)

    def source(self, id: int) -> Source | None:
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

    @requires_auth_sync
    def check_favorite(self, song: int) -> bool:
        query = self.queries.check_favorite
        params = {"songs": song}
        res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
        favorite = res['checkFavorite']
        if song in favorite:
            return True
        return False
    
    # mutation
    @requires_auth_sync
    def favorite_song(self, song: int):
        query = self.queries.favorite_song
        params = {"id": song}
        self._client.execute(document=query, variable_values=params)  # pyright: ignore
        return self.check_favorite(song)


if __name__ == "__main__":
    async def main():
        async with AIOListen() as listen:
            print(await listen.album(1))
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())

    # async def main():
    #     async with AIOListen.login('username', 'password') as listen:
    #         print(await listen.favorite_song(14))

    # e = Listen()
    # print(e.user('kwin4279'))

    # e = Listen.login('username', 'password')
    # print(e.favorite_song(14))
