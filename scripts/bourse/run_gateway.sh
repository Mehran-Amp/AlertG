#!/bin/sh
# Supervisor for tsetmc-gateway on server360 (Phase 18c-3).
# POSIX sh, strict mode, cron-safe (absolute Python path), never prints secrets.
#
# Usage: run_gateway.sh {start|stop|restart|status|ensure}
# Environment overrides:
#   GATEWAY_DIR    (default: $HOME/tsetmc-gateway)
#   PYTHON         (default: $HOME/.pyenv/versions/miniconda3-3.11-24.11.1-0/bin/python3, fallback python3)
#   LOG_MAX_BYTES  (default: 5242880 = 5 MiB)

set -eu

GATEWAY_DIR="${GATEWAY_DIR:-$HOME/tsetmc-gateway}"
ENV_FILE="$GATEWAY_DIR/gateway.env"
PID_FILE="$GATEWAY_DIR/gateway.pid"
LOG_FILE="$GATEWAY_DIR/gateway.log"
LOG_MAX_BYTES="${LOG_MAX_BYTES:-5242880}"

TSETMC_HOST="127.0.0.1"
TSETMC_PORT="8080"

resolve_python() {
    if [ -n "${PYTHON:-}" ]; then
        if [ -x "$PYTHON" ] || command -v "$PYTHON" >/dev/null 2>&1; then
            printf '%s\n' "$PYTHON"
            return 0
        fi
        printf '%s\n' "error: configured PYTHON is not executable" >&2
        return 1
    fi

    if [ -x "$HOME/.pyenv/versions/miniconda3-3.11-24.11.1-0/bin/python3" ]; then
        printf '%s\n' "$HOME/.pyenv/versions/miniconda3-3.11-24.11.1-0/bin/python3"
        return 0
    fi

    if [ -x "$HOME/.pyenv/shims/python3" ]; then
        printf '%s\n' "$HOME/.pyenv/shims/python3"
        return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi

    printf '%s\n' "error: python3 not found" >&2
    return 1
}

