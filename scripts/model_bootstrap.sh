#!/bin/sh

set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MODEL_ENV_NAME=${MODEL_ENV_NAME:-lc-asr-model}
CONDA_COMMAND=${CONDA_EXE:-$(command -v conda 2>/dev/null || true)}

if [ -z "$CONDA_COMMAND" ]; then
    printf 'conda is required; set CONDA_EXE or add conda to PATH\n' >&2
    exit 1
fi

if ! "$CONDA_COMMAND" env list | awk '{print $1}' | grep -qx "$MODEL_ENV_NAME"; then
    printf 'Creating native model environment: %s\n' "$MODEL_ENV_NAME"
    "$CONDA_COMMAND" create -y -n "$MODEL_ENV_NAME" python=3.12 pip
else
    printf 'Using existing native model environment: %s\n' "$MODEL_ENV_NAME"
fi

printf 'Installing pinned model runtime dependencies...\n'
"$CONDA_COMMAND" run -n "$MODEL_ENV_NAME" python -m pip install \
    'mlx-qwen3-asr[aligner,diarize,serve]==0.3.5' \
    'pyannote.audio==4.0.7' \
    'huggingface_hub[cli]>=0.35,<2' \
    'python-dotenv>=1.1,<2'

mkdir -p \
    "$PROJECT_ROOT/model/cache/huggingface" \
    "$PROJECT_ROOT/model/downloads" \
    "$PROJECT_ROOT/data/uploads" \
    "$PROJECT_ROOT/data/transcripts"

printf 'Model environment ready. Run:\n'
printf '  conda run -n %s python scripts/model_doctor.py\n' "$MODEL_ENV_NAME"
