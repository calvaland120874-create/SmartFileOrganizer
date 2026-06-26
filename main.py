"""Entry point for Smart File Organizer."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.gui import SmartFileOrganizerWindow


def main() -> None:
    """Start the Qt desktop application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Smart File Organizer")
    app.setQuitOnLastWindowClosed(False)

    background = "--background" in sys.argv
    window = SmartFileOrganizerWindow(start_in_background=background)
    if background:
        window.start_background_mode()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
