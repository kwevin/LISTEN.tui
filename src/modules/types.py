from dataclasses import dataclass


@dataclass
class Status:
    running: bool
    reason: str


@dataclass
class Activity:
    PLAYING: int = 0
    _STREAMING: int = 1
    LISTENING: int = 2
    WATCHING: int = 3
    _CUSTOM: int = 4
    COMPETING: int = 5

    
@dataclass
class Rpc:
    is_arrpc: bool
    detail: str
    state: str
    end: int | None
    large_image: str | None
    large_text: str | None
    small_image: str | None
    small_text: str | None
    buttons: list[dict[str, str]]
    type: int
