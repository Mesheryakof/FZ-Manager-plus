from fz_manager_plus.domain.errors import OperationError
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ChoiceScreen, ConfirmScreen
from fz_manager_plus.tui.flows.host import FlowHost


class ServerFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    async def start(self) -> None:
        session, settings = self.host.session, self.host.settings
        session.require_ready("server", "regions", "versions", "saves")
        if not session.regions or not session.versions or not session.saves:
            raise OperationError(
                "Server did not provide any available regions, versions or save slots"
            )
        region = await self.host.push_screen_wait(
            ChoiceScreen(
                "Choose a region:",
                [(f"{code} - {name}", code) for code, name in sorted(session.regions.items())],
                default=settings.region,
            )
        )
        if region is None:
            return
        version = await self.host.push_screen_wait(
            ChoiceScreen(
                "Choose a Factorio version:",
                [(v, v) for v in session.versions],
                default=settings.version,
            )
        )
        if version is None:
            return
        default_slot = settings.slot
        if default_slot and not default_slot.startswith("slot"):
            default_slot = f"slot{default_slot}"
        slot = await self.host.push_screen_wait(
            ChoiceScreen(
                "Choose a save slot:",
                [(description, key) for key, description in session.saves.items()],
                default=default_slot,
            )
        )
        if slot is None:
            return
        if not await self.host.push_screen_wait(
            ConfirmScreen(f"Start server in '{region}', version {version}, {slot}?")
        ):
            return
        settings.region, settings.version, settings.slot = (
            region,
            version,
            slot.removeprefix("slot"),
        )
        await self.host.save_settings()
        self.host.push_log(Term.info("[start server]", "Starting instance..."))
        await session.start_instance(region, version, slot)
        self.host.push_log(
            Term.info("[start server]", f"Server running at {session.server_address}")
        )

    async def stop(self) -> None:
        self.host.session.require_ready("server")
        self.host.push_log(Term.info("[stop server]", "Stopping instance..."))
        await self.host.session.stop_instance()
        self.host.push_log(Term.info("[stop server]", "Instance stopped."))
