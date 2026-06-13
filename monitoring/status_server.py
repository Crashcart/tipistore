"""Lightweight status/health HTTP server (stdlib only).

Exposes /health (for systemd/Docker healthchecks), /status (JSON snapshot), and
/metrics (Prometheus text). Reads a shared, lock-guarded AgentState that the
main loop updates each cycle, so serving a request never triggers extra work.
"""

import json
import threading
import time
from dataclasses import dataclass, field, fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional


@dataclass
class AgentState:
    """Thread-safe snapshot of the agent's current view of the world."""

    started_at: float = field(default_factory=time.time)
    last_update: float = 0.0
    qbt_running: bool = False
    qbt_responsive: bool = False
    lag_score: float = 0.0
    issues: List[str] = field(default_factory=list)
    predicted_score: float = 0.0
    dl_speed: int = 0
    up_speed: int = 0
    peers: int = 0
    dht: int = 0
    cpu: float = 0.0
    mem: float = 0.0
    listen_port: int = 0
    storage_paused: bool = False
    disk_issues: List[Dict[str, Any]] = field(default_factory=list)
    dead_torrents: int = 0
    restarts: int = 0
    recovery_count: int = 0
    maintenance: bool = False
    last_event: str = ""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def update(self, **kwargs):
        """Atomically update fields and bump last_update."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key) and not key.startswith("_"):
                    setattr(self, key, value)
            self.last_update = time.time()

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable copy of the state."""
        with self._lock:
            data = {}
            for f in fields(self):
                if f.name.startswith("_"):
                    continue
                value = getattr(self, f.name)
                data[f.name] = list(value) if isinstance(value, list) else value
        data["uptime_seconds"] = round(time.time() - data["started_at"], 1)
        return data

    def is_healthy(self) -> bool:
        """Healthy = qBittorrent running and responsive (or in maintenance)."""
        with self._lock:
            if self.maintenance:
                return True
            return self.qbt_running and self.qbt_responsive


def _prometheus_text(snap: Dict[str, Any]) -> str:
    """Render a state snapshot as Prometheus exposition text."""
    metrics = {
        "qbittorrent_lag_score": snap["lag_score"],
        "qbittorrent_predicted_score": snap["predicted_score"],
        "qbittorrent_download_speed": snap["dl_speed"],
        "qbittorrent_upload_speed": snap["up_speed"],
        "qbittorrent_peers_connected": snap["peers"],
        "qbittorrent_dht_nodes": snap["dht"],
        "qbittorrent_listen_port": snap["listen_port"],
        "qbittorrent_running": int(snap["qbt_running"]),
        "qbittorrent_responsive": int(snap["qbt_responsive"]),
        "qbittorrent_storage_paused": int(snap["storage_paused"]),
        "qbittorrent_dead_torrents": snap["dead_torrents"],
        "qbittorrent_restarts_total": snap["restarts"],
        "qbittorrent_recovery_total": snap["recovery_count"],
        "qbittorrent_maintenance": int(snap["maintenance"]),
        "system_cpu_percent": snap["cpu"],
        "system_memory_percent": snap["mem"],
        "agent_uptime_seconds": snap["uptime_seconds"],
    }
    lines = []
    for name, value in metrics.items():
        lines.append(f"{name} {value}")
    return "\n".join(lines) + "\n"


class _Handler(BaseHTTPRequestHandler):
    state: Optional[AgentState] = None  # injected by StatusServer

    def _send(self, code: int, body: str, content_type: str):
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):  # noqa: N802 (http.server API)
        state = type(self).state
        if state is None:
            self._send(503, "no state\n", "text/plain")
            return

        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        if path == "/health":
            healthy = state.is_healthy()
            self._send(
                200 if healthy else 503,
                json.dumps({"status": "ok" if healthy else "unhealthy"}) + "\n",
                "application/json",
            )
        elif path in ("/status", "/"):
            self._send(200, json.dumps(state.snapshot(), indent=2) + "\n", "application/json")
        elif path == "/metrics":
            self._send(200, _prometheus_text(state.snapshot()), "text/plain; version=0.0.4")
        else:
            self._send(404, "not found\n", "text/plain")

    def log_message(self, *args):  # silence default stderr logging
        return


class StatusServer:
    """Runs the status HTTP server in a background daemon thread."""

    def __init__(self, state: AgentState, bind: str = "127.0.0.1", port: int = 8081, logger=None):
        """Initialize the status server.

        Args:
            state: Shared AgentState to serve.
            bind: Bind address.
            port: TCP port (0 disables; caller should not start in that case).
            logger: Optional logger.
        """
        self.state = state
        self.bind = bind
        self.port = port
        self.logger = logger
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Start serving. Returns True if the server bound successfully."""
        if self.port == 0:
            return False
        handler = type("BoundHandler", (_Handler,), {"state": self.state})
        try:
            self._httpd = ThreadingHTTPServer((self.bind, self.port), handler)
        except OSError as e:
            if self.logger:
                self.logger.error(f"Status server failed to bind {self.bind}:{self.port}: {e}")
            return False
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        if self.logger:
            self.logger.info(f"Status server listening on http://{self.bind}:{self.port}")
        return True

    def stop(self):
        """Stop the server and join its thread."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
