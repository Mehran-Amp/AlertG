#!/bin/bash

# ===== Settings =====
APP="server:app"
HOST="0.0.0.0"
PORT="8000"
ENV_FILE=".env"
LOG_FILE="server.log"
PID_FILE="server.pid"
WORKDIR="$(cd "$(dirname "$0")" && pwd)"

# ===== Colors =====
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$WORKDIR" || exit 1

# ===== Functions =====

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

start() {
    if is_running; then
        echo -e "${YELLOW}[WARN] Server is already running (PID: $(cat $PID_FILE))${NC}"
        exit 1
    fi

    echo -e "${GREEN}[INFO] Starting server with env-file '$ENV_FILE'...${NC}"
    
    ENV_OPT=""
    if [ -f "$ENV_FILE" ]; then
        ENV_OPT="--env-file $ENV_FILE"
    else
        echo -e "${YELLOW}[WARN] Environment file '$ENV_FILE' not found! Server starting with default env...${NC}"
    fi

    nohup python -m uvicorn "$APP" --host "$HOST" --port "$PORT" $ENV_OPT > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 2

    if is_running; then
        echo -e "${GREEN}[OK] Server started successfully${NC}"
        echo -e "  PID: ${YELLOW}$(cat $PID_FILE)${NC}"
        echo -e "  URL: ${YELLOW}http://$HOST:$PORT${NC}"
        echo -e "  Log: ${YELLOW}$WORKDIR/$LOG_FILE${NC}"
    else
        echo -e "${RED}[ERROR] Server failed to start! Check log:${NC}"
        tail -n 20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if ! is_running; then
        echo -e "${YELLOW}[WARN] Server is not running${NC}"
        rm -f "$PID_FILE"
        exit 0
    fi

    PID=$(cat "$PID_FILE")
    echo -e "${YELLOW}[INFO] Stopping server (PID: $PID)...${NC}"

    kill "$PID" 2>/dev/null

    # Wait for clean exit up to 10 seconds
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    # Force kill if still alive
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}[WARN] Clean exit failed, using kill -9...${NC}"
        kill -9 "$PID" 2>/dev/null
    fi

    rm -f "$PID_FILE"
    echo -e "${GREEN}[OK] Server stopped${NC}"
}

restart() {
    stop
    sleep 1
    start
}

status() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo -e "${GREEN}[OK] Server is running${NC}"
        echo -e "  PID: ${YELLOW}$PID${NC}"
        echo -e "  URL: ${YELLOW}http://$HOST:$PORT${NC}"
        echo -e "  Uptime:"
        ps -o etime= -p "$PID" | awk '{print "    "$1}'
    else
        echo -e "${RED}[ERROR] Server is not running${NC}"
    fi
}

logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${RED}[ERROR] Log file does not exist${NC}"
        exit 1
    fi
    echo -e "${GREEN}[INFO] Showing log (Ctrl+C to exit)${NC}"
    tail -f "$LOG_FILE"
}

case "$1" in
    start)   start   ;;
    stop)    stop    ;;
    restart) restart ;;
    status)  status  ;;
    logs)    logs    ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start    -> start the server"
        echo "  stop     -> stop the server"
        echo "  restart  -> restart the server"
        echo "  status   -> show server status"
        echo "  logs     -> follow live log"
        exit 1
        ;;
esac
