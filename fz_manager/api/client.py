import asyncio
import json
import re
import ssl
from collections.abc import Callable, Coroutine
from inspect import iscoroutinefunction

import certifi
import httpx
from websockets import client

from fz_manager.api.models import Mod, Save
from fz_manager.terminal import Term

FACTORIO_ZONE_ENDPOINT = "factorio.zone"


class ServerStatus:
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    RUNNING = "RUNNING"


class _UploadProgressFile:
    """Wraps a binary file object and reports cumulative bytes read via `cb`.

    Used in place of requests-toolbelt's MultipartEncoderMonitor to track
    upload progress with httpx's native multipart encoding, which reads the
    file object in chunks via `.read(size)`.
    """

    def __init__(self, file, cb: Callable = None):
        self._file = file
        self._cb = cb
        self._bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._file.read(size)
        self._bytes_read += len(chunk)
        if self._cb:
            self._cb(self._bytes_read)
        return chunk

    def seek(self, *args, **kwargs):
        return self._file.seek(*args, **kwargs)

    def tell(self):
        return self._file.tell()

    def fileno(self):
        return self._file.fileno()


class FZClient:
    def __init__(self, token: str = None):
        self.socket = None
        self._http = httpx.AsyncClient()
        self.user_token = token
        self.visit_secret = None
        self.referrer_code = None
        self.regions = {}
        self.versions = {}
        self.slots = {}
        self.saves = {}
        self.mods = []
        self.running = False
        self.launch_id = None
        self.region = None
        self.server_address = None
        self.server_status = ServerStatus.OFFLINE
        self.logs_map = {}
        self.logs_listeners: list[Callable[[str], Coroutine | Callable]] = []
        self.mods_sync = False
        self.saves_sync = False

    async def connect(self):
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self.socket = await client.connect(
            f"wss://{FACTORIO_ZONE_ENDPOINT}/ws", ping_interval=30, ping_timeout=10, ssl=ssl_context
        )
        while True:
            message = await self.socket.recv()
            data = json.loads(message)
            match data["type"]:
                case "visit":
                    self.visit_secret = data["secret"]
                    await self.login()
                case "options":
                    match data["name"]:
                        case "regions":
                            self.regions = data["options"]
                        case "versions":
                            self.versions = data["options"]
                        case "saves":
                            self.saves = data["options"]
                            self.saves_sync = True
                case "mods":
                    self.mods = data["mods"]
                    self.mods_sync = True
                case "idle":
                    self.running = False
                    self.launch_id = None
                    self.server_status = ServerStatus.OFFLINE
                    self.server_address = None
                case "starting":
                    self.running = True
                    self.launch_id = data.get("launchId")
                    self.server_status = ServerStatus.STARTING
                case "stopping":
                    self.running = True
                    self.launch_id = data.get("launchId")
                    self.server_status = ServerStatus.STOPPING
                case "running":
                    self.running = True
                    self.launch_id = data.get("launchId")
                    self.server_address = data.get("socket")
                    self.server_status = ServerStatus.RUNNING
                case "slot":
                    self.slots[data["slot"]] = data
                case "log":
                    log_id = data["num"]
                    if log_id not in self.logs_map:
                        log = data.get("line")
                        self.logs_map[log_id] = log_id
                        await self.on_new_log(log)
                case "info":
                    line = data.get("line")
                    if len(
                        match := re.findall(r"selecting connection (\d+\.\d+\.\d+\.\d+:\d+)", line)
                    ):
                        self.server_address = match[0]
                        self.server_status = ServerStatus.STARTING
                    log = Term.info("info", line)
                    await self.on_new_log(log)
                case "warn":
                    log = Term.warn("warn", data.get("line"))
                    await self.on_new_log(log)
                case "error":
                    log = Term.error("error", data.get("line"))
                    await self.on_new_log(log)

    async def wait_sync(self):
        while not self.mods_sync or not self.saves_sync:
            await asyncio.sleep(1)

    def add_logs_listener(self, listener):
        self.logs_listeners.append(listener)

    def remove_logs_listener(self, listener):
        self.logs_listeners.remove(listener)

    async def on_new_log(self, log: str):
        for listener in self.logs_listeners:
            if iscoroutinefunction(listener):
                await listener(log)
            else:
                listener(log)

    # ------ USER APIs ------------------------------------------------------------------
    async def login(self):
        resp = await self._http.post(
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/user/login",
            data={
                "userToken": self.user_token,
                "visitSecret": self.visit_secret,
                "reconnected": False,
            },
        )
        if resp.is_success:
            body = resp.json()
            self.user_token = body["userToken"]
            self.referrer_code = body["referralCode"]
        else:
            raise Exception(f"Error logging in: {resp.text}")

    # ------ MODs APIs ------------------------------------------------------------------
    async def toggle_mod(self, mod_id: int, enabled: bool):
        self.mods_sync = False
        resp = await self._http.post(
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/mod/toggle",
            data={"visitSecret": self.visit_secret, "modId": mod_id, "enabled": enabled},
        )
        if not resp.is_success:
            self.mods_sync = True
            raise Exception(f"Error in toggling mod: {resp.text}")

    async def delete_mod(self, mod_id: int):
        self.mods_sync = False
        resp = await self._http.post(
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/mod/delete",
            data={"visitSecret": self.visit_secret, "modId": mod_id},
        )
        if not resp.is_success:
            self.mods_sync = True
            raise Exception(f"Error in deleting mod: {resp.text}")

    async def upload_mod(self, mod: Mod, cb: Callable = None):
        if mod.size > 268435456:  # 256MB
            raise Exception("Mod file must be under 256MB")

        self.mods_sync = False
        with open(mod.filePath, "rb") as file:
            upload_file = _UploadProgressFile(file, cb)
            resp = await self._http.post(
                f"https://{FACTORIO_ZONE_ENDPOINT}/api/mod/upload",
                data={"visitSecret": self.visit_secret, "size": str(mod.size)},
                files={"file": (mod.name, upload_file, "application/x-zip-compressed")},
            )
        if not resp.is_success:
            self.mods_sync = True
            raise Exception(f"Error uploading mod: {resp.text}")

    # ------ SAVE APIs ------------------------------------------------------------------
    async def delete_save_slot(self, slot: str):
        self.saves_sync = False
        resp = await self._http.post(
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/save/delete",
            data={"visitSecret": self.visit_secret, "save": slot},
        )
        if resp.status_code != 200:
            self.saves_sync = True
            raise Exception(f"Error deleting save: {resp.text}")

    async def download_save_slot(self, slot: str, file_path: str, cb: Callable):
        async with self._http.stream(
            "POST",
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/save/download",
            data={"visitSecret": self.visit_secret, "save": slot},
        ) as resp:
            if resp.status_code != 200:
                self.saves_sync = True
                await resp.aread()
                raise Exception(f"Error downloading save: {resp.text}")
            with open(file_path, "wb") as file:
                async for chunk in resp.aiter_bytes(8192):
                    if chunk:
                        file.write(chunk)
                        cb(file.tell())

    async def upload_save(self, save: Save, cb: Callable = None):
        if save.size > 100663296:  # 96MB
            raise Exception("Save file must be under 96MB")

        self.saves_sync = False
        with open(save.filePath, "rb") as file:
            upload_file = _UploadProgressFile(file, cb)
            resp = await self._http.post(
                url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/save/upload",
                data={"visitSecret": self.visit_secret, "size": str(save.size), "save": save.slot},
                files={"file": (save.name, upload_file, "application/x-zip-compressed")},
            )
        if not resp.is_success:
            self.saves_sync = True
            raise Exception(f"Error uploading save: {resp.text}")

    # ------ INSTANCE APIs --------------------------------------------------------------
    async def send_command(self, command):
        resp = await self._http.post(
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/instance/console",
            data={"visitSecret": self.visit_secret, "launchId": self.launch_id, "input": command},
        )
        if resp.status_code != 200:
            raise Exception(f"Error sending console command: {resp.text}")

    async def start_instance(self, region, version, save):
        resp = await self._http.post(
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/instance/start",
            data={
                "visitSecret": self.visit_secret,
                "region": region,
                "version": version,
                "save": save,
            },
        )
        if resp.status_code != 200:
            raise Exception(f"Error starting instance: {resp.text}")
        self.launch_id = resp.json()["launchId"]

    async def stop_instance(self):
        resp = await self._http.post(
            url=f"https://{FACTORIO_ZONE_ENDPOINT}/api/instance/stop",
            data={
                "visitSecret": self.visit_secret,
                "launchId": self.launch_id,
            },
            timeout=3600,
        )
        if resp.status_code != 200:
            raise Exception(f"Error stopping instance: {resp.text}")
