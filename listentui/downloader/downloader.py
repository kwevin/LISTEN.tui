from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from enum import Enum
from threading import Event
from typing import Any, Callable, ClassVar, Sequence

from listentui.downloader.baseInterface import (
    AutoFill,
    DownloadItem,
    ItemDownloadCallback,
    ItemSearchCallback,
    QueueState,
    SearchProvider,
    SongMetadata,
)
from listentui.downloader.providers.search.youtubeMusic import YoutubeMusic
from listentui.downloader.ytdlpDownloadManager import YoutubeDLDownloadManager
from listentui.listen.interface import Song, SongID


class Downloader:
    SEARCH_PROVIDER: set[SearchProvider] = {YoutubeMusic()}  # noqa: RUF012
    _ytdlp_manager = YoutubeDLDownloadManager()
    _download_queue: ClassVar[dict[SongID, DownloadItem]] = {}

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="Downloader")
        self._futures: list[Future] = []
        self._should_cancel = Event()
        self._done_cancel = Event()

    def has_searchable(self) -> bool:
        return any(item.state == QueueState.QUEUED for item in self._download_queue.values())

    def has_downloadable(self) -> bool:
        return any(item.state == QueueState.FOUND for item in self._download_queue.values())

    def _single_search(self, song_id: SongID, callback: ItemSearchCallback, current_position: int, total_entry: int):
        download_item = self._download_queue[song_id]
        download_item.state = QueueState.SEARCHING
        callback(song_id, download_item, (current_position, total_entry))

        best, other = self.get_metadata(download_item.song)

        if best is None:
            download_item.state = QueueState.NOT_FOUND
        else:
            download_item.state = QueueState.FOUND
            download_item.metadata = best[0]

        download_item.all_results = other

        if best is not None:
            download_item.all_results.extend(best)
            download_item.all_results.sort(key=lambda data: data.scores.total, reverse=True)

        callback(song_id, download_item, (current_position, total_entry))

    def search(self, entry_song_id: SongID, callback: ItemSearchCallback):
        self._single_search(entry_song_id, callback, 0, 0)

    def batch_search_all(self, callback: ItemSearchCallback):
        self._futures.clear()
        length = len(self._download_queue.items())
        for idx, (song_id, queue_item) in enumerate(self._download_queue.items(), start=1):
            if queue_item.state == QueueState.QUEUED:
                self._futures.append(self._pool.submit(self._single_search, song_id, callback, idx, length))

        # idk why but this method lags
        # while any(futures.running() for futures in self._futures):
        #     if self._should_cancel.is_set():
        #         self._cancel_futures()
        #         return
        #     wait(self._futures, return_when="FIRST_COMPLETED")

        for future in self._futures:
            if self._should_cancel.is_set():
                self._cancel_futures()
                return
            future.result()

    def cancel_batch_search(self):
        self._wait_cancel()

    def _wait_cancel(self):
        if any(futures.running() for futures in self._futures):
            self._should_cancel.set()
            self._done_cancel.wait()
            self._done_cancel.clear()

    def _cancel_futures(self):
        for future in self._futures:
            if not future.running():
                future.cancel()

        wait(self._futures)

        self._should_cancel.clear()
        self._done_cancel.set()

    def cancel_download(self):
        self._wait_cancel()

    def download(self, entry_song_id: SongID, callback: ItemDownloadCallback) -> Exception | None:
        download_item = self._download_queue[entry_song_id]

        ret = self._ytdlp_manager.download([download_item], callback)
        return ret

    def batch_download_all(self, entry_song_id: SongID, callback: ItemDownloadCallback) -> Exception | None:
        download_items = [item for item in self._download_queue.values() if item.state == QueueState.FOUND]

        ret = self._ytdlp_manager.download(download_items, callback)
        return ret

    def get_metadata(self, song: Song) -> tuple[list[SongMetadata] | None, list[SongMetadata]]:
        """
        Return a tuple that holds a list of best matches and all other results in that order
        """
        other_results: list[SongMetadata] = []
        best_results: list[SongMetadata] = []
        for provider in self.SEARCH_PROVIDER:
            best, other = provider.find_best(song)

            if best:
                best_results.append(best)
            other_results.extend(other)

        other_results.sort(key=lambda data: data.scores.total)
        best_results.sort(key=lambda data: data.scores.total)

        if len(best_results) > 0:
            return (best_results, other_results)
        return (None, other_results)

    def get_from_link(self, url: str) -> SongMetadata | None:
        for provider in self.SEARCH_PROVIDER:
            if isinstance(provider, AutoFill) and provider.supported_link(url):
                return provider.autofill(url)
        return None

    def has_song(self, song_id: SongID) -> bool:
        return self._download_queue.get(song_id) is not None

    def add_to_queue(self, song: Song) -> DownloadItem | None:
        if self._download_queue.get(song.id):
            return None

        item = DownloadItem(song, None, [])
        self._download_queue[song.id] = item
        return item

    def batch_to_queue(self, songs: Sequence[Song]) -> list[DownloadItem]:
        items: list[DownloadItem] = []

        for song in songs:
            result = self.add_to_queue(song)
            if result:
                items.append(result)

        return items

    def remove_from_queue(self, song_id: SongID) -> bool:
        try:
            self._download_queue.pop(song_id)
            return True
        except KeyError:
            return False

    def clear_queue(self):
        self._download_queue.clear()

    def get_queue(self) -> list[DownloadItem]:
        return list(self._download_queue.values())
