#!/bin/bash

##############################################################################
# qBittorrent-nox Monitor and Recovery Script
#
# Description: Monitors qbittorrent-nox daemon process and restarts it if crashed
# Features: Drive mount checking, health monitoring, smart restart with backoff
#
# Usage: ./qbittorrent-monitor.sh -i <5m|1h|30m> [-d /mnt/drive] [-M /mnt/downloads]
#
# Examples:
#   ./qbittorrent-monitor.sh -i 5m              # Check every 5 minutes
#   ./qbittorrent-monitor.sh -i 1h              # Check every 1 hour
#   ./qbittorrent-monitor.sh -i 10m -d /mnt/data -M /mnt/downloads
##############################################################################

set -euo pipefail

# Default values
INTERVAL="5m"
QB_USER="${QB_USER:-debian-qbittorrent}"
QB_PORT="6881"
LOG_FILE="/var/log/qbittorrent-monitor.log"
PID_FILE="/var/run/qbittorrent-monitor.pid"
STATUS_FILE="/var/run/qbittorrent-monitor.status"
DATA_DIR=""
DOWNLOAD_DIR=""
DISK_WARN_PERCENT=90
MOUNT_WAIT_MAX=60
RESTART_ATTEMPTS=0
RESTART_MAX_ATTEMPTS=3
DAEMON_MODE=true
FOREGROUND=false

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

##############################################################################
# Functions
##############################################################################

print_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
    -i <time>        Check interval: 5m, 1h, 30m, etc (default: 5m)
    -U <user>        System user running qbittorrent-nox (default: debian-qbittorrent)
    -p <port>        qBittorrent port (default: 6881)
    -d <path>        qBittorrent data directory (optional, checks if mounted)
    -M <path>        Downloads directory (optional, checks if mounted)
    -l <logfile>     Log file path (default: /var/log/qbittorrent-monitor.log)
    -w <percent>     Disk space warning threshold (default: 90%)
    -f               Run in foreground mode (default: daemon mode)
    -h               Display this help message

Examples:
    $0 -i 5m                                              # Runs as daemon
    $0 -i 30m -d /mnt/qb-data -M /mnt/downloads          # Runs as daemon
    $0 -i 1h -d /data -w 85 -f                            # Runs in foreground
    $0 -i 5m -l /custom/path/monitor.log

EOF
}

log_message() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local color=""

    case "$level" in
        ERROR) color="$RED" ;;
        WARN) color="$YELLOW" ;;
        INFO) color="$GREEN" ;;
        DEBUG) color="$BLUE" ;;
    esac

    echo -e "${color}[${timestamp}] [${level}]${NC} ${message}" | tee -a "${LOG_FILE}"
}

parse_time_interval() {
    local input="$1"
    # Remove leading dash if present (e.g., "-5m" -> "5m")
    input="${input#-}"

    if [[ $input =~ ^([0-9]+)([mh])$ ]]; then
        local num="${BASH_REMATCH[1]}"
        local unit="${BASH_REMATCH[2]}"

        if [[ "$unit" == "h" ]]; then
            echo $((num * 3600))
        else
            echo $((num * 60))
        fi
    else
        echo "error"
    fi
}

