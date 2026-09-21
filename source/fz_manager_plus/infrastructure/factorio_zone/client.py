import os
import secrets
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import httpx

from fz_manager_plus.config import Settings
from fz_manager_plus.domain.errors import ApiError, AuthenticationError
from fz_manager_plus.domain.messages import LoginResponse
from fz_manager_plus.utils.api_router.http import ApiRouterHttp
from fz_manager_plus.utils.async_io import blocking_io


class MultipartUpload(httpx.AsyncByteStream):
    """Streaming multipart body with disk reads off the event loop."""

    def __init__(self, fields: dict[str, str], name: str, file: BinaryIO, size: int, progress):
        self.file, self.size, self.progress = file, size, progress
        self.boundary = secrets.token_hex(16)
        escaped_name = (
            name.replace("\\", "\\\\").replace('"', "%22").replace("\r", "%0D").replace("\n", "%0A")
        )
        parts = [
            f'--{self.boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
            for key, value in fields.items()
        ]
        parts.append(
            f'--{self.boundary}\r\nContent-Disposition: form-data; name="file"; filename="{escaped_name}"\r\n'
            "Content-Type: application/x-zip-compressed\r\n\r\n"
        )
        self.prefix = "".join(parts).encode()
        self.suffix = f"\r\n--{self.boundary}--\r\n".encode()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": f"multipart/form-data; boundary={self.boundary}",
            "Content-Length": str(len(self.prefix) + self.size + len(self.suffix)),
        }

    async def __aiter__(self):
        yield self.prefix
        done = 0
        while chunk := await blocking_io(self.file.read, 256 * 1024):
            done += len(chunk)
            if done > self.size:
                raise ValueError("File size changed during upload")
            yield chunk
            if self.progress:
                self.progress(done)
        if done != self.size:
            raise ValueError("File size changed during upload")
        yield self.suffix


class FactorioZoneAPI:
    """Owns its HTTP client, including an injected client, until aclose()."""

    def __init__(self, settings: Settings, *, http: httpx.AsyncClient):
        self.settings = settings
        self.visit_secret: str | None = None
        self.user_token = settings.user_token
        self.transport = ApiRouterHttp(http)

    def _request(self, path: str, **kwargs) -> httpx.Request:
        return self.transport.build_request(
            "POST", f"https://{self.settings.factorio_zone_endpoint}{path}", **kwargs
        )

    async def _post(self, path: str, **fields) -> None:
        await self.transport.execute(
            self._request(path, data={"visitSecret": self.visit_secret, **fields})
        )

    async def login(self, reconnected: bool = False) -> LoginResponse:
        try:
            response = await self.transport.execute(
                self._request(
                    "/api/user/login",
                    data={
                        "userToken": self.user_token,
                        "visitSecret": self.visit_secret,
                        "reconnected": reconnected,
                    },
                ),
                LoginResponse,
            )
        except ApiError as error:
            if error.status_code in (401, 403):
                raise AuthenticationError(
                    "Authentication failed. Enter your user token again."
                ) from error
            raise
        assert response is not None
        self.user_token = response.user_token
        return response

    async def toggle_mod(self, mod_id: int, enabled: bool) -> None:
        await self._post("/api/mod/toggle", modId=mod_id, enabled=enabled)

    async def delete_mod(self, mod_id: int) -> None:
        await self._post("/api/mod/delete", modId=mod_id)

    async def _upload(
        self, endpoint: str, name: str, file: BinaryIO, size: int, limit: int, progress, **fields
    ) -> None:
        if size < 0 or size > limit:
            raise ValueError(f"File size must be between 0 and {limit} bytes")
        body = MultipartUpload(
            {"visitSecret": self.visit_secret or "", "size": str(size), **fields},
            name,
            file,
            size,
            progress,
        )
        await self.transport.execute(
            self._request(endpoint, content=body, headers=body.headers, timeout=60)
        )

    async def upload_mod(
        self, name: str, file: BinaryIO, size: int, progress: Callable[[int], None] | None = None
    ) -> None:
        await self._upload(
            "/api/mod/upload", name, file, size, self.settings.max_mod_size, progress
        )

    async def upload_save(
        self,
        name: str,
        file: BinaryIO,
        size: int,
        slot: str,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        await self._upload(
            "/api/save/upload", name, file, size, self.settings.max_save_size, progress, save=slot
        )

    async def delete_save_slot(self, slot: str) -> None:
        await self._post("/api/save/delete", save=slot)

    async def download_save_slot(
        self, slot: str, file_path: str, progress: Callable[[int], None] | None = None
    ) -> None:
        request = self._request(
            "/api/save/download", data={"visitSecret": self.visit_secret, "save": slot}, timeout=60
        )
        response = await self.transport.send(request, stream=True)
        temporary: Path | None = None
        try:
            if not response.is_success:
                await response.aread()
                self.transport.check_response(response)
            target = Path(file_path)
            fd, name = tempfile.mkstemp(
                prefix=f".{target.name}-", suffix=".part", dir=target.parent
            )
            temporary = Path(name)
            with os.fdopen(fd, "wb") as file:
                done = 0
                async for chunk in response.aiter_bytes(256 * 1024):
                    await blocking_io(file.write, chunk)
                    done += len(chunk)
                    if progress:
                        progress(done)
                await blocking_io(file.flush)
                await blocking_io(os.fsync, file.fileno())
            # Atomic commit; no asynchronous work may replace the file after cancellation.
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            await response.aclose()

    async def send_command(self, launch_id: int, command: str) -> None:
        await self._post("/api/instance/console", launchId=launch_id, input=command)

    async def start_instance(self, region: str, version: str, save: str) -> None:
        await self._post("/api/instance/start", region=region, version=version, save=save)

    async def stop_instance(self, launch_id: int) -> None:
        await self.transport.execute(
            self._request(
                "/api/instance/stop",
                data={"visitSecret": self.visit_secret, "launchId": launch_id},
                timeout=self.settings.stop_timeout,
            )
        )

    async def aclose(self) -> None:
        await self.transport.aclose()
