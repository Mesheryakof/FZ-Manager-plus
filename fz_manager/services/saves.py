from typing import Callable

from fz_manager.api.client import FZClient
from fz_manager.api.models import Save


class SavesService:
    """Business logic for save-related operations (upload/delete/download/list slots)."""

    def __init__(self, client: FZClient):
        self.client = client

    def slots(self) -> list[str]:
        return list(self.client.saves.values().mapping.values())

    def used_slots(self) -> list[tuple[int, str]]:
        return [(i + 1, v) for i, v in enumerate(self.slots()) if not v.endswith('(empty)')]

    def is_slot_used(self, slot_index: int) -> bool:
        slot_name = f'slot{slot_index}'
        return self.client.saves[slot_name] != f'slot {slot_index} (empty)'

    @staticmethod
    def build_save(name: str, file_path: str, size: int, slot_name: str) -> Save:
        return Save(name, file_path, size, slot_name)

    async def upload_save(self, save: Save, cb: Callable = None):
        await self.client.upload_save(save, cb)

    async def delete_save_slot(self, slot_name: str):
        await self.client.delete_save_slot(slot_name)

    async def download_save_slot(self, slot_name: str, file_path: str, cb: Callable):
        await self.client.download_save_slot(slot_name, file_path, cb)
