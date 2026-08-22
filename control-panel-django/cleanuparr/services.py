"""Cleanuparr routes, ported from the FastAPI-era
control-panel/services/cleanuparr/router.py.

Both routes are read-only, session-or-service-key authenticated, and read
directly from Cleanuparr's own SQLite files rather than its (nonexistent)
HTTP API. A missing SQLite file is diagnostic, not fatal - it just means
Cleanuparr isn't deployed on this host (or hasn't run yet), not that this
endpoint is broken - so both functions return an empty/diagnostic result
instead of raising. This is a deliberate deviation from router.py, which
calls core.responses.fail() (raises a 502) on a missing file; the SDD
brief for this task explicitly calls for the non-raising behavior.
"""
import os
import sqlite3

from core.host_paths import HOST_CONFIG_DIR


def check_instances() -> dict:
    """Which *arr apps Cleanuparr actually has a connected arr_instance for,
    vs. just an arr_configs type placeholder - the exact gap that historically
    left Lidarr and Whisparr (both since removed) completely uncovered by
    queue-cleaning/strikes despite both apps being fully functional at the
    time."""
    db_path = os.path.join(HOST_CONFIG_DIR, "cleanuparr", "cleanuparr.db")
    if not os.path.isfile(db_path):
        return {"message": f"{db_path} not present.", "connected": [], "gaps": []}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("SELECT type FROM arr_configs")
        configured_types = {row["type"] for row in cur.fetchall()}
        cur.execute("SELECT name FROM arr_instances")
        connected = {row["name"].lower() for row in cur.fetchall()}
    finally:
        con.close()
    gaps = sorted(t for t in configured_types if t not in connected and t != "readarr")
    if not gaps:
        return {
            "message": "Every configured app type has a connected instance.",
            "connected": sorted(connected),
            "gaps": [],
        }
    return {
        "message": f"{len(gaps)} app(s) have a config placeholder but no connected instance: "
        f"{', '.join(gaps)}",
        "connected": sorted(connected),
        "gaps": gaps,
    }


def recent_strikes(limit: int = 15) -> dict:
    """Recent strikes Cleanuparr has issued (stalled/slow/malware) - lives
    in events.db, a separate SQLite file from the arr_instances/arr_configs
    one check_instances() above reads (Cleanuparr splits its own state
    across cleanuparr.db and events.db)."""
    db_path = os.path.join(HOST_CONFIG_DIR, "cleanuparr", "events.db")
    if not os.path.isfile(db_path):
        return {"message": f"{db_path} not present.", "items": [], "total": 0}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT s.created_at, s.type, d.title FROM strikes s "
            "JOIN download_items d ON d.id = s.download_item_id "
            "ORDER BY s.created_at DESC LIMIT ?",
            (limit,),
        )
        rows = [
            {"created_at": r["created_at"], "type": r["type"], "title": r["title"]}
            for r in cur.fetchall()
        ]
        cur.execute("SELECT COUNT(*) FROM strikes")
        total = cur.fetchone()[0]
    finally:
        con.close()
    return {
        "message": f"{total} strike(s) total, showing {len(rows)} most recent.",
        "items": rows,
        "total": total,
    }
