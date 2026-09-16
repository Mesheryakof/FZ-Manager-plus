from __future__ import annotations

from rich.text import Text

from fz_manager_plus.domain.state import LogEvent


class Colors:
    BLUE = "#1e90ff"
    GREEN = "#33ff00"
    ORANGE = "#ffa500"
    RED = "#ff0000"


class Term:
    """Builds colored `rich.text.Text` labels for the TUI log pane, using
    Rich's own styling instead of hand-rolled ANSI escape sequences."""

    @staticmethod
    def debug(*text: str) -> Text:
        return Text(" ".join(text), style=Colors.BLUE)

    @staticmethod
    def info(*text: str) -> Text:
        return Text(" ".join(text), style=Colors.GREEN)

    @staticmethod
    def warn(*text: str) -> Text:
        return Text(" ".join(text), style=Colors.ORANGE)

    @staticmethod
    def error(*text: str) -> Text:
        return Text(" ".join(text), style=Colors.RED)

    @staticmethod
    def event(event: LogEvent) -> Text:
        if event.level == "plain":
            return Text.from_ansi(event.text)
        formatter = {
            "info": Term.info,
            "warn": Term.warn,
            "error": Term.error,
            "debug": Term.debug,
        }.get(event.level, Term.debug)
        return formatter(event.level, event.text)
