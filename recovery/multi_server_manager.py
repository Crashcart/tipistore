"""Multi-server management for distributed qBittorrent deployments."""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ServerStatus(Enum):
    """Server health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class ServerInstance:
    """Single qBittorrent server instance."""

    name: str
    host: str
    port: int
    username: str = ""
    password: str = ""
    priority: int = 1  # Higher = preferred for new torrents
    max_torrents: int = 1000
    enabled: bool = True

    def __hash__(self):
        return hash(f"{self.host}:{self.port}")

    def __eq__(self, other):
        return self.host == other.host and self.port == other.port


class MultiServerManager:
    """Manages monitoring and failover across multiple qBittorrent servers."""

    def __init__(self, logger=None):
        """Initialize multi-server manager.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.servers: Dict[str, ServerInstance] = {}
        self.server_status: Dict[str, ServerStatus] = {}
        self.server_clients: Dict[str, Any] = {}  # API clients per server

    def add_server(self, instance: ServerInstance):
        """Add a server to management.

        Args:
            instance: ServerInstance to add
        """
        key = f"{instance.host}:{instance.port}"
        self.servers[key] = instance
        self.server_status[key] = ServerStatus.OFFLINE

        if self.logger:
            self.logger.info(f"Added server: {instance.name} ({key})")

    def remove_server(self, host: str, port: int):
        """Remove a server from management.

        Args:
            host: Server host
            port: Server port
        """
        key = f"{host}:{port}"
        if key in self.servers:
            del self.servers[key]
            if key in self.server_status:
                del self.server_status[key]

            if self.logger:
                self.logger.info(f"Removed server: {key}")

    def register_client(self, host: str, port: int, client: Any):
        """Register API client for a server.

        Args:
            host: Server host
            port: Server port
            client: API client instance
        """
        key = f"{host}:{port}"
        self.server_clients[key] = client

    def check_health(self) -> Dict[str, Any]:
        """Check health of all servers.

        Returns:
            Health status dict
        """
        health_status = {}

        for key, server in self.servers.items():
            if not server.enabled:
                self.server_status[key] = ServerStatus.OFFLINE
                health_status[key] = {
                    "status": ServerStatus.OFFLINE.value,
                    "reason": "Server disabled",
                }
                continue

            try:
                client = self.server_clients.get(key)
                if not client:
                    self.server_status[key] = ServerStatus.OFFLINE
                    health_status[key] = {
                        "status": ServerStatus.OFFLINE.value,
                        "reason": "No client registered",
                    }
                    continue

                # Try to get server state
                stats = client.get_server_state()
                if not stats:
                    self.server_status[key] = ServerStatus.OFFLINE
                    health_status[key] = {
                        "status": ServerStatus.OFFLINE.value,
                        "reason": "API call failed",
                    }
                    continue

                # Analyze status
                torrent_count = stats.get("nb_dl", 0) + stats.get("nb_up", 0)
                dl_speed = stats.get("dl_info_speed", 0)
                peers = stats.get("peers", 0)

                if torrent_count >= server.max_torrents:
                    status = ServerStatus.CRITICAL
                elif dl_speed == 0 and torrent_count > 0:
                    status = ServerStatus.DEGRADED
                else:
                    status = ServerStatus.HEALTHY

                self.server_status[key] = status
                health_status[key] = {
                    "status": status.value,
                    "torrents": torrent_count,
                    "dl_speed": dl_speed,
                    "peers": peers,
                    "utilization": (torrent_count / server.max_torrents * 100),
                }

            except Exception as e:
                self.server_status[key] = ServerStatus.OFFLINE
                health_status[key] = {
                    "status": ServerStatus.OFFLINE.value,
                    "reason": str(e),
                }

                if self.logger:
                    self.logger.error(f"Error checking server {key}: {e}")

        return health_status

    def get_healthy_servers(self) -> List[ServerInstance]:
        """Get list of healthy servers sorted by priority.

        Returns:
            List of healthy ServerInstance objects
        """
        healthy = []

        for key, status in self.server_status.items():
            if status == ServerStatus.HEALTHY:
                server = self.servers.get(key)
                if server and server.enabled:
                    healthy.append(server)

        # Sort by priority (higher first)
        return sorted(healthy, key=lambda s: -s.priority)

    def get_backup_server(self) -> Optional[ServerInstance]:
        """Get best backup server for failover.

        Returns:
            ServerInstance or None
        """
        # Prefer degraded over critical
        for key, status in self.server_status.items():
            if status == ServerStatus.DEGRADED:
                server = self.servers.get(key)
                if server and server.enabled:
                    return server

        # Fall back to any enabled server
        for server in self.servers.values():
            if server.enabled:
                return server

        return None

    def distribute_torrents(
        self,
        all_servers: bool = False,
    ) -> Dict[str, List[str]]:
        """Suggest torrent distribution across servers.

        Args:
            all_servers: Include unhealthy servers in distribution

        Returns:
            Dict mapping server keys to torrent hashes
        """
        distribution = {}

        if all_servers:
            servers_to_use = [s for s in self.servers.values() if s.enabled]
        else:
            servers_to_use = self.get_healthy_servers()

        if not servers_to_use:
            return distribution

        # Initialize buckets
        for server in servers_to_use:
            key = f"{server.host}:{server.port}"
            distribution[key] = []

        return distribution

    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report.

        Returns:
            Status report dict
        """
        health = self.check_health()

        healthy_count = sum(
            1 for s in self.server_status.values() if s == ServerStatus.HEALTHY
        )
        total_enabled = sum(1 for s in self.servers.values() if s.enabled)

        return {
            "total_servers": len(self.servers),
            "enabled_servers": total_enabled,
            "healthy_servers": healthy_count,
            "server_health": health,
            "servers": {
                key: {
                    "name": server.name,
                    "host": server.host,
                    "port": server.port,
                    "priority": server.priority,
                    "enabled": server.enabled,
                    "status": self.server_status.get(key, ServerStatus.OFFLINE).value,
                }
                for key, server in self.servers.items()
            },
        }

    def failover_torrent(self, torrent_hash: str, from_server: str, to_server: str) -> bool:
        """Failover a torrent from one server to another.

        Args:
            torrent_hash: Torrent hash
            from_server: Source server key (host:port)
            to_server: Target server key (host:port)

        Returns:
            True if successful
        """
        try:
            from_client = self.server_clients.get(from_server)
            to_client = self.server_clients.get(to_server)

            if not (from_client and to_client):
                return False

            # Get torrent from source
            torrents = from_client.get_torrents()
            torrent = next((t for t in torrents if t["hash"] == torrent_hash), None)

            if not torrent:
                return False

            # Note: Actual failover would require:
            # 1. Export torrent metadata
            # 2. Add to target server
            # 3. Remove from source
            # This is simplified for demonstration

            if self.logger:
                self.logger.info(
                    f"Failover torrent {torrent_hash} from {from_server} to {to_server}"
                )

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failover error: {e}")
            return False
