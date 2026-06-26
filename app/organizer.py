"""File scanning and organization services."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    """Return the writable application data directory."""
    if getattr(sys, "frozen", False):
        root = os.environ.get("APPDATA")
        if root:
            return Path(root) / "Smart File Organizer"
        return Path.home() / "Smart File Organizer"
    return BASE_DIR


DATA_DIR = app_data_dir()
CONFIG_PATH = DATA_DIR / "config/settings.json"
HISTORY_PATH = DATA_DIR / "config/history.json"
LOG_PATH = DATA_DIR / "logs/smart_organizer.log"
PARTIAL_EXTENSIONS = {".crdownload", ".download", ".part", ".tmp"}
EXCLUDED_SCAN_DIRS = {
    ".cache",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "AppData",
    "Application Data",
    "Library",
    "node_modules",
    "venv",
}

CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv"},
    "Music": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
    "PDF": {".pdf"},
    "Documents": {
        ".doc",
        ".docx",
        ".txt",
        ".rtf",
        ".odt",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".csv",
    },
    "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Executables": {".exe", ".msi", ".bat", ".cmd"},
    "Code": {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".json",
        ".md",
        ".sql",
    },
}


@dataclass(frozen=True)
class OrganizedFile:
    """A file moved by the organizer."""

    name: str
    source: Path
    destination: Path
    category: str
    moved_at: datetime


@dataclass(frozen=True)
class DashboardSnapshot:
    """Current data rendered by the dashboard."""

    monitored_folders: list[Path]
    files_by_type: Counter[str]
    total_files: int
    latest_files: list[Path]
    pending_files: list[Path]
    organized_today: int
    most_common_type: str


@dataclass(frozen=True)
class InventorySnapshot:
    """Recursive metrics for the current user's home directory."""

    root: Path
    total_files: int
    total_size_bytes: int
    files_by_type: Counter[str]
    files_by_extension: Counter[str]
    largest_files: list[tuple[Path, int]]
    recent_files: list[Path]
    skipped_paths: int


@dataclass(frozen=True)
class AppSettings:
    """User-editable application settings."""

    monitored_folders: list[Path]
    auto_organize: bool
    scan_interval_seconds: int
    conflict_strategy: str
    start_with_windows: bool


class OrganizerConfig:
    """Load and save local application settings."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        """Create the config service."""
        self.path = path

    def load(self) -> AppSettings:
        """Return all application settings, creating defaults when missing."""
        if not self.path.exists():
            settings = AppSettings(
                monitored_folders=self._default_folders(),
                auto_organize=False,
                scan_interval_seconds=10,
                conflict_strategy="rename",
                start_with_windows=True,
            )
            self.save(settings)
            return settings

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}

        raw_folders = data.get("monitored_folders")
        if raw_folders is None:
            existing = self._default_folders()
        else:
            folders = [Path(item).expanduser() for item in raw_folders]
            existing = [folder for folder in folders if folder.exists()]
        return AppSettings(
            monitored_folders=existing,
            auto_organize=bool(data.get("auto_organize", False)),
            scan_interval_seconds=max(3, int(data.get("scan_interval_seconds", 10))),
            conflict_strategy=str(data.get("conflict_strategy", "rename")),
            start_with_windows=bool(data.get("start_with_windows", True)),
        )

    def load_monitored_folders(self) -> list[Path]:
        """Return configured monitored folders."""
        return self.load().monitored_folders

    def save_monitored_folders(self, folders: list[Path]) -> None:
        """Persist monitored folders to the JSON config file."""
        settings = self.load()
        self.save(
            AppSettings(
                monitored_folders=folders,
                auto_organize=settings.auto_organize,
                scan_interval_seconds=settings.scan_interval_seconds,
                conflict_strategy=settings.conflict_strategy,
                start_with_windows=settings.start_with_windows,
            )
        )

    def save(self, settings: AppSettings) -> None:
        """Persist all application settings to the JSON config file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "monitored_folders": [str(folder) for folder in settings.monitored_folders],
            "auto_organize": settings.auto_organize,
            "scan_interval_seconds": settings.scan_interval_seconds,
            "conflict_strategy": settings.conflict_strategy,
            "start_with_windows": settings.start_with_windows,
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _default_folders(self) -> list[Path]:
        """Return common Windows folders from the current user profile."""
        home = Path.home()
        candidates = [home / "Downloads", home / "Desktop"]
        return [folder for folder in candidates if folder.exists()]


