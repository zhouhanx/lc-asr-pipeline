"""Sparse 5 GiB boundary probe with an explicit physical-write opt-in."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SparseBoundaryResult:
    logical_bytes: int
    allocated_bytes: int
    expected_chunks: int


def create_sparse_boundary(
    directory: Path,
    *,
    size_bytes: int,
    chunk_bytes: int,
) -> SparseBoundaryResult:
    path = directory / "boundary.sparse"
    with path.open("wb") as target:
        target.truncate(size_bytes)
    stat = path.stat()
    return SparseBoundaryResult(
        logical_bytes=stat.st_size,
        allocated_bytes=stat.st_blocks * 512,
        expected_chunks=(size_bytes + chunk_bytes - 1) // chunk_bytes,
    )


def physical_copy_probe(
    directory: Path,
    *,
    size_bytes: int,
    reserve_bytes: int,
) -> str:
    free_bytes = shutil.disk_usage(directory).free
    required = size_bytes * 2 + reserve_bytes
    if free_bytes < required:
        raise RuntimeError(
            f"Physical probe requires at least {required} free bytes; found {free_bytes}"
        )
    source_path = directory / "boundary.sparse"
    copy_path = directory / "boundary.physical"
    digest = hashlib.sha256()
    with source_path.open("rb") as source, copy_path.open("wb") as target:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
            target.write(chunk)
    if copy_path.stat().st_size != size_bytes:
        raise RuntimeError("Physical boundary copy size mismatch")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the exact 5 GiB upload boundary")
    parser.add_argument(
        "--physical",
        action="store_true",
        help="physically write and hash 5 GiB after a free-space preflight",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        help="parent directory for the isolated temporary probe",
    )
    arguments = parser.parse_args()
    size_bytes = 5 * 1024**3
    chunk_bytes = 8 * 1024**2
    parent = arguments.directory.resolve() if arguments.directory else None
    with tempfile.TemporaryDirectory(
        prefix="lc-asr-5g-boundary-",
        dir=parent,
    ) as temporary:
        directory = Path(temporary)
        result = create_sparse_boundary(
            directory,
            size_bytes=size_bytes,
            chunk_bytes=chunk_bytes,
        )
        print(
            f"logical_bytes={result.logical_bytes} "
            f"allocated_bytes={result.allocated_bytes} "
            f"expected_chunks={result.expected_chunks}"
        )
        if arguments.physical:
            digest = physical_copy_probe(
                directory,
                size_bytes=size_bytes,
                reserve_bytes=1024**3,
            )
            print(f"physical_sha256={digest}")


if __name__ == "__main__":
    main()
