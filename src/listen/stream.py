# pyright: reportUnknownMemberType=false, reportMissingTypeStubs=false
import threading
import time
from typing import Any

import mpv

from src.listen.types import MPVData
from src.module import Module

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


class StreamPlayerMPV(Module):
    def __init__(self) -> None:
        super().__init__()
        self.stream_url = "https://listen.moe/stream"
        self.mpv_options = {'cache': False}
        self.player = mpv.MPV(**self.mpv_options)
        self._data: MPVData
        self.idle_count: int = 0

    @property
    def data(self) -> MPVData:
        return self._data
    
    @property
    def paused(self) -> bool | None:
        return bool(self._get_value('pause'))
    
    @paused.setter
    def paused(self, state: bool):
        setattr(self.player, 'pause', state)
    
    @property
    def core_idle(self) -> bool:
        return bool(self._get_value('core_idle'))
    
    @property
    def time_remaining(self) -> float:
        remaining = self._get_value('playtime_remaining')
        if not remaining:
            return -1
        return float(remaining)
    
    @property
    def volume(self) -> int:
        volume = self._get_value('volume')
        if not volume:
            return 0
        return int(volume)
    
    @volume.setter
    def volume(self, volume: int):
        setattr(self.player, 'volume', volume)
    
    @property
    def ao_volume(self) -> float:
        ao_volume = self._get_value('ao_volume')
        if not ao_volume:
            return 0
        return float(ao_volume)
    
    @ao_volume.setter
    def ao_volume(self, volume: int):
        setattr(self.player, 'ao_volume', volume)
    
    def _get_value(self, value: str, *args: Any) -> Any | None:
        try:
            return getattr(self.player, value, *args)
        except RuntimeError:
            return None

    def _restarter(self, duration: int = 20):
        self.player.wait_until_playing()
        while self._running:
            if self.core_idle and not self.paused:
                if self.idle_count > duration:
                    self._log.info(f'Idle time exceed {duration}s when not paused. Restarting...')
                    self.restart()
                    self.idle_count = 0
                    continue
                self.idle_count += 1
            else:
                self.idle_count = 0
            time.sleep(1)

    def run(self):
        threading.Thread(target=self._restarter, name='MPV_restarter').start()
        self.player.play(self.stream_url)
        self.player.wait_until_playing()
        self.update_status(True)
        self.player.wait_for_playback()

    def restart(self):
        self.player.play(self.stream_url)
        if self.paused:
            self.play()

    def play(self):
        self.paused = False
    
    def pause(self):
        self.paused = True

    def play_pause(self):
        if self.paused:
            self.play()
        else:
            self.pause()

    def set_volume(self, volume: int):
        self.volume = volume

    def set_ao_volume(self, volume: int):
        self.ao_volume = volume


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
