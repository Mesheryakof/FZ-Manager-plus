import os


class Term:
    HEAD = "\r\x1b[K"
    RESET = "\x1b[0m"
    RESET_FG = "\x1b[39m"
    RESET_BG = "\x1b[49m"
    ENDL = "\x1b[K"
    F_RESET = "\x1b[0m\x1b]11;?\a\x1b[K"

    @staticmethod
    def cls():
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def fg(rgb: tuple[int, int, int]):
        return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

    @staticmethod
    def bg(rgb: tuple[int, int, int]):
        return f"\x1b[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

    @staticmethod
    def colorize(
        fg_color: tuple[int, int, int] = None,
        bg_color: tuple[int, int, int] = None,
        *text: str,
        sep: str = " ",
        end: str = RESET,
    ) -> str:
        if not fg_color and not bg_color:
            return " ".join(text)
        foreground = Term.fg(fg_color) if fg_color else ""
        background = Term.bg(bg_color) if bg_color else ""
        t = sep.join(text)
        return background + foreground + t + end

    @staticmethod
    def debug(*text: str):
        return Term.colorize(Colors.BLUE, None, *text)

    @staticmethod
    def info(*text: str):
        return Term.colorize(Colors.GREEN, None, *text)

    @staticmethod
    def warn(*text: str):
        return Term.colorize(Colors.ORANGE, None, *text)

    @staticmethod
    def error(*text: str):
        return Term.colorize(Colors.RED, None, *text)


class Colors:
    FACTORIO_FG = 230, 145, 0
    FACTORIO_BG = 43, 43, 43
    GREEN = 51, 255, 0
    RED = 255, 0, 0
    BLUE = 30, 144, 255
    ORANGE = 255, 165, 0

    @staticmethod
    def rgb_to_hex(rgb: tuple[int, int, int]):
        def clamp(x):
            return max(0, min(x, 255))

        return f"#{clamp(rgb[0]):02x}{clamp(rgb[1]):02x}{clamp(rgb[2]):02x}"

    FACTORIO_FG_HEX = rgb_to_hex(FACTORIO_FG)
    FACTORIO_BG_HEX = rgb_to_hex(FACTORIO_BG)


class String:
    @staticmethod
    def isblank(string: (str | None)):
        return string is None or string.strip() == ""
