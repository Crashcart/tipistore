"""qBittorrent configuration manager."""

import configparser
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigManager:
    """Manages qBittorrent configuration."""

    def __init__(self, config_path: str):
        """Initialize config manager.

        Args:
            config_path: Path to qBittorrent config file
        """
        self.config_path = Path(config_path)
        self.config = configparser.ConfigParser()
        self.reload()

    def reload(self):
        """Reload configuration from file."""
        if self.config_path.exists():
            self.config.read(self.config_path)

    def get_config(self) -> Dict[str, Dict[str, Any]]:
        """Get configuration as nested dict.

        Returns:
            Configuration dict
        """
        result = {}
        for section in self.config.sections():
            result[section] = dict(self.config.items(section))
        return result

    def get_value(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            section: Config section
            key: Config key
            default: Default value if not found

        Returns:
            Configuration value
        """
        try:
            return self.config.get(section, key)
        except configparser.NoOptionError:
            return default

    def get_section(self, section: str) -> Optional[Dict[str, str]]:
        """Get a configuration section.

        Args:
            section: Config section name

        Returns:
            Section dict or None
        """
        try:
            return dict(self.config.items(section))
        except configparser.NoSectionError:
            return None

    def get_network_config(self) -> Dict[str, Any]:
        """Get network configuration.

        Returns:
            Network config dict
        """
        network = self.get_section("BitTorrent") or {}
        return {
            "port": int(network.get("Port", 6881)),
            "upnp": network.get("Upnp", "true").lower() == "true",
            "max_connections": int(network.get("MaxConnections", 500)),
            "max_peers": int(network.get("MaxPeers", 200)),
        }

    def get_transfer_config(self) -> Dict[str, Any]:
        """Get transfer configuration.

        Returns:
            Transfer config dict
        """
        transfer = self.get_section("Preferences") or {}
        return {
            "max_dl_speed": int(transfer.get("GlobalMaxDlSpeed", 0)),
            "max_ul_speed": int(transfer.get("GlobalMaxUpSpeed", 0)),
            "max_active_downloads": int(transfer.get("MaxActiveDownloads", 3)),
            "max_active_torrents": int(transfer.get("MaxActiveTorrents", 5)),
        }
