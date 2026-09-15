from collections.abc import Callable

import httpx

from fz_manager.config import Settings, get_settings
from fz_manager.infrastructure.factorio_zone.models import LoginResponse
from fz_manager.utils.api_router.http import ApiRouterHttp, UploadProgressFile

router = ApiRouterHttp(
    client=httpx.AsyncClient(
        base_url=f"https://{get_settings().factorio_zone_endpoint}",
    )
)


class FactorioZoneAPI:
    def __init__(self, settings: Settings, visit_secret: str | None = None):
        self.settings = settings
        self.visit_secret = visit_secret

    @router.endpoint(response_model=LoginResponse)
    def login(self, reconnected: bool = False) -> httpx.Request:
        return router.build_request(
            method="POST",
            path="/api/user/login",
            data={
                "userToken": self.settings.user_token,
                "visitSecret": self.visit_secret,
                "reconnected": reconnected,
            },
        )

    @router.endpoint()
    def toggle_mod(self, mod_id: int, enabled: bool) -> httpx.Request:
        return router.build_request(
            method="POST",
            path="/api/mod/toggle",
            data={
                "visitSecret": self.visit_secret,
                "modId": mod_id,
                "enabled": enabled,
            },
        )

    @router.endpoint()
    def delete_mod(self, mod_id: int) -> httpx.Request:
        return router.build_request(
            method="POST",
            path="/api/mod/delete",
            data={
                "visitSecret": self.visit_secret,
                "modId": mod_id,
            },
        )

    @router.endpoint()
    def upload_mod(
        self,
        name: str,
        file,
        size: int,
        progress: Callable[[int], None] | None = None,
    ) -> httpx.Request:
        if size > self.settings.max_mod_size:
            raise ValueError(f"Mod file must be under {self.settings.max_mod_size} bytes")
        upload_file = UploadProgressFile(file, progress)
        return router.build_request(
            method="POST",
            path="/api/mod/upload",
            data={
                "visitSecret": self.visit_secret,
                "size": str(size),
            },
            files={"file": (name, upload_file, "application/x-zip-compressed")},
        )

    @router.endpoint()
    def delete_save_slot(self, slot: str) -> httpx.Request:
        return router.build_request(
            method="POST",
            path="/api/save/delete",
            data={
                "visitSecret": self.visit_secret,
                "save": slot,
            },
        )

    @router.endpoint()
    def upload_save(
        self, name: str, file, size: int, slot: str, progress: Callable[[int], None] | None = None
    ) -> httpx.Request:
        if size > self.settings.max_save_size:
            raise ValueError(f"Save file must be under {self.settings.max_save_size} bytes")
        upload_file = UploadProgressFile(file, progress)
        return router.build_request(  # noqa
            method="POST",
            path="/api/save/upload",
            data={
                "visitSecret": self.visit_secret,
                "size": str(size),
                "save": slot,
            },
            files={"file": (name, upload_file, "application/x-zip-compressed")},
        )

    async def download_save_slot(
        self,
        slot: str,
        file_path: str,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        request = router.build_request(
            method="POST",
            path="/api/save/download",
            data={
                "visitSecret": self.visit_secret,
                "save": slot,
            },
        )
        response = await router.send(request, stream=True)
        try:
            if not response.is_success:
                await response.aread()
                raise httpx.HTTPStatusError(
                    f"Error downloading save: {response.text}",
                    request=request,
                    response=response,
                )
            with open(file_path, "wb") as file:
                async for chunk in response.aiter_bytes(8192):
                    if chunk:
                        file.write(chunk)
                        if progress:
                            progress(file.tell())
        finally:
            await response.aclose()

    @router.endpoint()
    def send_command(self, launch_id: int, command: str) -> httpx.Request:
        return router.build_request(
            method="POST",
            path="/api/instance/console",
            data={
                "visitSecret": self.visit_secret,
                "launchId": launch_id,
                "input": command,
            },
        )

    @router.endpoint()
    def start_instance(self, region: str, version: str, save: str) -> httpx.Request:
        return router.build_request(
            method="POST",
            path="/api/instance/start",
            data={
                "visitSecret": self.visit_secret,
                "region": region,
                "version": version,
                "save": save,
            },
        )

    @router.endpoint()
    def stop_instance(self, launch_id: int) -> httpx.Request:
        return router.build_request(
            method="POST",
            path="/api/instance/stop",
            data={
                "visitSecret": self.visit_secret,
                "launchId": launch_id,
            },
            timeout=3600,
        )
