"""Transcribe one local audio file through the LangChain/provider pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from lc_asr_pipeline.providers.openai_compatible import OpenAICompatibleASRProvider
from lc_asr_pipeline.providers.stepfun import StepFunASRProvider
from lc_asr_pipeline.schemas.transcription import TranscriptionRequest
from lc_asr_pipeline.services.secrets import resolve_secret_reference
from lc_asr_pipeline.services.transcription_chain import build_transcription_chain

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def audio_duration(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(completed.stdout.strip())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024**2):
            digest.update(chunk)
    return digest.hexdigest()


def write_private_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--provider", choices=("local", "stepfun"), default="local")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--model")
    parser.add_argument("--language", default="Chinese")
    parser.add_argument("--diarize", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/test_results/smoke-transcription.json",
    )
    arguments = parser.parse_args()

    audio = arguments.audio.expanduser().resolve()
    if not audio.is_file():
        raise SystemExit("Audio file does not exist")
    api_key_env = arguments.api_key_env or (
        "stepfun_api_key" if arguments.provider == "stepfun" else "MLX_ASR_API_KEY"
    )
    api_key = resolve_secret_reference(api_key_env)
    if not api_key:
        raise SystemExit(f"Secret reference {api_key_env} is not configured")

    base_url = arguments.base_url or (
        "https://api.stepfun.com/v1"
        if arguments.provider == "stepfun"
        else "http://127.0.0.1:8765"
    )
    model = arguments.model or (
        "stepaudio-2.5-asr"
        if arguments.provider == "stepfun"
        else "qwen3-asr-1.7b-mlx-8bit"
    )
    provider = (
        StepFunASRProvider(
            name="StepFun",
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        if arguments.provider == "stepfun"
        else OpenAICompatibleASRProvider(
            name="Local MLX",
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    )
    request = TranscriptionRequest(
        audio_path=audio,
        language=arguments.language,
        timestamps=True,
        diarize=arguments.diarize,
    )
    duration = audio_duration(audio)
    started = time.monotonic()
    result = build_transcription_chain(provider).invoke(request)
    elapsed = time.monotonic() - started
    payload: dict[str, object] = {
        "source": {
            "path": str(audio.relative_to(PROJECT_ROOT))
            if audio.is_relative_to(PROJECT_ROOT)
            else audio.name,
            "size_bytes": audio.stat().st_size,
            "sha256": sha256(audio),
            "duration_seconds": duration,
        },
        "transcription": result.model_dump(mode="json"),
        "test": {
            "elapsed_seconds": elapsed,
            "real_time_factor": elapsed / duration,
            "diarization_requested": arguments.diarize,
        },
    }
    output = arguments.output.resolve()
    write_private_json(output, payload)
    print(
        f"status=completed duration_seconds={duration:.2f} elapsed_seconds={elapsed:.2f} "
        f"rtf={elapsed / duration:.4f} segments={len(result.segments)} "
        f"speaker_segments={len(result.speaker_segments)} output={output}"
    )


if __name__ == "__main__":
    main()
