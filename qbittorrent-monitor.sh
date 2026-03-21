#!/bin/bash

##############################################################################
# qBittorrent-nox Monitor and Recovery Script
#
# Description: Monitors qbittorrent-nox daemon process and restarts it if crashed
# Usage: ./qbittorrent-monitor.sh -i <interval> [-u <unit>] [-u <user>] [-p <port>]
#
# Examples:
#   ./qbittorrent-monitor.sh -i 5 -u m        # Check every 5 minutes
#   ./qbittorrent-monitor.sh -i 2 -u h        # Check every 2 hours
#   ./qbittorrent-monitor.sh -i 1 -u h -u user # Run as specific user
##############################################################################

set -euo pipefail

# Default values
INTERVAL=5
UNIT="m"  # m for minutes, h for hours
QB_USER="${QB_USER:-debian-qbittorrent}"
QB_PORT="6881"
LOG_FILE="/var/log/qbittorrent-monitor.log"
PID_FILE="/var/run/qbittorrent-monitor.pid"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

##############################################################################
# Functions
##############################################################################

print_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
    -i <interval>    Check interval (default: 5)
    -u <unit>        Time unit: 'm' for minutes, 'h' for hours (default: m)
    -U <user>        System user running qbittorrent-nox (default: debian-qbittorrent)
    -p <port>        qBittorrent port (default: 6881)
    -l <logfile>     Log file path (default: /var/log/qbittorrent-monitor.log)
    -h               Display this help message

EOF
}

log_message() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
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

    # Try to start qbittorrent-nox as the specified user
    if su - "${QB_USER}" -c "qbittorrent-nox --daemon" > /dev/null 2>&1; then
        sleep 2
        if check_qbittorrent; then
            log_message "INFO" "qbittorrent-nox successfully restarted"
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

calculate_sleep_time() {
    local interval="$1"
    local unit="$2"

    if [[ "$unit" == "h" ]]; then
        echo $((interval * 3600))
    else
        echo $((interval * 60))
    fi
}

cleanup() {
    log_message "INFO" "Monitor shutting down"
    rm -f "${PID_FILE}"
    exit 0
}

##############################################################################
# Main Script
##############################################################################

# Parse command line arguments
while getopts "i:u:U:p:l:h" opt; do
    case $opt in
        i)
            INTERVAL="$OPTARG"
            ;;
        u)
            UNIT="$OPTARG"
            ;;
        U)
            QB_USER="$OPTARG"
            ;;
        p)
            QB_PORT="$OPTARG"
            ;;
        l)
            LOG_FILE="$OPTARG"
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

# Validate unit
if [[ ! "$UNIT" =~ ^[mh]$ ]]; then
    echo "Error: Unit must be 'm' (minutes) or 'h' (hours)"
    exit 1
fi

# Validate interval
if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || [[ "$INTERVAL" -lt 1 ]]; then
    echo "Error: Interval must be a positive integer"
    exit 1
fi

# Ensure log directory exists
LOG_DIR=$(dirname "${LOG_FILE}")
if [[ ! -d "$LOG_DIR" ]]; then
    mkdir -p "$LOG_DIR"
fi

# Calculate sleep time
SLEEP_TIME=$(calculate_sleep_time "$INTERVAL" "$UNIT")
UNIT_NAME="minutes"
[[ "$UNIT" == "h" ]] && UNIT_NAME="hours"

# Write PID file
echo $$ > "${PID_FILE}"

# Set up trap for graceful shutdown
trap cleanup SIGINT SIGTERM

# Initial log
log_message "INFO" "qBittorrent-nox monitor started"
log_message "INFO" "Check interval: ${INTERVAL} ${UNIT_NAME} (${SLEEP_TIME} seconds)"
log_message "INFO" "Running as user: ${QB_USER}"
log_message "INFO" "Log file: ${LOG_FILE}"

# Main monitoring loop
while true; do
    if ! check_qbittorrent; then
        restart_qbittorrent
    else
        log_message "INFO" "qbittorrent-nox is running normally"
    fi

    sleep "$SLEEP_TIME"
done