load_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        return 1
    fi

    while IFS= read -r raw_line || [ -n "$raw_line" ]; do
        # Strip trailing CR (CRLF safety)
        line=$(printf '%s' "$raw_line" | tr -d '\r')
        # Skip empty lines and comments
        case "$line" in
            ''|'#'*) continue ;;
        esac
        # Strip optional leading "export "
        case "$line" in
            export\ *) line=${line#export } ;;
        esac
        # Must contain '='
        case "$line" in
            *=*) ;;
            *) continue ;;
        esac

        key=${line%%=*}
        val=${line#*=}

        # Validate key is a strict POSIX identifier (prevents eval injection)
        case "$key" in
            ''|[0-9]*|*[!A-Za-z0-9_]*)
                continue
                ;;
        esac

        # Strip matching single or double surrounding quotes if present
        case "$val" in
            \"*\")
                val=${val#\"}
                val=${val%\"}
                ;;
            \'*\')
                val=${val#\'}
                val=${val%\'}
                ;;
        esac

        eval "${key}=\$val"
        # shellcheck disable=SC2163
        export "$key"
    done < "$ENV_FILE"

    TSETMC_HOST="${TSETMC_HOST:-127.0.0.1}"
    TSETMC_PORT="${TSETMC_PORT:-8080}"
    return 0
}

read_pid() {
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi
    pid=$(tr -d '[:space:]' < "$PID_FILE" 2>/dev/null || true)
    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    printf '%s\n' "$pid"
    return 0
}

is_pid_alive() {
    check_pid="$1"
    if ! kill -0 "$check_pid" 2>/dev/null; then
        return 1
    fi
    # Guard against zombie processes
    proc_stat=$(ps -p "$check_pid" -o stat= 2>/dev/null | tr -d '[:space:]' || true)
    case "$proc_stat" in
        Z*) return 1 ;;
    esac
    return 0
}

is_running() {
    pid=$(read_pid) || return 1
    is_pid_alive "$pid"
}

is_port_busy() {
    py_bin="$1"
    "$py_bin" -c '
import socket, sys
host = sys.argv[1]
port = int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(0.5)
try:
    rc = s.connect_ex((host, port))
finally:
    s.close()
sys.exit(0 if rc == 0 else 1)
' "$TSETMC_HOST" "$TSETMC_PORT" 2>/dev/null
}

rotate_log_if_needed() {
    if [ ! -f "$LOG_FILE" ]; then
        return 0
    fi
    size=$(wc -c < "$LOG_FILE" | tr -d '[:space:]')
    case "$size" in
        ''|*[!0-9]*) return 0 ;;
    esac
    if [ "$size" -ge "$LOG_MAX_BYTES" ]; then
        mv -f "$LOG_FILE" "${LOG_FILE}.1"
    fi
}

do_start() {
    if [ ! -f "$ENV_FILE" ]; then
        printf '%s\n' "error: gateway env file not found: $ENV_FILE" >&2
        return 1
    fi
    load_env_file

    py_bin=$(resolve_python)

    if is_running; then
        running_pid=$(read_pid)
        printf '%s\n' "error: gateway is already running (pid=$running_pid port=$TSETMC_PORT)" >&2
        return 1
    fi

    # Remove stale pid file if process is gone
    rm -f "$PID_FILE"

    if is_port_busy "$py_bin"; then
        printf '%s\n' "error: port $TSETMC_PORT on $TSETMC_HOST is already in use" >&2
        return 1
    fi

    mkdir -p "$GATEWAY_DIR"
    rotate_log_if_needed

    (
        cd "$GATEWAY_DIR"
        if [ -n "${PYTHONPATH:-}" ]; then
            PYTHONPATH="$GATEWAY_DIR:$PYTHONPATH"
        else
            PYTHONPATH="$GATEWAY_DIR"
        fi
        export PYTHONPATH
        nohup "$py_bin" -u -m tsetmc_gateway >>"$LOG_FILE" 2>&1 </dev/null &
        printf '%s\n' "$!" > "$PID_FILE"
    )

    new_pid=$(read_pid || true)
    if [ -z "$new_pid" ]; then
        printf '%s\n' "error: failed to record gateway pid" >&2
        return 1
    fi

    # Brief liveness check so immediate startup crashes are caught
    sleep 1
    if ! is_pid_alive "$new_pid"; then
        rm -f "$PID_FILE"
        printf '%s\n' "error: gateway exited immediately after start (check $LOG_FILE)" >&2
        return 1
    fi

    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || printf '%s' 'unknown')
    printf '%s\n' "[$ts] gateway started (pid=$new_pid port=$TSETMC_PORT)"
    return 0
}

do_stop() {
    load_env_file || true

    if ! is_running; then
        rm -f "$PID_FILE"
        printf '%s\n' "gateway stopped (port=$TSETMC_PORT)"
        return 0
    fi

    target_pid=$(read_pid)
    kill "$target_pid" 2>/dev/null || true

    waited=0
    while [ "$waited" -lt 10 ]; do
        if ! is_pid_alive "$target_pid"; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    if is_pid_alive "$target_pid"; then
        kill -9 "$target_pid" 2>/dev/null || true
        sleep 1
    fi

    rm -f "$PID_FILE"
    printf '%s\n' "gateway stopped (pid=$target_pid port=$TSETMC_PORT)"
    return 0
}

do_status() {
    load_env_file || true

    if is_running; then
        cur_pid=$(read_pid)
        uptime_str=$(ps -p "$cur_pid" -o etime= 2>/dev/null | tr -d '[:space:]' || true)
        if [ -z "$uptime_str" ]; then
            uptime_str="unknown"
        fi
        printf '%s\n' "status=running pid=$cur_pid port=$TSETMC_PORT uptime=$uptime_str"
        return 0
    fi

    printf '%s\n' "status=stopped pid=none port=$TSETMC_PORT uptime=0"
    return 3
}

do_ensure() {
    if is_running; then
        return 0
    fi
    do_start
}

do_restart() {
    do_stop
    do_start
}

cmd="${1:-}"
case "$cmd" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_restart ;;
    status)  do_status ;;
    ensure)  do_ensure ;;
    *)
        printf '%s\n' "Usage: $0 {start|stop|restart|status|ensure}" >&2
        exit 2
        ;;
esac
