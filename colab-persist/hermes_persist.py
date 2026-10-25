"""Snapshot and restore Hermes state between an ephemeral Colab VM and MongoDB Atlas.

Hermes keeps its source checkout, PM tool store, and Python environments inside the
data root. Those are rebuilt from a pinned commit, so they stay out of snapshots.
Everything else under HERMES_HOME (config, secrets, memories, skills, plugins,
sessions, state DBs, WhatsApp pairing) plus the project workspace is archived as one
tarball into a GridFS bucket. GridFS writes the file document only after all chunks
land, so readers never see a partial snapshot.

Requires MONGODB_URI in the environment.

Usage:
    python3 hermes_persist.py snapshot
    python3 hermes_persist.py restore
    python3 hermes_persist.py loop --interval 300
    python3 hermes_persist.py list
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import socket
import sqlite3
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import gridfs
import pymongo
import pymongo.errors

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
WORK_DIR = Path(os.environ.get("HERMES_WORK_DIR", "/content/work"))
DB_NAME = os.environ.get("HERMES_PERSIST_DB", "hermes_persist")
BUCKET = "snapshots"
ARC_HOME = "home"
ARC_WORK = "work"
DEFAULT_KEEP = 24
DEFAULT_INTERVAL_SECONDS = 300
SERVER_SELECTION_TIMEOUT_MS = 20000
SQLITE_TIMEOUT_SECONDS = 30.0
HASH_CHUNK_BYTES = 1 << 20
SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

# Top-level HERMES_HOME entries the installer recreates from the pinned commit.
REBUILDABLE = frozenset({"hermes-agent", "tools", "installs", "cache", "node_modules"})
# Directory names never worth persisting from the project workspace.
WORK_SKIP = frozenset({".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"})

log = logging.getLogger("hermes_persist")


def _bucket() -> tuple[pymongo.MongoClient, gridfs.GridFSBucket]:
    """Connect to Atlas and return the client and snapshot bucket.

    Returns:
        Tuple of the client (caller closes it) and the GridFS bucket.

    Raises:
        RuntimeError: If MONGODB_URI is unset.
        pymongo.errors.PyMongoError: If the cluster is unreachable.
    """
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")
    client: pymongo.MongoClient = pymongo.MongoClient(uri, serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS)
    client.admin.command("ping")
    return client, gridfs.GridFSBucket(client[DB_NAME], bucket_name=BUCKET)


def _is_sqlite_sidecar(path: Path) -> bool:
    """Return True for WAL/SHM/journal files, which the online backup replaces.

    Args:
        path: File to classify.

    Returns:
        Whether the file is a sidecar of a database copied separately.
    """
    return any(path.name.endswith(db + side) for db in SQLITE_SUFFIXES for side in SQLITE_SIDECAR_SUFFIXES)


def _copy_sqlite(src: Path, dst: Path) -> None:
    """Copy a live SQLite database consistently with the online backup API.

    Args:
        src: Source database path.
        dst: Destination path.

    Raises:
        sqlite3.Error: If the database cannot be read.
    """
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=SQLITE_TIMEOUT_SECONDS)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _stage_tree(src_root: Path, dst_root: Path, skip_top: frozenset[str], skip_any: frozenset[str]) -> int:
    """Copy a directory tree into staging, using consistent copies for SQLite files.

    Args:
        src_root: Directory to copy.
        dst_root: Staging destination.
        skip_top: Directory names skipped at the top level only.
        skip_any: Directory names skipped at every level.

    Returns:
        Number of files staged.
    """
    count = 0
    for root, dirs, files in os.walk(src_root):
        rel_root = Path(root).relative_to(src_root)
        dirs[:] = [d for d in dirs if d not in skip_any and not (rel_root == Path(".") and d in skip_top)]
        (dst_root / rel_root).mkdir(parents=True, exist_ok=True)
        for name in files:
            src = Path(root) / name
            if src.is_symlink() or not src.is_file() or _is_sqlite_sidecar(src):
                continue
            dst = dst_root / rel_root / name
            try:
                if src.suffix in SQLITE_SUFFIXES:
                    _copy_sqlite(src, dst)
                else:
                    shutil.copy2(src, dst)
            except (OSError, sqlite3.Error) as exc:
                log.warning("skipped %s: %s", src, exc)
                continue
            count += 1
    return count


def _sha256(path: Path) -> str:
    """Hash a file in chunks.

    Args:
        path: File to hash.

    Returns:
        Hex SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _prune(bucket: gridfs.GridFSBucket, keep: int) -> None:
    """Delete all but the newest `keep` snapshots.

    Args:
        bucket: Snapshot bucket.
        keep: Number of snapshots to retain; values below 1 keep everything.
    """
    if keep < 1:
        return
    for old in bucket.find().sort("uploadDate", pymongo.DESCENDING).skip(keep):
        bucket.delete(old._id)


