"""Upload checks before parsing: byte limit and hash while streaming, file type by extension and magic, safe names.

Types: CSV = text (no NUL bytes, not a zip), XLSX = a zip holding `xl/workbook.xml`, VCF = first non-blank line
`BEGIN:VCARD`. The extension and the content must agree; anything else is 415.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import zipfile
from typing import BinaryIO, Literal

from .errors import PAYLOAD_TOO_LARGE, UNSUPPORTED_MEDIA_TYPE, ImportFileError

FileType = Literal["csv", "xlsx", "vcf"]

CHUNK_BYTES = 64 * 1024
SNIFF_BYTES = 64 * 1024
ZIP_MAGIC = b"PK\x03\x04"
WORKBOOK_PART = "xl/workbook.xml"
VCARD_BEGIN = "BEGIN:VCARD"
UTF8_BOM = "﻿"
EXTENSIONS: dict[str, FileType] = {".csv": "csv", ".txt": "csv", ".xlsx": "xlsx", ".vcf": "vcf", ".vcard": "vcf"}
FILENAME_MAX = 120
FALLBACK_STEM = "upload"
UNSAFE_RUN = re.compile(r"[^A-Za-z0-9_-]+")
SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,8}$")
PATH_SEPARATORS = re.compile(r"[\\/]")


def hash_upload(stream: BinaryIO, prefix: bytes, max_bytes: int) -> tuple[str, int]:
    """Stream a file once: count its bytes against the limit and hash `prefix + bytes`; leave it rewound.

    Args:
        stream: Seekable file.
        prefix: Bytes hashed before the content (the entity name).
        max_bytes: Largest allowed size.

    Returns:
        (hex SHA-256, size in bytes).

    Raises:
        ImportFileError: 413 file_too_large once the size passes max_bytes (the rest is never read).
    """
    digest = hashlib.sha256(prefix)
    size = 0
    while chunk := stream.read(CHUNK_BYTES):
        size += len(chunk)
        if size > max_bytes:
            raise ImportFileError(PAYLOAD_TOO_LARGE, "file_too_large", f"the file is larger than {max_bytes} bytes")
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest(), size


def _extension(filename: str) -> str:
    """Return the lowercased extension of the last path component.

    Args:
        filename: Client-supplied name.

    Returns:
        Extension with the dot, or "".
    """
    name = PATH_SEPARATORS.split(filename)[-1]
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


def _is_workbook(stream: BinaryIO) -> bool:
    """Check a zip holds an Excel workbook part.

    Args:
        stream: Seekable file starting with the zip magic.

    Returns:
        True when `xl/workbook.xml` is in the archive.
    """
    try:
        with zipfile.ZipFile(stream) as archive:
            return WORKBOOK_PART in archive.namelist()
    except (zipfile.BadZipFile, OSError, ValueError, EOFError):
        return False


def _is_vcard(head: bytes) -> bool:
    """Check the first non-blank line is BEGIN:VCARD.

    Args:
        head: First bytes of the file.

    Returns:
        True for a vCard.
    """
    text = head.decode("utf-8", errors="replace").lstrip(UTF8_BOM + " \t\r\n")
    return text.splitlines()[0].strip().upper() == VCARD_BEGIN if text else False


def _matches(kind: FileType, head: bytes, stream: BinaryIO) -> bool:
    """Check the content agrees with the extension.

    Args:
        kind: Type the extension claims.
        head: First bytes.
        stream: The whole file (rewound by the caller).

    Returns:
        True when the magic matches.
    """
    if kind == "xlsx":
        return head.startswith(ZIP_MAGIC) and _is_workbook(stream)
    if kind == "vcf":
        return _is_vcard(head)
    return b"\x00" not in head and not head.startswith(ZIP_MAGIC)


def detect_type(filename: str, stream: BinaryIO) -> FileType:
    """Decide the file type from its extension and content; leave the stream rewound.

    Args:
        filename: Client-supplied name.
        stream: Seekable file.

    Returns:
        csv, xlsx or vcf.

    Raises:
        ImportFileError: 415 unsupported_file_type when the extension is unknown or the content disagrees.
    """
    kind = EXTENSIONS.get(_extension(filename))
    if kind is None:
        raise ImportFileError(UNSUPPORTED_MEDIA_TYPE, "unsupported_file_type", "upload a .csv, .xlsx or .vcf file")
    head = stream.read(SNIFF_BYTES)
    stream.seek(0)
    matched = _matches(kind, head, stream)
    stream.seek(0)
    if not matched:
        raise ImportFileError(UNSUPPORTED_MEDIA_TYPE, "unsupported_file_type",
                              f"the file content is not a valid .{kind} file")
    return kind


def sanitize_filename(raw: str) -> str:
    """Make a client-supplied file name safe to store and to put in a header: no path, no control or odd characters.

    Args:
        raw: Name as uploaded.

    Returns:
        A name of ASCII letters, digits, `_` and `-` with an optional short extension, at most FILENAME_MAX chars.
    """
    name = unicodedata.normalize("NFKC", PATH_SEPARATORS.split(raw or "")[-1])
    dot = name.rfind(".")
    stem, suffix = (name[:dot], name[dot:].lower()) if dot > 0 else (name, "")
    if not SAFE_SUFFIX.fullmatch(suffix):
        stem, suffix = name, ""
    clean = UNSAFE_RUN.sub("_", stem).strip("_-") or FALLBACK_STEM
    return clean[: FILENAME_MAX - len(suffix)] + suffix
