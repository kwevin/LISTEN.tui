from src.display.display import Display
from src.listen.stream import StreamPlayerMPV
from src.listen.websocket import ListenWebsocket
from src.log import Logger

if __name__ == "__main__":
    log = Logger.create_logger(True)
    display = Display()
    display.start()
    listen = ListenWebsocket(display)
    listen.start()
    stream = StreamPlayerMPV(display)
    stream.start()

    while True:
        e = input('k')
        print(e)
