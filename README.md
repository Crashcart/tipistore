# qBittorrent Intelligent Recovery Agent

Intelligent monitoring and recovery daemon for qBittorrent-nox. Detects when qBittorrent is lagged or degraded and automatically applies recovery strategies while preserving user configurations.

## Features

### 🎯 Multi-Factor Lag Detection
- **Performance Metrics** - Download/upload speeds, peer count, DHT nodes
- **System Health** - CPU usage, memory pressure, disk I/O
- **Configuration Analysis** - Validates qBittorrent settings
- **Log Analysis** - Detects errors and connection issues
- **Trend Analysis** - Rolling 5-minute window for performance degradation

### 🔧 Intelligent Recovery Strategies (In Order)
1. **Connection Cleanup** - Clear stale peer/connection data
2. **DHT Refresh** - Trigger full DHT node rescan
3. **Reload Config** - Reload configuration from disk
4. **Dynamic Limits** - Adjust connection/bandwidth limits
5. **Torrent Refresh** - Pause and resume torrents to reset state
6. **Restart Process** - Graceful restart (last resort)

### ⚙️ Advanced Features
- Rule-based decision making (not AI)
- Balanced lag detection (configurable: aggressive/balanced/conservative)
- User-specified config paths (preserves defaults)
- Detailed logging with decision tracking
- Dry-run mode for testing
- **Notifications** - Email, webhook, and syslog alerts
- **Auto-Tuning** - System-aware configuration recommendations
- **State Snapshots** - Backup and restore recovery state
- **Completion Prediction** - ETA calculations and speed analysis
- **A/B Testing** - Optimize recovery strategies over time
- **Docker Support** - Run agent in containers with Prometheus export
- **Multi-Server** - Manage multiple qBittorrent instances
- **Per-Category Rules** - Different strategies by torrent category

## Installation

### Prerequisites
- Python 3.8+
- qBittorrent-nox with Web API enabled (port 8080)
- Access to qBittorrent config file

### Quick Install

```bash
# Clone repository
git clone https://github.com/Crashcart/qbittorrent-monitor.sh.git
cd qbittorrent-monitor.sh

# Install Python dependencies
pip install -r requirements.txt

# Find your qBittorrent config
find ~/.config -name "qBittorrent.conf" 2>/dev/null
# or 
find ~ -name "*.conf" -path "*/qBittorrent/*" 2>/dev/null
```

## Usage

### Basic Usage

```bash
# Basic monitoring (balanced sensitivity)
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf

# Aggressive monitoring (more sensitive to lag)
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
                        --sensitivity aggressive

# Conservative monitoring (only fix severe issues)
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
                        --sensitivity conservative
```

### Advanced Options

```bash
# Dry run - see what would happen without making changes
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
                        --dry-run

# Custom API port
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
                        --qbt-port 8080

# Custom monitoring interval (seconds)
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
                        --interval 30

# Verbose logging
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
                        --log-level DEBUG

# Custom log file
./qbittorrent_agent.py --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
                        --log-file /tmp/qb-agent.log
```

### Command-Line Options

```
--qbt-config PATH           Path to qBittorrent config file (REQUIRED)
--qbt-port PORT             Web API port (default: 8080)
--qbt-username USER         Web API username (if auth required)
--qbt-password PASS         Web API password (if auth required)
--interval SECONDS          Monitoring interval in seconds (default: 60)
--sensitivity LEVEL         Lag detection sensitivity: aggressive/balanced/conservative (default: balanced)
--log-level LEVEL           Logging level: DEBUG/INFO/WARNING/ERROR (default: INFO)
--log-file PATH             Log file path (default: /var/log/qbittorrent-agent.log)
--dry-run                   Show what would be done without making changes
--daemon                    Run as background daemon
--help                      Show help message
```

## How It Works

### Lag Detection

The agent monitors qBittorrent health through multiple dimensions:

1. **Performance (0-30 points)**
   - Speed drops below baseline by configured threshold
   - Peer count falls below minimum
   - DHT nodes degrade

2. **System Health (0-25 points)**
   - CPU usage exceeds threshold
   - Memory pressure too high
   - Disk I/O bottlenecks

3. **Configuration (0-15 points)**
   - Invalid listening port
   - Missing or corrupt settings

4. **Log Analysis (0-20 points)**
   - Connection errors
   - Timeout patterns
   - Resource exhaustion warnings

5. **Trend Analysis (0-10 points)**
   - Performance degrading over time
   - Sustained low speeds
   - Connection instability

