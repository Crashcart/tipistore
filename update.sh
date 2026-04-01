#!/bin/bash
set -e

# Update script with comprehensive logging

log_cmd() {
  local level=$1
  local message=$2
  node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.log('$level', '$message');" 2>/dev/null || true
}

echo "💉 ═══════════════════════════════════════════════════════════════════ 💉"
echo "    Kali Hacker Bot - Update"
echo "💉 ═══════════════════════════════════════════════════════════════════ 💉"
echo ""

log_cmd "INFO" "Starting update process..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found. Cannot update."
    log_cmd "ERROR" ".env file not found"
    exit 1
fi

# Track system info
node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.trackSystemInfo();" 2>/dev/null || true
node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.trackEnvironment();" 2>/dev/null || true

echo "✓ Checking current installation..."
log_cmd "INFO" "Verifying existing installation"

# Check if containers exist
if docker ps -a | grep -q "kali-ai-term-kali"; then
    echo "  ✓ Kali container found"
    log_cmd "SUCCESS" "Kali container exists"
else
    echo "  ❌ Kali container not found"
    log_cmd "ERROR" "Kali container not found - cannot update"
    exit 1
fi

if docker ps -a | grep -q "kali-ai-term-app"; then
    echo "  ✓ App container found"
    log_cmd "SUCCESS" "App container exists"
else
    echo "  ❌ App container not found"
    log_cmd "ERROR" "App container not found - cannot update"
    exit 1
fi

# Stop containers
echo ""
echo "✓ Stopping containers..."
docker_down=$(docker compose down 2>&1 || docker-compose down 2>&1)
docker_down_exit=$?
if [ $docker_down_exit -eq 0 ]; then
    echo "  ✓ Containers stopped"
    log_cmd "SUCCESS" "Containers stopped"
    node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.trackCommand('docker compose down', 0, '');" 2>/dev/null || true
else
    echo "  ⚠ Warning: docker compose down returned exit code $docker_down_exit"
    log_cmd "WARN" "docker compose down returned non-zero exit code"
fi

# Update dependencies
echo ""
echo "✓ Updating Node.js dependencies..."
npm_output=$(npm install 2>&1)
npm_exit=$?
if [ $npm_exit -eq 0 ]; then
    echo "  ✓ Dependencies updated"
    log_cmd "SUCCESS" "npm install completed"
    node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.trackCommand('npm install', 0, '');" 2>/dev/null || true
else
    echo "  ❌ npm install failed with exit code $npm_exit"
    log_cmd "ERROR" "npm install failed"
    node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.trackCommand('npm install', $npm_exit, 'Installation failed');" 2>/dev/null || true
    exit 1
fi

# Start containers
echo ""
echo "✓ Starting containers..."
docker_up=$(docker compose up -d 2>&1 || docker-compose up -d 2>&1)
docker_up_exit=$?
if [ $docker_up_exit -eq 0 ]; then
    echo "  ✓ Containers started"
    log_cmd "SUCCESS" "Containers started"
    node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.trackCommand('docker compose up -d', 0, '');" 2>/dev/null || true
else
    echo "  ❌ Failed to start containers"
    log_cmd "ERROR" "Docker containers failed to start"
    node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.trackCommand('docker compose up -d', $docker_up_exit, 'Startup failed');" 2>/dev/null || true
    exit 1
fi

# Health check
echo "✓ Verifying container health..."
KALI_READY=0
APP_READY=0
WAIT_TIME=0
MAX_WAIT=30

while [ $WAIT_TIME -lt $MAX_WAIT ]; do
  if docker ps --format "table {{.Names}}" | grep -q "kali-ai-term-kali"; then
    KALI_READY=1
  fi

  if docker ps --format "table {{.Names}}" | grep -q "kali-ai-term-app"; then
    APP_READY=1
  fi

  if [ $KALI_READY -eq 1 ] && [ $APP_READY -eq 1 ]; then
    echo "  ✓ Containers verified as running"
    log_cmd "SUCCESS" "All containers verified"
    break
  fi

  WAIT_TIME=$((WAIT_TIME + 1))
  sleep 1
done

if [ $KALI_READY -eq 0 ] || [ $APP_READY -eq 0 ]; then
  echo "  ⚠ Warning: Not all containers started within 30 seconds"
  log_cmd "WARN" "Container startup timeout"
fi

# Generate diagnostic report
INSTALL_STATUS="success"
if [ $KALI_READY -eq 0 ] || [ $APP_READY -eq 0 ]; then
  INSTALL_STATUS="partial"
fi

node -e "const {createLogger} = require('./lib/install-logger'); const l = createLogger('update'); l.generateDiagnostic('$INSTALL_STATUS', 'complete', '');" 2>/dev/null || true

echo ""
echo "💉 ═══════════════════════════════════════════════════════════════════ 💉"
echo "    ✓ Update Complete!"
echo "💉 ═══════════════════════════════════════════════════════════════════ 💉"
echo ""
echo "✓ Installation updated successfully"
echo ""
echo "Next steps:"
echo "    1. Verify application: http://localhost:31337"
echo "    2. Check container logs: docker compose logs -f app"
echo ""

log_cmd "SUCCESS" "Update completed successfully"
