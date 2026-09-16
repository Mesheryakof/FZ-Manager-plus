import asyncio

import pytest

from fz_manager_plus.application.session import FactorioZoneSession
from fz_manager_plus.config import Settings
from fz_manager_plus.domain.errors import AuthenticationError, DisconnectedError, OperationError
from fz_manager_plus.domain.messages import (
    BlankMessage,
    ErrorMessage,
    IdleMessage,
    LogMessage,
    OptionsMessage,
    RunningMessage,
    StartingMessage,
    WarnMessage,
)
from fz_manager_plus.domain.state import (
    AuthenticationRequired,
    ConnectionStatus,
    LogEvent,
    ServerStatus,
)
from tests.fakes import FakeAPI, FakeSocket, eventually, initial_messages, ready_session


def test_empty_logs_unknown_messages_and_async_callable_listener():
    async def check():
        session, _, _ = await ready_session()
        received = []

        class Listener:
            async def __call__(self, event):
                received.append(event)

        session.subscribe(Listener())
        for message in (
            WarnMessage(type="warn"),
            ErrorMessage(type="error"),
            BlankMessage(type="future"),
        ):
            await session.handle_message(message)
        logs = [event for event in received if isinstance(event, LogEvent)]
        assert [event.text for event in logs[:2]] == ["", ""]
        assert logs[-1].level == "warn"
        await session.aclose()

    asyncio.run(check())


def test_start_waits_for_running_and_address_and_times_out():
    async def check():
        session, api, _ = await ready_session(start_timeout=0.05)
        task = asyncio.create_task(session.start_instance("eu", "2.0", "slot3"))
        await eventually(lambda: any(name == "start" for name, _ in api.calls))
        await session.handle_message(StartingMessage(type="starting", launchId=4))
        await asyncio.sleep(0)
        assert not task.done()
        await session.handle_message(RunningMessage(type="running", launchId=4))
        assert not task.done()
        await session.handle_message(
            RunningMessage(type="running", launchId=4, socket="127.0.0.1:1234")
        )
        await task
        assert session.server_status == ServerStatus.RUNNING
        await session.handle_message(IdleMessage(type="idle"))
        with pytest.raises(TimeoutError):
            await session.start_instance("eu", "2.0", "slot3")
        assert len([call for call in api.calls if call[0] == "start"]) == 2
        await session.aclose()

    asyncio.run(check())


def test_start_validates_slot_identity_not_dictionary_position():
    async def check():
        session, api, _ = await ready_session()
        assert session.used_save_slots() == [(3, "third 1.0MB")]
        assert not session.is_save_slot_used(2)
        with pytest.raises(OperationError, match="options changed"):
            await session.start_instance("eu", "2.0", "slot2")
        with pytest.raises(OperationError, match="Unknown"):
            await session.delete_save_slot("slot2")
        assert not any(name in ("start", "delete_save") for name, _ in api.calls)
        await session.aclose()

    asyncio.run(check())


def test_log_deduplication_is_launch_scoped_and_bounded():
    async def check():
        session, _, _ = await ready_session()
        received = []
        session.subscribe(received.append)
        for launch in (1, 1, 2):
            await session.handle_message(
                LogMessage(type="log", num=1, launchId=launch, line=str(launch))
            )
        assert [event.text for event in received if isinstance(event, LogEvent)] == ["1", "2"]
        for number in range(10_100):
            await session.handle_message(LogMessage(type="log", num=number, launchId=3))
        assert len(session._logs) == 10_000
        await session.aclose()

    asyncio.run(check())


def test_disconnect_interrupts_inflight_command_without_replay():
    async def check():
        session, api, _ = await ready_session()
        await session.handle_message(RunningMessage(type="running", launchId=4, socket="host:1234"))
        finished = asyncio.Event()

        async def command(*args):
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()

        api.hooks["command"] = command
        task = asyncio.create_task(session.send_command("/save"))
        await eventually(lambda: any(name == "command" for name, _ in api.calls))
        await session._disconnect()
        with pytest.raises(DisconnectedError):
            await task
        assert finished.is_set()
        assert len([call for call in api.calls if call[0] == "command"]) == 1
        await session.aclose()

    asyncio.run(check())


def test_stop_waits_for_idle_and_disconnect_aborts_wait():
    async def check():
        session, api, _ = await ready_session()
        await session.handle_message(RunningMessage(type="running", launchId=4, socket="host:1234"))
        task = asyncio.create_task(session.stop_instance())
        await eventually(lambda: any(name == "stop" for name, _ in api.calls))
        assert not task.done()
        await session.handle_message(IdleMessage(type="idle"))
        await task
        await session.handle_message(RunningMessage(type="running", launchId=5, socket="host:1234"))
        task = asyncio.create_task(session.stop_instance())
        await eventually(lambda: len([call for call in api.calls if call[0] == "stop"]) == 2)
        await session._disconnect()
        with pytest.raises(DisconnectedError):
            await task
        await session.aclose()

    asyncio.run(check())


def test_reconnect_uses_new_token_and_clears_readiness():
    async def check():
        api, socket = FakeAPI(), FakeSocket()
        session = FactorioZoneSession(api, socket, Settings(_env_file=None))
        for message in initial_messages():
            socket.queue.put_nowait(message)
        runner = asyncio.create_task(session.run())
        await eventually(lambda: session.state.connection == ConnectionStatus.CONNECTED)
        socket.queue.put_nowait(DisconnectedError("offline"))
        await eventually(lambda: session.state.connection == ConnectionStatus.DISCONNECTED)
        assert not session.state.ready
        with pytest.raises(DisconnectedError):
            await session.toggle_mod(1, True)
        for message in initial_messages():
            socket.queue.put_nowait(message)
        await eventually(
            lambda: (
                socket.connections == 2 and session.state.connection == ConnectionStatus.CONNECTED
            )
        )
        logins = [args for name, args in api.calls if name == "login"]
        assert logins == [(False, "original-token"), (True, "new-token")]
        await asyncio.gather(session.aclose(), session.aclose())
        assert runner.done()
        assert api.closed == 1

    asyncio.run(check())


def test_auth_failure_requests_token_without_retry():
    async def check():
        api, socket = FakeAPI(), FakeSocket()

        async def fail(*args):
            raise AuthenticationError("invalid token")

        api.hooks["login"] = fail
        session = FactorioZoneSession(api, socket, Settings(_env_file=None))
        events = []
        session.subscribe(events.append)
        socket.queue.put_nowait(initial_messages()[0])
        await session.run()
        assert socket.connections == 1
        assert session.state.connection == ConnectionStatus.AUTH_REQUIRED
        assert any(isinstance(event, AuthenticationRequired) for event in events)
        await session.aclose()

    asyncio.run(check())


def test_invalid_options_do_not_poison_state():
    async def check():
        session, _, _ = await ready_session()
        await session.handle_message(
            OptionsMessage(type="options", name="saves", options=["not a mapping"])
        )
        assert "slot3" in session.saves
        await session.aclose()

    asyncio.run(check())


def test_missing_launch_id_can_arrive_in_log():
    async def check():
        session, _, _ = await ready_session()
        await session.handle_message(StartingMessage(type="starting"))
        await session.handle_message(LogMessage(type="log", num=1, launchId=42))
        await session.handle_message(RunningMessage(type="running", socket="host:42"))
        assert session.launch_id == 42
        await session.aclose()

    asyncio.run(check())
