import asyncio

from fz_manager.terminal import Term
from fz_manager.ui.app import Main


def main():
    Term.cls()
    program = Main()
    asyncio.get_event_loop_policy().get_event_loop().run_until_complete(
        program.main()
    )  # pragma: no cover
    Term.cls()
