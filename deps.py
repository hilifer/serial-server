"""
Shared dependency checker. Import this once at entry point —
installs all missing packages in one shot, skips if already done.
"""

import importlib
import subprocess
import sys
from pathlib import Path

_MARKER = Path(__file__).parent / "venv" / ".deps_ok"

# module_name -> pip_package_name
ALL_DEPS = {
    "serial": "pyserial",
    "paho.mqtt": "paho-mqtt",
    "yaml": "pyyaml",
    "flask": "flask",
    "requests": "requests",
    "pytest": "pytest",
}


def ensure_deps():
    """Install any missing dependencies. Skips if marker file exists."""
    if _MARKER.exists():
        return

    missing = []
    for mod, pkg in ALL_DEPS.items():
        try:
            importlib.import_module(mod.split(".")[0])
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[deps] Installing: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing, "-q"],
        )

    # Write marker so we don't check again
    try:
        _MARKER.parent.mkdir(parents=True, exist_ok=True)
        _MARKER.write_text("ok")
    except OSError:
        pass  # no venv dir, that's fine — will check every time
