from datetime import datetime
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

from listentui.config import Config
from listentui.listen.client import (AIOListen, Listen,
                                     NotAuthenticatedException)
from listentui.listen.types import (Album, AlbumID, Artist, ArtistID,
                                    Character, CharacterID, CurrentUser,
                                    PlayStatistics, Song, SongID, Source,
                                    SourceID, User)

_ALBUM = AlbumID(4644)
_SONG = SongID(22488)
_ARTIST = ArtistID(215)
_CHARACTER = CharacterID(403)
_SOURCE = SourceID(507)
_ALBUM_LINK = 'https://listen.moe/albums/'
_ARTIST_LINK = 'https://listen.moe/artists/'
_CHARACTER_LINK = 'https://listen.moe/characters/'
_ALBUM_CDN_LINK = 'https://cdn.listen.moe/covers/'
_ARTIST_CDN_LINK = 'https://cdn.listen.moe/artists/'


class TestListenUnauth(TestCase):

    def setUp(self) -> None:
        self.listen = Listen()

    def test_album(self):
        album = self.listen.album(_ALBUM)
        self.assertIsInstance(album, Album)
        if album:
            self.assertEqual(album.id, _ALBUM)
            self.assertEqual(album.name, 'ごーいん!')
            self.assertEqual(album.name_romaji, 'Go-in!')
            self.assertEqual(album.link, f'{_ALBUM_LINK}{_ALBUM}')
            if album.image:
                self.assertEqual(album.image.name, 'ごーいん_cover_jpop.jpg')
                self.assertEqual(album.image.url, f'{_ALBUM_CDN_LINK}{album.image.name}')

    def test_artist(self):
        artist = self.listen.artist(_ARTIST)
        self.assertIsInstance(artist, Artist)
        if artist:
            self.assertEqual(artist.id, _ARTIST)
            self.assertEqual(artist.name, 'ななひら')
            self.assertEqual(artist.name_romaji, 'Nanahira')
            self.assertEqual(artist.link, f'{_ARTIST_LINK}{_ARTIST}')
            if artist.image:
                self.assertEqual(artist.image.name, 'ななひら_image.jpg')
                self.assertEqual(artist.image.url, f'{_ARTIST_CDN_LINK}{artist.image.name}')

    def test_character(self):
        character = self.listen.character(_CHARACTER)
        self.assertIsInstance(character, Character)
        if character:
            self.assertEqual(character.id, _CHARACTER)
            self.assertEqual(character.name, '加賀美ありす')
            self.assertEqual(character.name_romaji, None)
            self.assertEqual(character.link, f'{_CHARACTER_LINK}{_CHARACTER}')

    def test_check_favorite(self):
        with self.assertRaises(NotAuthenticatedException):
            self.listen.check_favorite()

    def test_current_user(self):
        current_user = self.listen.current_user
        self.assertEqual(current_user, None)

    def test_favorite_song(self):
        with self.assertRaises(NotAuthenticatedException):
            self.listen.favorite_song(_SONG)

    def test_song(self):
        song = self.listen.song(_SONG)
        self.assertIsInstance(song, Song)
        if song:
            self.assertEqual(song.id, _SONG)
            self.assertEqual(song.title, 'ベースラインやってる？笑(Cranky Remix)')
            self.assertEqual(song.title_romaji, 'Bassline Yatteru? Emi (Cranky Remix)')
            self.assertFalse(song.characters)
            self.assertEqual(song.duration, 288)
            if song.played:
                self.assertGreaterEqual(song.played, 19)

    def test_user(self):
        user = self.listen.user('kwin4279')
        self.assertIsInstance(user, User)
        if user:
            self.assertEqual(user.uuid, "6857c0b5-7ad2-4751-bb4f-9eb951154c34")
            self.assertEqual(user.username, "kwin4279")
            self.assertEqual(user.display_name, "kwin4279")
            self.assertGreaterEqual(user.favorites, 461)
            self.assertGreaterEqual(user.requests, 0)
            self.assertGreaterEqual(user.uploads, 0)

    def test_sources(self):
        source = self.listen.source(_SOURCE)
        self.assertIsInstance(source, Source)
        if source:
            self.assertEqual(source.id, _SOURCE)
            self.assertEqual(source.name, None)
            self.assertEqual(source.name_romaji, 'ReLIFE')
            self.assertEqual(source.image, None)

    def test_play_statistic(self):
        statistic = self.listen.play_statistic(5)
        self.assertIsInstance(statistic, list)
        self.assertEqual(len(statistic), 5)
        for playstatistic in statistic:
            self.assertIsInstance(playstatistic, PlayStatistics)
            self.assertIsInstance(playstatistic.created_at, datetime)
            self.assertIsInstance(playstatistic.song, Song)

    def test_search(self):
        search_res = self.listen.search("nanahira", 5)
        self.assertIsInstance(search_res, list)
        self.assertEqual(len(search_res), 5)
        for song in search_res:
            self.assertIsInstance(song, Song)


class TestListenAuth(TestCase):
    def setUp(self) -> None:
        conf = Path().resolve().joinpath('devconf.toml')
        self.conf = Config(conf).system
        self.listen = Listen.login(self.conf.username, self.conf.password)

    def test_current_user(self):
        user = self.listen.current_user
        self.assertIsInstance(user, CurrentUser)
        self.assertIsNotNone(user)

    def test_check_favorite(self):
        res = self.listen.check_favorite(_SONG)
        self.assertIsInstance(res, bool)

    def test_favorite_song(self):
        self.listen.favorite_song(_SONG)
        self.listen.favorite_song(_SONG)


