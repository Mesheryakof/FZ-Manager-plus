import asyncio

from fz_manager.api.client import FZClient


class InstanceService:
    """Orchestration for starting/stopping the Factorio server instance."""

    def __init__(self, client: FZClient):
        self.client = client

    async def start(self, region, version, slot, log_listener=None):
        if log_listener:
            self.client.add_logs_listener(log_listener)
        await self.client.start_instance(region, version, f"slot{slot}")
        while not self.client.running and not self.client.server_address:
            await asyncio.sleep(1)
        if log_listener:
            self.client.remove_logs_listener(log_listener)

    async def stop(self, log_listener=None):
        if log_listener:
            self.client.add_logs_listener(log_listener)
        await self.client.stop_instance()
        while self.client.running:
            await asyncio.sleep(1)
        if log_listener:
            self.client.remove_logs_listener(log_listener)
