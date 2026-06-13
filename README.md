# qBittorrent Intelligent Recovery Agent

A monitoring and self-healing daemon for **qbittorrent-nox**. It detects when
qBittorrent has crashed, hit a storage problem, or degraded into lag, and
applies recovery automatically — while preserving your existing configuration.
qBittorrent keeps running "as if you ran it yourself."

## What it does

### Reliability & self-healing
- **Crash watchdog** — if the `qbittorrent-nox` process dies or its Web API stops
  responding, the agent restarts it (via `systemctl`), with a restart cap and
  cooldown so it never loops. Hitting the cap raises a CRITICAL alert instead.
- **Disk / mount safety** — guards your save paths. If a disk fills up or a mount
  disappears (e.g. a slow-to-mount NAS), it pauses torrents *before* they error
  and resumes them automatically once storage recovers.
- **API resilience** — retries with backoff and re-authenticates on an expired
  session, so a transient hiccup isn't mistaken for "healthy."
- **Wait-for-mount gate** — on startup, optionally wait until watched mounts are
  present and writable before doing anything.

### Detection (multi-factor lag score, 0–100)
Performance (speeds, peers, DHT), system health (CPU, memory), configuration,
**qBittorrent log parsing** (I/O errors, "too many open files", tracker errors),
and a rolling **trend analysis**. A **predictive analyzer** warns before lag
fully sets in.

### Recovery (escalating, least-invasive first)
1. **Connection cleanup** — force tracker re-announce to refresh peers
2. **DHT refresh** — toggle DHT off/on to re-bootstrap
3. **Reload config**
4. **Dynamic limits** — retune connection/bandwidth limits to system capacity
5. **Torrent refresh** — pause/resume to reset per-torrent state
6. **Restart** — graceful drain, then `systemctl restart` (last resort)

### Visibility & alerting
- **Status server** (stdlib HTTP): `/health` (for systemd/Docker healthchecks),
  `/status` (JSON snapshot), `/metrics` (Prometheus).
- **SQLite history** of samples and events.
- **Notifications** via webhook, syslog, or email.

### Maintenance / throttled hours
Define a maintenance window (e.g. `22:00-06:00`). During it the agent pauses
downloads and stops actively recovering; **when the window ends it resumes
downloading automatically.** A manual `--maintenance` mode is also available.

### Ports
Optionally randomize the **BitTorrent listen port** (and outgoing port range) to
evade port-based ISP throttling — at every startup, on a timer, once, or on
detected throttling. Reachability is verified after each change. **The WebUI/API
port is never randomized.**

### Other checks
Tracker health (all-trackers-down / "unregistered"), hash-fail / corruption
watch, optional auto-pause of confirmed-dead torrents, and a WebUI security
warning (default credentials, public bind, auth bypass).

## Installation

```bash
git clone <your-repo-url> qbittorrent-agent
cd qbittorrent-agent
pip install -r requirements.txt    # requests + psutil (everything else is stdlib)
```

Requires Python 3.8+ and qbittorrent-nox with the Web API enabled.

## Configuration

The agent keeps its **own config file next to `qBittorrent.conf`**
(`~/.config/qBittorrent/qbittorrent-agent.conf` by default). It is generated on
first run. **Any value you pass on the command line is written back and
remembered**, so you only need a flag once.

Precedence: CLI flag (this run) → saved config file → built-in default.

Edit it interactively with the built-in text GUI:

```bash
./qbittorrent_agent.py --configure
```

Or set values via flags (which persist):

```bash
./qbittorrent_agent.py --status-port 9000 --sensitivity aggressive
```

## Usage

```bash
# Default: reads ~/.config/qBittorrent/qBittorrent.conf, balanced sensitivity
./qbittorrent_agent.py

# Custom qBittorrent config location
./qbittorrent_agent.py --qbt-config /mnt/nas/qBittorrent/qBittorrent.conf

# See exactly what it would do, changing nothing
./qbittorrent_agent.py --dry-run --log-level DEBUG

# Throttled hours: pause downloads 22:00–06:00, resume after
./qbittorrent_agent.py --maintenance-window 22:00-06:00

# Guard a NAS mount and randomize the listen port on each start
./qbittorrent_agent.py --watch-mount /mnt/nas/downloads --random-port

# Alerts to a webhook
./qbittorrent_agent.py --notify-webhook https://hooks.example.com/xyz
```

