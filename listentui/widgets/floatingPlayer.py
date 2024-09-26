from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message

from listentui.listen.interface import ListenWsData, Song
from listentui.widgets.songContainer import SongContainer


class ShowFloatingPlayer(Message):
    def __init__(self) -> None:
        super().__init__()


class HideFloatingPlayer(Message):
    def __init__(self) -> None:
        super().__init__()


class FloatingPlayer(Container):
    # all the important is because I need to rewrite a whole lot of css to make sure it doesnt touch this Widget
    DEFAULT_CSS = """
    FloatingPlayer {
        layer: floating_player;
        border-left: heavy $primary;
        dock: top;
        display: none;
        background: $background-lighten-1;
        height: 2 !important;
        width: 20 !important;
        offset: 2 1 !important;
        padding: 0 0 !important;
        align: left top !important;

        & SongContainer {
            height: 2 !important;
            margin-left: 1 !important;
        }
    }
    """

    def __init__(self, ws_data: ListenWsData | None = None, song: Song | None = None) -> None:
        super().__init__(id="floating_player")
        self.ws_data = ws_data
        self.song = song
        self.mouse_drag = False
        self.mouse_relative: tuple[int, int] = (0, 0)

    def compose(self) -> ComposeResult:
        yield SongContainer(self.song)

    def on_mount(self) -> None:
        screen_layers = list(self.screen.styles.layers)
        if "floating_player" not in screen_layers:
            screen_layers.append("floating_player")
        self.screen.styles.layers = tuple(screen_layers)  # type: ignore

    def update(self, data: tuple[ListenWsData, Song]) -> None:
        ws_data, song = data
        self.ws_data = ws_data
        self.song = song
        self.query_one(SongContainer).update_song(song)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.mouse_drag = True
        self.capture_mouse()
        self.mouse_relative = (event.x, event.y)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.mouse_drag:
            offset = (
                event.screen_x - self.mouse_relative[0],
                event.screen_y - self.mouse_relative[1],
            )
            self.styles.offset = offset

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self.mouse_drag = False
        self.release_mouse()

    def show(self) -> None:
        self.styles.display = "block"
        self.styles.offset = (4, 2)

    def hide(self) -> None:
        self.styles.display = "none"

    def on_unmount(self) -> None:
        self.app.post_message(ShowFloatingPlayer())


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    class MyApp(App[None]):
        def compose(self) -> ComposeResult:
            yield FloatingPlayer()

        async def on_mount(self) -> None:
            self.query_one(FloatingPlayer).show()

    app = MyApp()
    app.run()


# TODO: currently all the modal screen recomposes themselves after fetching the information
# which deletes the floating player
