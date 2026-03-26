from __future__ import annotations

from enum import StrEnum
from logging import getLogger
from threading import Event, Lock
from typing import Any, ClassVar

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import PostProcessor  # type: ignore

from listentui.data.config import Config
from listentui.downloader.baseInterface import DownloadItem, ItemDownloadCallback, QueueState


class DownloadStatus(StrEnum):
    DOWNLOADING = "downloading"
    FINISHED = "finished"
    ERROR = "error"


class YtdlpLogger:
    def __init__(self) -> None:
        self.log = getLogger("ytdlp")

    def debug(self, msg: str):
        self.log.debug(msg.replace("[debug]", "").strip())

    def info(self, msg: str):
        self.log.info(msg.replace("[info]", "").strip())

    def warning(self, msg: str):
        self.log.warning(msg.replace("[warning]", "").strip())

    def error(self, msg: str):
        self.log.error(msg.replace("[error]", "").strip())


class DownloadItemPostProcessor(PostProcessor):
    def __init__(self, manager: YoutubeDLDownloadManager, downloader=None):
        super().__init__(downloader)
        self.manager = manager

    def run(self, information: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        items = self.manager._current_items
        assert items is not None

        item = next(filter(lambda item: item.metadata.url, items))  # type: ignore
        information["downloadItem"] = item
        return [], information


class MetadataPostProcessor(PostProcessor):
    def run(self, information: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        download_item: DownloadItem | None = information.get("downloadItem")
        assert download_item is not None

        # this is definitely not the best way,
        # it would be better if I modify the metadata after its downloaded
        # but then I need to manually handle all the formats.

        # TODO: final title is wrong id 666
        information["title"] = download_item.final_title
        information["artist"] = download_item.final_artists
        information["album"] = download_item.final_album

        return [], information


class YoutubeDLDownloadManager:
    _active_instance: YoutubeDLDownloadManager | None = None
    OPTS_FLAG: ClassVar[dict[str, Any]] = {
        "logger": YtdlpLogger(),
        "paths": {"home": str(Config.get_config().downloader.get_output_directory())},
        "verbose": Config.get_config().advance.stats_for_nerd,
    }

    def __init__(self) -> None:
        self._active_instance = self
        self.set_up_download_dir()
        self.ytdlp = self.configure_ytdlp()

        self._current_callback: ItemDownloadCallback | None = None
        """callback is not none when download is called"""
        self._current_items: list[DownloadItem] | None = None
        """items is not none when download is called"""

        self._update_setting_flag = Event()
        self._download_lock = Lock()

    @classmethod
    def get_instance(cls) -> YoutubeDLDownloadManager:
        if YoutubeDLDownloadManager._active_instance:
            return YoutubeDLDownloadManager._active_instance
        return cls()

    def set_up_download_dir(self):
        Config.get_config().downloader.get_output_directory().mkdir(parents=True, exist_ok=True)

    def configure_ytdlp(self) -> YoutubeDL:
        opts = Config.get_config().downloader.custom_args
        opts.update(self.OPTS_FLAG)

        ytdlp = YoutubeDL(opts)  # type: ignore
        ytdlp.add_progress_hook(self._progress_hook)
        ytdlp.add_post_processor(DownloadItemPostProcessor(self), when="pre_process")
        ytdlp.add_post_processor(MetadataPostProcessor(), when="pre_process")

        return ytdlp

    def update_settings(self):
        if not self._download_lock.locked():
            self.ytdlp = self.configure_ytdlp()
        else:
            self._update_setting_flag.set()

    def _progress_hook(self, download_object: dict[str, Any]):
        assert self._current_callback is not None
        download_item: DownloadItem = download_object["info_dict"]["downloadItem"]
        callback = self._current_callback

        if download_object["status"] == DownloadStatus.DOWNLOADING:
            download_item.state = QueueState.DOWNLOADING
            total_byte = download_object.get("total_bytes")
            downloaded_byte = download_object.get("downloaded_bytes")
            progress = -1 if total_byte is None or downloaded_byte is None else downloaded_byte / total_byte
            callback(
                download_item.song.id,
                download_item,
                progress,
            )
        elif download_object["status"] == DownloadStatus.FINISHED:
            download_item.state = QueueState.DONE
            callback(download_item.song.id, download_item, 1)
        elif download_object["status"] == DownloadStatus.ERROR:
            download_item.state = QueueState.DOWNLOAD_FAILED
            callback(download_item.song.id, download_item, -1)

    def download(self, items: list[DownloadItem], callback: ItemDownloadCallback) -> Exception | None:
        with self._download_lock:
            self._current_callback = callback
            self._current_items = items
            urls = [item.metadata.url for item in items if item.metadata]

            def post_download():
                if self._update_setting_flag.is_set():
                    self.ytdlp = self.configure_ytdlp()
                    self._update_setting_flag.clear()

            try:
                with self.ytdlp as ytdlp:
                    ytdlp.download(urls)
            except Exception as exc:
                post_download()
                return exc

            post_download()

            return None


if __name__ == "__main__":
    from listentui.downloader.baseInterface import Scores, SongMetadata
    from listentui.listen.interface import Artist, ArtistID, Song, SongID

    def __false_callback(song_id: SongID, item: DownloadItem, progress: float):
        print(f"Progress: {progress * 100:.2f}%")

    item = DownloadItem(
        Song(
            SongID(0),
            "test_name",
            None,
            [Artist(ArtistID(0), "test_artist", None, None, None)],
            None,
            None,
            None,
            0,
        ),
        SongMetadata(
            "https://music.youtube.com/watch?v=Vi_asBY5UX8",
            "YoutubeMusic",
            "完全放棄宣言 / ナナヲアカリ",
            ["Nanawoakari"],
            Scores(0, 0, 0, []),
        ),
        [],
    )
    manager = YoutubeDLDownloadManager()
    manager.download([item], __false_callback)
