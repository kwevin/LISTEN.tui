import re
from dataclasses import dataclass, field
from typing import Any

from ytmusicapi import YTMusic  # type: ignore

from listentui.downloader.providers.search.baseProvider import BaseSearch, Scores, SearchResult
from listentui.listen.interface import Song


@dataclass
class Result:
    is_song: bool
    is_first: bool
    video_id: str
    title: str
    artists: set[str]
    album: str | None
    views: int | None
    duration: int | None
    video_url: str = field(default_factory=str)

    def __post_init__(self) -> None:
        self.video_url = f"https://music.youtube.com/watch?v={self.video_id}"


class YoutubeMusic(BaseSearch):
    ytm = YTMusic(language="de")
    title_multiplier = 1
    artist_multiplier = 1
    album_multiplier = 0.6
    duration_mul = 0.2
    views_mul = 0.2
    artist_punish = 5
    song_bonus = 10
    first_bonus = 20

    title_threshold = 70
    artist_threshold = 70

    def __init__(self, song: Song) -> None:
        super().__init__(song)

    def clean(self, string: str) -> str:
        artists = self.get_artist_variation()
        characters = self.get_character_variation()

        string = string.lower()

        for artist in artists:
            string = string.replace(artist.lower(), "")
        for character in characters:
            string = string.replace(character.lower(), "")

        string = string.replace("cv:", "")

        return string.strip()

    def find_best(self) -> SearchResult | list[SearchResult]:  # noqa: PLR0915
        results = self.find()

        scored_result: list[SearchResult] = []
        for result in results:
            # compares title
            # we want to remove from the title any occurance of artists or characters to do a fair comparison
            # we want to compare both version of the song title
            clean_title = self.clean(result.title)
            title_variation = [re.sub(r"[^a-zA-Z]", "", clean_title), re.sub(r"[a-zA-Z]", "", clean_title)]
            # title_score = max(self.ratio(title, clean_title) for title in self.get_title_variation()) * 100
            original_title_score = 0
            romanised_title_score = 0
            if self.song.title:
                original_title_score = max(self.ratio(self.song.title, title) for title in title_variation)
            if self.song.title_romaji:
                romanised_title_score = max(self.ratio(self.song.title_romaji, title) for title in title_variation)

            title_score = max(original_title_score, romanised_title_score) * 100

            # compares artists
            # result artists can be within the result object or be within the title itself (pain-peko)
            # we want to give higher scores for more artists that matched and punish for each artist that doesnt match
            matched: list[float] = []
            for artist in self.get_artist_variation():
                # compares artist in title
                artist_in_title = 0
                if artist.lower() in result.title.lower():
                    artist_in_title = 1
                # compares artist in artist
                comparison = [self.ratio(artist, result_artist) for result_artist in result.artists] + [0.0]
                artist_score = (max(comparison) + artist_in_title) / 2 if artist_in_title else max(comparison)
                matched.append(artist_score)

            artist_score = sum(matched) / max(len(matched), 1) * 100 - (
                (max(len(self.get_artist_variation()) - len(matched), 0)) * self.artist_punish
            )

            # compares album if an album is present
            album_score = 0
            if result.album and self.song.album:
                album_score = max(self.ratio(album, result.album) for album in self.get_album_variation()) * 100
            elif result.album and any(result.album.lower() in album.lower() for album in self.get_album_variation()):
                album_score = 100

            # compares duration if present
            # within 5% score > 90; within 1% fullscore; anything greater than 10% no score
            duration_score = 0
            if result.duration and self.song.duration:
                one_percentile = self.song.duration * 0.01
                five_percentile = self.song.duration * 0.05
                difference = abs(result.duration - self.song.duration)
                if difference <= one_percentile:
                    duration_score = 100
                elif difference <= five_percentile:
                    duration_score = 90 + (10 * (difference / five_percentile))

            # score views if present
            # surely it cant be below 5k so < 5k = -100, where >= 100k = 100
            # we punish low views video heavily because most of the time
            # it will be bad reupload nightcore etc
            view_score = 0
            if result.views:
                min_view = 5000
                max_view = 100_000
                view_score = -100 if result.views < min_view else min(result.views / max_view, 100)

            bonuses: list[float] = []
            if result.is_song:
                bonuses.append(self.song_bonus)
            if result.is_first:
                bonuses.append(self.first_bonus)

            scored_result.append(
                SearchResult(
                    url=result.video_url,
                    title=result.title,
                    artist=list(result.artists),
                    album=result.album,
                    views=result.views,
                    duration=result.duration,
                    scores=Scores(
                        title_score * self.title_multiplier,
                        artist_score * self.artist_multiplier,
                        album_score * self.album_multiplier,
                        duration_score * self.duration_mul,
                        view_score * self.views_mul,
                        bonuses,
                    ),
                    similar=[],
                )
            )
        scored_result.sort(key=lambda result: result.scores.total, reverse=True)

        passed_result: list[SearchResult] = []

        for result in scored_result:
            if result.scores.title < self.title_threshold:
                continue
            if result.scores.artist < self.artist_threshold:
                continue
            passed_result.append(result)

        if passed_result:
            best = scored_result[0]
            best.similar = [*scored_result[1:3]]
            return best

        return scored_result[:3]

    def find(self) -> list[Result]:
        song_title = self.get_title_variation()[0]
        song_artist = self.get_artist_variation()
        song_artist = song_artist[0] if song_artist else ""
        # idk if 2 requests per song is ok
        res: list[dict[str, Any]] = self.ytm.search(  # type: ignore
            f"{song_title} - {song_artist}", filter="songs", limit=4
        )
        res.extend(
            self.ytm.search(  # type: ignore
                f"{song_title} - {song_artist}", filter="videos", limit=4
            )
        )

        def parse_view(view: str) -> int | None:
            try:
                return int(view)
            except ValueError:
                # 7,5\xa0Mio.
                # 11.285
                try:
                    if view.endswith("Mio.") and "," in view:
                        quantity = float(view[:3].replace(",", "."))
                        return round(quantity * 1_000_000)
                    if view.endswith("Mio."):
                        quantity = float(view[0])
                        return round(quantity * 1_000_000)
                    return round(float(view) * 1_000)
                except ValueError:
                    self._log.warning(f"unable to parse '{view}'")
                    return None

        results: list[Result] = []

        for idx, result in enumerate(res):
            if result["resultType"] not in {"song", "video"}:
                continue
            is_song = result["resultType"] == "song"
            title = result["title"]
            video_id = result["videoId"]
            artists = {artist["name"] for artist in result["artists"] if artist is not None}
            album = album["name"] if (album := result.get("album")) else None
            views = parse_view(view) if (view := result.get("views")) else None
            duration = result.get("duration_seconds")

            results.append(Result(is_song, idx == 0, video_id, title, artists, album, views, duration))

        return results


# from textual.app import App, ComposeResult
# from textual.widgets import RichLog
# from listentui.listen.client import ListenClient


# class MyApp(App[None]):
#     def compose(self) -> ComposeResult:
#         yield RichLog()

#     async def on_mount(self) -> None:
#         client = ListenClient.get_instance()
#         await client.connect()
#         song = await client.song(13777)
#         searcher = YoutubeMusic(song)
#         self.query_one(RichLog).write(searcher.find_best())


# app = MyApp()
# app.run()

# should match
# 23325

# needs double checking
# 21795
