from textual.message import Message

from listentui.listen.interface import AlbumID, ArtistID, SongID, SourceID


class SpawnAlbumScreen(Message):
    def __init__(self, album_id: AlbumID) -> None:
        super().__init__()
        self.album_id = album_id


class SpawnArtistScreen(Message):
    def __init__(self, artist_id: ArtistID) -> None:
        super().__init__()
        self.artist_id = artist_id


# class SpawnConfirmScreen(Message):
#     def __init__(self, album_id: AlbumID) -> None:
#         super().__init__()
#         self.album_id = album_id

# class SpawnSelectionScreen(Message):
#     def __init__(self, album_id: AlbumID) -> None:
#         super().__init__()
#         self.album_id = album_id


class SpawnSongScreen(Message):
    def __init__(self, song_id: SongID, favourited: bool = False) -> None:
        super().__init__()
        self.song_id = song_id
        self.favourited = favourited


class SpawnSourceScreen(Message):
    def __init__(self, source_id: SourceID) -> None:
        super().__init__()
        self.source_id = source_id
