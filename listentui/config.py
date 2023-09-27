import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from string import Template
from typing import Any, Optional, Self, Type

import tomli
import tomli_w
from readchar import key


class ConfigException(Exception):
    pass


class InvalidConfigException(Exception):
    pass


@dataclass
class System:
    username: str = ''
    password: str = ''
    instance_lock: bool = False


@dataclass
class Keybind:
    play_pause: str = '${SPACE}'
    lower_volume: str = '${DOWN}'
    raise_volume: str = '${UP}'
    lower_volume_fine: str = '${LEFT}'
    raise_volume_fine: str = '${RIGHT}'
    favourite_song: str = 'f'
    restart_player: str = 'r'
    open_terminal: str = 'i'

    def sub_identifier(self) -> Self:
        s = {k: v for k, v in key.__dict__.items() if "__" not in k}
        for i in fields(self):
            k: str = getattr(self, i.name)
            if "$" in k:
                e = Template(k)
                n = e.substitute(s)
                setattr(self, i.name, n)
        return self


@dataclass
class RPC:
    enable: bool = True
    default_placeholder: str = " ♪"
    fallback: str = "fallback2"
    use_fallback: bool = True
    use_artist: bool = True
    detail: str = '${title}'
    state: str = '${artist}'
    large_text: str = '${source} ${title}'
    small_text: str = '${artist}'
    show_time_left: bool = True
    show_small_image: bool = True

    def __post_init__(self):
        if len(self.default_placeholder) < 2:
            raise InvalidConfigException("default_placeholder must be greater than two characters")


@dataclass
class Display:
    romaji_first: bool = True
    separator: str = ', '


@dataclass
class Player:
    mpv_options: dict[str, Any] = field(default_factory=dict)
    volume_step: int = 10
    restart_timeout: int = 20

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
class Persist:
    token: str = ''
    last_volume: int = 100


@dataclass
class Configuration:
    system: System = field(default_factory=System)
    keybind: Keybind = field(default_factory=Keybind)
    display: Display = field(default_factory=Display)
    rpc: RPC = field(default_factory=RPC)
    player: Player = field(default_factory=Player)


class Config:
    _CONFIG: "Config"

    def __init__(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        if not self.config_path.is_file():
            self._write(self.config_path, self._default())
        self.persist_path = Path().resolve().joinpath('.persist\\persist.toml')
        if not self.persist_path.parent.is_dir():
            os.mkdir(self.persist_path.parent)
            self._write(self.persist_path, asdict(Persist()))
        if not self.persist_path.is_file():
            self._write(self.persist_path, asdict(Persist()))

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
    def persist(self):
        return self._persist

    @classmethod
    def get_config(cls: Type[Self]) -> Self:
        if not Config._CONFIG:
            raise ConfigException("No config instantiated")
        else:
            return Config._CONFIG

    @classmethod
    def create_new(cls: Type[Self], path: Optional[Path] = None) -> Self:
        if not path:
            path = Path().resolve().joinpath('config.toml')
        else:
            path = path
        Config._write(path, Config._default())
        return cls(path)

    def _load(self) -> None:
        with open(self.config_path, 'rb') as f:
            self._conf = tomli.load(f)

        for catagory in self._conf.keys():
            match catagory:
                case 'keybind':
                    self._keybind = Keybind(**self._conf[catagory]).sub_identifier()
                case 'system':
                    self._system = System(**self._conf[catagory])
                case 'rpc':
                    self._rpc = RPC(**self._conf[catagory])
                case 'display':
                    self._display = Display(**self._conf[catagory])
                case 'player':
                    self._player = Player(**self._conf[catagory])
                case _:
                    pass

        with open(self.persist_path, 'rb') as f:
            self._pers = tomli.load(f)
            self._persist = Persist(**self._pers)

    @staticmethod
    def _write(path: Path, config: dict[str, Any]) -> None:
        with open(path, 'wb') as f:
            tomli_w.dump(config, f)

    @staticmethod
    def _default() -> dict[str, Any]:
        return asdict(Configuration())

    def update(self, component: str, key: str, value: Any):
        if component == 'persist':
            self._pers[key] = value
            self._write(self.persist_path, self._pers)
            return
        self._conf[component][key] = value
        self._write(self.config_path, self._conf)


if __name__ == "__main__":
    conf = Config.create_new()