**Lag Score Interpretation:**
- **0-20**: Normal operation
- **20-40**: Minor lag, monitor
- **40-60**: Moderate lag, cleanup/DHT refresh
- **60-75**: Significant lag, config reload + torrent refresh
- **75-85**: Severe lag, dynamic limits adjustment
- **85+**: Critical lag, process restart

### Recovery Execution

When lag is detected, the agent executes recovery strategies in order, least to most invasive:

1. **Connection Cleanup** (15s) - Minimal disruption
2. **DHT Refresh** (10s) - Rescan DHT network
3. **Config Reload** (10s) - Reload settings from disk
4. **Dynamic Limits** (20s) - Adjust bandwidth/connections
5. **Torrent Refresh** (30s) - Pause and resume torrents
6. **Restart** (60s) - Graceful restart of qBittorrent

Each strategy waits for effect before next action. Stops if lag resolves.

## Configuration Examples

### Standard NAS Setup

```bash
./qbittorrent_agent.py \
  --qbt-config /mnt/nas/qbittorrent/qBittorrent.conf \
  --interval 30 \
  --sensitivity balanced
```

### High-Performance Aggressive Monitoring

```bash
./qbittorrent_agent.py \
  --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
  --interval 10 \
  --sensitivity aggressive \
  --log-level DEBUG
```

### Conservative (Production)

```bash
./qbittorrent_agent.py \
  --qbt-config ~/.config/qBittorrent/qBittorrent.conf \
  --interval 120 \
  --sensitivity conservative
```

## Systemd Service (Optional)

Create `/etc/systemd/system/qbittorrent-agent.service`:

```ini
[Unit]
Description=qBittorrent Intelligent Recovery Agent
After=network-online.target qbittorrent-nox.service
Wants=network-online.target

[Service]
Type=simple
User=debian-qbittorrent
WorkingDirectory=/opt/qbittorrent-agent
ExecStart=/opt/qbittorrent-agent/qbittorrent_agent.py \
  --qbt-config /home/debian-qbittorrent/.config/qBittorrent/qBittorrent.conf \
  --interval 60 \
  --sensitivity balanced
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable qbittorrent-agent
sudo systemctl start qbittorrent-agent
sudo systemctl status qbittorrent-agent
```

## Logging

Logs are written to `/var/log/qbittorrent-agent.log` by default (configurable).

### View logs

```bash
# Real-time logs
tail -f /var/log/qbittorrent-agent.log

# Recent logs
tail -50 /var/log/qbittorrent-agent.log

# Filter by level
grep ERROR /var/log/qbittorrent-agent.log
grep WARN /var/log/qbittorrent-agent.log
```

### Log Levels

- `DEBUG` - Detailed diagnostic information
- `INFO` - General informational messages
- `WARNING` - Warning messages (lag detected, recovery applied)
- `ERROR` - Error messages (failures, exceptions)

## Troubleshooting

### Agent won't start

```bash
# Check Python 3.8+
python3 --version

# Check dependencies
pip install -r requirements.txt

# Test script syntax
python3 -m py_compile qbittorrent_agent.py
```

### Can't connect to qBittorrent API

```bash
# Check qBittorrent is running
ps aux | grep qbittorrent-nox

# Check API is enabled (in qBittorrent settings)
# Options → WebUI → Web User Interface (Remote)

# Test API connectivity
curl http://127.0.0.1:8080/api/v2/app/webapiVersion

# Try custom port if not default
./qbittorrent_agent.py --qbt-config ... --qbt-port 8080
```

### Config file not found

```bash
# Find your qBittorrent config
find ~ -name "qBittorrent.conf" 2>/dev/null

# Check full path
file ~/.config/qBittorrent/qBittorrent.conf
```

## Architecture

```
qbittorrent_agent.py              Main entry point & CLI
├── detectors/
│   ├── lag_detector.py           Multi-factor lag detection
│   ├── torrent_health.py         Health scoring system
│   ├── predictive_analyzer.py    Trend-based predictions
│   └── completion_predictor.py   ETA calculations
├── recovery/
│   ├── recovery_engine.py        Recovery strategy execution
│   ├── bandwidth_optimizer.py    Dynamic bandwidth tuning
│   ├── connection_optimizer.py   Connection limit optimization
│   ├── category_rules.py         Per-category recovery rules
│   ├── config_auto_tuner.py      System-aware recommendations
│   ├── multi_server_manager.py   Multi-instance support
│   └── backup_restore.py         State snapshots
├── qbt_api/
│   ├── api_client.py             Web API client
│   └── config_manager.py         Config file handling
├── monitoring/
│   ├── metrics.py                System metrics collection
│   └── prometheus_exporter.py    Prometheus metrics export
├── logging/
│   ├── agent_logger.py           Logging configuration
│   └── notification_system.py    Multi-channel notifications
├── integration/
│   └── docker_integration.py     Docker container support
├── optimization/
│   └── ab_testing_framework.py   Strategy optimization
└── tests/
    └── test_integration.py       Integration tests
```

