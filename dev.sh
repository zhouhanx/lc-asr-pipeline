#!/bin/sh

set -u

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LOG_DIR="$PROJECT_ROOT/logs"
CONTROL_LOG="$LOG_DIR/dev.log"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
WORKER_LOG="$LOG_DIR/worker.log"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
WORKER_PID_FILE="$LOG_DIR/worker.pid"

CONDA_ENV_NAME=${CONDA_ENV_NAME:-lc-asr-pipeline}
BACKEND_HOST=${BACKEND_HOST:-127.0.0.1}
BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_HOST=${FRONTEND_HOST:-127.0.0.1}
FRONTEND_PORT=${FRONTEND_PORT:-5173}

mkdir -p "$LOG_DIR"
touch "$CONTROL_LOG" "$BACKEND_LOG" "$FRONTEND_LOG" "$WORKER_LOG"

log() {
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    printf '[%s] %s\n' "$timestamp" "$*" | tee -a "$CONTROL_LOG"
}

read_pid() {
    pid_file=$1
    if [ -f "$pid_file" ]; then
        sed -n '1p' "$pid_file"
    fi
}

process_matches() {
    pid=$1
    marker=$2
    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    kill -0 "$pid" 2>/dev/null || return 1
    command_line=$(ps -p "$pid" -o command= 2>/dev/null || true)
    case "$command_line" in
        *"$marker"*) return 0 ;;
        *) return 1 ;;
    esac
}

resolve_python() {
    if [ -n "${PROJECT_PYTHON:-}" ] && [ -x "$PROJECT_PYTHON" ]; then
        printf '%s\n' "$PROJECT_PYTHON"
        return 0
    fi

    if [ "${CONDA_DEFAULT_ENV:-}" = "$CONDA_ENV_NAME" ] && command -v python >/dev/null 2>&1; then
        command -v python
        return 0
    fi

    conda_command=${CONDA_EXE:-}
    if [ -z "$conda_command" ]; then
        conda_command=$(command -v conda 2>/dev/null || true)
    fi
    if [ -n "$conda_command" ]; then
        "$conda_command" run -n "$CONDA_ENV_NAME" python -c 'import sys; print(sys.executable)' 2>/dev/null
        return $?
    fi

    return 1
}

start_backend() {
    existing_pid=$(read_pid "$BACKEND_PID_FILE")
    if process_matches "$existing_pid" 'lc_asr_pipeline.main:app'; then
        log "backend already running (PID $existing_pid)"
        return 0
    fi

    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        log "backend not started: $PROJECT_ROOT/.env is missing"
        return 1
    fi

    python_bin=$(resolve_python) || {
        log "backend not started: activate Conda environment '$CONDA_ENV_NAME' or set PROJECT_PYTHON"
        return 1
    }

    log "starting backend at http://$BACKEND_HOST:$BACKEND_PORT (log: $BACKEND_LOG)"
    cd "$PROJECT_ROOT" || return 1
    nohup "$python_bin" -m uvicorn lc_asr_pipeline.main:app \
        --host "$BACKEND_HOST" --port "$BACKEND_PORT" >>"$BACKEND_LOG" 2>&1 &
    backend_pid=$!
    printf '%s\n' "$backend_pid" >"$BACKEND_PID_FILE"
    sleep 1
    if ! process_matches "$backend_pid" 'lc_asr_pipeline.main:app'; then
        log "backend failed to start; recent output follows"
        tail -n 20 "$BACKEND_LOG"
        return 1
    fi
    log "backend started (PID $backend_pid)"
}

start_frontend() {
    existing_pid=$(read_pid "$FRONTEND_PID_FILE")
    if process_matches "$existing_pid" 'node_modules/vite/bin/vite.js'; then
        log "frontend already running (PID $existing_pid)"
        return 0
    fi

    vite_bin="$PROJECT_ROOT/frontend/node_modules/vite/bin/vite.js"
    if [ ! -f "$vite_bin" ]; then
        log "frontend not started: run 'npm install' in $PROJECT_ROOT/frontend first"
        return 1
    fi
    node_bin=$(command -v node 2>/dev/null || true)
    if [ -z "$node_bin" ]; then
        log "frontend not started: node is not available"
        return 1
    fi

    log "starting frontend at http://$FRONTEND_HOST:$FRONTEND_PORT (log: $FRONTEND_LOG)"
    cd "$PROJECT_ROOT/frontend" || return 1
    nohup "$node_bin" "$vite_bin" --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
        >>"$FRONTEND_LOG" 2>&1 &
    frontend_pid=$!
    printf '%s\n' "$frontend_pid" >"$FRONTEND_PID_FILE"
    sleep 1
    if ! process_matches "$frontend_pid" 'node_modules/vite/bin/vite.js'; then
        log "frontend failed to start; recent output follows"
        tail -n 20 "$FRONTEND_LOG"
        return 1
    fi
    log "frontend started (PID $frontend_pid)"
}

