import asyncio

from fz_manager_plus.application.session import FactorioZoneSession
from fz_manager_plus.config import Settings
from fz_manager_plus.domain.messages import (
    IdleMessage,
    LoginResponse,
    ModsMessage,
    OptionsMessage,
    VisitMessage,
)


class FakeAPI:
    def __init__(self):
        self.user_token = "original-token"
        self.visit_secret = None
        self.calls = []
        self.closed = 0
        self.hooks = {}

    async def invoke(self, name, *args):
        self.calls.append((name, args))
        if hook := self.hooks.get(name):
            return await hook(*args)

    async def login(self, reconnected=False):
        await self.invoke("login", reconnected, self.user_token)
        self.user_token = "new-token"
        return LoginResponse(userToken=self.user_token)

    async def start_instance(self, *args):
        await self.invoke("start", *args)

    async def stop_instance(self, *args):
        await self.invoke("stop", *args)

    async def send_command(self, *args):
        await self.invoke("command", *args)

    async def toggle_mod(self, *args):
        await self.invoke("toggle", *args)

    async def delete_mod(self, *args):
        await self.invoke("delete_mod", *args)

    async def upload_mod(self, *args):
        await self.invoke("upload_mod", *args)

    async def upload_save(self, *args):
        await self.invoke("upload_save", *args)

    async def delete_save_slot(self, *args):
        await self.invoke("delete_save", *args)

    async def download_save_slot(self, *args):
        await self.invoke("download_save", *args)

    async def aclose(self):
        self.closed += 1


class FakeSocket:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.connections = 0
        self.closes = 0

    async def connect(self):
        self.connections += 1

    async def messages(self):
        while True:
            message = await self.queue.get()
            if isinstance(message, Exception):
                raise message
            if message is None:
                return
            yield message

    async def close(self):
        self.closes += 1


def initial_messages():
    return [
        VisitMessage(type="visit", secret="secret"),
        OptionsMessage(type="options", name="regions", options={"eu": "Europe"}),
        OptionsMessage(type="options", name="versions", options=["2.0"]),
        OptionsMessage(
            type="options", name="saves", options={"slot3": "third 1.0MB", "slot1": "first (empty)"}
        ),
        ModsMessage(type="mods", mods=[]),
        IdleMessage(type="idle"),
    ]


async def ready_session(**settings):
    api, socket = FakeAPI(), FakeSocket()
    session = FactorioZoneSession(api, socket, Settings(_env_file=None, **settings))
    await session.connect()
    for message in initial_messages():
        await session.handle_message(message)
    return session, api, socket


async def eventually(predicate, timeout=2):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.001)
