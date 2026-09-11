import asyncio

from fz_manager.ui.app import Main
from fz_manager.utils import Term


def main():
    Term.cls()
    program = Main()
    asyncio.get_event_loop_policy().get_event_loop().run_until_complete(program.main())  # pragma: no cover
    Term.cls()
