"""Filesystem and EPUB boundaries shared by API and audit tooling."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import zipfile


def resolve_under_root(root: str | Path, *parts: str) -> Path:
    base = Path(root).resolve()
    candidate = base.joinpath(*[str(part) for part in parts]).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError("Resolved path escapes the configured library root") from exc
    return candidate


def safe_epub_filename(filename: str | None) -> str:
    leaf = Path(str(filename or "book.epub").replace("\\", "/")).name
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(leaf).stem).strip(". _") or "book"
    return stem[:120] + ".epub"


def validate_epub_archive(
    path: str | Path,
    *,
    max_members: int = 20_000,
    max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024,
    max_compression_ratio: float = 250.0,
    max_member_bytes: int = 512 * 1024 * 1024,
) -> dict:
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not zipfile.is_zipfile(source):
        raise ValueError("EPUB is not a valid ZIP archive")
    total = 0
    blocked_extensions = {".bat", ".cmd", ".com", ".dll", ".exe", ".jar", ".msi", ".ps1", ".scr"}
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise ValueError(f"EPUB contains too many members: {len(members)}")
        if not members or members[0].filename != "mimetype" or members[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("EPUB mimetype entry must be the first uncompressed archive member")
        if archive.read(members[0]) != b"application/epub+zip":
            raise ValueError("EPUB mimetype signature is invalid")
        seen: set[str] = set()
        for item in members:
            normalized = item.filename.replace("\\", "/")
            member = PurePosixPath(normalized)
            if not normalized or "\x00" in normalized or len(normalized) > 512:
                raise ValueError("EPUB member name is invalid")
            identity = normalized.casefold()
            if identity in seen:
                raise ValueError(f"Duplicate EPUB member path: {item.filename}")
            seen.add(identity)
            if member.is_absolute() or ".." in member.parts or normalized.startswith("/") or ":" in member.parts[0]:
                raise ValueError(f"Unsafe EPUB member path: {item.filename}")
            unix_mode = (item.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError(f"EPUB symbolic links are not supported: {item.filename}")
            if item.flag_bits & 0x1:
                raise ValueError(f"Encrypted EPUB member is not supported: {item.filename}")
            if member.suffix.lower() in blocked_extensions:
                raise ValueError(f"Executable EPUB member is not supported: {item.filename}")
            if item.file_size > max_member_bytes:
                raise ValueError(f"EPUB member exceeds configured size limit: {item.filename}")
            total += int(item.file_size)
            if total > max_uncompressed_bytes:
                raise ValueError("EPUB uncompressed size exceeds configured limit")
            if item.file_size and item.compress_size == 0:
                raise ValueError(f"Unsafe compression ratio for EPUB member: {item.filename}")
            if item.file_size / max(1, item.compress_size) > max_compression_ratio:
                raise ValueError(f"Unsafe compression ratio for EPUB member: {item.filename}")
    return {"members": len(members), "uncompressed_bytes": total, "path": str(source)}


def copy_limited(source, target: Path, max_bytes: int, block_size: int = 1024 * 1024) -> int:
    written = 0
    with target.open("xb") as output:
        while True:
            block = source.read(block_size)
            if not block:
                break
            written += len(block)
            if written > max_bytes:
                raise ValueError("Uploaded EPUB exceeds configured size limit")
            output.write(block)
    return written
