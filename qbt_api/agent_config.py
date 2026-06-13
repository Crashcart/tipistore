"""Agent configuration file: auto-generated, persisted, CLI-overridable.

The agent keeps its own INI config file (separate from qBittorrent.conf) in the
same directory as the qBittorrent config. Values set on the command line are
written back so they are remembered on the next run.

Precedence: CLI flag (this run) > saved config file > built-in default.
"""

import os
import stat
import configparser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# Schema: section -> key -> (default, type, comment)
# type is one of: "str", "int", "float", "bool", "list" (comma-separated)
SCHEMA: Dict[str, Dict[str, Tuple[Any, str, str]]] = {
    "agent": {
        "interval": (60, "int", "Monitoring interval in seconds"),
        "sensitivity": ("balanced", "str", "Lag sensitivity: aggressive/balanced/conservative"),
        "log_level": ("INFO", "str", "DEBUG/INFO/WARNING/ERROR"),
        "log_file": ("/var/log/qbittorrent-agent.log", "str", "Log file path"),
        "dry_run": (False, "bool", "Log intended actions without making changes"),
        "maintenance": (False, "bool", "Start in maintenance mode (monitoring paused)"),
        "state_db": ("/var/lib/qbittorrent-agent/state.db", "str", "SQLite history DB ('none' disables)"),
    },
    "qbittorrent": {
        "host": ("127.0.0.1", "str", "qBittorrent Web API host"),
        "port": (8080, "int", "qBittorrent Web API port (NEVER randomized)"),
        "username": ("", "str", "Web API username"),
        "password": ("", "str", "Web API password"),
        "service_name": ("qbittorrent-nox", "str", "systemd service name for restarts"),
        "qbt_log": ("", "str", "qBittorrent log path ('' = auto-detect)"),
        "api_timeout": (10, "int", "Per-request timeout in seconds"),
        "api_retries": (3, "int", "Number of API retry attempts"),
    },
    "detection": {
        "qbt_log_scan": (True, "bool", "Parse qBittorrent logs for errors"),
    },
    "schedule": {
        "maintenance_window": ("", "str", "Auto maintenance during throttled hours, e.g. '22:00-06:00' (comma-separate multiple)"),
        "pause_during_maintenance": (True, "bool", "Pause torrents during maintenance; resume when it ends"),
    },
    "recovery": {
        "no_watchdog": (False, "bool", "Disable process crash watchdog"),
        "max_restarts": (3, "int", "Max restarts before requiring manual intervention"),
        "restart_cooldown": (300, "int", "Cooldown window for restart counting (seconds)"),
        "unresponsive_cycles": (2, "int", "Consecutive unresponsive cycles before restart"),
        "drain_timeout": (15, "int", "Seconds to drain torrents before restart (5g)"),
        "auto_pause_dead": (False, "bool", "Pause confirmed-dead torrents"),
    },
    "storage": {
        "no_disk_guard": (False, "bool", "Disable disk/mount safety checks"),
        "watch_mount": ([], "list", "Mount points to guard (comma-separated)"),
        "min_free_gb": (5.0, "float", "Pause torrents below this free space (GB)"),
        "min_free_percent": (2.0, "float", "Pause torrents below this free space (%)"),
        "wait_for_mount": (False, "bool", "Wait for mounts before starting (5m)"),
        "mount_wait_timeout": (120, "int", "Max seconds to wait for mounts"),
    },
    "ports": {
        "random_port": (False, "bool", "Randomize the BitTorrent listen port (5a)"),
        "random_port_mode": ("startup", "str", "startup/interval/once/on-throttle"),
        "random_port_range": ("49152-65535", "str", "Listen port range LOW-HIGH"),
        "random_port_interval": (86400, "int", "Seconds between rotations (interval mode)"),
        "random_outgoing_ports": (True, "bool", "Also randomize outgoing port range"),
        "verify_port": (True, "bool", "Verify port reachability after change (5d)"),
        "random_status_port": (False, "bool", "Randomize the agent status-server port"),
    },
    "status": {
        "status_port": (8081, "int", "Agent status/health HTTP port (0 disables)"),
        "status_bind": ("127.0.0.1", "str", "Status server bind address"),
    },
    "notifications": {
        "notify_level": ("WARNING", "str", "Min level to send: DEBUG/INFO/WARNING/CRITICAL"),
        "notify_webhook": ("", "str", "Webhook URL"),
        "notify_syslog": ("", "str", "Syslog facility (e.g. local0); '' disables"),
        "notify_email_smtp": ("", "str", "SMTP server"),
        "notify_email_port": (587, "int", "SMTP port"),
        "notify_email_from": ("", "str", "Sender email"),
        "notify_email_password": ("", "str", "SMTP password (secret)"),
        "notify_email_to": ([], "list", "Recipient emails (comma-separated)"),
    },
}

# Keys whose values are secrets (masked / can be excluded from disk)
SECRET_KEYS = {("qbittorrent", "password"), ("notifications", "notify_email_password")}


def _coerce(value: Any, type_name: str) -> Any:
    """Coerce a raw string/value to the declared type."""
    if type_name == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if type_name == "int":
        return int(value)
    if type_name == "float":
        return float(value)
    if type_name == "list":
        if isinstance(value, list):
            return value
        return [v.strip() for v in str(value).split(",") if v.strip()]
    return str(value)


def _to_ini(value: Any, type_name: str) -> str:
    """Serialize a typed value to its INI string form."""
    if type_name == "bool":
        return "true" if value else "false"
    if type_name == "list":
        return ",".join(str(v) for v in (value or []))
    return str(value)


