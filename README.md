# qBittorrent Monitor & Recovery Service

Automated monitoring and recovery daemon for qBittorrent-nox. Monitors the qBittorrent process and automatically restarts it if it crashes, with configurable intervals, mount checking, and disk space monitoring.

## Features

- 🚀 **Daemon Mode** - Runs as background service by default
- 🔄 **Auto-Recovery** - Automatically restarts crashed qBittorrent instances
- 📦 **Mount Monitoring** - Checks if data/download directories are mounted before startup
- 💾 **Disk Monitoring** - Warns when disk usage exceeds threshold
- ⏱️ **Smart Backoff** - Exponential backoff on restart failures (2s → 4s → 8s → max 5min)
- 📊 **Health Checks** - Monitors memory usage and process health
- 🔧 **Flexible Configuration** - All settings configurable via command-line flags
- 📝 **Detailed Logging** - Color-coded logs with timestamps

## Quick Installation

### Option 1: Automated Installation (Recommended)

```bash
# Download and install script
curl -sSL https://raw.githubusercontent.com/Crashcart/tipistore/main/qbittorrent-monitor.sh \
  -o /usr/local/bin/qbittorrent-monitor.sh && \
  chmod +x /usr/local/bin/qbittorrent-monitor.sh

# Download and install systemd service
curl -sSL https://raw.githubusercontent.com/Crashcart/tipistore/main/qbittorrent-monitor.service \
  -o /etc/systemd/system/qbittorrent-monitor.service

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable qbittorrent-monitor.service
sudo systemctl start qbittorrent-monitor.service
```

### Option 2: Manual Installation

```bash
# Clone the repository
git clone https://github.com/Crashcart/tipistore.git
cd tipistore

# Copy script
sudo cp qbittorrent-monitor.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/qbittorrent-monitor.sh

# Copy systemd service
sudo cp qbittorrent-monitor.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable qbittorrent-monitor.service
sudo systemctl start qbittorrent-monitor.service
```

## Usage

### Basic Daemon Mode (Default)

```bash
# Run with 5-minute check interval (default)
qbittorrent-monitor.sh -i 5m

# Run with 1-hour check interval
qbittorrent-monitor.sh -i 1h

# Runs in background automatically, returns PID
```

### Foreground Mode (Debugging)

```bash
# Run in foreground with verbose output
qbittorrent-monitor.sh -i 5m -f

# Useful for testing and debugging
```

### Full Configuration Example

```bash
qbittorrent-monitor.sh \
  -i 5m \                                  # Check every 5 minutes
  -U debian-qbittorrent \                  # Run qBittorrent as this user
  -d /mnt/qb-data \                        # Data directory (will check mount)
  -M /mnt/downloads \                      # Download directory (will check mount)
  -l /var/log/qbittorrent-monitor.log \    # Custom log file
  -w 85                                    # Warn when disk usage > 85%
```

## Command-Line Options

```
-i <time>        Check interval: 5m, 1h, 30m, etc (default: 5m)
-U <user>        System user running qbittorrent-nox (default: debian-qbittorrent)
-p <port>        qBittorrent port (default: 6881)
-d <path>        qBittorrent data directory (optional, checks if mounted)
-M <path>        Downloads directory (optional, checks if mounted)
-l <logfile>     Log file path (default: /var/log/qbittorrent-monitor.log)
-w <percent>     Disk space warning threshold (default: 90%)
-f               Run in foreground mode (default: daemon mode)
-h               Display help message
```

## Systemd Service Configuration

The included `qbittorrent-monitor.service` file provides:

```ini
[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/qbittorrent-monitor.sh -i 5m -U debian-qbittorrent -d /mnt/qb-data -M /mnt/downloads
Restart=on-failure
RestartSec=10
```

Modify `ExecStart` to customize the monitor behavior.

### Service Management

```bash
# Check status
sudo systemctl status qbittorrent-monitor.service

# View logs
sudo journalctl -u qbittorrent-monitor.service -f

# Restart
sudo systemctl restart qbittorrent-monitor.service

# Stop
sudo systemctl stop qbittorrent-monitor.service

# Disable
sudo systemctl disable qbittorrent-monitor.service
```

## Logging

Logs are written to `/var/log/qbittorrent-monitor.log` by default.

### Log Levels

```
[INFO]  - Normal operations and status
[WARN]  - Warnings (mount issues, high disk usage, restart attempts)
[ERROR] - Error conditions requiring attention
[DEBUG] - Debug information (process health checks)
```

### View Logs

```bash
# Real-time logs
tail -f /var/log/qbittorrent-monitor.log

# Last 50 entries
tail -50 /var/log/qbittorrent-monitor.log

# Filter by level
grep "ERROR" /var/log/qbittorrent-monitor.log
grep "WARN" /var/log/qbittorrent-monitor.log
```

## Examples

### Standard NAS Setup

```bash
qbittorrent-monitor.sh \
  -i 10m \
  -U debian-qbittorrent \
  -d /mnt/qb-data \
  -M /mnt/downloads \
  -w 85
```

### High-Frequency Monitoring

```bash
qbittorrent-monitor.sh \
  -i 1m \
  -U debian-qbittorrent \
  -d /data \
  -w 80
```

### Custom User and Path

```bash
qbittorrent-monitor.sh \
  -i 30m \
  -U qbittorrent \
  -d /opt/qb/data \
  -M /opt/qb/downloads \
  -l /custom/logs/qb-monitor.log
```

## Troubleshooting

### Script won't start

```bash
# Check if script is executable
ls -l /usr/local/bin/qbittorrent-monitor.sh

# Make executable if needed
sudo chmod +x /usr/local/bin/qbittorrent-monitor.sh

# Test in foreground mode
sudo /usr/local/bin/qbittorrent-monitor.sh -i 5m -f
```

### Mount checking failing

Ensure directories exist and are mounted:

```bash
# Check if mounted
mountpoint /mnt/qb-data
mountpoint /mnt/downloads

# Mount if needed
sudo mount <device> /mnt/qb-data
sudo mount <device> /mnt/downloads
```

### High memory usage warnings

The script warns if qBittorrent uses >1GB RAM. Check qBittorrent config or reduce active torrents.

### View daemon PID

When started as daemon, the PID is displayed. Also check:

```bash
ps aux | grep qbittorrent-monitor.sh
cat /var/run/qbittorrent-monitor.pid
```

## Requirements

- Bash 4.0+
- `pgrep` - Process grep utility
- `mountpoint` - Mount point checking utility
- `su` - User switching utility
- Linux/Unix-like system

## Security

- Runs as root in systemd service (to manage qBittorrent)
- Uses `su` to switch to qBittorrent user for process management
- PID file stored in `/var/run/`
- No network access required
- No external dependencies beyond standard Unix utilities

## License

See LICENSE file for details.

## Support

For issues or questions:
- Check the [GitHub Issues](https://github.com/Crashcart/tipistore/issues)
- Review logs: `tail -f /var/log/qbittorrent-monitor.log`
- Test in foreground mode: `-f` flag

## Contributing

Pull requests and suggestions welcome!
