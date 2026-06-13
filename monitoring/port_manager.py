"""Randomized / rotating BitTorrent ports (5a) and reachability checks (5d).

Randomizes the qBittorrent *incoming listen port* and (by default) the
libtorrent *outgoing port range* to help evade port-based ISP throttling. Never
touches the WebUI/API port.
"""

import random
import socket
import time
from typing import Optional, Tuple


def parse_range(spec: str, default: Tuple[int, int] = (49152, 65535)) -> Tuple[int, int]:
    """Parse a 'LOW-HIGH' port range string, falling back to a default."""
    try:
        low_str, high_str = str(spec).split("-", 1)
        low, high = int(low_str), int(high_str)
        if 1024 <= low < high <= 65535:
            return low, high
    except (ValueError, AttributeError):
        pass
    return default


class PortManager:
    """Chooses and applies random ports, and tracks rotation timing."""

    def __init__(
        self,
        port_range: Tuple[int, int] = (49152, 65535),
        randomize_outgoing: bool = True,
        verify: bool = True,
        webui_port: int = 8080,
        logger=None,
    ):
        """Initialize the port manager.

        Args:
            port_range: (low, high) range to choose listen ports from.
            randomize_outgoing: Also randomize the outgoing port range.
            verify: Verify the change took effect after applying.
            webui_port: The WebUI/API port to never collide with.
            logger: Optional logger.
        """
        self.low, self.high = port_range
        self.randomize_outgoing = randomize_outgoing
        self.verify = verify
        self.webui_port = webui_port
        self.logger = logger
        self.last_rotation = 0.0

    def choose_port(self) -> int:
        """Pick a random free port in range, avoiding the WebUI port."""
        for _ in range(20):
            port = random.randint(self.low, self.high)
            if port == self.webui_port:
                continue
            if self._is_locally_free(port):
                return port
        # Fall back to any in-range port that isn't the WebUI port.
        port = random.randint(self.low, self.high)
        return port + 1 if port == self.webui_port else port

    @staticmethod
    def _is_locally_free(port: int) -> bool:
        """Best-effort check that nothing local is already bound to ``port``."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def should_rotate(self, mode: str, now: Optional[float] = None) -> bool:
        """Decide whether to rotate the port for the given mode.

        Args:
            mode: 'startup', 'interval', 'once', or 'on-throttle'.
            now: Current epoch time (for testing).

        Returns:
            True if a rotation should happen now.
        """
        now = now if now is not None else time.time()
        if mode in ("startup", "once"):
            return self.last_rotation == 0.0
        if mode == "interval":
            return True  # caller decides interval via apply cadence
        return False  # on-throttle handled by the caller on demand

    def apply(self, api_client, interval: int = 86400, dry_run: bool = False,
              now: Optional[float] = None) -> dict:
        """Choose and apply a new random port set.

        Args:
            api_client: QBittorrentAPIClient.
            interval: Minimum seconds between rotations (interval mode).
            dry_run: Log intended actions without making changes.
            now: Current epoch time (for testing).

        Returns:
            Dict: {changed, listen_port, outgoing, verified, reason}.
        """
        now = now if now is not None else time.time()
        if self.last_rotation and (now - self.last_rotation) < interval:
            return {"changed": False, "reason": "within rotation interval"}

        listen_port = self.choose_port()
        prefs = {"listen_port": listen_port, "random_port": False}

        outgoing = None
        if self.randomize_outgoing:
            out_low = self.choose_port()
            out_high = min(65535, out_low + random.randint(50, 500))
            prefs["outgoing_ports_min"] = out_low
            prefs["outgoing_ports_max"] = out_high
            outgoing = (out_low, out_high)

        if dry_run:
            self.logger and self.logger.info(
                f"[DRY RUN] would set listen_port={listen_port}, outgoing={outgoing}"
            )
            self.last_rotation = now
            return {"changed": True, "listen_port": listen_port, "outgoing": outgoing,
                    "verified": False, "reason": "dry-run"}

        ok = api_client.set_preferences(prefs)
        verified = False
        if ok and self.verify:
            current = api_client.get_preferences() or {}
            verified = current.get("listen_port") == listen_port
            if not verified and self.logger:
                self.logger.warning(
                    f"Listen port not verified (wanted {listen_port}, "
                    f"got {current.get('listen_port')})"
                )

        if ok:
            self.last_rotation = now
            self.logger and self.logger.info(
                f"Listen port set to {listen_port}"
                + (f", outgoing {outgoing}" if outgoing else "")
                + (" (verified)" if verified else "")
            )

        return {"changed": ok, "listen_port": listen_port, "outgoing": outgoing,
                "verified": verified, "reason": "applied" if ok else "set_preferences failed"}
