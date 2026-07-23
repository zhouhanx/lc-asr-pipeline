"""Stable user-visible task references and safe correlation logging."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Literal
from uuid import UUID

TaskKind = Literal["asr", "ocr"]
_TASK_PREFIX: dict[TaskKind, str] = {
    "asr": "ASR",
    "ocr": "OCR",
}


def task_reference(kind: TaskKind, task_uuid: UUID) -> str:
    """Return the stable correlation ID shown to users and written to logs."""
    return f"{_TASK_PREFIX[kind]}-{task_uuid}"


def log_task_event(
    logger: logging.Logger,
    level: int,
    *,
    event: str,
    kind: TaskKind,
    task_uuid: UUID,
    stage: str | None = None,
    attempt: int | None = None,
    status: str | None = None,
    retry: bool | None = None,
    error: Exception | None = None,
    safe_message: str | None = None,
) -> None:
    """Write searchable task context without logging provider secrets or payloads."""
    fields = [
        f"event={event}",
        f"task_id={task_reference(kind, task_uuid)}",
        f"task_kind={kind}",
    ]
    if stage is not None:
        fields.append(f"stage={stage}")
    if attempt is not None:
        fields.append(f"attempt={attempt}")
    if status is not None:
        fields.append(f"status={status}")
    if retry is not None:
        fields.append(f"retry={str(retry).lower()}")
    if error is not None:
        fields.append(f"error_type={type(error).__name__}")
        frames = traceback.extract_tb(error.__traceback__)
        if frames:
            trace = ">".join(
                f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames
            )
            fields.append(f"trace={trace}")
    if safe_message:
        fields.append(f"message={safe_message.replace(chr(10), ' ')[:500]}")
    logger.log(level, " ".join(fields))
