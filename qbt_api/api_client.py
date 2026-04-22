"""qBittorrent Web API client."""

import requests
from typing import Dict, List, Any, Optional


class QBittorrentAPIClient:
    """Client for qBittorrent Web API."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        username: str = "",
        password: str = "",
    ):
        """Initialize API client.

        Args:
            host: API host
            port: API port
            username: API username (if auth required)
            password: API password (if auth required)
        """
        self.base_url = f"http://{host}:{port}/api/v2"
        self.username = username
        self.password = password
        self.session = requests.Session()

        # Try to authenticate if credentials provided
        if username and password:
            self._authenticate()

    def _authenticate(self) -> bool:
        """Authenticate with qBittorrent API.

        Returns:
            True if authentication successful
        """
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                data={"username": self.username, "password": self.password},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_server_state(self) -> Optional[Dict[str, Any]]:
        """Get server state/stats.

        Returns:
            Server state dict or None
        """
        try:
            response = self.session.get(f"{self.base_url}/app/webapiVersion", timeout=5)
            if response.status_code != 200:
                return None

            # Get full stats
            response = self.session.get(f"{self.base_url}/app/serverState", timeout=5)
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    def get_torrents(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Get list of torrents.

        Args:
            filters: Optional filter dict

        Returns:
            List of torrent dicts
        """
        try:
            params = filters or {}
            response = self.session.get(
                f"{self.base_url}/torrents/info",
                params=params,
                timeout=5,
            )
            return response.json() if response.status_code == 200 else []
        except Exception:
            return []

    def pause_torrent(self, torrent_hash: str) -> bool:
        """Pause a torrent.

        Args:
            torrent_hash: Torrent hash

        Returns:
            True if successful
        """
        try:
            response = self.session.post(
                f"{self.base_url}/torrents/pause",
                data={"hashes": torrent_hash},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    def resume_torrent(self, torrent_hash: str) -> bool:
        """Resume a torrent.

        Args:
            torrent_hash: Torrent hash

        Returns:
            True if successful
        """
        try:
            response = self.session.post(
                f"{self.base_url}/torrents/resume",
                data={"hashes": torrent_hash},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    def purge_all_cache(self) -> bool:
        """Purge all cache.

        Returns:
            True if successful
        """
        try:
            response = self.session.post(
                f"{self.base_url}/torrents/toggleFirstLastPiecePrio",
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_preferences(self) -> Optional[Dict[str, Any]]:
        """Get qBittorrent preferences.

        Returns:
            Preferences dict or None
        """
        try:
            response = self.session.get(
                f"{self.base_url}/app/preferences",
                timeout=5,
            )
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    def set_preferences(self, preferences: Dict[str, Any]) -> bool:
        """Set qBittorrent preferences.

        Args:
            preferences: Preferences dict

        Returns:
            True if successful
        """
        try:
            response = self.session.post(
                f"{self.base_url}/app/setPreferences",
                json={"json": preferences},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False
