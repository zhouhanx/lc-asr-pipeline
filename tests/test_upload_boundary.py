"""Exact upload-limit and sparse 5 GiB pressure checks."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from scripts.upload_boundary_pressure import create_sparse_boundary

from lc_asr_pipeline.api.routes.uploads import enforce_upload_batch_size


def test_upload_limit_accepts_exact_boundary_and_rejects_one_byte_over() -> None:
    limit = 5 * 1024**3
    enforce_upload_batch_size(limit - 1, limit)
    enforce_upload_batch_size(limit, limit)
    with pytest.raises(HTTPException) as error:
        enforce_upload_batch_size(limit + 1, limit)
    assert error.value.status_code == 413


def test_exact_five_gib_sparse_boundary_has_expected_chunk_math(tmp_path: Path) -> None:
    result = create_sparse_boundary(
        tmp_path,
        size_bytes=5 * 1024**3,
        chunk_bytes=8 * 1024**2,
    )
    assert result.logical_bytes == 5 * 1024**3
    assert result.expected_chunks == 640
    assert result.allocated_bytes < result.logical_bytes
