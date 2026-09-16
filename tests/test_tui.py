import asyncio
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Button, Input

from fz_manager_plus.application.session import FactorioZoneSession
from fz_manager_plus.config import Settings, SettingsStore
from fz_manager_plus.domain.messages import ModEntry, ModsMessage, OptionsMessage
from fz_manager_plus.domain.state import (
    ConnectionStatus,
    Mod,
    TransferProgress,
    TransferResult,
    UploadItem,
)
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.app import FzManagerApp
from fz_manager_plus.tui.components import (
    ConfirmScreen,
    LogPane,
    MenuPane,
    ModsPane,
    ModsUploadScreen,
    SavesPane,
    StatusBar,
)
from tests.fakes import FakeAPI, FakeSocket, eventually, initial_messages


def make_app(tmp_path):
    settings = Settings(user_token="token", _env_file=None)
    api, socket = FakeAPI(), FakeSocket()
    session = FactorioZoneSession(api, socket, settings)
    store = SettingsStore(tmp_path, legacy_path=tmp_path / "missing")
    app = FzManagerApp(settings, session, store)
    for message in initial_messages():
        socket.queue.put_nowait(message)
    return app, api, socket


def test_tui_event_updates_under_modal_and_shutdown(tmp_path):
    async def check():
        app, api, socket = make_app(tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await eventually(lambda: app.session.state.connection == ConnectionStatus.CONNECTED)
            await pilot.pause()
            assert not app.main_screen.query_one(MenuPane).disabled
            assert app.store.path.exists()
            app.push_screen(ConfirmScreen("Still here?"))
            await pilot.pause()
            long_name = "very-long-mod-" * 30
            socket.queue.put_nowait(
                ModsMessage(type="mods", mods=[ModEntry(id=5, text=long_name, enabled=True)])
            )
            socket.queue.put_nowait(
                OptionsMessage(type="options", name="saves", options={"slot7": "new save"})
            )
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)
            assert app.main_screen.query_one(ModsPane).selection_list.option_count == 1
            assert app.main_screen.query_one(SavesPane).list_view.children[0].name == "slot7"
            await pilot.press("escape")
            await pilot.pause()
            await app.action_quit()
        assert api.closed == 1
        assert socket.closes >= 1

    asyncio.run(check())


def test_mod_selection_and_focus_survive_recompose(tmp_path):
    async def check():
        app, _, socket = make_app(tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await eventually(lambda: app.session.state.connection == ConnectionStatus.CONNECTED)
            mods = [ModEntry(id=i, text=f"mod-{i}", enabled=True) for i in range(30)]
            socket.queue.put_nowait(ModsMessage(type="mods", mods=mods))
            await pilot.pause()
            pane = app.main_screen.query_one(ModsPane)
            pane.selection_list.focus()
            pane.selection_list.highlighted = 20
            pane.selection_list.scroll_to(y=10, animate=False, force=True)
            await pilot.pause()
            scroll = pane.selection_list.scroll_y
            socket.queue.put_nowait(
                ModsMessage(type="mods", mods=[ModEntry(id=100, text="new", enabled=False), *mods])
            )
            await pilot.pause()
            current = pane.selection_list
            assert current.has_focus
            assert current.get_option_at_index(current.highlighted).value == 20
            assert current.scroll_y == scroll

    asyncio.run(check())


def test_disconnect_disables_actions_and_auth_requests_token(tmp_path):
    from fz_manager_plus.domain.errors import AuthenticationError
    from fz_manager_plus.tui.components.token_screen import TokenScreen

    async def check():
        app, api, socket = make_app(tmp_path)

        async def fail(*args):
            raise AuthenticationError("bad token")

        api.hooks["login"] = fail
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, TokenScreen)
            assert app.main_screen.query_one(MenuPane).disabled
            assert app.main_screen.query_one(LogPane).command_input.disabled
            api.hooks.clear()
            # The failed consumer left snapshot messages in this fake queue.
            # Feed a new visit too, just like a new WebSocket connection.
            socket.queue.put_nowait(initial_messages()[0])
            app.screen.query_one(Input).value = "replacement"
            await pilot.press("enter")
            await eventually(lambda: app.session.state.connection == ConnectionStatus.CONNECTED)
            await pilot.pause()
            assert not isinstance(app.screen, TokenScreen)

    asyncio.run(check())


def test_upload_dialog_reports_progress_and_preserves_cancel_semantics(tmp_path):
    async def check():
        gate = asyncio.Event()
        called = asyncio.Event()

        async def upload(notify):
            called.set()
            notify(TransferProgress(0, 2))
            await gate.wait()
            notify(TransferResult(0))
            notify(TransferResult(1, "rejected"))
            return ["two.zip"]

        items = [
            UploadItem("one.zip", 3, tmp_path / "one.zip"),
            UploadItem("two.zip", 4, tmp_path / "two.zip"),
        ]
        app = App()
        results = []
        async with app.run_test(size=(100, 35)) as pilot:
            screen = ModsUploadScreen("Upload?", items, upload)
            app.push_screen(screen, results.append)
            await pilot.pause()
            await pilot.press("escape")
            assert results == [None] and not called.is_set()
            screen = ModsUploadScreen("Upload?", items, upload)
            app.push_screen(screen, results.append)
            await pilot.pause()
            await pilot.click("#confirm")
            await called.wait()
            await pilot.press("escape")
            assert app.screen is screen
            gate.set()
            await pilot.pause()
            assert screen._finished and screen._failed == ["two.zip"]
            await pilot.click("#close")
            assert results == [None, ["two.zip"]]

    asyncio.run(check())