is_directory_mounted() {
    local dir="$1"
    if [[ -z "$dir" ]]; then
        return 0
    fi

    if mountpoint -q "$dir" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

wait_for_mount() {
    local dir="$1"
    local timeout="${2:-$MOUNT_WAIT_MAX}"
    local elapsed=0

    if [[ -z "$dir" ]]; then
        return 0
    fi

    while [[ $elapsed -lt $timeout ]]; do
        if is_directory_mounted "$dir"; then
            log_message "INFO" "Directory mounted: $dir"
            return 0
        fi

        if [[ $elapsed -eq 0 ]]; then
            log_message "WARN" "Waiting for mount: $dir (timeout: ${timeout}s)"
        fi

        sleep 1
        ((elapsed++))
    done

    log_message "ERROR" "Mount timeout for $dir after ${timeout}s"
    return 1
}

check_disk_space() {
    local dir="$1"
    if [[ -z "$dir" ]] || [[ ! -d "$dir" ]]; then
        return 0
    fi

    local usage=$(df "$dir" | awk 'NR==2 {print $5}' | sed 's/%//')

    if [[ $usage -gt $DISK_WARN_PERCENT ]]; then
        log_message "WARN" "Disk usage on $dir is ${usage}% (threshold: ${DISK_WARN_PERCENT}%)"
        return 1
    fi

    return 0
}

check_process_health() {
    if ! check_qbittorrent; then
        return 1
    fi

    # Check memory usage (warn if >1GB)
    local mem=$(pgrep -u "${QB_USER}" -f "qbittorrent-nox" | xargs ps aux | grep qbittorrent-nox | grep -v grep | awk '{sum+=$6} END {print sum}')
    if [[ $mem -gt 1000000 ]]; then
        log_message "WARN" "qbittorrent-nox using high memory: $(( mem / 1024 ))MB"
    fi

    return 0
}

exponential_backoff() {
    local attempt="$1"
    local max_wait=300  # Max 5 minutes
    local wait=$((2 ** attempt))

    if [[ $wait -gt $max_wait ]]; then
        wait=$max_wait
    fi

    log_message "WARN" "Restart attempt $((attempt + 1))/$RESTART_MAX_ATTEMPTS, waiting ${wait}s before retry"
    sleep "$wait"
}

check_qbittorrent() {
    if pgrep -u "${QB_USER}" -f "qbittorrent-nox" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

restart_qbittorrent() {
    log_message "WARN" "qbittorrent-nox is not running. Attempting to restart..."

    # Check if critical directories are available
    if [[ -n "$DATA_DIR" ]] && ! is_directory_mounted "$DATA_DIR"; then
        log_message "ERROR" "Cannot restart: data directory not mounted ($DATA_DIR)"
        return 1
    fi

    if [[ -n "$DOWNLOAD_DIR" ]] && ! is_directory_mounted "$DOWNLOAD_DIR"; then
        log_message "ERROR" "Cannot restart: download directory not mounted ($DOWNLOAD_DIR)"
        return 1
    fi

    # Try to start qbittorrent-nox as the specified user
    if su - "${QB_USER}" -c "qbittorrent-nox --daemon" > /dev/null 2>&1; then
        sleep 2
        if check_qbittorrent; then
            log_message "INFO" "qbittorrent-nox successfully restarted"
            RESTART_ATTEMPTS=0
            echo "success" > "$STATUS_FILE"
            return 0
        else
            log_message "ERROR" "qbittorrent-nox started but process not detected"
            return 1
        fi
    else
        log_message "ERROR" "Failed to restart qbittorrent-nox"
        return 1
    fi
}

cleanup() {
    log_message "INFO" "Monitor shutting down"
    rm -f "${PID_FILE}" "${STATUS_FILE}"
    exit 0
}

daemonize() {
    # Fork to background
    "$0" "$@" > /dev/null 2>&1 &
    local daemon_pid=$!
    echo "Started qBittorrent monitor daemon (PID: $daemon_pid)"
    exit 0
}

##############################################################################
# Main Script
##############################################################################

# Parse command line arguments
while getopts "i:U:p:d:M:l:w:fh" opt; do
    case $opt in
        i)
            INTERVAL="$OPTARG"
            ;;
        U)
            QB_USER="$OPTARG"
            ;;
        p)
            QB_PORT="$OPTARG"
            ;;
        d)
            DATA_DIR="$OPTARG"
            ;;
        M)
            DOWNLOAD_DIR="$OPTARG"
            ;;
        l)
            LOG_FILE="$OPTARG"
            ;;
        w)
            DISK_WARN_PERCENT="$OPTARG"
            ;;
        f)
            FOREGROUND=true
            DAEMON_MODE=false
            ;;
        h)
            print_help
            exit 0
            ;;
        *)
            print_help
            exit 1
            ;;
    esac
done

