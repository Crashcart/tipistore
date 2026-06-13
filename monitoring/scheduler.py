"""Time-window scheduling for automatic maintenance mode (throttled hours).

A maintenance window is "HH:MM-HH:MM" in 24h local time. Multiple windows may
be comma-separated. Windows that cross midnight (e.g. "22:00-06:00") are
handled. While inside any window, the agent enters maintenance mode
automatically and pauses active monitoring/recovery.
"""

from datetime import datetime, time as dtime
from typing import List, Optional, Tuple


def parse_windows(spec) -> List[Tuple[dtime, dtime]]:
    """Parse a window specification into (start, end) time pairs.

    Args:
        spec: A string like "22:00-06:00,12:00-13:00", or a list of such
            strings, or empty/None.

    Returns:
        List of (start_time, end_time) tuples. Invalid entries are skipped.
    """
    if not spec:
        return []
    if isinstance(spec, (list, tuple)):
        parts = []
        for item in spec:
            parts.extend(str(item).split(","))
    else:
        parts = str(spec).split(",")

    windows: List[Tuple[dtime, dtime]] = []
    for part in parts:
        part = part.strip()
        if not part or "-" not in part:
            continue
        start_str, end_str = part.split("-", 1)
        start = _parse_hhmm(start_str)
        end = _parse_hhmm(end_str)
        if start is not None and end is not None:
            windows.append((start, end))
    return windows


def _parse_hhmm(value: str) -> Optional[dtime]:
    value = value.strip()
    if ":" not in value:
        return None
    try:
        hh, mm = value.split(":", 1)
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return dtime(hour=h, minute=m)
    except ValueError:
        pass
    return None


def is_within_windows(windows: List[Tuple[dtime, dtime]], now: Optional[datetime] = None) -> bool:
    """Return True if ``now`` falls within any window.

    Args:
        windows: List of (start, end) pairs from :func:`parse_windows`.
        now: The moment to test; defaults to the current local time.

    Returns:
        True if inside a maintenance window.
    """
    if not windows:
        return False
    current = (now or datetime.now()).time()
    for start, end in windows:
        if start == end:
            continue  # zero-length window
        if start < end:
            if start <= current < end:
                return True
        else:
            # Crosses midnight, e.g. 22:00-06:00.
            if current >= start or current < end:
                return True
    return False
