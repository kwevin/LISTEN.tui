import asyncio
from functools import wraps
from types import TracebackType
from typing import Any, Callable, Coroutine, Optional, Self, Type

from gql import Client, gql
from gql.client import ReconnectingAsyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.requests import RequestsHTTPTransport

from src.listen.types import (Album, Artist, Character, CurrentUser, Link,
                              Song, Source, User)


class AuthenticationErrorException(Exception):
    pass


def requires_auth(func: Callable[..., Coroutine[Any, Any, Any]]) -> Any:
    @wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not self._headers.get('Authorization', None):
            raise AuthenticationErrorException("Not logged in")
        return await func(self, *args, **kwargs)
    return wrapper


def requires_auth_sync(func: Callable[..., Any]) -> Any:
    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not self._headers.get('Authorization', None):
            raise AuthenticationErrorException("Not logged in")
        return func(self, *args, **kwargs)
    return wrapper


class AIOListen:
    _ENDPOINT = 'https://listen.moe/graphql'

    def __init__(self, user: CurrentUser | None = None) -> None:
        self._user: CurrentUser | None = None
        self._loop = asyncio.get_event_loop()
        self._client: Client
        self._session: ReconnectingAsyncClientSession
        self._headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        if user:
            self._token = user.token
            self._user = user

    @property
    def headers(self):
        return self._headers

    @property
    def current_user(self):
        if not self._user:
            return None
        return self._user

    @classmethod
    def login(cls: Type[Self], username: str, password: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        transport = RequestsHTTPTransport(url=AIOListen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = gql(
            """
            mutation login($username: String!, $password: String!) {
                login(username: $username, password: $password) {
                    user {
                        uuid
                        username
                        displayName
                        bio
                    }
                    token
                }
            }
        """
        )
        params = {'username': username, 'password': password}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        login = res['login']
        user = res['login']['user']
        return cls(CurrentUser(user['uuid'], user['username'], user['displayName'], user['bio'], login['token']))

    @classmethod
    def from_username_token(cls: Type[Self], username: str, token: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        transport = RequestsHTTPTransport(url=AIOListen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = gql(
            """
            query user($username: String!) {
                user(username: $username) {
                    uuid
                    username
                    displayName
                    bio
                }
            }
        """
        )
        params = {'username': username}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        user = res.get('user', None)
        if not user:
            raise Exception("What the")
        return cls(CurrentUser(user['uuid'], user['username'], user['displayName'], user['bio'], token))

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
        query = gql(
            """
            query album($id: Int!) {
                album(id: $id) {
                    id
                    name
                    nameRomaji
                    image
                }
            }
        """
        )
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
        query = gql(
            """
            query artist($id: Int!) {
                artist(id: $id) {
                    id
                    name
                    nameRomaji
                    image
                }
            }
        """
        )
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
        query = gql(
            """
            query character($id: Int!) {
                character(id: $id) {
                    id
                    name
                    nameRomaji
                }
            }

        """
        )
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
        query = gql(
            """
            query song($id: Int!) {
                song(id: $id) {
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
                        }
                    }
                    characters {
                        id
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
                }
            }
        """
        )
        params = {'id': id}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        song = res.get('song', None)
        if not song:
            return None
        return Song.from_data(song)

    async def source(self, id: int) -> Source | None:
        query = gql(
            """
            query source($id: Int!) {
                source(id: $id) {
                    id
                    name
                    nameRomaji
                    image
                }
            }
        """
        )
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
    
    async def user(self, username: str) -> User | None:
        query = gql(
            """
            query user($username: String!) {
                user(username: $username) {
                    id
                    name
                    nameRomaji
                    image
                }
            }
        """
        )
        params = {'username': username}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        user = res.get('user', None)
        if not user:
            return None
        return User(
            uuid=user['uuid'],
            username=user['username'],
            display_name=user['displayName'],
            bio=user['bio']
        )

    @requires_auth
    async def check_favourite(self, song: int) -> bool:
        query = gql(
            """
            query checkFavorite($songs: [Int!]!) {
                checkFavorite(songs: $songs)
            }
        """
        )
        params = {"songs": song}
        res = await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        favourite = res['checkFavorite']
        if song in favourite:
            return True
        return False
    
    # mutations
    @requires_auth
    async def favourite_song(self, song: int):
        query = gql(
            """
            mutation favoriteSong($id: Int!) {
                favoriteSong(id: $id) {
                    id
                }
            }
        """
        )
        params = {"id": song}
        await self._session.execute(document=query, variable_values=params)  # pyright: ignore
        return await self.check_favourite(song)


class Listen:
    _ENDPOINT = 'https://listen.moe/graphql'

    def __init__(self, user: CurrentUser | None = None) -> None:
        self._user: CurrentUser | None = None
        self._headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        if user:
            self._token = user.token
            self._update_header({'Authorization': f'Bearer {user.token}'})
            self._user = user
        self._transport = RequestsHTTPTransport(url=self._ENDPOINT, headers=self._headers, retries=3)
        self._client = Client(transport=self._transport)

    @property
    def headers(self):
        return self._headers
    
    @property
    def current_user(self):
        if not self._user:
            return None
        return self._user
    
    @classmethod
    def login(cls: Type[Self], username: str, password: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
        }
        transport = RequestsHTTPTransport(url=Listen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = gql(
            """
            mutation login($username: String!, $password: String!) {
                login(username: $username, password: $password) {
                    user {
                        uuid
                        username
                        displayName
                        bio
                    }
                    token
                }
            }
        """
        )
        params = {'username': username, 'password': password}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        login = res['login']
        user = res['login']['user']
        return cls(CurrentUser(user['uuid'], user['username'], user['displayName'], user['bio'], login['token']))
    
    @classmethod
    def from_username_token(cls: Type[Self], username: str, token: str) -> Self:
        headers = {
            'Accept': "*/*",
            'content-type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        transport = RequestsHTTPTransport(url=Listen._ENDPOINT, headers=headers, retries=3)
        client = Client(transport=transport)
        query = gql(
            """
            query user($username: String!) {
                user(username: $username) {
                    uuid
                    username
                    displayName
                    bio
                }
            }
        """
        )
        params = {'username': username}
        res = client.execute(document=query, variable_values=params)  # pyright: ignore
        user = res.get('user', None)
        if not user:
            raise Exception("What the")
        return cls(CurrentUser(user['uuid'], user['username'], user['displayName'], user['bio'], token))

    def _update_header(self, header: dict[str, Any]):
        self._headers.update(header)
        self._transport = RequestsHTTPTransport(url=self._ENDPOINT, headers=self._headers, retries=3)
        self._client = Client(transport=self._transport)
    
    # queries
    def album(self, id: int) -> Album | None:
        query = gql(
            """
            query album($id: Int!) {
                album(id: $id) {
                    id
                    name
                    nameRomaji
                    image
                }
            }
        """
        )
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
        query = gql(
            """
            query artist($id: Int!) {
                artist(id: $id) {
                    id
                    name
                    nameRomaji
                    image
                }
            }
        """
        )
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
            character=[Character(character['id']) for character in artist['character']] if len(artist['characters']) != 0 else None
        )

    def character(self, id: int) -> Character | None:
        query = gql(
            """
            query character($id: Int!) {
                character(id: $id) {
                    id
                    name
                    nameRomaji
                }
            }

        """
        )
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
        query = gql(
            """
            query song($id: Int!) {
                song(id: $id) {
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
                        }
                    }
                    characters {
                        id
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
                }
            }
        """
        )
        params = {'id': id}
        res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
        song = res.get('song', None)
        if not song:
            return None
        return Song.from_data(song)

    def source(self, id: int) -> Source | None:
        query = gql(
            """
            query source($id: Int!) {
                source(id: $id) {
                    id
                    name
                    nameRomaji
                    image
                }
            }
        """
        )
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
    
    def user(self, username: str) -> User | None:
        query = gql(
            """
            query user($username: String!) {
                user(username: $username) {
                    uuid
                    username
                    displayName
                    bio
                }
            }
        """
        )
        params = {'username': username}
        res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
        user = res.get('user', None)
        if not user:
            return None
        return User(
            uuid=user['uuid'],
            username=user['username'],
            display_name=user['displayName'],
            bio=user['bio']
        )

    @requires_auth_sync
    def check_favourite(self, song: int) -> bool:
        query = gql(
            """
            query checkFavorite($songs: [Int!]!) {
                checkFavorite(songs: $songs)
            }
        """
        )
        params = {"songs": song}
        res = self._client.execute(document=query, variable_values=params)  # pyright: ignore
        favourite = res['checkFavorite']
        if song in favourite:
            return True
        return False
    
    # mutation
    @requires_auth_sync
    def favourite_song(self, song: int):
        query = gql(
            """
            mutation favoriteSong($id: Int!) {
                favoriteSong(id: $id) {
                    id
                }
            }
        """
        )
        params = {"id": song}
        self._client.execute(document=query, variable_values=params)  # pyright: ignore
        return self.check_favourite(song)


if __name__ == "__main__":
    async def main():
        async with AIOListen() as listen:
            print(await listen.album(1))
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
    # e = Listen()
    # print(e.user('kwin4279'))
