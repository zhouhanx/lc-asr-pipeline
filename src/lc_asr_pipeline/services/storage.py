"""Safe physical-storage deletion helpers."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID


def delete_uploaded_file_storage(
    *,
    data_path: Path,
    tenant_id: UUID,
    root_file_id: UUID | None,
    exact_storage_path: str | None,
) -> None:
    """Delete only paths proven to be below the current tenant upload root."""
    tenant_root = (data_path.resolve() / "uploads" / str(tenant_id)).resolve()
    if root_file_id is not None:
        root = (tenant_root / str(root_file_id)).resolve()
        if not root.is_relative_to(tenant_root):
            raise ValueError("Upload storage target escaped the tenant root")
        shutil.rmtree(root, ignore_errors=True)
        return
    if exact_storage_path is None:
        return
    target = Path(exact_storage_path).resolve()
    if not target.is_relative_to(tenant_root):
        raise ValueError("Upload storage target escaped the tenant root")
    target.unlink(missing_ok=True)
    parent = target.parent
    while parent != tenant_root and parent.is_relative_to(tenant_root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
