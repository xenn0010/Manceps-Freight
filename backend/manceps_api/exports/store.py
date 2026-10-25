"""Where finished export files live: the ExportStore interface and its filesystem implementation.

Keys are `<tenant>/<export id>/<file name>`, checked against a strict pattern and resolved inside the store's root,
so a key can never reach outside it. The filesystem store serves downloads through the authenticated API route
(`url_for` returns None); an object-storage store (R2, Phase 3) returns short-lived presigned URLs instead. In
production a store must be configured explicitly (EXPORT_DIR until R2 exists); without one exports answer 503.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from ..settings import Settings

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]/[0-9a-f]{24}/[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
DEV_DIR_NAME = "manceps-exports"
PRODUCTION = "production"


class StoreError(RuntimeError):
    """A key is malformed, a file is missing, or the storage backend failed."""


class ExportStore(ABC):
    """Storage for export files."""

    @abstractmethod
    def put(self, key: str, source: Path) -> int:
        """Store a finished file under a key.

        Args:
            key: `<tenant>/<export id>/<file name>`.
            source: Local file to store.

        Returns:
            Stored size in bytes.

        Raises:
            StoreError: On a bad key or a storage failure.
        """

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open a stored file for reading.

        Args:
            key: Stored key.

        Returns:
            A binary file object (the caller closes it).

        Raises:
            StoreError: On a bad key or a missing file.
        """

    @abstractmethod
    def url_for(self, key: str, expires_in: timedelta) -> str | None:
        """Return a direct, short-lived download URL when the backend supports one.

        Args:
            key: Stored key.
            expires_in: How long the URL may work.

        Returns:
            The URL, or None when downloads go through the API.
        """

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove a stored file (missing files are ignored).

        Args:
            key: Stored key.

        Raises:
            StoreError: On a bad key or a storage failure.
        """

    @abstractmethod
    def purge(self, before: datetime) -> int:
        """Remove files stored before a time (expired exports).

        Args:
            before: Cut-off time.

        Returns:
            Number of files removed.
        """


class FilesystemExportStore(ExportStore):
    """Export files in a local directory."""

    def __init__(self, root: Path) -> None:
        """Use a directory (created on first write).

        Args:
            root: Base directory.
        """
        self.root = root

    def _path(self, key: str) -> Path:
        """Resolve a key inside the root.

        Args:
            key: Stored key.

        Returns:
            The file path.

        Raises:
            StoreError: When the key is malformed or would leave the root.
        """
        if not KEY_PATTERN.fullmatch(key) or ".." in key.split("/"):
            raise StoreError("malformed export key")
        root = self.root.resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise StoreError("export key leaves the store")
        return path

    def put(self, key: str, source: Path) -> int:
        """Copy a file into the store.

        Args:
            key: Stored key.
            source: Local file.

        Returns:
            Size in bytes.

        Raises:
            StoreError: On a bad key or a filesystem failure.
        """
        target = self._path(key)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return target.stat().st_size
        except OSError as exc:
            raise StoreError("could not store the export file") from exc

    def open(self, key: str) -> BinaryIO:
        """Open a stored file.

        Args:
            key: Stored key.

        Returns:
            The open file.

        Raises:
            StoreError: On a bad key or a missing file.
        """
        try:
            return self._path(key).open("rb")
        except OSError as exc:
            raise StoreError("export file not found") from exc

    def url_for(self, key: str, expires_in: timedelta) -> str | None:
        """Report that downloads go through the authenticated API route.

        Args:
            key: Stored key.
            expires_in: Unused by this backend.

        Returns:
            None.
        """
        self._path(key)
        return None

    def delete(self, key: str) -> None:
        """Remove a stored file and its now-empty folder.

        Args:
            key: Stored key.

        Raises:
            StoreError: On a bad key or a filesystem failure.
        """
        path = self._path(key)
        try:
            path.unlink(missing_ok=True)
            if path.parent.is_dir() and not any(path.parent.iterdir()):
                path.parent.rmdir()
        except OSError as exc:
            raise StoreError("could not delete the export file") from exc

    def purge(self, before: datetime) -> int:
        """Remove files last written before a time.

        Args:
            before: Cut-off time.

        Returns:
            Files removed.
        """
        if not self.root.is_dir():
            return 0
        cutoff = before.timestamp()
        removed = 0
        for path in self.root.glob("*/*/*"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed


def store_from_settings(settings: Settings) -> ExportStore | None:
    """Build the configured export store.

    Args:
        settings: Settings.

    Returns:
        A filesystem store at EXPORT_DIR; outside production a temporary directory when unset; None in production
        without a configured store (exports then answer 503).
    """
    if settings.export_dir:
        return FilesystemExportStore(Path(settings.export_dir))
    if settings.env == PRODUCTION:
        return None
    return FilesystemExportStore(Path(tempfile.gettempdir()) / DEV_DIR_NAME)
