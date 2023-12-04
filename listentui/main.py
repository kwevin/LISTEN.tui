from rich.console import RenderableType
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, ContentSwitcher, Header, Label, Placeholder


class ListentuiApp(App[None]):
    TITLE = "LISTEN.moe"
    CSS_PATH = "listentui.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(id="app-grid"):
            with Vertical(id="sidebar"):
                yield Button("T", id="home-page")
                yield Button("T", id="user-page")
                yield Button("T", id="terminal-page")
                yield Button("T", id="download-progress-page")
                yield Button("T", id="setting-page")
            with ContentSwitcher(initial="home-page"):
                with Grid(id="home-page"):
                    yield Placeholder(id="home-main")
                    yield Placeholder(id="home-sub")
                    yield Placeholder(id="home-user")
                yield Placeholder(id="user-page")
                yield Placeholder(id="terminal-page")
                yield Placeholder(id="download-progress-page")
                yield Placeholder(id="setting-page")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.query_one(ContentSwitcher).current = event.button.id


if __name__ == "__main__":
    app = ListentuiApp()
    app.run()
