# type: ignore
import threading
import time
from logging import getLogger

import mpv

from src.display.display import Display
from src.module.types import Status

# class StreamPlayerVLC:
#     def __init__(self) -> None:
#         import vlc
#         from vlc import MediaPlayer
#         self.stream_url = "https://listen.moe/stream"
#         self.vlc = vlc.Instance()
#         self.player: MediaPlayer = self.vlc.media_player_new()
#         self.player.set_media(self.vlc.media_new(self.stream_url))
#         self.player.audio_set_volume(30)

#     def play(self) -> None:
#         self.player.play()

#     def pause(self) -> None:
#         self.player.pause()

#     def is_playing(self) -> bool:
#         return True if self.player.is_playing() else False
    
#     def set_volume(self, volume: int):
#         e = self.player.audio_set_volume(volume)
#         if not e:
#             return
#         else:
#             raise Exception("Unable to set volume")
        
#     def length(self):
#         return self.player.get_time()
    
#     def release(self):
#         self.player.release()

#     def retain(self):
#         self.player.retain()

    
class StreamPlayerMPV(threading.Thread):
    def __init__(self, display: Display) -> None:
        super().__init__()
        self.log = getLogger(__name__)
        self.display = display
        self.status: Status = Status(False, 'Initialising')
        self.stream_url = "https://listen.moe/stream"
        # self._mpv_options = {'cache': False}
        # self.player = mpv.MPV(**self._mpv_options)
        self.player = mpv.MPV()
        self.is_paused: bool = False

    def update_status(self, status: bool, reason: str = ''):
        self.status.running = status
        self.status.reason = reason
        self.display.update_status('Stream', self.status)

    def _restarter(self, duration: int = 20):
        self.player.wait_until_playing()
        print('Playback started')
        e = 0
        while True:
            if self.player.core_idle and not self.is_paused:
                if e > duration:
                    print(f'Restarting player: idle exceed {duration}s while not paused')
                    self.restart()
                    e = 0
                    continue
                e += 1
            else:
                e = 0
            time.sleep(1)

    def _debugger(self):
        while True:
            print(f'core_idle: {self.player.core_idle}')
            print(f'time_remaining: {self.player.time_remaining}')
            print(f'demuxer_cache_duration: {self.player.demuxer_cache_duration}')
            print(f'demuxer_cache_time: {self.player.demuxer_cache_time}')
            # pprint(self.player.demuxer_cache_state)
            time.sleep(1)

    def run(self):
        threading.Thread(target=self._restarter).start()
        # threading.Thread(target=self._debugger).start()
        self.player.play(self.stream_url)
        self.update_status(True)
        self.player.wait_for_playback()

    def restart(self):
        self.player.play(self.stream_url)
        if self.is_paused:
            self.play()

    def play(self):
        self.player.pause = False
        self.is_paused = False
    
    def pause(self):
        self.player.pause = True
        self.is_paused = True

    def play_pause(self):
        if self.player.pause:
            self.play()
        else:
            self.pause()

    def volume(self, volume: int):
        volume = int(volume)
        if volume < 0 or volume > 100:
            raise Exception
        self.player.volume = volume

    def ao_volume(self, volume: int):
        self.player.ao_volume = volume


if __name__ == "__main__":
    e = StreamPlayerMPV()
    e.start()
    
    while True:
        try:
            k = input()
            p = eval(k)
            print(p)
        except Exception:
            continue
