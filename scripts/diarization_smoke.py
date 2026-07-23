"""Validate local two-speaker ASR, alignment, and pyannote attribution."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "audio",
        type=Path,
        nargs="?",
        default=PROJECT_ROOT / "data/fixtures/two-speaker-zh.wav",
    )
    arguments = parser.parse_args()
    pyannote_path = PROJECT_ROOT / "model/pyannote-community-1"
    if not pyannote_path.is_dir():
        raise RuntimeError("pyannote Community-1 is not downloaded")
    os.environ["PYANNOTE_MODEL_ID"] = str(pyannote_path)

    from mlx_qwen3_asr import Session  # type: ignore[import-not-found]

    session = Session(str(PROJECT_ROOT / "model/qwen3-asr-1.7b-8bit"))
    result = session.transcribe(
        arguments.audio.resolve(),
        language="Chinese",
        return_timestamps=True,
        return_chunks=True,
        forced_aligner=str(PROJECT_ROOT / "model/qwen3-forced-aligner-0.6b"),
        diarize=True,
        diarization_num_speakers=2,
    )
    segments = result.speaker_segments or []
    speakers = {str(segment.get("speaker")) for segment in segments if segment.get("speaker")}
    if len(speakers) < 2:
        raise RuntimeError("Diarization did not identify two speakers")
    if not result.segments:
        raise RuntimeError("Forced alignment returned no timestamp segments")
    print(
        f"status=ok speakers={len(speakers)} "
        f"speaker_segments={len(segments)} timestamp_segments={len(result.segments)}"
    )


if __name__ == "__main__":
    main()
