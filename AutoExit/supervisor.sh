#!/bin/bash
# supervisor.sh - Auto-restart supervisor for AutoExit bot
# Usage: ./supervisor.sh
# Make executable: chmod +x supervisor.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="${SCRIPT_DIR}"
VENV_PYTHON="${BOT_DIR}/../venv/bin/python3"
MAIN_SCRIPT="${BOT_DIR}/main.py"
LOG_FILE="${BOT_DIR}/logs/bot.log"
PID_FILE="${BOT_DIR}/autoexit.pid"

# Ensure logs directory exists
mkdir -p "${BOT_DIR}/logs"

# Function to check if bot is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Function to start the bot
start_bot() {
    echo "[$(date)] Starting AutoExit bot..." | tee -a "$LOG_FILE"
    
    # Kill orphaned processes if any
    pkill -f "python.*main.py" 2>/dev/null
    
    # Start bot in background with nohup
    nohup "$VENV_PYTHON" "$MAIN_SCRIPT" >> "$LOG_FILE" 2>&1 &
    BOT_PID=$!
    
    echo "$BOT_PID" > "$PID_FILE"
    echo "[$(date)] Bot started with PID: $BOT_PID" | tee -a "$LOG_FILE"
}

# Function to stop the bot
stop_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        echo "[$(date)] Stopping bot (PID: $PID)..." | tee -a "$LOG_FILE"
        kill "$PID" 2>/dev/null
        rm -f "$PID_FILE"
        echo "[$(date)] Bot stopped" | tee -a "$LOG_FILE"
    else
        echo "[$(date)] No PID file found" | tee -a "$LOG_FILE"
    fi
}

# Handle signals for graceful shutdown
trap 'stop_bot; exit 0' SIGINT SIGTERM

# Main supervision loop
echo "[$(date)] Supervisor started" | tee -a "$LOG_FILE"

while true; do
    if ! is_running; then
        echo "[$(date)] Bot not running, starting..." | tee -a "$LOG_FILE"
        start_bot
        sleep 5
    fi
    
    # Check every 30 seconds
    sleep 30
done
