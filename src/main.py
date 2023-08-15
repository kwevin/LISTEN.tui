from display.display import Display
from listen.websocket import ListenWebsocket
from log import Logger

if __name__ == "__main__":
    log = Logger.create_logger(True)
    display = Display()
    display.start()
    listen = ListenWebsocket(display)
    listen.start()

    while True:
        e = input('k')
        print(e)