def snapshot(keep: int) -> str:
    """Archive HERMES_HOME user data and the workspace into Atlas.

    Args:
        keep: Number of snapshots to retain after writing.

    Returns:
        Filename of the snapshot written.

    Raises:
        RuntimeError: If HERMES_HOME is missing or MONGODB_URI is unset.
        pymongo.errors.PyMongoError: If the upload fails.
    """
    if not HERMES_HOME.is_dir():
        raise RuntimeError(f"{HERMES_HOME} does not exist")
    name = time.strftime("hermes-%Y%m%dT%H%M%SZ.tar.gz", time.gmtime())
    with tempfile.TemporaryDirectory(prefix="hermes-stage-") as tmp:
        staging = Path(tmp) / "stage"
        count = _stage_tree(HERMES_HOME, staging / ARC_HOME, REBUILDABLE, frozenset())
        if WORK_DIR.is_dir():
            count += _stage_tree(WORK_DIR, staging / ARC_WORK, frozenset(), WORK_SKIP)
        archive = Path(tmp) / name
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname=".")
        metadata = {"sha256": _sha256(archive), "files": count, "host": socket.gethostname()}
        client, bucket = _bucket()
        try:
            with archive.open("rb") as handle:
                bucket.upload_from_stream(name, handle, metadata=metadata)
            _prune(bucket, keep)
        finally:
            client.close()
        log.info("snapshot %s (%d files, %.1f KB)", name, count, archive.stat().st_size / 1e3)
    return name


def _merge_into(src: Path, dst: Path) -> None:
    """Copy an extracted tree over a destination, keeping unrelated files.

    Args:
        src: Extracted directory.
        dst: Live destination directory.
    """
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)


def restore() -> str | None:
    """Download, verify, and unpack the newest snapshot.

    Returns:
        Filename restored, or None if Atlas has no snapshots.

    Raises:
        RuntimeError: If the checksum does not match or MONGODB_URI is unset.
        pymongo.errors.PyMongoError: If the download fails.
    """
    client, bucket = _bucket()
    try:
        latest = next(iter(bucket.find().sort("uploadDate", pymongo.DESCENDING).limit(1)), None)
        if latest is None:
            log.info("no snapshots in %s.%s; starting fresh", DB_NAME, BUCKET)
            return None
        with tempfile.TemporaryDirectory(prefix="hermes-restore-") as tmp:
            archive = Path(tmp) / latest.filename
            with archive.open("wb") as handle:
                bucket.download_to_stream(latest._id, handle)
            expected = (latest.metadata or {}).get("sha256")
            if expected and _sha256(archive) != expected:
                raise RuntimeError(f"checksum mismatch for {latest.filename}")
            extracted = Path(tmp) / "x"
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(extracted, filter="data")
            _merge_into(extracted / ARC_HOME, HERMES_HOME)
            _merge_into(extracted / ARC_WORK, WORK_DIR)
    finally:
        client.close()
    log.info("restored %s", latest.filename)
    return latest.filename


def list_snapshots() -> None:
    """Print stored snapshots, newest first."""
    client, bucket = _bucket()
    try:
        for doc in bucket.find().sort("uploadDate", pymongo.DESCENDING):
            meta = doc.metadata or {}
            print(f"{doc.upload_date:%Y-%m-%d %H:%M:%S}  {doc.length / 1e3:9.1f} KB  "
                  f"{meta.get('files', '?'):>6} files  {doc.filename}")
    finally:
        client.close()


def loop(interval: int, keep: int) -> None:
    """Snapshot forever, logging failures instead of exiting.

    Args:
        interval: Seconds between snapshots.
        keep: Number of snapshots to retain.
    """
    while True:
        try:
            snapshot(keep)
        except (OSError, RuntimeError, tarfile.TarError, pymongo.errors.PyMongoError) as exc:
            log.error("snapshot failed: %s", exc)
        time.sleep(interval)


def main() -> int:
    """Parse arguments and dispatch the requested command.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("snapshot", "restore", "loop", "list"))
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "snapshot":
            snapshot(args.keep)
        elif args.command == "restore":
            restore()
        elif args.command == "list":
            list_snapshots()
        else:
            loop(args.interval, args.keep)
    except (OSError, RuntimeError, tarfile.TarError, sqlite3.Error, pymongo.errors.PyMongoError) as exc:
        log.error("%s failed: %s", args.command, exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
