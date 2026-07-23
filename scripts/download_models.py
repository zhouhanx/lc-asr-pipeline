"""Download selected model assets into the repository model directory."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import snapshot_download

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.getenv("LC_ASR_MODEL_DIR", PROJECT_ROOT / "model")).expanduser().resolve()
MANIFEST = json.loads((PROJECT_ROOT / "model" / "manifest.json").read_text(encoding="utf-8"))


def token_from_environment() -> str | None:
    values = {**dotenv_values(PROJECT_ROOT / ".env"), **os.environ}
    for key in ("PYANNOTE_AUTH_TOKEN", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        value = values.get(key)
        if value:
            return str(value)
    return None


def artifact(artifact_id: str) -> dict[str, object]:
    for item in MANIFEST["artifacts"]:
        if item["id"] == artifact_id:
            return item
    raise KeyError(artifact_id)


def artifact_complete(artifact_id: str, path: Path) -> bool:
    if artifact_id == "pyannote-community-1":
        return (path / "config.yaml").is_file() and any(path.rglob("*.bin"))
    return (path / "config.json").is_file() and any(path.glob("*.safetensors"))


def download(artifact_id: str, *, token: str | None = None) -> Path:
    item = artifact(artifact_id)
    source = str(item["source"])
    destination = MODEL_ROOT / str(item["local_directory"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    if artifact_complete(artifact_id, destination):
        print(f"Already complete: {destination}")
        return destination
    staging = destination.with_name(destination.name + ".partial")
    print(f"Downloading {source} -> {destination}")
    resolved = snapshot_download(
        repo_id=source,
        local_dir=staging,
        token=token,
        max_workers=4,
    )
    resolved_path = Path(resolved)
    if not artifact_complete(artifact_id, resolved_path):
        raise RuntimeError(f"Downloaded artifact is incomplete: {artifact_id}")
    if destination.exists():
        backup = destination.with_name(f"{destination.name}.incomplete-{int(time.time())}")
        destination.rename(backup)
    resolved_path.rename(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact",
        choices=("qwen", "aligner", "pyannote", "ungated", "all"),
        required=True,
    )
    arguments = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(MODEL_ROOT / "cache" / "huggingface"))
    os.environ.setdefault("HF_HUB_CACHE", str(MODEL_ROOT / "cache" / "huggingface" / "hub"))

    selected: list[str] = []
    if arguments.artifact in {"qwen", "ungated", "all"}:
        selected.append("qwen3-asr-1.7b-source")
    if arguments.artifact in {"aligner", "ungated", "all"}:
        selected.append("qwen3-forced-aligner-0.6b")
    if arguments.artifact in {"pyannote", "all"}:
        selected.append("pyannote-community-1")

    token = token_from_environment()
    if "pyannote-community-1" in selected and token is None:
        parser.error(
            "pyannote requires accepted Hugging Face terms and PYANNOTE_AUTH_TOKEN in .env"
        )

    for artifact_id in selected:
        download(artifact_id, token=token if artifact_id == "pyannote-community-1" else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
