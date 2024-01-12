from textual import work
from textual.app import App

from ..data import Config
from ..listen import ListenClient
from ..screen import Main
from ..utilities import ListenLog


class ListentuiApp(App[None]):
    TITLE = "LISTEN.moe"

    async def on_mount(self) -> None:
        ListenLog.create_logger(True)
        await self.login().wait()
        self.push_screen(Main())

    @work(group="login", name="login")
    async def login(self) -> None:
        username = Config.get_config().client.username
        password = Config.get_config().client.password
        token = Config.get_config().persistant.token
        if username and password:
            client = await ListenClient.login(username, password, token)
        else:
            client = ListenClient.get_instance()

        user = client.current_user
        if user and user.token:
            Config.get_config().persistant.token = user.token
            Config.get_config().save()


def run() -> None:
    ListentuiApp().run()


if __name__ == "__main__":
    ListentuiApp().run()
