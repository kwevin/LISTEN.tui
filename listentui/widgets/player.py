from typing import Any, ClassVar

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Label, Static

from ..data import Config, Theme
from ..listen import Event, Requester
from ..listen.client import ListenClient
from .base import BasePage
from .containers import SongContainer
from .mpvplayer import MPVStreamPlayer
from .websocket import ListenWebsocket


class VanityBar(Horizontal):
    DEFAULT_CSS = """
    VanityBar {
        align: center middle;
        height: 1;
        width: 1fr;
    }
    VanityBar #listener {
        align-horizontal: left;
    }
    VanityBar Label {
        width: 1fr;
        height: 1;
    }
    """
    listener: reactive[int] = reactive(0, layout=True)
    event: reactive[Event | Requester | None] = reactive(None, layout=True)

    def watch_listener(self, value: int) -> None:
        self.query_one("#listener", Label).update(f"{value} Listeners")

    def watch_event(self, value: Event | Requester | None) -> None:
        if isinstance(value, Event):
            self.query_one("#event", Label).update(
                f"[{Theme.ACCENT}]♫♪.ılılıll {value.name} llılılı.♫♪[/]"  # noqa: RUF001
            )
        elif isinstance(value, Requester):
            self.query_one("#event", Label).update(f"Requested by [{Theme.ACCENT}]{value.display_name}[/]")
        else:
            self.query_one("#event", Label).update("")

    def compose(self) -> ComposeResult:
        yield Label(id="listener")
        yield Label(id="event")


class PlayButton(Button):
    DEFAULT_CSS = f"""
    PlayButton {{
        background: {Theme.BUTTON_BACKGROUND};
    }}
    PlayButton.-disabled {{
        tint: black 80%;
    }}
    """
    is_playing: reactive[bool] = reactive(True, init=False, layout=True)

    def __init__(self):
        super().__init__("Pause")
        self.can_focus = False

    def watch_is_playing(self, new: bool) -> None:
        self.label = "Pause" if new else "Play"
        self.app.query_one(MPVStreamPlayer).is_playing = new
        if new:
            self.disable()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.is_playing = not self.is_playing

    def enable(self) -> None:
        # self.remove_class("-disabled")
        self.disabled = False

    def disable(self) -> None:
        # self.add_class("-disabled")
        self.disabled = True


class FavoriteButton(Button):
    DEFAULT_CSS = f"""
    FavoriteButton {{
        background: {Theme.BUTTON_BACKGROUND};
    }}
    FavoriteButton.-toggled {{
        background: {Theme.ACCENT};
        text-style: bold reverse;
    }}
    """
    is_favorited: reactive[bool] = reactive(False, init=False, layout=True)

    def __init__(self):
        super().__init__("Favorite")
        self.can_focus = False

    async def on_mount(self) -> None:
        self.can_focus = False
        client = ListenClient.get_instance()
        if not client.logged_in:
            self.disabled = True

    def watch_is_favorited(self, new: bool) -> None:
        self.add_class("-toggled") if new else self.remove_class("-toggled")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        self.is_favorited = not self.is_favorited
        self.favorite()

    @work(group="player_button")
    async def favorite(self) -> None:
        client = ListenClient.get_instance()
        data = self.app.query_one(ListenWebsocket).data
        if data:
            await client.favorite_song(data.song.id)


class VolumeButton(Button):
    DEFAULT_CSS = f"""
    VolumeButton {{
        background: {Theme.BUTTON_BACKGROUND};
    }}
    VolumeButton.-toggled {{
        background: {Theme.ACCENT};
        text-style: bold reverse;
    }}
    """
    volume: reactive[int] = reactive(Config.get_config().persistant.volume, init=False, layout=True)
    is_muted: reactive[bool] = reactive(False, init=False, layout=True)

    def __init__(self):
        super().__init__(f"Volume: {self.volume}")
        self.can_focus = False

    def watch_volume(self, new: int) -> None:
        self.label = f"Volume: {new}"
        self.app.query_one(MPVStreamPlayer).volume = new
        Config.get_config().persistant.volume = new

    def watch_is_muted(self, new: bool) -> None:
        self.label = "Muted" if new else f"Volume: {self.volume}"
        self.add_class("-toggled") if new else self.remove_class("-toggled")
        self.app.query_one(MPVStreamPlayer).volume = 0 if new else self.volume

    def validate_volume(self, volume: int) -> int:
        min_volume = 0
        max_volume = 100
        if volume < min_volume:
            volume = 0
        if volume > max_volume:
            volume = 100
        return volume

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.is_muted = not self.is_muted

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.volume -= 1

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.volume += 1


