#!/bin/sh

set -u

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MODEL_ENV_NAME=${MODEL_ENV_NAME:-lc-asr-model}
MODEL_HOST=${MODEL_HOST:-127.0.0.1}
MODEL_PORT=${MODEL_PORT:-8765}
MODEL_PATH=${MODEL_PATH:-$PROJECT_ROOT/model/qwen3-asr-1.7b-8bit}
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/model.log"
PID_FILE="$LOG_DIR/model.pid"
CONDA_COMMAND=${CONDA_EXE:-$(command -v conda 2>/dev/null || true)}

mkdir -p "$LOG_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() {
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    printf '[%s] %s\n' "$timestamp" "$*" | tee -a "$LOG_FILE"
}

resolve_python() {
    if [ -z "$CONDA_COMMAND" ]; then
        return 1
    fi
    "$CONDA_COMMAND" run -n "$MODEL_ENV_NAME" python -c 'import sys; print(sys.executable)' \
        2>/dev/null
}

read_setting() {
    python_bin=$1
    setting_name=$2
    "$python_bin" -c \
        'import os, sys; from dotenv import dotenv_values; values=dotenv_values(sys.argv[1]); print(os.getenv(sys.argv[2]) or values.get(sys.argv[2]) or "")' \
        "$PROJECT_ROOT/.env" "$setting_name"
}

read_pid() {
    if [ -f "$PID_FILE" ]; then
        sed -n '1p' "$PID_FILE"
    fi
}

is_running() {
    pid=$1
    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    kill -0 "$pid" 2>/dev/null || return 1
    command_line=$(ps -p "$pid" -o command= 2>/dev/null || true)
    case "$command_line" in
        *"uvicorn model_service.app:app"*) return 0 ;;
        *) return 1 ;;
    esac
}

start_service() {
    current_pid=$(read_pid)
    if is_running "$current_pid"; then
        log "model service already running (PID $current_pid)"
        return 0
    fi
    if [ ! -d "$MODEL_PATH" ]; then
        log "model service not started: model directory missing: $MODEL_PATH"
        return 1
    fi
    model_python=$(resolve_python) || {
        log "model service not started: Conda environment '$MODEL_ENV_NAME' is unavailable"
        return 1
    }
    if ! "$model_python" -c 'import uvicorn, mlx_qwen3_asr' >/dev/null 2>&1; then
        log "model service not started: run ./scripts/model_bootstrap.sh first"
        return 1
    fi

    service_key=$(read_setting "$model_python" MLX_ASR_API_KEY)
    case "$service_key" in
        ''|replace-with-a-long-random-service-key)
            log "model service not started: configure MLX_ASR_API_KEY in .env"
            return 1
            ;;
    esac
    pyannote_token=$(read_setting "$model_python" PYANNOTE_AUTH_TOKEN)

    log "starting native MLX model service at http://$MODEL_HOST:$MODEL_PORT"
    cd "$PROJECT_ROOT" || return 1
    HF_HOME="$PROJECT_ROOT/model/cache/huggingface" \
    HF_HUB_CACHE="$PROJECT_ROOT/model/cache/huggingface/hub" \
    MLX_ASR_API_KEY="$service_key" \
    MLX_ASR_MODEL_PATH="$MODEL_PATH" \
    MLX_ASR_ALIGNER_PATH="$PROJECT_ROOT/model/qwen3-forced-aligner-0.6b" \
    MLX_ASR_MAX_UPLOAD_BYTES=5368709120 \
    PYANNOTE_AUTH_TOKEN="$pyannote_token" \
    PYANNOTE_MODEL_ID="$PROJECT_ROOT/model/pyannote-community-1" \
    nohup "$model_python" -m uvicorn model_service.app:app \
        --host "$MODEL_HOST" --port "$MODEL_PORT" >>"$LOG_FILE" 2>&1 &
    model_pid=$!
    printf '%s\n' "$model_pid" >"$PID_FILE"
    chmod 600 "$PID_FILE"

    attempts=0
    while [ "$attempts" -lt 60 ]; do
        if curl -fsS "http://$MODEL_HOST:$MODEL_PORT/health" >/dev/null 2>&1; then
            log "model service started (PID $model_pid)"
            return 0
        fi
        if ! is_running "$model_pid"; then
            break
        fi
        sleep 0.5
        attempts=$((attempts + 1))
    done
    log "model service failed to become healthy; recent output follows"
    tail -n 30 "$LOG_FILE"
    return 1
}

stop_service() {
    current_pid=$(read_pid)
    if ! is_running "$current_pid"; then
        rm -f "$PID_FILE"
        log "model service is not running"
        return 0
    fi
    log "stopping model service (PID $current_pid)"
    kill "$current_pid"
    attempts=0
    while kill -0 "$current_pid" 2>/dev/null && [ "$attempts" -lt 100 ]; do
        sleep 0.1
        attempts=$((attempts + 1))
    done
    if kill -0 "$current_pid" 2>/dev/null; then
        log "model service did not stop gracefully; forcing shutdown"
        kill -KILL "$current_pid"
    fi
    rm -f "$PID_FILE"
    log "model service stopped"
}

show_status() {
    current_pid=$(read_pid)
    if is_running "$current_pid"; then
        if curl -fsS "http://$MODEL_HOST:$MODEL_PORT/health" >/dev/null 2>&1; then
            log "model service: running and healthy (PID $current_pid, http://$MODEL_HOST:$MODEL_PORT)"
        else
            log "model service: running but unhealthy (PID $current_pid)"
            return 1
        fi
    else
        rm -f "$PID_FILE"
        log "model service: stopped"
    fi
}

usage() {
    printf 'Usage: %s {start|stop|restart|status|logs}\n' "$0"
}

case "${1:-}" in
    start) start_service ;;
    stop) stop_service ;;
    restart) stop_service && start_service ;;
    status) show_status ;;
    logs) tail -n 100 -f "$LOG_FILE" ;;
    *) usage; exit 2 ;;
esac