start_worker() {
    existing_pid=$(read_pid "$WORKER_PID_FILE")
    if process_matches "$existing_pid" 'lc_asr_pipeline.worker'; then
        log "worker already running (PID $existing_pid)"
        return 0
    fi
    python_bin=$(resolve_python) || {
        log "worker not started: Conda environment '$CONDA_ENV_NAME' is unavailable"
        return 1
    }
    log "starting transcription worker (log: $WORKER_LOG)"
    cd "$PROJECT_ROOT" || return 1
    nohup "$python_bin" -m lc_asr_pipeline.worker >>"$WORKER_LOG" 2>&1 &
    worker_pid=$!
    printf '%s\n' "$worker_pid" >"$WORKER_PID_FILE"
    sleep 1
    if ! process_matches "$worker_pid" 'lc_asr_pipeline.worker'; then
        log "worker failed to start; recent output follows"
        tail -n 20 "$WORKER_LOG"
        return 1
    fi
    log "worker started (PID $worker_pid)"
}

stop_service() {
    service_name=$1
    pid_file=$2
    marker=$3
    pid=$(read_pid "$pid_file")

    if ! process_matches "$pid" "$marker"; then
        rm -f "$pid_file"
        log "$service_name is not running"
        return 0
    fi

    log "stopping $service_name (PID $pid)"
    kill "$pid"
    attempts=0
    while kill -0 "$pid" 2>/dev/null && [ "$attempts" -lt 50 ]; do
        sleep 0.1
        attempts=$((attempts + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        log "$service_name did not stop gracefully; forcing shutdown"
        kill -KILL "$pid"
    fi
    rm -f "$pid_file"
    log "$service_name stopped"
}

show_status() {
    backend_pid=$(read_pid "$BACKEND_PID_FILE")
    frontend_pid=$(read_pid "$FRONTEND_PID_FILE")
    worker_pid=$(read_pid "$WORKER_PID_FILE")
    if process_matches "$backend_pid" 'lc_asr_pipeline.main:app'; then
        log "backend: running (PID $backend_pid, http://$BACKEND_HOST:$BACKEND_PORT)"
    else
        log "backend: stopped"
    fi
    if process_matches "$frontend_pid" 'node_modules/vite/bin/vite.js'; then
        log "frontend: running (PID $frontend_pid, http://$FRONTEND_HOST:$FRONTEND_PORT)"
    else
        log "frontend: stopped"
    fi
    if process_matches "$worker_pid" 'lc_asr_pipeline.worker'; then
        log "worker: running (PID $worker_pid)"
    else
        log "worker: stopped"
    fi
}

start_all() {
    start_backend || return 1
    if ! start_worker; then
        stop_service backend "$BACKEND_PID_FILE" 'lc_asr_pipeline.main:app'
        return 1
    fi
    if ! start_frontend; then
        stop_service worker "$WORKER_PID_FILE" 'lc_asr_pipeline.worker'
        stop_service backend "$BACKEND_PID_FILE" 'lc_asr_pipeline.main:app'
        return 1
    fi
    log "services started; use '$0 logs' to follow output"
}

stop_all() {
    stop_service frontend "$FRONTEND_PID_FILE" 'node_modules/vite/bin/vite.js'
    stop_service worker "$WORKER_PID_FILE" 'lc_asr_pipeline.worker'
    stop_service backend "$BACKEND_PID_FILE" 'lc_asr_pipeline.main:app'
}

usage() {
    printf 'Usage: %s {start|stop|restart|status|logs}\n' "$0"
}

case "${1:-}" in
    start) start_all ;;
    stop) stop_all ;;
    restart) stop_all && start_all ;;
    status) show_status ;;
    logs)
        log "following backend, worker, and frontend logs; press Ctrl-C to exit"
        tail -n 100 -f "$BACKEND_LOG" "$WORKER_LOG" "$FRONTEND_LOG"
        ;;
    *) usage; exit 2 ;;
esac