### Key options

| Flag | Meaning |
|------|---------|
| `--qbt-config PATH` | qBittorrent.conf path (default `~/.config/qBittorrent/qBittorrent.conf`) |
| `--config PATH` | Agent config path (default: next to qBittorrent.conf) |
| `--configure` | Open the text-GUI config screen and exit |
| `--interval N` | Monitoring interval, seconds (default 60) |
| `--sensitivity` | `aggressive` / `balanced` / `conservative` |
| `--dry-run` | Log intended actions without making changes |
| `--maintenance` / `--maintenance-window 22:00-06:00` | Manual / scheduled maintenance |
| `--no-watchdog` / `--max-restarts N` / `--restart-cooldown S` | Crash watchdog |
| `--watch-mount PATH` (repeatable) / `--min-free-gb N` / `--wait-for-mount` | Storage guard |
| `--random-port` / `--random-port-mode` / `--random-port-range LOW-HIGH` | Port randomization |
| `--status-port N` (0 disables) / `--status-bind ADDR` | Status server |
| `--notify-webhook` / `--notify-syslog` / `--notify-email-*` | Alerts |
| `--state-db PATH` (`none` disables) | SQLite history |

Run `./qbittorrent_agent.py --help` for the complete list.

## Status endpoints

```bash
curl http://127.0.0.1:8081/health     # 200 healthy / 503 unhealthy
curl http://127.0.0.1:8081/status     # JSON snapshot
curl http://127.0.0.1:8081/metrics    # Prometheus text
```

## systemd service

```ini
[Unit]
Description=qBittorrent Intelligent Recovery Agent
After=network-online.target qbittorrent-nox.service
Wants=network-online.target

[Service]
Type=simple
User=debian-qbittorrent
ExecStart=/opt/qbittorrent-agent/qbittorrent_agent.py --interval 60 --sensitivity balanced
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now qbittorrent-agent
```

## Architecture

```
qbittorrent_agent.py          Entry point, CLI, monitor loop
qbt_api/
  agent_config.py             Self-generating, persisted INI config
  api_client.py               Web API client (retry, re-auth, reachability)
  config_manager.py           Reads qBittorrent.conf
detectors/
  lag_detector.py             Multi-factor lag score (incl. log parsing)
  predictive_analyzer.py      Early-warning trend analysis
  torrent_health.py           Per-torrent health scoring
recovery/
  recovery_engine.py          Escalating real recovery strategies + restart
  bandwidth_optimizer.py      Dynamic bandwidth limits
  connection_optimizer.py     Dynamic connection limits
  backup_restore.py           State snapshots + conf backups
monitoring/
  process_watchdog.py         Crash detection
  storage_monitor.py          Disk/mount safety + wait-for-mount
  maintenance.py              Scheduled/manual maintenance (pause/resume)
  scheduler.py                Maintenance-window time logic
  port_manager.py             Random listen/outgoing ports + verification
  health_checks.py            Tracker health, hash-fail, WebUI security
  status_server.py            /health, /status, /metrics + AgentState
  history_store.py            SQLite samples/events
  metrics.py                  System metrics (psutil)
  prometheus_exporter.py      Prometheus formatting
agent_logging/
  agent_logger.py             Rotating logger
  notification_system.py      Email / webhook / syslog
tui/
  config_tui.py               Curses configuration screen
```

## Safety

- `--dry-run` gates every mutating action (restart, pause/resume, preference changes).
- The agent backs up `qBittorrent.conf` before applying preference changes.
- It never randomizes or changes the WebUI/API port.
- The config file is written `chmod 600` (it can hold credentials); use
  `--no-save-secrets` to keep passwords out of the file.

## Testing

```bash
python3 -m unittest discover tests
```

## Future work (not yet implemented)

VPN-interface kill-switch, outbound IP-leak check, disk-aware pre-emptive
throttling, Discord/Telegram/ntfy notifiers, and force-encryption anti-throttle
tuning.
