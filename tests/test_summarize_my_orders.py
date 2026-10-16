"""Tests for summarize_my_orders, the student-added HW1 tool.

Expected values come from plain SQL over the seeded world, independent of the
tool's own code path, so the tests check the aggregates rather than restate them.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent import tools
from agent.agent import TOOLS_BY_ROLE
from agent.auth import AuthContext

SHOPPER_1 = AuthContext(user_id=1, role="shopper")
MERCHANT_STORE_2 = AuthContext(user_id=9002, role="merchant", store_id=2)
SUPPORT = AuthContext(user_id=9501, role="support")


def _sql(world: dict, query: str, *params):
    conn = sqlite3.connect(world["db"])
    try:
        return conn.execute(query, params).fetchone()
    finally:
        conn.close()


def test_shopper_summary_covers_all_orders_not_just_20(world: dict) -> None:
    count, cents, stores, eligible = _sql(
        world,
        "SELECT COUNT(*), SUM(total_cents), COUNT(DISTINCT store_id), SUM(refund_eligible) "
        "FROM orders WHERE user_id = ?",
        1,
    )
    assert count > tools.DEFAULT_ORDER_LIMIT  # shopper 1 has more than list_my_orders shows

    result = tools.summarize_my_orders(SHOPPER_1)
    assert result["ok"] is True
    assert result["order_count"] == count
    assert result["total_usd"] == cents / 100
    assert result["store_count"] == stores == len(result["stores"])
    assert result["refund_eligible_count"] == eligible
    assert sum(s["order_count"] for s in result["stores"]) == count
    assert sum(s["count"] for s in result["by_status"].values()) == count
    assert round(sum(s["total_usd"] for s in result["by_status"].values()), 2) == result["total_usd"]


def test_stores_sorted_by_order_count_then_id(world: dict) -> None:
    stores = tools.summarize_my_orders(SHOPPER_1)["stores"]
    keys = [(-s["order_count"], s["store_id"]) for s in stores]
    assert keys == sorted(keys)
    assert all(s["store_name"] for s in stores)


def test_merchant_summary_is_scoped_to_own_store(world: dict) -> None:
    count, cents = _sql(
        world, "SELECT COUNT(*), SUM(total_cents) FROM orders WHERE store_id = ?", 2
    )
    result = tools.summarize_my_orders(MERCHANT_STORE_2)
    assert result["ok"] is True
    assert result["order_count"] == count
    assert result["total_usd"] == cents / 100
    assert [s["store_id"] for s in result["stores"]] == [2]


def test_support_is_rejected_and_not_registered(world: dict) -> None:
    result = tools.summarize_my_orders(SUPPORT)
    assert result["ok"] is False
    assert result["error"] == "invalid_argument"
    names = lambda role: {t.name for t in TOOLS_BY_ROLE[role]}
    assert "summarize_my_orders" in names("shopper")
    assert "summarize_my_orders" in names("merchant")
    assert "summarize_my_orders" not in names("support")


def test_shopper_with_no_orders_gets_empty_summary(world_copy: Path) -> None:
    conn = sqlite3.connect(world_copy)
    try:
        conn.execute("DELETE FROM orders WHERE user_id = 2")
        conn.commit()
    finally:
        conn.close()
    result = tools.summarize_my_orders(AuthContext(user_id=2, role="shopper"))
    assert result == {
        "ok": True, "order_count": 0, "total_usd": 0, "by_status": {},
        "refund_eligible_count": 0, "store_count": 0, "stores": [],
        "first_ordered_at": None, "last_ordered_at": None,
        "avg_days_to_delivery": None, "delivered_order_count": 0,
        "cancelled_pct": None, "refunded_pct": None,
    }


def test_delivery_time_and_cancel_refund_rates(world: dict) -> None:
    avg_days, delivered = _sql(
        world,
        "SELECT ROUND(AVG(julianday(delivered_at) - julianday(ordered_at)), 1), COUNT(*) "
        "FROM orders WHERE user_id = ? AND delivered_at IS NOT NULL AND delivered_at >= ordered_at",
        1,
    )
    total, cancelled, refunded = _sql(
        world,
        "SELECT COUNT(*), SUM(status = 'cancelled'), SUM(status = 'refunded') "
        "FROM orders WHERE user_id = ?",
        1,
    )
    result = tools.summarize_my_orders(SHOPPER_1)
    assert result["avg_days_to_delivery"] == avg_days
    assert result["delivered_order_count"] == delivered
    assert result["cancelled_pct"] == round(100 * cancelled / total, 1)
    assert result["refunded_pct"] == round(100 * refunded / total, 1)


def test_bad_delivery_dates_are_left_out_not_guessed(world_copy: Path) -> None:
    conn = sqlite3.connect(world_copy)
    try:
        conn.execute("DELETE FROM orders WHERE user_id = 2")
        rows = [  # ordered, delivered -> 4 days, then a missing and a reversed date
            (900001, "2026-06-01", "2026-06-05"),
            (900002, "2026-06-01", None),
            (900003, "2026-06-10", "2026-06-02"),
        ]
        for order_id, ordered, delivered in rows:
            conn.execute(
                "INSERT INTO orders (id, user_id, store_id, product_id, quantity, total_cents, "
                "status, ordered_at, shipped_at, delivered_at, refund_eligible) "
                "VALUES (?, 2, 1, 1, 1, 1000, 'delivered', ?, NULL, ?, 0)",
                (order_id, ordered, delivered),
            )
        conn.commit()
    finally:
        conn.close()
    result = tools.summarize_my_orders(AuthContext(user_id=2, role="shopper"))
    assert result["order_count"] == 3
    assert result["delivered_order_count"] == 1
    assert result["avg_days_to_delivery"] == 4.0
    assert result["cancelled_pct"] == 0.0