class TestAioListenUnath(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.listen = AIOListen()

    async def asyncTearDown(self) -> None:
        pass

    async def test_album(self):
        async with self.listen as listen:
            album = await listen.album(_ALBUM)
            self.assertIsInstance(album, Album)
            if album:
                self.assertEqual(album.id, _ALBUM)
                self.assertEqual(album.name, 'ごーいん!')
                self.assertEqual(album.name_romaji, 'Go-in!')
                self.assertEqual(album.link, f'{_ALBUM_LINK}{_ALBUM}')
                if album.image:
                    self.assertEqual(album.image.name, 'ごーいん_cover_jpop.jpg')
                    self.assertEqual(album.image.url, f'{_ALBUM_CDN_LINK}{album.image.name}')

    async def test_artist(self):
        async with self.listen as listen:
            artist = await listen.artist(_ARTIST)
            self.assertIsInstance(artist, Artist)
            if artist:
                self.assertEqual(artist.id, _ARTIST)
                self.assertEqual(artist.name, 'ななひら')
                self.assertEqual(artist.name_romaji, 'Nanahira')
                self.assertEqual(artist.link, f'{_ARTIST_LINK}{_ARTIST}')
                if artist.image:
                    self.assertEqual(artist.image.name, 'ななひら_image.jpg')
                    self.assertEqual(artist.image.url, f'{_ARTIST_CDN_LINK}{artist.image.name}')

    async def test_character(self):
        async with self.listen as listen:
            character = await listen.character(_CHARACTER)
            self.assertIsInstance(character, Character)
            if character:
                self.assertEqual(character.id, _CHARACTER)
                self.assertEqual(character.name, '加賀美ありす')
                self.assertEqual(character.name_romaji, None)
                self.assertEqual(character.link, f'{_CHARACTER_LINK}{_CHARACTER}')

    async def test_check_favorite(self):
        with self.assertRaises(NotAuthenticatedException):
            async with self.listen as listen:
                await listen.check_favorite()

    async def test_current_user(self):
        async with self.listen as listen:
            current_user = listen.current_user
            self.assertEqual(current_user, None)

    async def test_favorite_song(self):
        with self.assertRaises(NotAuthenticatedException):
            async with self.listen as listen:
                await listen.favorite_song(_SONG)

    async def test_song(self):
        async with self.listen as listen:
            song = await listen.song(_SONG)
            self.assertIsInstance(song, Song)
            if song:
                self.assertEqual(song.id, _SONG)
                self.assertEqual(song.title, 'ベースラインやってる？笑(Cranky Remix)')
                self.assertEqual(song.title_romaji, 'Bassline Yatteru? Emi (Cranky Remix)')
                self.assertFalse(song.characters)
                self.assertEqual(song.duration, 288)
                if song.played:
                    self.assertGreaterEqual(song.played, 19)

    async def test_user(self):
        async with self.listen as listen:
            user = await listen.user('kwin4279')
            self.assertIsInstance(user, User)
            if user:
                self.assertEqual(user.uuid, "6857c0b5-7ad2-4751-bb4f-9eb951154c34")
                self.assertEqual(user.username, "kwin4279")
                self.assertEqual(user.display_name, "kwin4279")
                self.assertGreaterEqual(user.favorites, 461)
                self.assertGreaterEqual(user.requests, 0)
                self.assertGreaterEqual(user.uploads, 0)

    async def test_sources(self):
        async with self.listen as listen:
            source = await listen.source(_SOURCE)
            self.assertIsInstance(source, Source)
            if source:
                self.assertEqual(source.id, _SOURCE)
                self.assertEqual(source.name, None)
                self.assertEqual(source.name_romaji, 'ReLIFE')
                self.assertEqual(source.image, None)

    async def test_play_statistic(self):
        async with self.listen as listen:
            statistic = await listen.play_statistic(5)
            self.assertIsInstance(statistic, list)
            self.assertEqual(len(statistic), 5)
            for playstatistic in statistic:
                self.assertIsInstance(playstatistic, PlayStatistics)
                self.assertIsInstance(playstatistic.created_at, datetime)
                self.assertIsInstance(playstatistic.song, Song)

    async def test_search(self):
        async with self.listen as listen:
            search_res = await listen.search("nanahira", 5)
            self.assertIsInstance(search_res, list)
            self.assertEqual(len(search_res), 5)
            for song in search_res:
                self.assertIsInstance(song, Song)


class TestAioListenAuth(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        conf = Path().resolve().joinpath('devconf.toml')
        self.conf = Config(conf).system
        self.listen = AIOListen.login(self.conf.username, self.conf.password)

    async def asyncTearDown(self) -> None:
        pass

    async def test_current_user(self):
        async with self.listen as listen:
            user = listen.current_user
            self.assertIsInstance(user, CurrentUser)
            self.assertIsNotNone(user)

    async def test_check_favorite(self):
        async with self.listen as listen:
            res = await listen.check_favorite(_SONG)
            self.assertIsInstance(res, bool)

    async def test_favorite_song(self):
        async with self.listen as listen:
            await listen.favorite_song(_SONG)
            await listen.favorite_song(_SONG)
