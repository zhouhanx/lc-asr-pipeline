"""Bounded, traversal-safe extraction for uploaded audio archives."""

from __future__ import annotations

import hashlib
import shutil
import stat
import tarfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

AUDIO_SUFFIXES = {
    ".aac",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}


@dataclass(frozen=True, slots=True)
class ExtractedAudio:
    relative_path: str
    storage_path: Path
    size_bytes: int
    sha256: str


def _safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError("Archive contains an unsafe path")
    return path


def _copy_member(
    source: IO[bytes],
    target: Path,
    *,
    remaining_bytes: int,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    written = 0
    with target.open("xb") as output:
        while chunk := source.read(8 * 1024 * 1024):
            written += len(chunk)
            if written > remaining_bytes:
                raise ValueError("Archive expands beyond the configured limit")
            digest.update(chunk)
            output.write(chunk)
    return written, digest.hexdigest()


def _zip_members(archive: zipfile.ZipFile) -> Iterator[tuple[str, int, IO[bytes]]]:
    for member in archive.infolist():
        mode = member.external_attr >> 16
        if member.is_dir():
            continue
        if stat.S_ISLNK(mode):
            raise ValueError("Archive links are not allowed")
        yield member.filename, member.file_size, archive.open(member)


def _tar_members(archive: tarfile.TarFile) -> Iterator[tuple[str, int, IO[bytes]]]:
    for member in archive.getmembers():
        if member.isdir():
            continue
        if not member.isfile():
            raise ValueError("Archive links and special files are not allowed")
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("Archive member cannot be read")
        yield member.name, member.size, source


def extract_audio_archive(
    source_path: Path,
    destination: Path,
    *,
    archive_type: str,
    max_bytes: int,
    max_entries: int = 10000,
) -> list[ExtractedAudio]:
    """Extract audio members without trusting archive paths or sizes."""
    destination.mkdir(parents=True, exist_ok=False)
    extracted: list[ExtractedAudio] = []
    seen: set[str] = set()
    total = 0
    try:
        container: zipfile.ZipFile | tarfile.TarFile
        members: Iterator[tuple[str, int, IO[bytes]]]
        if archive_type == "zip":
            container = zipfile.ZipFile(source_path)
            members = _zip_members(container)
        elif archive_type in {"tar", "tar.gz", "tgz"}:
            container = tarfile.open(source_path, mode="r:*")  # noqa: SIM115
            members = _tar_members(container)
        else:
            raise ValueError("Unsupported archive type")
        with container:
            for entry_index, (name, declared_size, stream) in enumerate(members):
                with stream:
                    if entry_index >= max_entries:
                        raise ValueError("Archive contains too many entries")
                    member_path = _safe_member_path(name)
                    normalized = str(member_path)
                    if normalized in seen:
                        raise ValueError("Archive contains duplicate paths")
                    seen.add(normalized)
                    if declared_size < 0 or total + declared_size > max_bytes:
                        raise ValueError("Archive expands beyond the configured limit")
                    if member_path.suffix.lower() not in AUDIO_SUFFIXES:
                        continue
                    if declared_size == 0:
                        continue
                    target = destination / f"{len(extracted):08d}{member_path.suffix.lower()}"
                    size, checksum = _copy_member(
                        stream,
                        target,
                        remaining_bytes=max_bytes - total,
                    )
                    total += size
                    extracted.append(ExtractedAudio(normalized, target, size, checksum))
        if not extracted:
            raise ValueError("Archive contains no supported audio files")
        return extracted
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
