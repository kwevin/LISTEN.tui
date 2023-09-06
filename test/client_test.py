from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

from src.config import Config
from src.listen.client import AIOListen, Listen, NotAuthenticatedException
from src.listen.types import (Album, Artist, Character, CurrentUser, Song,
                              Source, User)

_ALBUM = 4644
_SONG = 22488
_ARTIST = 215
_CHARACTER = 403
_SOURCE = 507
_ALBUM_LINK = 'https://listen.moe/albums/'
_ARTIST_LINK = 'https://listen.moe/artists/'
_SOURCE_LINK = 'https://listen.moe/sources/'
_CHARACTER_LINK = 'https://listen.moe/characters/'
_ALBUM_CDN_LINK = 'https://cdn.listen.moe/covers/'
_ARTIST_CDN_LINK = 'https://cdn.listen.moe/artists/'
_SOURCE_CDN_LINK = 'https://cdn.listen.moe/source/'


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
            if user.bio:
                self.assertIn("Nothing here", user.bio)
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
