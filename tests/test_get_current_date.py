"""Tests for get_current_date, the student-added HW1 tool.

"Today" must be the world's fixed world_asof date (the date every
refund_eligible flag is computed from), never the machine clock.
"""

from __future__ import annotations

import sqlite3

from agent import tools
from agent.agent import TOOLS_BY_ROLE
from agent.auth import AuthContext

SHOPPER_1 = AuthContext(user_id=1, role="shopper")


def _world_asof(world: dict) -> str:
    conn = sqlite3.connect(world["db"])
    try:
        return conn.execute("SELECT value FROM meta WHERE key = 'world_asof'").fetchone()[0]
    finally:
        conn.close()


def test_today_is_the_world_date_in_utc(world: dict) -> None:
    result = tools.get_current_date(SHOPPER_1)
    assert result == {"ok": True, "today": _world_asof(world), "timezone": "UTC"}


def test_days_since_is_computed_in_code(world: dict) -> None:
    # Order 4455 was placed 2026-06-21 and the world date is 2026-07-01.
    assert _world_asof(world) == "2026-07-01"
    result = tools.get_current_date(SHOPPER_1, "2026-06-21")
    assert result["ok"] is True
    assert result["since_date"] == "2026-06-21"
    assert result["days_since"] == 10
    assert tools.get_current_date(SHOPPER_1, "2026-07-01")["days_since"] == 0
    assert tools.get_current_date(SHOPPER_1, "2026-07-03")["days_since"] == -2


def test_invalid_since_date_is_rejected(world: dict) -> None:
    for bad in ("", "June 21", "2026-13-01", "21/06/2026"):
        result = tools.get_current_date(SHOPPER_1, bad)
        assert result["ok"] is False
        assert result["error"] == "invalid_argument"


def test_registered_for_every_role() -> None:
    for role in ("shopper", "merchant", "support"):
        assert "get_current_date" in {t.name for t in TOOLS_BY_ROLE[role]}