## Requirements

- Python 3.8+
- requests (HTTP client for webhooks and API)
- psutil (system metrics)
- configparser (config parsing)
- python-daemon (daemon mode)

See `requirements.txt` for versions.

## Advanced Features

### 📬 Notifications

Configure alerts through multiple channels:

```bash
# Email notifications
./qbittorrent_agent.py --qbt-config ... \
  --notify-email-smtp smtp.gmail.com \
  --notify-email-port 587 \
  --notify-email-from user@gmail.com \
  --notify-email-password APP_PASSWORD \
  --notify-email-to admin@example.com

# Webhook notifications
./qbittorrent_agent.py --qbt-config ... \
  --notify-webhook https://hooks.slack.com/services/YOUR/WEBHOOK

# Syslog notifications
./qbittorrent_agent.py --qbt-config ... \
  --notify-syslog local0
```

### 🎯 Completion Prediction

The agent predicts torrent completion times:

```bash
# View predictions in real-time
tail -f /var/log/qbittorrent-agent.log | grep "ETA"
```

Predictions improve over time as the agent collects speed history.

### ⚙️ Auto-Configuration Tuning

Let the agent suggest optimal settings based on your system:

```bash
# Get recommendations (dry-run only)
./qbittorrent_agent.py --qbt-config ... --suggest-config
```

Suggestions include:
- Connection limits based on available memory
- Bandwidth limits based on CPU cores
- Cache size based on RAM
- Piece size for disk I/O optimization
- Active torrent count recommendations

### 📊 A/B Testing

Compare recovery strategies:

```bash
# Enable A/B testing
./qbittorrent_agent.py --qbt-config ... --enable-ab-testing

# View results
curl http://localhost:8081/ab-testing/results
```

### 🐳 Docker Deployment

Run the agent in a container:

```bash
# Build image
docker build -t qbittorrent-agent .

# Run container
docker run -d \
  --name qb-agent \
  --network host \
  -e QBT_HOST=localhost \
  -e QBT_PORT=8080 \
  qbittorrent-agent

# Or use docker-compose
docker-compose up -d
```

### 💾 State Backup & Restore

Automatic snapshots of recovery state:

```bash
# Snapshots saved to /var/lib/qbittorrent-agent/backups/
# Each contains: lag_score, applied_limits, system_metrics, recovery_attempts

# View snapshots
ls -la /var/lib/qbittorrent-agent/backups/

# Restore from snapshot (manual)
python3 -c "
from recovery.backup_restore import BackupRestoreManager
mgr = BackupRestoreManager()
snapshot = mgr.load_snapshot_from_file('backups/20240101_120000.json')
print(f'Lag score: {snapshot.lag_score}')
"
```

### 📈 Prometheus Metrics

Export metrics for monitoring and visualization:

```bash
# Enable Prometheus export
./qbittorrent_agent.py --qbt-config ... --enable-prometheus --prometheus-port 8081

# Scrape metrics
curl http://localhost:8081/metrics

# Configure Prometheus (prometheus.yml)
scrape_configs:
  - job_name: 'qbittorrent-agent'
    static_configs:
      - targets: ['localhost:8081']
    scrape_interval: 30s

# View in Grafana
# Import the generated dashboard template for instant visualization
```

Exported metrics include:
- qBittorrent speeds, peer counts, DHT nodes
- Lag score and detection status
- Applied connection/bandwidth limits
- System CPU, memory, disk usage
- Recovery attempt counts
- Notification history

## Security

- ✓ No external API calls (self-contained)
- ✓ No elevated privileges required
- ✓ Respects user configurations
- ✓ Graceful error handling
- ✓ Detailed audit logging
- ✓ Dry-run mode for testing
- ✓ Credentials stored securely (not in configs)
- ✓ Optional TLS for webhook/SMTP

## Contributing

Pull requests welcome! Areas for enhancement:

- Additional lag detection metrics
- More recovery strategies
- Better API error handling
- Test coverage
- Docker container support

## License

MIT License

## Support

For issues:
1. Check logs: `tail -f /var/log/qbittorrent-agent.log`
2. Run with verbose logging: `--log-level DEBUG`
3. Test in dry-run mode: `--dry-run`
4. File an issue with logs and config details (masked IPs)
