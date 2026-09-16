from __future__ import annotations

import asyncio

from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ChoiceScreen, ConfirmScreen
from fz_manager_plus.tui.flows.host import FlowHost


class ServerFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    async def start(self) -> None:
        session, settings = self.host.session, self.host.settings

        regions = sorted(session.regions.items())
        if not regions:
            self.host.push_log(Term.error("[start server]", "No regions available yet (still syncing?)"))
            return
        region = await self.host.push_screen_wait(
            ChoiceScreen(
                "Choose a region:",
                [(f"{code} - {name}", code) for code, name in regions],
                default=settings.region,
            )
        )
        if region is None:
            return
        settings.region = region

        versions = list(session.versions)
        if not versions:
            self.host.push_log(
                Term.error("[start server]", "No versions available yet (still syncing?)")
            )
            return
        version = await self.host.push_screen_wait(
            ChoiceScreen(
                "Choose a Factorio version:",
                [(v, v) for v in versions],
                default=settings.version,
            )
        )
        if version is None:
            return
        settings.version = version

        slots = list(session.saves.values())
        if not slots:
            self.host.push_log(
                Term.error("[start server]", "No save slots available yet (still syncing?)")
            )
            return
        slot = await self.host.push_screen_wait(
            ChoiceScreen(
                "Choose a save slot:",
                [(desc, str(i + 1)) for i, desc in enumerate(slots)],
                default=settings.slot,
            )
        )
        if slot is None:
            return
        settings.slot = slot

        confirmed = await self.host.push_screen_wait(
            ConfirmScreen(f"Start server in '{region}', version {version}, slot {slot}?")
        )
        if not confirmed:
            return

        self.host.push_log(Term.info("[start server]", "Starting instance..."))
        try:
            await session.start_instance(region, version, f"slot{slot}")
            while not session.running and not session.server_address:
                await asyncio.sleep(1)
            self.host.push_log(
                Term.info("[start server]", f"Server running at {session.server_address}")
            )
        except Exception as ex:  # noqa: BLE001
            self.host.push_log(Term.error("[start server]", str(ex)))

    async def stop(self) -> None:
        session = self.host.session
        self.host.push_log(Term.info("[stop server]", "Stopping instance..."))
        try:
            await session.stop_instance()
            while session.running:
                await asyncio.sleep(1)
            self.host.push_log(Term.info("[stop server]", "Instance stopped."))
        except Exception as ex:  # noqa: BLE001
            self.host.push_log(Term.error("[stop server]", str(ex)))
