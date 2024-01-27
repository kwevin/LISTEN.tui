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

    @work
    async def login(self) -> None:
        config = Config.get_config()
        username = config.client.username
        password = config.client.password
        token = config.persistant.token
        if username and password:
            client = await ListenClient.login(username, password, token)
            if not client:
                print("Login failed, please check your username and password")
                return
        else:
            client = ListenClient.get_instance()

        user = client.current_user
        if user and user.token:
            config = Config.get_config()
            config.persistant.token = user.token
            config.save()


def run() -> None:
    ListentuiApp().run()


if __name__ == "__main__":
    ListentuiApp().run()
