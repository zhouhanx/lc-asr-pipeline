"""Secret-safe diagnostics for the native MLX speech-model runtime."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_ROOT = PROJECT_ROOT / "model"
PLACEHOLDERS = {"", "replace-me", "replace-with-a-long-random-service-key"}


def dotenv_presence(key: str) -> bool:
    value = os.getenv(key, "").strip()
    if value and value not in PLACEHOLDERS:
        return True
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        candidate, raw_value = stripped.split("=", 1)
        if candidate.strip() == key:
            return raw_value.strip().strip("'\"") not in PLACEHOLDERS
    return False


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def directory_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "files": 0, "bytes": 0}
    files = [item for item in path.rglob("*") if item.is_file()]
    summary = {
        "present": True,
        "files": len(files),
        "bytes": sum(item.stat().st_size for item in files),
    }
    if path.name == "pyannote-community-1":
        summary["complete"] = (path / "config.yaml").is_file() and any(path.rglob("*.bin"))
    elif path.name in {
        "qwen3-forced-aligner-0.6b",
        "qwen3-asr-1.7b",
        "qwen3-asr-1.7b-8bit",
    }:
        summary["complete"] = (path / "config.json").is_file() and any(
            path.glob("*.safetensors")
        )
    return summary


def mlx_summary() -> dict[str, Any]:
    try:
        import mlx.core as mx

        value = mx.array([1.0, 2.0]) + 1
        mx.eval(value)
        return {"available": True, "device": str(mx.default_device()), "smoke_test": True}
    except Exception as error:  # noqa: BLE001 - diagnostic boundary
        return {"available": False, "error": type(error).__name__}


def torch_summary() -> dict[str, Any]:
    try:
        import torch

        return {
            "available": True,
            "version": torch.__version__,
            "mps_built": bool(torch.backends.mps.is_built()),
            "mps_available": bool(torch.backends.mps.is_available()),
        }
    except Exception as error:  # noqa: BLE001 - diagnostic boundary
        return {"available": False, "error": type(error).__name__}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when core runtime is unavailable",
    )
    arguments = parser.parse_args()
    model_root = Path(os.getenv("LC_ASR_MODEL_DIR", DEFAULT_MODEL_ROOT)).expanduser().resolve()
    artifacts = {
        name: directory_summary(model_root / relative)
        for name, relative in {
            "qwen_source": "downloads/qwen3-asr-1.7b",
            "qwen_8bit": "qwen3-asr-1.7b-8bit",
            "aligner": "qwen3-forced-aligner-0.6b",
            "pyannote": "pyannote-community-1",
        }.items()
    }
    report = {
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "macos": platform.mac_ver()[0],
            "python": platform.python_version(),
        },
        "model_root": str(model_root),
        "model_root_inside_project": model_root.is_relative_to(PROJECT_ROOT),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "packages": {
            name: package_version(name)
            for name in ("mlx", "mlx-qwen3-asr", "pyannote.audio", "torch", "huggingface-hub")
        },
        "mlx": mlx_summary(),
        "torch": torch_summary(),
        "secrets": {
            "pyannote_token_configured": dotenv_presence("PYANNOTE_AUTH_TOKEN")
            or dotenv_presence("HF_TOKEN")
            or dotenv_presence("HUGGINGFACE_HUB_TOKEN"),
            "model_service_key_configured": dotenv_presence("MLX_ASR_API_KEY"),
        },
        "artifacts": artifacts,
    }
    try:
        disk = shutil.disk_usage(model_root)
        report["disk"] = {"free_bytes": disk.free, "total_bytes": disk.total}
    except FileNotFoundError:
        report["disk"] = {"free_bytes": 0, "total_bytes": 0}

    print(json.dumps(report, ensure_ascii=False, indent=2))
    core_ok = (
        report["platform"]["system"] == "Darwin"
        and report["platform"]["machine"] == "arm64"
        and report["ffmpeg"]
        and report["mlx"]["available"]
    )
    return 0 if core_ok or not arguments.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
