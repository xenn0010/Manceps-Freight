"""Copy backend/manceps_core into hermes-freight/_vendor/manceps_core, or verify the copy with --check.

The plugin does not import the vendored copy yet (Phase 2 wires it); this keeps the copy byte-identical meanwhile.

Usage (working directory backend/):
    uv run python scripts/vendor_core.py           # sync
    uv run python scripts/vendor_core.py --check   # exit 1 if the copy drifted
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = BACKEND_DIR / "manceps_core"
DEFAULT_DEST = BACKEND_DIR.parent / "hermes-freight" / "_vendor" / "manceps_core"
IGNORED_DIRS = frozenset({"__pycache__"})
IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})
EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2


def _files(root: Path) -> dict[str, bytes]:
    """Read every vendorable file under a directory.

    Args:
        root: Directory to scan.

    Returns:
        Relative POSIX path to file contents; empty when the directory does not exist.
    """
    if not root.is_dir():
        return {}
    found: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or IGNORED_DIRS & set(relative.parts) or path.suffix in IGNORED_SUFFIXES:
            continue
        found[relative.as_posix()] = path.read_bytes()
    return found


def drift(source: Path, dest: Path) -> list[str]:
    """List differences between the source package and the vendored copy.

    Args:
        source: Source package directory.
        dest: Vendored directory.

    Returns:
        Human-readable differences; empty when identical.
    """
    wanted, present = _files(source), _files(dest)
    problems = [f"missing {name}" for name in sorted(wanted.keys() - present.keys())]
    problems += [f"extra {name}" for name in sorted(present.keys() - wanted.keys())]
    problems += [f"changed {name}" for name in sorted(wanted.keys() & present.keys()) if wanted[name] != present[name]]
    return problems


def sync(source: Path, dest: Path) -> None:
    """Replace the vendored copy with the source files.

    Args:
        source: Source package directory.
        dest: Vendored directory (recreated).
    """
    if dest.exists():
        shutil.rmtree(dest)
    for name, content in _files(source).items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main(argv: Sequence[str] | None = None) -> int:
    """Sync or check the vendored copy.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        0 when in sync, 1 when --check finds drift, 2 when the source is missing.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the vendored copy differs")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args(argv)
    source: Path = args.source
    dest: Path = args.dest
    if not (source / "__init__.py").is_file():
        print(f"source package {source} not found", file=sys.stderr)
        return EXIT_USAGE
    problems = drift(source, dest)
    if args.check:
        for problem in problems:
            print(problem, file=sys.stderr)
        print("vendored manceps_core is up to date" if not problems else f"{dest} drifted; run scripts/vendor_core.py")
        return EXIT_DRIFT if problems else EXIT_OK
    sync(source, dest)
    print(f"synced {source} -> {dest}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