# Daemonize if not in foreground mode
if [[ "$DAEMON_MODE" == true ]]; then
    # Reconstruct arguments for daemon
    declare -a daemon_args
    [[ "$INTERVAL" != "5m" ]] && daemon_args+=("-i" "$INTERVAL")
    [[ "$QB_USER" != "debian-qbittorrent" ]] && daemon_args+=("-U" "$QB_USER")
    [[ "$QB_PORT" != "6881" ]] && daemon_args+=("-p" "$QB_PORT")
    [[ -n "$DATA_DIR" ]] && daemon_args+=("-d" "$DATA_DIR")
    [[ -n "$DOWNLOAD_DIR" ]] && daemon_args+=("-M" "$DOWNLOAD_DIR")
    [[ "$LOG_FILE" != "/var/log/qbittorrent-monitor.log" ]] && daemon_args+=("-l" "$LOG_FILE")
    [[ "$DISK_WARN_PERCENT" != "90" ]] && daemon_args+=("-w" "$DISK_WARN_PERCENT")
    daemonize "${daemon_args[@]}"
fi

# Validate interval format
SLEEP_TIME=$(parse_time_interval "$INTERVAL")
if [[ "$SLEEP_TIME" == "error" ]]; then
    echo "Error: Invalid interval format. Use format like: 5m, 1h, 30m"
    exit 1
fi

# Validate disk warning percent
if ! [[ "$DISK_WARN_PERCENT" =~ ^[0-9]+$ ]] || [[ "$DISK_WARN_PERCENT" -lt 1 ]] || [[ "$DISK_WARN_PERCENT" -gt 100 ]]; then
    echo "Error: Disk warning percent must be 1-100"
    exit 1
fi

# Ensure log directory exists
LOG_DIR=$(dirname "${LOG_FILE}")
if [[ ! -d "$LOG_DIR" ]]; then
    mkdir -p "$LOG_DIR"
fi

# Write PID file
echo $$ > "${PID_FILE}"

# Set up trap for graceful shutdown
trap cleanup SIGINT SIGTERM

# Initial log
log_message "INFO" "qBittorrent-nox monitor started"
log_message "INFO" "Check interval: ${INTERVAL} (${SLEEP_TIME} seconds)"
log_message "INFO" "Running as user: ${QB_USER}"
[[ -n "$DATA_DIR" ]] && log_message "INFO" "Data directory: ${DATA_DIR}"
[[ -n "$DOWNLOAD_DIR" ]] && log_message "INFO" "Download directory: ${DOWNLOAD_DIR}"
log_message "INFO" "Log file: ${LOG_FILE}"

# Wait for initial mount before starting
if [[ -n "$DATA_DIR" ]] || [[ -n "$DOWNLOAD_DIR" ]]; then
    log_message "INFO" "Checking for required mounts..."
    [[ -n "$DATA_DIR" ]] && wait_for_mount "$DATA_DIR"
    [[ -n "$DOWNLOAD_DIR" ]] && wait_for_mount "$DOWNLOAD_DIR"
fi

# Main monitoring loop
while true; do
    # Check for required mounts
    if [[ -n "$DATA_DIR" ]]; then
        if ! is_directory_mounted "$DATA_DIR"; then
            log_message "WARN" "Data directory not mounted: $DATA_DIR"
            sleep "$SLEEP_TIME"
            continue
        fi
        check_disk_space "$DATA_DIR"
    fi

    if [[ -n "$DOWNLOAD_DIR" ]]; then
        if ! is_directory_mounted "$DOWNLOAD_DIR"; then
            log_message "WARN" "Download directory not mounted: $DOWNLOAD_DIR"
            sleep "$SLEEP_TIME"
            continue
        fi
        check_disk_space "$DOWNLOAD_DIR"
    fi

    # Check qBittorrent process
    if ! check_qbittorrent; then
        log_message "ERROR" "qbittorrent-nox is not running"

        if [[ $RESTART_ATTEMPTS -lt $RESTART_MAX_ATTEMPTS ]]; then
            exponential_backoff "$RESTART_ATTEMPTS"
            if restart_qbittorrent; then
                RESTART_ATTEMPTS=0
            else
                ((RESTART_ATTEMPTS++))
            fi
        else
            log_message "ERROR" "Max restart attempts reached. Manual intervention required."
            echo "failed" > "$STATUS_FILE"
        fi
    else
        check_process_health
        log_message "DEBUG" "qbittorrent-nox is running normally"
    fi

    sleep "$SLEEP_TIME"
done
