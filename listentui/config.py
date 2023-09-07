from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from string import Template
from typing import Any, Self, Type

import tomli
import tomli_w
from readchar import key


class ConfigNotFoundException(Exception):
    pass


@dataclass
class Keybind:
    play_pause: str = '${SPACE}'
    lower_volume: str = '${DOWN}'
    raise_volume: str = '${UP}'
    lower_volume_fine: str = '${LEFT}'
    raise_volume_fine: str = '${RIGHT}'
    favourite_song: str = 'f'
    restart_player: str = 'r'
    seek_to_end: str = 's'

    def sub_key_to_str(self) -> Self:
        s = {k: v for k, v in key.__dict__.items() if "__" not in k}
        for i in fields(self):
            k: str = getattr(self, i.name)
            if "$" in k:
                e = Template(k)
                n = e.substitute(s)
                setattr(self, i.name, n)

        return self


@dataclass
class System:
    username: str = ''
    password: str = ''
    token: str = ''
    debug: bool = False
    instance_lock: bool = False


@dataclass
class RPC:
    enable_rpc: bool = True
    default_placeholder: str = " ♪"
    use_fallback: bool = True
    fallback: str = "fallback2"
    use_artist: bool = True


@dataclass
class Display:
    romaji_first: bool = True
    separator: str = ', '


@dataclass
class Player:
    mpv_options: dict[str, Any] = field(default_factory=dict)
    volume_step: int = 10
    restart_timeout: int = 20
    last_volume: int = 100

    def __post_init__(self):
        if not self.mpv_options:
            self.mpv_options = {
                'ad': 'vorbis',
                'cache': True,
                'cache_secs': 20,
                'cache_pause_initial': True,
                'cache_pause_wait': 3,
                'demuxer_lavf_linearize_timestamps': True,
            }


@dataclass
class Configuration:
    keybind: Keybind = field(default_factory=Keybind)
    system: System = field(default_factory=System)
    rpc: RPC = field(default_factory=RPC)
    display: Display = field(default_factory=Display)
    player: Player = field(default_factory=Player)


class Config:
    _CONFIG: "Config"

    def __init__(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        self._load()
        Config._CONFIG = self

    @property
    def keybind(self):
        return self._keybind

    @property
    def system(self):
        return self._system

    @property
    def rpc(self):
        return self._rpc

    @property
    def display(self):
        return self._display

    @property
    def player(self):
        return self._player

    @property
    def config(self):
        return self._config

    @classmethod
    def get_config(cls: Type[Self]) -> Self:
        if not Config._CONFIG:
            raise ConfigNotFoundException("No config instantiated")
        else:
            return Config._CONFIG

    @classmethod
    def create_new(cls: Type[Self], path: Path | None = None) -> Self:
        if not path:
            path = Path().resolve().joinpath('config.toml')
        else:
            path = path
        Config._write(path, Config._default())
        return Config(path)

    def _load(self) -> None:
        if not self.config_path.is_file():
            raise FileNotFoundError(f"Config file at {self.config_path} not found")
        with open(self.config_path, 'rb') as f:
            self._conf = tomli.load(f)
        # keybind
        kb = self._conf.get('keybind', None)
        if not kb:
            kb = Keybind()
        else:
            kb = Keybind(**kb).sub_key_to_str()
        # system
        system = self._conf.get('system', None)
        if not system:
            system = System()
        else:
            system = System(**system)
        # rpc
        rpc = self._conf.get('rpc', None)
        if not rpc:
            rpc = RPC()
        else:
            rpc = RPC(**rpc)
        # display
        ws = self._conf.get('display', None)
        if not ws:
            ws = Display()
        else:
            ws = Display(**ws)
        # player
        pl = self._conf.get('player', None)
        if not pl:
            pl = Player()
        else:
            pl = Player(**pl)

        self._keybind = kb
        self._system = system
        self._rpc = rpc
        self._display = ws
        self._player = pl
        self._config = Configuration(self._keybind, self._system, self._rpc, self._display, self._player)

    @staticmethod
    def _write(path: Path, config: dict[str, Any]) -> None:
        with open(path, 'wb') as f:
            tomli_w.dump(config, f)

    @staticmethod
    def _default() -> dict[str, Any]:
        e = Configuration()
        return asdict(e)

    def update(self, component: str, key: str, value: Any):
        self._conf[component][key] = value
        self._write(self.config_path, self._conf)


if __name__ == "__main__":
    from rich.pretty import pprint

    # pprint(Config._default())  # pyright: ignore
    conf = Config.create_new()
    pprint(conf.config)
    # conf = Path().resolve().joinpath('config.toml')
    # conf = Config(conf)
    # pprint(conf.config)
