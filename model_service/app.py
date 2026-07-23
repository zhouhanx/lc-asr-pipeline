"""FastAPI adapter that keeps MLX model loading and inference on one thread."""

from __future__ import annotations

import asyncio
import hmac
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(
    os.getenv("MLX_ASR_MODEL_PATH", PROJECT_ROOT / "model/qwen3-asr-1.7b-8bit")
).resolve()
ALIGNER_PATH = Path(
    os.getenv(
        "MLX_ASR_ALIGNER_PATH", PROJECT_ROOT / "model/qwen3-forced-aligner-0.6b"
    )
).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("MLX_ASR_MAX_UPLOAD_BYTES", 5 * 1024**3))
UPLOAD_CHUNK_BYTES = 8 * 1024**2


class InferenceRuntime:
    """Own one thread so MLX's thread-local Metal stream stays valid."""

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx-asr")
        self.session: Any = None

    def load(self) -> None:
        from mlx_qwen3_asr import Session

        self.session = Session(str(MODEL_PATH))

    def transcribe(self, audio_path: str, **options: Any) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("model runtime is not loaded")
        timestamps = options.pop("timestamps")
        diarize = options.get("diarize", False)
        result = self.session.transcribe(
            audio_path,
            return_timestamps=timestamps or diarize,
            return_chunks=True,
            forced_aligner=str(ALIGNER_PATH) if timestamps or diarize else None,
            **options,
        )
        return {key: value for key, value in asdict(result).items() if value is not None}

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)


runtime = InferenceRuntime()


def _configured_keys() -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in os.getenv("MLX_ASR_API_KEY", "").split(",")
        if value.strip()
    )


def _authorize(authorization: str | None) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")
    supplied = authorization.split(" ", 1)[1]
    if not any(hmac.compare_digest(supplied, key) for key in _configured_keys()):
        raise HTTPException(status_code=403, detail="Invalid API key")


def _pyannote_path() -> Path:
    return Path(os.getenv("PYANNOTE_MODEL_ID", PROJECT_ROOT / "model/pyannote-community-1"))


def _pyannote_available() -> bool:
    path = _pyannote_path()
    return (path / "config.yaml").is_file() and any(path.rglob("*.bin"))


async def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "audio.bin").suffix
    descriptor, raw_path = tempfile.mkstemp(prefix="lc_asr_", suffix=suffix)
    path = Path(raw_path)
    total = 0
    try:
        with os.fdopen(descriptor, "wb") as target:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Audio exceeds 5 GiB limit")
                target.write(chunk)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not _configured_keys():
        raise RuntimeError("MLX_ASR_API_KEY must be configured")
    if not MODEL_PATH.is_dir():
        raise RuntimeError(f"ASR model directory is missing: {MODEL_PATH}")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(runtime.executor, runtime.load)
    try:
        yield
    finally:
        runtime.close()


app = FastAPI(title="LC ASR Native Model Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok" if runtime.session is not None else "starting",
        "model": MODEL_PATH.name,
        "diarization_available": _pyannote_available(),
    }


@app.get("/v1/models")
async def models(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _authorize(authorization)
    return {
        "object": "list",
        "data": [{
            "id": "qwen3-asr-1.7b-mlx-8bit",
            "object": "model",
            "owned_by": "local",
            "capabilities": ["transcription", "timestamps", "diarization"],
        }],
    }


async def _run_transcription(
    upload: UploadFile,
    *,
    language: str | None,
    prompt: str,
    timestamps: bool,
    diarize: bool,
    num_speakers: int | None,
    min_speakers: int,
    max_speakers: int,
) -> dict[str, Any]:
    if min_speakers < 1 or max_speakers < min_speakers:
        raise HTTPException(status_code=422, detail="Invalid speaker bounds")
    if num_speakers is not None and num_speakers < 1:
        raise HTTPException(status_code=422, detail="num_speakers must be positive")
    if diarize and not _pyannote_available():
        raise HTTPException(status_code=503, detail="Diarization model is unavailable")
    path = await _save_upload(upload)
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            runtime.executor,
            lambda: runtime.transcribe(
                str(path),
                language=language,
                context=prompt,
                timestamps=timestamps,
                diarize=diarize,
                diarization_num_speakers=num_speakers,
                diarization_min_speakers=min_speakers,
                diarization_max_speakers=max_speakers,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        detail = f"Transcription failed: {type(exc).__name__}"
        raise HTTPException(status_code=500, detail=detail) from exc
    finally:
        path.unlink(missing_ok=True)


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: Annotated[UploadFile, File()],
    authorization: Annotated[str | None, Header()] = None,
    model: Annotated[str, Form()] = "qwen3-asr-1.7b-mlx-8bit",
    language: Annotated[str | None, Form()] = None,
    prompt: Annotated[str, Form()] = "",
    response_format: Annotated[str, Form()] = "json",
    diarize: Annotated[bool, Form()] = False,
    timestamps: Annotated[bool, Form()] = False,
    num_speakers: Annotated[int | None, Form()] = None,
    min_speakers: Annotated[int, Form()] = 1,
    max_speakers: Annotated[int, Form()] = 8,
) -> dict[str, Any]:
    _authorize(authorization)
    if model not in {"qwen3-asr-1.7b-mlx-8bit", str(MODEL_PATH)}:
        raise HTTPException(status_code=404, detail="Model not found")
    if response_format not in {"json", "verbose_json"}:
        raise HTTPException(status_code=422, detail="Only json and verbose_json are supported")
    result = await _run_transcription(
        file,
        language=language,
        prompt=prompt,
        timestamps=timestamps or response_format == "verbose_json",
        diarize=diarize,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    return result if response_format == "verbose_json" else {"text": result["text"]}
