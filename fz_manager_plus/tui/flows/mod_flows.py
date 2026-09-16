from __future__ import annotations

from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ConfirmScreen
from fz_manager_plus.tui.flows.host import FlowHost


class ModFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    async def toggle(self, mod_id: int, enabled: bool) -> None:
        try:
            await self.host.session.toggle_mod(mod_id, enabled)
        except Exception as ex:  # noqa: BLE001
            self.host.push_log(Term.error("[manage mods]", str(ex)))

    async def delete(self, mod_id: int) -> None:
        name = next((m.text for m in self.host.session.mods if m.id == mod_id), str(mod_id))
        confirmed = await self.host.push_screen_wait(ConfirmScreen(f"Delete mod '{name}'?"))
        if not confirmed:
            return
        try:
            await self.host.session.delete_mod(mod_id)
            self.host.push_log(Term.info("[manage mods]", f"Deleted {name}"))
        except Exception as ex:  # noqa: BLE001
            self.host.push_log(Term.error("[manage mods]", str(ex)))

    async def delete_all(self) -> None:
        mods = list(self.host.session.mods)
        if not mods:
            self.host.push_log(Term.info("[manage mods]", "No uploaded mods found"))
            return
        confirmed = await self.host.push_screen_wait(
            ConfirmScreen(f"Delete all {len(mods)} mod(s)?")
        )
        if not confirmed:
            return
        for mod in mods:
            try:
                await self.host.session.delete_mod(mod.id)
                self.host.push_log(Term.info("[manage mods]", f"Deleted {mod.text}"))
            except Exception as ex:  # noqa: BLE001
                self.host.push_log(Term.error("[manage mods]", f"{mod.text}: {ex}"))
