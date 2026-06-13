"""Curses-based text GUI for editing the agent configuration.

Reads and writes the same config file via AgentConfig. Falls back to a printed
summary when no interactive terminal is available.
"""

import sys
from typing import Callable, List, Optional, Tuple

from qbt_api.agent_config import SCHEMA


# Fields presented as a fixed choice list (cycled with space/enter).
CHOICE_FIELDS = {
    ("agent", "sensitivity"): ["aggressive", "balanced", "conservative"],
    ("agent", "log_level"): ["DEBUG", "INFO", "WARNING", "ERROR"],
    ("ports", "random_port_mode"): ["startup", "interval", "once", "on-throttle"],
    ("notifications", "notify_level"): ["DEBUG", "INFO", "WARNING", "CRITICAL"],
}


def _flatten() -> List[Tuple[str, str, str]]:
    """Return (section, key, type) for every editable field."""
    fields = []
    for section, keys in SCHEMA.items():
        for key, (_default, type_name, _comment) in keys.items():
            fields.append((section, key, type_name))
    return fields


def run_config_tui(cfg, api_client_factory: Optional[Callable] = None):
    """Entry point: launch the curses UI, or print a summary if non-interactive.

    Args:
        cfg: AgentConfig instance to edit.
        api_client_factory: Optional callable returning an API client, used to
            pre-fill live qBittorrent values (listen port, save path).
    """
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if interactive:
        try:
            import curses

            curses.wrapper(_run, cfg, api_client_factory)
            return
        except Exception as e:  # curses unavailable / terminal too small
            print(f"Text GUI unavailable ({e}); showing summary instead.\n")

    _print_summary(cfg)


def _print_summary(cfg):
    """Non-interactive fallback: print the current configuration."""
    print(f"Agent configuration: {cfg.config_path}\n")
    for section, keys in SCHEMA.items():
        print(f"[{section}]")
        for key in keys:
            print(f"  {key} = {cfg.get(section, key)}")
        print()
    print("Edit this file directly, or run --configure in an interactive terminal.")


def _prefill_live(cfg, api_client_factory, logger=None):
    """Best-effort: pull current listen port from qBittorrent into the view."""
    if not api_client_factory:
        return None
    try:
        api = api_client_factory()
        prefs = api.get_preferences()
        return prefs or None
    except Exception:
        return None


def _run(stdscr, cfg, api_client_factory):
    import curses

    curses.curs_set(0)
    stdscr.keypad(True)
    fields = _flatten()
    idx = 0
    status = "Arrows move - Space toggle/cycle - Enter edit - s save - q quit"
    live_prefs = _prefill_live(cfg, api_client_factory)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, "qBittorrent Agent - Configuration", w - 1, curses.A_BOLD)
        stdscr.addnstr(1, 0, cfg.config_path, w - 1, curses.A_DIM)

        top = 3
        visible = h - top - 2
        start = max(0, idx - visible + 1)
        for row, (section, key, type_name) in enumerate(fields[start:start + visible]):
            i = start + row
            value = cfg.get(section, key)
            shown = ",".join(str(v) for v in value) if isinstance(value, list) else str(value)
            label = f"[{section}] {key}"
            line = f"{label:42} = {shown}"
            attr = curses.A_REVERSE if i == idx else curses.A_NORMAL
            stdscr.addnstr(top + row, 0, line, w - 1, attr)

        # Inline hint about the focused field.
        sec, k, t = fields[idx]
        comment = SCHEMA[sec][k][2]
        stdscr.addnstr(h - 2, 0, comment[: w - 1], w - 1, curses.A_DIM)
        stdscr.addnstr(h - 1, 0, status[: w - 1], w - 1, curses.A_BOLD)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(fields)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(fields)
        elif ch == ord(" "):
            _toggle_or_cycle(cfg, fields[idx])
        elif ch in (curses.KEY_ENTER, 10, 13):
            if t == "bool" or (sec, k) in CHOICE_FIELDS:
                _toggle_or_cycle(cfg, fields[idx])
            else:
                _edit_field(stdscr, cfg, fields[idx])
        elif ch == ord("p") and live_prefs:
            _apply_live(cfg, live_prefs)
            status = "Pulled live values from qBittorrent"
        elif ch == ord("s"):
            cfg.save()
            status = f"Saved to {cfg.config_path}"
        elif ch == ord("q"):
            break


def _toggle_or_cycle(cfg, field):
    section, key, type_name = field
    if (section, key) in CHOICE_FIELDS:
        choices = CHOICE_FIELDS[(section, key)]
        current = cfg.get(section, key)
        nxt = choices[(choices.index(current) + 1) % len(choices)] if current in choices else choices[0]
        cfg.set(section, key, nxt)
    elif type_name == "bool":
        cfg.set(section, key, not bool(cfg.get(section, key)))


def _edit_field(stdscr, cfg, field):
    import curses

    section, key, type_name = field
    h, w = stdscr.getmaxyx()
    curses.curs_set(1)
    curses.echo()
    stdscr.addnstr(h - 1, 0, f"{key} = ", w - 1)
    stdscr.clrtoeol()
    try:
        raw = stdscr.getstr(h - 1, len(key) + 3, 200).decode(errors="replace")
    finally:
        curses.noecho()
        curses.curs_set(0)
    if raw != "":
        cfg.set(section, key, raw)


def _apply_live(cfg, prefs):
    if "listen_port" in prefs:
        # Informational only; the WebUI/API port is never randomized here.
        cfg.set("ports", "random_port_range",
                f"{max(1024, prefs['listen_port']-1)}-{min(65535, prefs['listen_port']+1000)}")
