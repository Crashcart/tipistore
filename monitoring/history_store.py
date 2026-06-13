"""Persistent history of samples and events using stdlib sqlite3."""

import os
import time
import sqlite3
from typing import Any, Dict, List, Optional


class HistoryStore:
    """SQLite-backed store for time-series samples and discrete events."""

    def __init__(self, db_path: str, logger=None):
        """Initialize the store and create tables if needed.

        Args:
            db_path: Path to the SQLite database file.
            logger: Optional logger.
        """
        self.db_path = db_path
        self.logger = logger
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    ts REAL NOT NULL,
                    lag_score REAL,
                    dl_speed INTEGER,
                    up_speed INTEGER,
                    peers INTEGER,
                    dht INTEGER,
                    cpu REAL,
                    mem REAL,
                    disk_free REAL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    ts REAL NOT NULL,
                    type TEXT NOT NULL,
                    detail TEXT
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
            self._conn.commit()
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"Failed to initialize history DB: {e}")
            self._conn = None

    def record_sample(
        self,
        lag_score: float = 0.0,
        dl_speed: int = 0,
        up_speed: int = 0,
        peers: int = 0,
        dht: int = 0,
        cpu: float = 0.0,
        mem: float = 0.0,
        disk_free: float = 0.0,
    ):
        """Insert one time-series sample."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?)",
                (time.time(), lag_score, dl_speed, up_speed, peers, dht, cpu, mem, disk_free),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            if self.logger:
                self.logger.debug(f"record_sample failed: {e}")

    def record_event(self, event_type: str, detail: str = ""):
        """Insert one discrete event (recovery, restart, disk alert, etc.)."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT INTO events VALUES (?,?,?)", (time.time(), event_type, detail)
            )
            self._conn.commit()
        except sqlite3.Error as e:
            if self.logger:
                self.logger.debug(f"record_event failed: {e}")

    def recent_samples(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent samples (newest first)."""
        if not self._conn:
            return []
        cols = ["ts", "lag_score", "dl_speed", "up_speed", "peers", "dht", "cpu", "mem", "disk_free"]
        try:
            rows = self._conn.execute(
                "SELECT ts,lag_score,dl_speed,up_speed,peers,dht,cpu,mem,disk_free "
                "FROM samples ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(zip(cols, row)) for row in rows]
        except sqlite3.Error:
            return []

    def recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent events (newest first)."""
        if not self._conn:
            return []
        try:
            rows = self._conn.execute(
                "SELECT ts,type,detail FROM events ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            return [{"ts": r[0], "type": r[1], "detail": r[2]} for r in rows]
        except sqlite3.Error:
            return []

    def prune(self, max_age_days: float = 30.0):
        """Delete samples/events older than ``max_age_days``."""
        if not self._conn:
            return
        cutoff = time.time() - max_age_days * 86400
        try:
            self._conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self._conn.commit()
        except sqlite3.Error:
            pass

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
