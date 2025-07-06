from __future__ import annotations

from typing import Any, Callable

from rich.text import Text
from textual import events
from textual.message import Message
from textual.reactive import var
from textual.widgets import Button, Static

from listentui.data.config import Config
from listentui.listen import ListenClient
from listentui.widgets.player import Player


class StaticButton(Button):
    DEFAULT_CSS = """
    StaticButton:disabled {
        tint: black 40%;
    }
    StaticButton.hidden {
        visibility: hidden;
    }
    """

    def __init__(
        self, label: str | Text | None = None, check_user: bool = False, hidden: bool = False, *args: Any, **kwargs: Any
    ):
        super().__init__(label, *args, **kwargs)
        self.can_focus = False
        self._check_user = check_user
        self._hidden = hidden

    async def on_mount(self) -> None:
        if self._check_user:
            client = ListenClient.get_instance()
            if not client.logged_in:
                self.disabled = True
                if self._hidden:
                    self.add_class("hidden")


class ToggleButton(StaticButton):
    DEFAULT_CSS = """
    ToggleButton.-toggled {
        background: red;
        text-style: bold reverse;
    }
    """
    is_toggled: var[bool] = var(False, init=False)

    def __init__(
        self,
        label: str | Text | None = None,
        toggled_label: str | Text | None = None,
        check_user: bool = False,
        hidden: bool = False,
        toggled: bool = False,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(label, check_user, hidden, *args, **kwargs)
        self._default = label
        self._toggled_label = toggled_label
        self.is_toggled = toggled

    def watch_is_toggled(self, new: bool) -> None:
        self.toggle_class("-toggled")
        if new and self._toggled_label:
            self.label = self._toggled_label
        else:
            self.label = self._default or ""

    def toggle_state(self) -> None:
        self.is_toggled = not self.is_toggled

    def set_toggle_state(self, state: bool) -> None:
        self.is_toggled = state

    def update_toggle_label(self, label: str | Text | None) -> None:
        self._toggled_label = label

    def update_default_label(self, label: str | Text | None) -> None:
        self._default = label


class VolumeButton(ToggleButton):
    volume: var[int] = var(Config.get_config().persistant.volume, init=False)
    muted: var[bool] = var(False)

    def __init__(self, id: str | None = None, preview_mode: bool = False):  # noqa: A002
        super().__init__(f"{Config.get_config().persistant.volume}", "Muted", id=id)
        self._pre_mode = preview_mode

    def watch_volume(self, new: int) -> None:
        self.label = f"{new}"
        self.update_default_label(self.label)
        if self._pre_mode:
            self.post_message(Player.PreviewSetVolume(new))
        else:
            self.post_message(Player.PlayerSetVolume(new))
        if not self._pre_mode:
            Config.get_config().persistant.volume = new

    def watch_muted(self, new: bool) -> None:
        self.set_toggle_state(new)
        if self._pre_mode:
            if new:
                self.post_message(Player.PreviewSetVolume(0))
            else:
                self.post_message(Player.PreviewSetVolume(self.volume))
        elif new:
            self.post_message(Player.PlayerSetVolume(0))
        else:
            self.post_message(Player.PlayerSetVolume(self.volume))
        self.refresh_bindings()

    def validate_volume(self, volume: int) -> int:
        min_volume = 0
        max_volume = 100
        if volume < min_volume:
            volume = 0
        if volume > max_volume:
            volume = 100
        return volume

    def on_button_pressed(self) -> None:
        self.toggle()
        self.set_toggle_state(self.muted)

    def on_mouse_scroll_down(self) -> None:
        if self.muted:
            return
        self.volume -= 1

    def on_mouse_scroll_up(self) -> None:
        if self.muted:
            return
        self.volume += 1

    def toggle(self) -> None:
        self.muted = not self.muted


class LabelButton(Static, can_focus=True):
    DEFAULT_CSS = """
    LabelButton {
        width: auto;
        height: auto;
        padding: 0 1 0 1;
    }

    LabelButton:hover {
        background: $foreground 10%;
        color: $text;
    }

    LabelButton:focus {
        background: $accent;
        color: $text;
    }
    """

    class Clicked(Message):
        def __init__(self, control: LabelButton) -> None:
            super().__init__()
            self.widget = control

        @property
        def control(self) -> LabelButton:
            return self.widget

    def __init__(self, label: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.label = label

    def on_mount(self) -> None:
        self.update(self.label)

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Clicked(self))
