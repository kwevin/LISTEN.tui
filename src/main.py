from log import Logger
from src.interface import Interface
from src.module.listen_ws import ListenMoe

if __name__ == "__main__":
    log = Logger.create_logger(True)
    interface = Interface(log)
    interface.start()
    listen = ListenMoe(interface, log)
    listen.start()

    while True:
        e = input('k')
        print(e)
