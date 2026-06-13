"""Auxiliary health checks: trackers (5h), hash-fail watch (5i), WebUI security (5j)."""

from typing import Any, Dict, List, Optional


# qBittorrent tracker status: 0 disabled, 1 not contacted, 2 working,
# 3 updating, 4 not working.
TRACKER_NOT_WORKING = 4

# Tracker messages that mean the torrent is gone from the tracker.
DEAD_TRACKER_MSGS = ("unregistered", "not registered", "torrent not found", "not exist")


class HealthChecks:
    """Tracker health, corruption (hash-fail) tracking, and WebUI security."""

    def __init__(self, max_tracker_lookups: int = 25, logger=None):
        """Initialize health checks.

        Args:
            max_tracker_lookups: Cap per-cycle tracker API calls to bound load.
            logger: Optional logger.
        """
        self.max_tracker_lookups = max_tracker_lookups
        self.logger = logger
        self._last_wasted: Optional[int] = None

    # ------------------------------------------------------------------ #
    # 5h: tracker health
    # ------------------------------------------------------------------ #
    def check_trackers(self, api_client, torrents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find torrents whose trackers are all failing or report 'unregistered'.

        Only inspects torrents that look troubled (not actively downloading), up
        to ``max_tracker_lookups``, to avoid hammering the API.

        Returns:
            Dict: {checked, all_trackers_down, unregistered:[names]}.
        """
        candidates = [
            t for t in torrents
            if not str(t.get("state", "")).startswith(("downloading", "uploading"))
        ][: self.max_tracker_lookups]

        all_down: List[str] = []
        unregistered: List[str] = []

        for t in candidates:
            trackers = api_client.get_trackers(t.get("hash", ""))
            # Ignore the pseudo-trackers (DHT/PeX/LSD) which have url like "** [DHT] **".
            real = [tr for tr in trackers if not str(tr.get("url", "")).startswith("**")]
            if not real:
                continue

            statuses = [tr.get("status", 1) for tr in real]
            if all(s == TRACKER_NOT_WORKING for s in statuses):
                all_down.append(t.get("name", t.get("hash", "?")))

            for tr in real:
                msg = str(tr.get("msg", "")).lower()
                if any(dead in msg for dead in DEAD_TRACKER_MSGS):
                    unregistered.append(t.get("name", t.get("hash", "?")))
                    break

        return {
            "checked": len(candidates),
            "all_trackers_down": all_down,
            "unregistered": unregistered,
        }

    # ------------------------------------------------------------------ #
    # 5i: hash-fail / corruption watch
    # ------------------------------------------------------------------ #
    def check_hash_fails(self, server_state: Dict[str, Any]) -> Dict[str, Any]:
        """Detect rising wasted bytes (failed/hash-failed pieces) between cycles.

        Args:
            server_state: server_state dict (has total_wasted_session).

        Returns:
            Dict: {wasted_delta, suspect} where suspect flags a notable rise.
        """
        wasted = int(server_state.get("total_wasted_session", 0) or 0)
        delta = 0
        if self._last_wasted is not None and wasted >= self._last_wasted:
            delta = wasted - self._last_wasted
        self._last_wasted = wasted

        # >16 MiB wasted in one cycle is a meaningful corruption signal.
        suspect = delta > 16 * 1024 * 1024
        return {"wasted_delta": delta, "suspect": suspect}

    # ------------------------------------------------------------------ #
    # 5j: WebUI security check
    # ------------------------------------------------------------------ #
    @staticmethod
    def check_webui_security(prefs: Dict[str, Any]) -> List[str]:
        """Return a list of WebUI security warnings based on preferences."""
        warnings: List[str] = []
        if not prefs:
            return warnings

        if prefs.get("bypass_local_auth"):
            warnings.append("WebUI auth is bypassed for localhost")
        if prefs.get("bypass_auth_subnet_whitelist_enabled"):
            warnings.append("WebUI auth is bypassed for a whitelisted subnet")
        if prefs.get("web_ui_username") == "admin":
            warnings.append("WebUI still uses the default 'admin' username")
        if prefs.get("web_ui_address") in ("*", "0.0.0.0"):
            warnings.append("WebUI is bound to all interfaces (0.0.0.0)")
        if prefs.get("web_ui_clickjacking_protection_enabled") is False:
            warnings.append("WebUI clickjacking protection is disabled")
        if prefs.get("use_https") is False and prefs.get("web_ui_address") in ("*", "0.0.0.0"):
            warnings.append("WebUI is exposed without HTTPS")
        return warnings