class FileOrganizer:
    """Organize files from monitored folders into category directories."""

    def __init__(self, config: OrganizerConfig | None = None) -> None:
        """Create the organizer service."""
        self.config = config or OrganizerConfig()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=LOG_PATH,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )

    def snapshot(self) -> DashboardSnapshot:
        """Scan monitored folders and return dashboard-ready data."""
        folders = self.config.load_monitored_folders()
        files = self._list_files(folders)
        files_by_type = Counter(self.category_for(file) for file in files)
        latest_files = sorted(files, key=lambda file: file.stat().st_mtime, reverse=True)[:6]
        history = self.history()
        today = datetime.now().date().isoformat()
        organized_today = sum(1 for item in history if item.get("date", "").startswith(today))
        most_common = files_by_type.most_common(1)
        return DashboardSnapshot(
            monitored_folders=folders,
            files_by_type=files_by_type,
            total_files=len(files),
            latest_files=latest_files,
            pending_files=sorted(files, key=lambda file: str(file.parent).lower())[:200],
            organized_today=organized_today,
            most_common_type=most_common[0][0] if most_common else "None",
        )

    def home_inventory(self) -> InventorySnapshot:
        """Analyze all accessible files under the current user's home directory."""
        root = Path.home()
        files_by_type: Counter[str] = Counter()
        files_by_extension: Counter[str] = Counter()
        largest_files: list[tuple[Path, int]] = []
        recent_candidates: list[tuple[Path, float]] = []
        total_files = 0
        total_size = 0
        skipped_paths = 0

        for file_path in self._walk_home_files(root):
            try:
                stat = file_path.stat()
            except OSError:
                skipped_paths += 1
                continue
            total_files += 1
            total_size += stat.st_size
            files_by_type[self.category_for(file_path)] += 1
            files_by_extension[file_path.suffix.lower() or "(no extension)"] += 1
            largest_files.append((file_path, stat.st_size))
            recent_candidates.append((file_path, stat.st_mtime))
            largest_files = sorted(largest_files, key=lambda item: item[1], reverse=True)[:10]
            recent_candidates = sorted(recent_candidates, key=lambda item: item[1], reverse=True)[:10]

        logging.info("Scanned home inventory: %s files under %s", total_files, root)
        return InventorySnapshot(
            root=root,
            total_files=total_files,
            total_size_bytes=total_size,
            files_by_type=files_by_type,
            files_by_extension=files_by_extension,
            largest_files=largest_files,
            recent_files=[path for path, _mtime in recent_candidates],
            skipped_paths=skipped_paths,
        )

    def organize_all(self) -> list[OrganizedFile]:
        """Move files from monitored folders into category subfolders."""
        moved: list[OrganizedFile] = []
        for source in self._list_files(self.config.load_monitored_folders()):
            category = self.category_for(source)
            destination_dir = source.parent / category
            destination_dir.mkdir(exist_ok=True)
            destination = self._unique_destination(destination_dir / source.name)
            shutil.move(str(source), str(destination))
            moved.append(
                OrganizedFile(
                    name=source.name,
                    source=source,
                    destination=destination,
                    category=category,
                    moved_at=datetime.now(),
                )
            )
            self._record_move(moved[-1])
        return moved

    def add_folder(self, folder: Path) -> None:
        """Add a monitored folder to the configuration."""
        folders = self.config.load_monitored_folders()
        resolved = folder.expanduser().resolve()
        if resolved.exists() and resolved not in folders:
            folders.append(resolved)
            self.config.save_monitored_folders(folders)
            logging.info("Added monitored folder: %s", resolved)

    def remove_folder(self, folder: Path) -> None:
        """Remove a monitored folder from the configuration."""
        resolved = folder.expanduser().resolve()
        folders = [item for item in self.config.load_monitored_folders() if item.resolve() != resolved]
        self.config.save_monitored_folders(folders)
        logging.info("Removed monitored folder: %s", resolved)

    def remove_all_folders(self) -> None:
        """Remove all monitored folders from the configuration."""
        self.config.save_monitored_folders([])
        logging.info("Removed all monitored folders")

    def save_settings(
        self,
        auto_organize: bool,
        scan_interval_seconds: int,
        start_with_windows: bool,
    ) -> None:
        """Update user-editable settings."""
        current = self.config.load()
        self.config.save(
            AppSettings(
                monitored_folders=current.monitored_folders,
                auto_organize=auto_organize,
                scan_interval_seconds=scan_interval_seconds,
                conflict_strategy=current.conflict_strategy,
                start_with_windows=start_with_windows,
            )
        )
        logging.info(
            "Updated settings: auto=%s interval=%s startup=%s",
            auto_organize,
            scan_interval_seconds,
            start_with_windows,
        )

    def history(self) -> list[dict[str, str]]:
        """Return persisted move history."""
        if not HISTORY_PATH.exists():
            return []
        try:
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, list):
            return data
        return []

    def logs(self) -> str:
        """Return the application log text."""
        if not LOG_PATH.exists():
            return "No logs yet."
        return LOG_PATH.read_text(encoding="utf-8")

    def clear_history(self) -> None:
        """Delete persisted move history."""
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text("[]", encoding="utf-8")
        logging.info("Cleared move history")

    def clear_logs(self) -> None:
        """Clear application logs."""
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("", encoding="utf-8")

    def category_for(self, path: Path) -> str:
        """Return the destination category for a file path."""
        extension = path.suffix.lower()
        for category, extensions in CATEGORY_EXTENSIONS.items():
            if extension in extensions:
                return category
        return "Others"

    def _list_files(self, folders: list[Path]) -> list[Path]:
        """Return movable files from monitored folders."""
        files: list[Path] = []
        for folder in folders:
            if not folder.exists():
                continue
            for item in folder.iterdir():
                if self._is_movable_file(item):
                    files.append(item)
        return files

    def _walk_home_files(self, root: Path):
        """Yield accessible files below home while skipping technical cache folders."""
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in EXCLUDED_SCAN_DIRS:
                                stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            yield Path(entry.path)
            except OSError:
                logging.warning("Skipped inaccessible path during home scan: %s", current)

    def _is_movable_file(self, path: Path) -> bool:
        """Return whether a path is safe to move now."""
        if not path.is_file():
            return False
        if path.suffix.lower() in PARTIAL_EXTENSIONS:
            return False
        if path.parent.name in CATEGORY_EXTENSIONS or path.parent.name == "Others":
            return False
        return True

    def _unique_destination(self, destination: Path) -> Path:
        """Return a non-conflicting destination path."""
        if not destination.exists():
            return destination

        stem = destination.stem
        suffix = destination.suffix
        parent = destination.parent
        counter = 1
        while True:
            candidate = parent / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _record_move(self, item: OrganizedFile) -> None:
        """Persist history and write a log entry for a moved file."""
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        history = self.history()
        history.insert(
            0,
            {
                "date": item.moved_at.isoformat(timespec="seconds"),
                "name": item.name,
                "source": str(item.source),
                "destination": str(item.destination),
                "category": item.category,
            },
        )
        HISTORY_PATH.write_text(json.dumps(history[:500], indent=2), encoding="utf-8")
        logging.info("Moved %s from %s to %s", item.name, item.source, item.destination)