class AgentConfig:
    """Loads, merges, and persists the agent's INI configuration."""

    DEFAULT_FILENAME = "qbittorrent-agent.conf"

    def __init__(self, config_path: str, logger=None):
        """Initialize and load configuration from ``config_path``.

        Args:
            config_path: Path to the agent config file.
            logger: Optional logger.
        """
        self.config_path = config_path
        self.logger = logger
        self.values: Dict[str, Dict[str, Any]] = self._defaults()
        self._loaded_from_file = False
        self._load()

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def resolve_path(qbt_config_path: str, override: Optional[str] = None) -> str:
        """Resolve the agent config path.

        By default it sits next to the qBittorrent config file.

        Args:
            qbt_config_path: Path to qBittorrent.conf (used to derive the dir).
            override: Explicit ``--config`` path, if provided.

        Returns:
            Absolute path to the agent config file.
        """
        if override:
            return str(Path(override).expanduser())
        qbt_dir = Path(qbt_config_path).expanduser().parent
        return str(qbt_dir / AgentConfig.DEFAULT_FILENAME)

    @staticmethod
    def _defaults() -> Dict[str, Dict[str, Any]]:
        return {
            section: {key: spec[0] for key, spec in keys.items()}
            for section, keys in SCHEMA.items()
        }

    # ------------------------------------------------------------------ #
    # Load / save
    # ------------------------------------------------------------------ #
    def _load(self):
        """Load values from the config file if it exists."""
        if not os.path.exists(self.config_path):
            return

        parser = configparser.ConfigParser()
        try:
            parser.read(self.config_path)
        except configparser.Error as e:
            if self.logger:
                self.logger.error(f"Failed to parse {self.config_path}: {e}")
            return

        for section in SCHEMA:
            if not parser.has_section(section):
                continue
            for key, (_default, type_name, _comment) in SCHEMA[section].items():
                if parser.has_option(section, key):
                    raw = parser.get(section, key)
                    try:
                        self.values[section][key] = _coerce(raw, type_name)
                    except (ValueError, TypeError):
                        if self.logger:
                            self.logger.warning(
                                f"Invalid value for [{section}] {key} in config; using default"
                            )

        self._loaded_from_file = True
        self._warn_if_world_readable()

    def apply_overrides(self, overrides: Dict[Tuple[str, str], Any]):
        """Apply CLI-provided overrides (only non-None values).

        Args:
            overrides: Mapping of (section, key) -> value. ``None`` values are
                ignored so unspecified flags fall back to file/default.
        """
        for (section, key), value in overrides.items():
            if value is None:
                continue
            if section in SCHEMA and key in SCHEMA[section]:
                type_name = SCHEMA[section][key][1]
                self.values[section][key] = _coerce(value, type_name)

    def save(self, include_secrets: bool = True):
        """Write the merged configuration back to disk.

        Args:
            include_secrets: If False, secret keys are written empty.
        """
        parser = configparser.ConfigParser()

        for section, keys in SCHEMA.items():
            parser.add_section(section)
            for key, (_default, type_name, _comment) in keys.items():
                value = self.values[section][key]
                if not include_secrets and (section, key) in SECRET_KEYS:
                    value = ""
                parser.set(section, key, _to_ini(value, type_name))

        directory = os.path.dirname(self.config_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # Write a commented header, then the parsed body.
        try:
            with open(self.config_path, "w") as f:
                f.write("# qBittorrent Agent configuration\n")
                f.write("# Auto-generated; edit values or use --configure (text GUI).\n")
                f.write("# CLI flags override these values and are saved back here.\n\n")
                self._write_with_comments(f, parser)
            # Tighten permissions since secrets may be present.
            os.chmod(self.config_path, stat.S_IRUSR | stat.S_IWUSR)
            if self.logger:
                self.logger.info(f"Saved agent config to {self.config_path}")
        except OSError as e:
            if self.logger:
                self.logger.error(f"Failed to write config {self.config_path}: {e}")

    def _write_with_comments(self, f, parser: configparser.ConfigParser):
        """Write the INI body with an inline comment above each key."""
        for section in parser.sections():
            f.write(f"[{section}]\n")
            for key, value in parser.items(section):
                comment = SCHEMA.get(section, {}).get(key, (None, None, ""))[2]
                if comment:
                    f.write(f"# {comment}\n")
                f.write(f"{key} = {value}\n")
            f.write("\n")

    def ensure_exists(self, include_secrets: bool = True):
        """Create the config file with current values if it does not exist."""
        if not os.path.exists(self.config_path):
            self.save(include_secrets=include_secrets)
            if self.logger:
                self.logger.info(f"Generated default agent config at {self.config_path}")

    def _warn_if_world_readable(self):
        """Warn if the config file is group/world readable (secrets at risk)."""
        try:
            mode = os.stat(self.config_path).st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                if self.logger:
                    self.logger.warning(
                        f"{self.config_path} is group/world-readable but may hold "
                        f"secrets; consider 'chmod 600' or use --no-save-secrets"
                    )
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #
    def get(self, section: str, key: str) -> Any:
        """Get a resolved configuration value."""
        return self.values.get(section, {}).get(key)

    def set(self, section: str, key: str, value: Any):
        """Set a value (coerced to its declared type)."""
        if section in SCHEMA and key in SCHEMA[section]:
            type_name = SCHEMA[section][key][1]
            self.values[section][key] = _coerce(value, type_name)

    def section(self, section: str) -> Dict[str, Any]:
        """Return a copy of all values in a section."""
        return dict(self.values.get(section, {}))

    def as_dict(self) -> Dict[str, Dict[str, Any]]:
        """Return the full resolved configuration."""
        return {section: dict(keys) for section, keys in self.values.items()}