class PlayerPage(BasePage):
    DEFAULT_CSS = f"""
    PlayerPage {{
        align: center middle;
        layers: below above;
        background: {Theme.BACKGROUND}
    }}
    PlayerPage MPVStreamPlayer {{
        layer: above;
        width: 100%;
        height: 100%;
    }}
    PlayerPage Vertical {{
        height: auto;
        margin: 0 12 0 12;
    }}
    PlayerPage #buttons {{
        align: left middle;
        height: auto;
        width: 100%;
    }}
    PlayerPage Button {{
        margin: 1 2 0 0;
    }}
    PlayerPage #filler {{
        width: 1fr;
    }}
    PlayerPage VolumeButton {{
        margin: 1 0 0 0;
    }}
    PlayerPage VanityBar {{
        margin: 0 1 1 1;
    }}
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "play_pause", "Play/Pause"),
        Binding("f", "favorite", "Favorite"),
        Binding("up,k", "volume_up", "Volume Up"),
        Binding("down,j", "volume_down", "Volume Down"),
        Binding("m", "mute", "Mute"),
        Binding("r", "restart", "Restart Player"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield MPVStreamPlayer()
        with Vertical():
            yield VanityBar()
            yield ListenWebsocket()
            with Horizontal(id="buttons"):
                yield PlayButton()
                yield FavoriteButton()
                yield Static(id="filler")
                yield VolumeButton()

    def on_mount(self) -> None:
        return

    def action_play_pause(self) -> None:
        play_button = self.query_one(PlayButton)
        play_button.is_playing = not play_button.is_playing

    def action_favorite(self) -> None:
        favorite_button = self.query_one(FavoriteButton)
        favorite_button.is_favorited = not favorite_button.is_favorited
        favorite_button.favorite()

    def action_volume_up(self) -> None:
        volume_button = self.query_one(VolumeButton)
        volume_button.volume += Config.get_config().player.volume_step

    def action_volume_down(self) -> None:
        volume_button = self.query_one(VolumeButton)
        volume_button.volume -= Config.get_config().player.volume_step

    def action_mute(self) -> None:
        volume_button = self.query_one(VolumeButton)
        volume_button.is_muted = not volume_button.is_muted

    def action_restart(self) -> None:
        self.query_one(PlayButton).is_playing = True
        self.query_one(MPVStreamPlayer).hard_restart()

    @on(MPVStreamPlayer.Restarted)
    def on_player_restart(self, event: MPVStreamPlayer.Restarted) -> None:
        self.query_one(PlayButton).enable()
        if self.query_one(VolumeButton).is_muted:
            self.query_one(MPVStreamPlayer).volume = 0

    @on(ListenWebsocket.Updated)
    async def on_listen_websocket_updated(self, event: ListenWebsocket.Updated) -> None:
        self.query_one(VanityBar).listener = event.data.listener
        self.query_one(VanityBar).event = event.data.event or event.data.requester
        client = ListenClient.get_instance()
        if client.logged_in:
            favorited = await client.check_favorite(event.data.song.id)
            self.query_one(FavoriteButton).is_favorited = favorited

        # set romaji tooltip
        # TODO: make this a setting option instead
        song = await client.song(event.data.song.id)
        if song:
            if song.title_romaji:
                self.query_one("ListenWebsocket > SongContainer", SongContainer).set_tooltips(song.title_romaji)
            else:
                self.query_one("ListenWebsocket > SongContainer", SongContainer).set_tooltips(None)
