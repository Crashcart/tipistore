"""qBittorrent Web API client with retries, re-auth, and reachability checks."""

import time
import requests
from typing import Dict, List, Any, Optional


class QBittorrentAPIClient:
    """Client for the qBittorrent Web API (v2)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        username: str = "",
        password: str = "",
        timeout: int = 10,
        retries: int = 3,
        logger=None,
    ):
        """Initialize API client.

        Args:
            host: API host.
            port: API port.
            username: API username (if auth required).
            password: API password (if auth required).
            timeout: Per-request timeout in seconds.
            retries: Number of attempts per request (>=1).
            logger: Optional logger.
        """
        self.base_url = f"http://{host}:{port}/api/v2"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retries = max(1, retries)
        self.logger = logger
        self.session = requests.Session()
        self._authenticated = False

        if username and password:
            self._authenticate()

    # ------------------------------------------------------------------ #
    # Auth + request plumbing
    # ------------------------------------------------------------------ #
    def _authenticate(self) -> bool:
        """Authenticate with the Web API. Returns True on success."""
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                data={"username": self.username, "password": self.password},
                timeout=self.timeout,
            )
            self._authenticated = response.status_code == 200 and response.text.strip() == "Ok."
            if not self._authenticated and self.logger:
                self.logger.error("qBittorrent API authentication failed")
            return self._authenticated
        except requests.RequestException as e:
            if self.logger:
                self.logger.debug(f"Authentication error: {e}")
            return False

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Optional[requests.Response]:
        """Perform an API request with retries, backoff, and re-auth.

        Args:
            method: "GET" or "POST".
            path: API path beginning with "/".
            params: Query parameters.
            data: Form body for POST.

        Returns:
            The Response on success (2xx), otherwise None.
        """
        url = f"{self.base_url}{path}"
        backoff = 1.0
        last_error = None

        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.request(
                    method, url, params=params, data=data, timeout=self.timeout
                )

                # Expired session -> re-auth once and retry immediately.
                if response.status_code == 403 and self.username and self.password:
                    if self.logger:
                        self.logger.info("Session expired (403); re-authenticating")
                    if self._authenticate():
                        continue

                if response.status_code == 200:
                    return response

                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as e:
                last_error = str(e)

            if attempt < self.retries:
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)

        if self.logger:
            self.logger.debug(f"{method} {path} failed after {self.retries} attempts: {last_error}")
        return None

    def is_reachable(self) -> bool:
        """Cheap liveness probe for the watchdog. Returns True if API responds."""
        try:
            response = self.session.get(f"{self.base_url}/app/version", timeout=self.timeout)
            return response.status_code in (200, 403)
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------ #
    # Read endpoints
    # ------------------------------------------------------------------ #
    def get_server_state(self) -> Optional[Dict[str, Any]]:
        """Get aggregate server stats (speeds, peers, DHT nodes)."""
        response = self._request("GET", "/sync/maindata")
        if response is None:
            return None
        try:
            data = response.json()
            return data.get("server_state", data)
        except ValueError:
            return None

    def get_version(self) -> Optional[str]:
        """Return the qBittorrent application version string, or None."""
        response = self._request("GET", "/app/version")
        return response.text.strip() if response is not None else None

    def get_torrents(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Return the list of torrents (optionally filtered)."""
        response = self._request("GET", "/torrents/info", params=filters or {})
        if response is None:
            return []
        try:
            return response.json()
        except ValueError:
            return []

    def get_trackers(self, torrent_hash: str) -> List[Dict[str, Any]]:
        """Return tracker entries for a torrent (status, msg, url)."""
        response = self._request("GET", "/torrents/trackers", params={"hash": torrent_hash})
        if response is None:
            return []
        try:
            return response.json()
        except ValueError:
            return []

    def get_preferences(self) -> Optional[Dict[str, Any]]:
        """Return qBittorrent preferences, or None on failure."""
        response = self._request("GET", "/app/preferences")
        if response is None:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    # ------------------------------------------------------------------ #
    # Write endpoints
    # ------------------------------------------------------------------ #
    def set_preferences(self, preferences: Dict[str, Any]) -> bool:
        """Apply a set of preference changes. Returns True on success."""
        import json

        response = self._request(
            "POST", "/app/setPreferences", data={"json": json.dumps(preferences)}
        )
        return response is not None

    def set_listen_port(self, port: int) -> bool:
        """Set the BitTorrent listen port (disables random_port)."""
        return self.set_preferences({"listen_port": int(port), "random_port": False})

    def pause_torrent(self, torrent_hash: str = "all") -> bool:
        """Pause a torrent (or 'all'). Returns True on success."""
        response = self._request("POST", "/torrents/pause", data={"hashes": torrent_hash})
        return response is not None

    def resume_torrent(self, torrent_hash: str = "all") -> bool:
        """Resume a torrent (or 'all'). Returns True on success."""
        response = self._request("POST", "/torrents/resume", data={"hashes": torrent_hash})
        return response is not None

    def reannounce_all(self) -> bool:
        """Force a tracker re-announce on all torrents (peer refresh)."""
        response = self._request("POST", "/torrents/reannounce", data={"hashes": "all"})
        return response is not None

    def recheck_torrent(self, torrent_hash: str) -> bool:
        """Force a hash recheck of a torrent. Returns True on success."""
        response = self._request("POST", "/torrents/recheck", data={"hashes": torrent_hash})
        return response is not None
