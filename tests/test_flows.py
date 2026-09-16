import asyncio
from pathlib import Path

from fz_manager_plus.domain.messages import RunningMessage
from fz_manager_plus.tui.components import ChoiceScreen, ConfirmScreen
from fz_manager_plus.tui.flows.save_flows import SaveFlows
from fz_manager_plus.tui.flows.server_flows import ServerFlows
from tests.fakes import ready_session


class Host:
    def __init__(self, session, answers):
        self.session = session
        self.settings = session.settings
        self.answers = iter(answers)
        self.screens = []
        self.logs = []
        self.saves = 0

    async def push_screen_wait(self, screen):
        self.screens.append(screen)
        return next(self.answers)

    def push_log(self, message):
        self.logs.append(message)

    async def save_settings(self):
        self.saves += 1


def test_start_flow_uses_real_slot_and_preserves_numeric_preference():
    async def check():
        session, api, _ = await ready_session(slot="3")

        async def start(*args):
            await session.handle_message(
                RunningMessage(type="running", launchId=1, socket="host:1")
            )

        api.hooks["start"] = start
        host = Host(session, ["eu", "2.0", "slot3", True])
        await ServerFlows(host).start()
        chooser = host.screens[2]
        assert isinstance(chooser, ChoiceScreen)
        assert chooser._options == [("third 1.0MB", "slot3"), ("first (empty)", "slot1")]
        assert chooser._default == "slot3"
        assert ("start", ("eu", "2.0", "slot3")) in api.calls
        assert host.settings.slot == "3"
        assert "host:1" in host.logs[-1].plain
        await session.aclose()

    asyncio.run(check())


def test_download_existing_archive_requires_confirmation(tmp_path):
    async def check():
        session, api, _ = await ready_session()
        target = tmp_path / "slot3.zip"
        target.write_bytes(b"existing")
        host = Host(session, [tmp_path, False])
        await SaveFlows(host).download("slot3")
        assert isinstance(host.screens[-1], ConfirmScreen)
        assert target.read_bytes() == b"existing"
        assert not any(name == "download_save" for name, _ in api.calls)
        host = Host(session, [tmp_path, True])
        await SaveFlows(host).download("slot3")
        calls = [args for name, args in api.calls if name == "download_save"]
        assert calls[0][0] == "slot3"
        assert Path(calls[0][1]) == target
        await session.aclose()

    asyncio.run(check())