def test_quit_during_upload_cancels_jobs_and_closes_files(tmp_path):
    from fz_manager_plus.application.transfers import ModTransferService

    async def check():
        app, api, _ = make_app(tmp_path / "config")
        (tmp_path / "mod.zip").write_bytes(b"archive")
        streams = []

        async def hold(name, stream, size, progress):
            streams.append(stream)
            await asyncio.Event().wait()

        api.hooks["upload_mod"] = hold
        async with app.run_test(size=(100, 35)) as pilot:
            await eventually(lambda: app.session.state.connection == ConnectionStatus.CONNECTED)
            service = ModTransferService(app.session)
            items = (await service.prepare(str(tmp_path))).upload

            async def upload(notify):
                return await service.upload(items, notify)

            app.push_screen(ModsUploadScreen("Upload?", items, upload))
            await pilot.pause()
            await pilot.click("#confirm")
            await eventually(lambda: bool(streams))
            await app.action_quit()
        assert all(stream.closed for stream in streams)
        assert not app.session._operations
        assert api.closed == 1

    asyncio.run(check())


def test_status_bar_server_address_opens_steam_direct_connect():
    class StatusBarApp(App):
        def compose(self) -> ComposeResult:
            yield StatusBar("", id="status-bar")

    async def check():
        app = StatusBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(StatusBar)
            bar.update_status(3, "RUNNING", "1.2.3.4:34197")
            await pilot.pause()
            with patch("fz_manager_plus.tui.components.status_bar.webbrowser.open") as mock_open:
                await pilot.click(bar, offset=(bar.visual.cell_length - 1, 0))
                await pilot.pause()
                mock_open.assert_called_once_with(
                    "steam://run/427520//--mp-connect%201.2.3.4:34197/"
                )

                mock_open.reset_mock()
                await pilot.click(bar, offset=(2, 0))
                await pilot.pause()
                mock_open.assert_not_called()

            bar.update_status(None, "OFFLINE", None)
            await pilot.pause()
            assert "Server:" not in str(bar.content)

    asyncio.run(check())


def test_push_log_appends_plain_text_to_server_log_file(tmp_path):
    async def check():
        app, _, _ = make_app(tmp_path)
        async with app.run_test() as pilot:
            await eventually(lambda: app.session.state.connection == ConnectionStatus.CONNECTED)
            app.push_log(Term.info("[test]", "hello world"))
            await pilot.pause()

        content = app.store.server_log_path.read_text(encoding="utf-8")
        line = content.splitlines()[-1]
        assert line.endswith("] [test] hello world")
        assert line.startswith("[") and "T" in line.split("]")[0]

    asyncio.run(check())


def test_mods_pane_hover_reveals_toggle_and_delete_buttons():
    events = []

    class ModsPaneApp(App):
        def compose(self) -> ComposeResult:
            yield ModsPane([Mod(1, "ModOne", True), Mod(2, "ModTwo", False)])

        def on_mods_pane_toggled(self, event: ModsPane.Toggled) -> None:
            events.append(("toggle", event.mod_id, event.enabled))

        def on_mods_pane_delete_requested(self, event: ModsPane.DeleteRequested) -> None:
            events.append(("delete", event.mod_id))

    async def check():
        app = ModsPaneApp()
        async with app.run_test(size=(60, 20)) as pilot:
            pane = app.query_one(ModsPane)
            toggle_button = pane.query_one("#mod-toggle-button", Button)
            delete_button = pane.query_one("#mod-delete-button", Button)
            assert toggle_button.disabled and delete_button.disabled

            await pilot.hover(pane.selection_list, offset=(3, 1))
            await pilot.pause()
            assert not toggle_button.disabled
            assert toggle_button.label.plain == "Disable"  # mod 1 starts enabled

            # Clicking the button leaves the SelectionList first (moving to the
            # toolbar below it), which must not clear the hovered mod before
            # the click is processed.
            await pilot.click(toggle_button)
            await pilot.pause()
            assert events == [("toggle", 1, False)]

            await pilot.hover(pane.selection_list, offset=(3, 2))
            await pilot.pause()
            assert toggle_button.label.plain == "Enable"  # mod 2 starts disabled

            await pilot.click(delete_button)
            await pilot.pause()
            assert events == [("toggle", 1, False), ("delete", 2)]

    asyncio.run(check())


def test_saves_pane_hover_reveals_download_upload_delete_buttons():
    events = []

    class SavesPaneApp(App):
        def compose(self) -> ComposeResult:
            yield SavesPane({"slot1": "first 1.0MB"})

        def on_saves_pane_download_requested(self, event: SavesPane.DownloadRequested) -> None:
            events.append(("download", event.slot))

        def on_saves_pane_upload_requested(self, event: SavesPane.UploadRequested) -> None:
            events.append(("upload", event.slot))

        def on_saves_pane_delete_requested(self, event: SavesPane.DeleteRequested) -> None:
            events.append(("delete", event.slot))

    async def check():
        app = SavesPaneApp()
        async with app.run_test(size=(60, 20)) as pilot:
            pane = app.query_one(SavesPane)
            download_button = pane.query_one("#save-download-button", Button)
            upload_button = pane.query_one("#save-upload-button", Button)
            delete_button = pane.query_one("#save-delete-button", Button)
            assert download_button.disabled and upload_button.disabled and delete_button.disabled

            await pilot.hover(pane.list_view, offset=(3, 0))
            await pilot.pause()
            assert not upload_button.disabled

            await pilot.click(upload_button)
            await pilot.pause()
            assert events == [("upload", "slot1")]

            await pilot.click(delete_button)
            await pilot.pause()
            assert events == [("upload", "slot1"), ("delete", "slot1")]

    asyncio.run(check())
