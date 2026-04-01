"""Shared terminal color support. Auto-detects Windows CMD compatibility."""

import os
import platform


def _supports_color():
    if os.environ.get("NO_COLOR"):
        return False
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


_COLOR = _supports_color()


class C:
    GREEN = "\033[92m" if _COLOR else ""
    RED = "\033[91m" if _COLOR else ""
    YELLOW = "\033[93m" if _COLOR else ""
    CYAN = "\033[96m" if _COLOR else ""
    BOLD = "\033[1m" if _COLOR else ""
    DIM = "\033[2m" if _COLOR else ""
    END = "\033[0m" if _COLOR else ""
