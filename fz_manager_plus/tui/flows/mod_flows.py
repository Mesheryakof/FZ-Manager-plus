from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ConfirmScreen
from fz_manager_plus.tui.flows.host import FlowHost


class ModFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    async def toggle(self, mod_id: int, enabled: bool) -> None:
        await self.host.session.toggle_mod(mod_id, enabled)

    async def delete(self, mod_id: int) -> None:
        self.host.session.require_ready("mods")
        name = next((mod.text for mod in self.host.session.mods if mod.id == mod_id), str(mod_id))
        if await self.host.push_screen_wait(ConfirmScreen(f"Delete mod '{name}'?")):
            await self.host.session.delete_mod(mod_id)
            self.host.push_log(Term.info("[manage mods]", f"Deleted {name}"))

    async def delete_all(self) -> None:
        session = self.host.session
        session.require_ready("mods")
        if not session.mods:
            self.host.push_log(Term.info("[manage mods]", "No uploaded mods found"))
            return
        if await self.host.push_screen_wait(
            ConfirmScreen(f"Delete all {len(session.mods)} mod(s)?")
        ):
            await session.delete_all_mods()
