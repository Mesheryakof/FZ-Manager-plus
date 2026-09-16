import asyncio
import io
import threading
import time
from email import policy
from email.parser import BytesParser

import httpx
import pytest

from fz_manager_plus.config import Settings
from fz_manager_plus.domain.errors import (
    ApiError,
    AuthenticationError,
    DecodeError,
    DisconnectedError,
)
from fz_manager_plus.infrastructure.factorio_zone.client import FactorioZoneAPI, MultipartUpload


def make_api(handler, endpoint="example.test"):
    return FactorioZoneAPI(
        Settings(factorio_zone_endpoint=endpoint, _env_file=None),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_client_endpoints_are_independent_and_clients_close():
    async def check():
        hosts = []

        def respond(request):
            hosts.append(request.url.host)
            return httpx.Response(200, json={"userToken": "new-token"})

        first, second = make_api(respond, "one.test"), make_api(respond, "two.test")
        assert (await first.login()).user_token == "new-token"
        await second.login()
        assert hosts == ["one.test", "two.test"]
        await first.aclose()
        await second.aclose()
        assert first.transport._http.is_closed and second.transport._http.is_closed

    asyncio.run(check())


@pytest.mark.parametrize("body", ["not json", "{}", "[]"])
def test_login_decode_errors_are_uniform(body):
    async def check():
        api = make_api(lambda request: httpx.Response(200, text=body))
        try:
            with pytest.raises(DecodeError):
                await api.login()
        finally:
            await api.aclose()

    asyncio.run(check())


def test_login_authentication_error_is_distinct():
    async def check():
        api = make_api(lambda request: httpx.Response(401, text="unauthorized"))
        try:
            with pytest.raises(AuthenticationError):
                await api.login()
        finally:
            await api.aclose()

    asyncio.run(check())


class DownloadStream(httpx.AsyncByteStream):
    def __init__(self, *, fail=False, wait=False):
        self.fail, self.wait = fail, wait
        self.closed = False
        self.started = asyncio.Event()

    async def __aiter__(self):
        yield b"x" * (256 * 1024)
        self.started.set()
        if self.fail:
            raise httpx.ReadError("download interrupted")
        if self.wait:
            await asyncio.Event().wait()
        yield b"end"

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("fail,cancel", [(False, False), (True, False), (False, True)])
def test_download_is_atomic_and_cleans_up(tmp_path, fail, cancel):
    async def check():
        target = tmp_path / "slot3.zip"
        target.write_bytes(b"old archive")
        stream = DownloadStream(fail=fail, wait=cancel)
        api = make_api(lambda request: httpx.Response(200, stream=stream))
        progress = []
        task = asyncio.create_task(api.download_save_slot("slot3", str(target), progress.append))
        if cancel:
            await stream.started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif fail:
            with pytest.raises(httpx.ReadError):
                await task
        else:
            await task
        assert stream.closed
        assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob(".*.part"))
        if fail or cancel:
            assert target.read_bytes() == b"old archive"
        else:
            assert target.read_bytes() == b"x" * (256 * 1024) + b"end"
            assert progress[-1] == target.stat().st_size
        await api.aclose()

    asyncio.run(check())


def test_download_http_failure_does_not_touch_target(tmp_path):
    async def check():
        target = tmp_path / "slot3.zip"
        target.write_bytes(b"old")
        api = make_api(lambda request: httpx.Response(503, text="unavailable"))
        try:
            with pytest.raises(ApiError):
                await api.download_save_slot("slot3", str(target))
            assert target.read_bytes() == b"old"
        finally:
            await api.aclose()

    asyncio.run(check())


def test_upload_multipart_contract_progress_and_file_ownership():
    async def check():
        captured = []

        def respond(request):
            captured.append(request)
            return httpx.Response(204)

        api = make_api(respond)
        api.visit_secret = "secret"
        file = io.BytesIO(b"archive")
        progress = []
        await api.upload_save("my save.zip", file, 7, "slot3", progress.append)
        request = captured[0]
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {request.headers['content-type']}\r\nMIME-Version: 1.0\r\n\r\n".encode()
            + request.content
        )
        fields = {
            part.get_param("name", header="content-disposition"): part
            for part in message.iter_parts()
        }
        assert fields["save"].get_payload(decode=True) == b"slot3"
        assert fields["visitSecret"].get_payload(decode=True) == b"secret"
        assert fields["size"].get_payload(decode=True) == b"7"
        assert fields["file"].get_filename() == "my save.zip"
        assert fields["file"].get_payload(decode=True) == b"archive"
        assert int(request.headers["content-length"]) == len(request.content)
        assert progress == [7]
        assert not file.closed
        await api.aclose()

    asyncio.run(check())


def test_upload_size_limits_and_changed_file():
    async def check():
        calls = []
        api = make_api(lambda request: calls.append(request) or httpx.Response(204))
        with pytest.raises(ValueError):
            await api.upload_mod("mod.zip", io.BytesIO(b"x"), api.settings.max_mod_size + 1)
        with pytest.raises(ValueError, match="changed"):
            await api.upload_mod("mod.zip", io.BytesIO(b"x"), 2)
        assert not calls
        await api.aclose()

    asyncio.run(check())


def test_streaming_reads_leave_event_loop_responsive():
    async def check():
        main_thread = threading.get_ident()
        reads = []

        class SlowFile(io.BytesIO):
            def read(self, size=-1):
                reads.append(threading.get_ident())
                time.sleep(0.015)
                return super().read(size)

        data = b"x" * (1024 * 1024)
        stream = MultipartUpload({}, "mod.zip", SlowFile(data), len(data), None)
        ticks = 0
        finished = False

        async def heartbeat():
            nonlocal ticks
            while not finished:
                ticks += 1
                await asyncio.sleep(0.002)

        beat = asyncio.create_task(heartbeat())
        async for _ in stream:
            pass
        finished = True
        await beat
        assert ticks >= 10
        assert reads and main_thread not in reads

    asyncio.run(check())


def test_network_errors_are_not_retried():
    async def check():
        calls = []

        def fail(request):
            calls.append(request)
            raise httpx.ConnectError("offline")

        api = make_api(fail)
        try:
            with pytest.raises(DisconnectedError):
                await api.send_command(1, "/save")
            assert len(calls) == 1
        finally:
            await api.aclose()

    asyncio.run(check())


def test_websocket_decoder_tolerates_unknown_and_malformed_messages():
    from fz_manager_plus.domain.messages import BlankMessage, WarnMessage
    from fz_manager_plus.infrastructure.factorio_zone.socket import FactorioZoneSocket

    class Socket:
        def __init__(self):
            self.closed = 0

        async def __aiter__(self):
            for raw in ("not-json", "[1,2]", '{"type":"future","value":1}', '{"type":"warn"}'):
                yield raw

        async def close(self):
            self.closed += 1

    async def check():
        transport = FactorioZoneSocket(Settings(_env_file=None))
        socket = Socket()
        transport._socket = socket
        messages = [message async for message in transport.messages()]
        assert all(isinstance(message, BlankMessage) for message in messages[:3])
        assert isinstance(messages[-1], WarnMessage) and messages[-1].line is None
        await transport.close()
        await transport.close()
        assert socket.closed == 1

    asyncio.run(check())
