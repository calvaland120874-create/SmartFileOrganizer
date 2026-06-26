"""Windows startup integration for Smart File Organizer."""

from __future__ import annotations

import sys
from pathlib import Path


APP_RUN_NAME = "SmartFileOrganizer"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command() -> str:
    """Return the command used by Windows to start the app without a console."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}" --background'

    python_executable = Path(sys.executable)
    pythonw = python_executable.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else python_executable
    main_file = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{launcher}" "{main_file}" --background'


def is_supported() -> bool:
    """Return whether startup integration is available on this platform."""
    return sys.platform.startswith("win")


def is_enabled() -> bool:
    """Return whether Windows startup is currently enabled."""
    if not is_supported():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _value_type = winreg.QueryValueEx(key, APP_RUN_NAME)
            return value == startup_command()
    except OSError:
        return False


def enable() -> None:
    """Enable Windows startup for the current user."""
    if not is_supported():
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_RUN_NAME, 0, winreg.REG_SZ, startup_command())


def disable() -> None:
    """Disable Windows startup for the current user."""
    if not is_supported():
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_RUN_NAME)
    except FileNotFoundError:
        return
