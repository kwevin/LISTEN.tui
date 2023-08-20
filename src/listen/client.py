import aiohttp


class ListenAPIClient:
    ...


class Listen:
    def __init__(self) -> None:
        pass

    def __enter__(self):
        ...

    def __exit__(self):
        ...

    def __iter__(self):
        ...

    def __next__(self):
        ...  # return instance of ListenAPIClient

    def __await__(self):
        ...

    # def __aenter__(self):
    #     ...

    # def __aexit__(self, type, value, traceback):
    #     ...

    # def __aiter__(self):
    #     ...
    
    # def __anext__(self):
    #     ...
    
    # def __await__(self):
    #     ...


# listen = Listen()
# ...

# with Listen() as listen:
#     ...

# for e in Listen():
#     ...

# listen = await Listen()
# ...

# async with Listen() as listen:
#   ...

# async for listen in Listen():
#   ...
