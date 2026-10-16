"""Homework 1: the remaining commerce-agent tools.

The three lecture tools (`search_help_center`, `get_order`, `issue_refund`)
are implemented in agent/agent.py and are worked examples of the pattern:
check permissions first, go through agent/db.py for data, and return a
structured dict, never a prose error. The homework tools follow the same
pattern. agent/agent.py already wraps each function below as an SDK tool, so
once a function works here it works in chat with no further wiring.

Result convention (see agent/auth.py):
  - Success: a dict with "ok": True plus the payload fields named in each
    docstring.
  - Failure: {"ok": False, "error": <code>, "reason": <human-readable str>}.

Run the contract tests with: uv run pytest tests/test_hw_holes.py -k hw1
They are marked xfail and flip to passing as you implement each function.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from agent import db
from agent.auth import AuthContext, can_cancel_order, permission_denied
from agent.helpcenter import load_policy_docs
from agent.killswitch import kill_switch

MAX_SEARCH_LIMIT = 25
DEFAULT_ORDER_LIMIT = 20


def get_policy(ctx: AuthContext, policy_id: str) -> dict[str, Any]:
    """Fetch one policy doc by its exact id. Risk tier: read.

    Every role may read every policy doc (the corpus is public help-center
    content), so this tool needs no permission check.

    Args:
        ctx: The caller's auth context. Unused here, but every tool takes it.
        policy_id: An exact policy id, e.g. "cw-returns" or
            "store-juniper-home-goods-policy". Matching is exact and
            case-sensitive; ids are the `policy_id` front-matter field of the
            files in data/policies/.

    Returns:
        On success: {"ok": True, "policy_id": str, "title": str,
        "audience": str, "body": str} where body is the markdown body of the
        doc without the front matter.
        If no doc has that id: {"ok": False, "error": "not_found",
        "reason": ...} naming the id that was requested.

    Implementation notes:
        agent.helpcenter.load_policy_docs() returns every parsed doc.
    """
    for doc in load_policy_docs():
        if doc.policy_id == policy_id:
            return {
                "ok": True,
                "policy_id": doc.policy_id,
                "title": doc.title,
                "audience": doc.audience,
                "body": doc.body,
            }
    return {"ok": False, "error": "not_found", "reason": f"no policy doc with id {policy_id!r}"}


def search_products(
    ctx: AuthContext,
    query: str,
    store: str | None = None,
    max_price_usd: float | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search the product catalog. Risk tier: read.

    Every role may search products. Matching is deterministic keyword
    matching, not semantic search: a product matches when every whitespace
    token of `query` appears case-insensitively as a substring of the
    product's title or description.

    Args:
        ctx: The caller's auth context.
        query: Free-text query. Must be non-empty after stripping whitespace;
            otherwise return {"ok": False, "error": "invalid_argument",
            "reason": ...}.
        store: Optional store filter. Matched with
            agent.db.get_store_by_name (case-insensitive name or slug). If
            given and no store matches, return {"ok": False, "error":
            "not_found", "reason": ...} naming the store string.
        max_price_usd: Optional inclusive price ceiling. If given and not
            strictly positive, return an "invalid_argument" error.
        limit: Maximum products to return. Clamp to the range
            [1, MAX_SEARCH_LIMIT]; do not error on out-of-range values.

    Returns:
        {"ok": True, "products": [...], "count": <len(products)>} where each
        product is {"product_id": int, "store_id": int, "title": str,
        "price_usd": float}. Sort matches by price_usd ascending, then by
        product_id ascending, and truncate to `limit`. No matches is still a
        success: {"ok": True, "products": [], "count": 0}.

    Implementation notes:
        agent.db.list_products(conn, store_id) gives the candidate set.
        Use `with db.connection() as conn:` to close the database automatically.
    """
    tokens = query.lower().split()
    if not tokens:
        return {"ok": False, "error": "invalid_argument", "reason": "query must not be empty"}
    if max_price_usd is not None and max_price_usd <= 0:
        return {
            "ok": False,
            "error": "invalid_argument",
            "reason": f"max_price_usd must be positive, got {max_price_usd}",
        }
    limit = max(1, min(limit, MAX_SEARCH_LIMIT))

    with db.connection() as conn:
        store_id = None
        if store is not None:
            found = db.get_store_by_name(conn, store)
            if found is None:
                return {"ok": False, "error": "not_found", "reason": f"no store named {store!r}"}
            store_id = found.id
        candidates = db.list_products(conn, store_id)

    matches = [
        p
        for p in candidates
        if all(t in p.title.lower() or t in p.description.lower() for t in tokens)
        and (max_price_usd is None or p.price_usd <= max_price_usd)
    ]
    matches.sort(key=lambda p: (p.price_usd, p.id))
    products = [
        {"product_id": p.id, "store_id": p.store_id, "title": p.title, "price_usd": p.price_usd}
        for p in matches[:limit]
    ]
    return {"ok": True, "products": products, "count": len(products)}


def list_my_orders(ctx: AuthContext) -> dict[str, Any]:
    """List recent orders in the caller's own scope. Risk tier: read.

    Role behavior, straight from the access matrix in SPEC.md:
        - shopper: the caller's own orders.
        - merchant: the caller's store's orders (ctx.store_id).
        - support: support staff have no orders of their own and look up
          specific orders with get_order instead, so return {"ok": False,
          "error": "invalid_argument", "reason": ...} saying exactly that.

    Returns:
        For shopper and merchant: {"ok": True, "orders": [...],
        "count": <len(orders)>} where each order is
        agent.db.Order.to_public_dict() and the list holds at most
        DEFAULT_ORDER_LIMIT orders, newest first (agent.db.list_orders_for_user
        and list_orders_for_store already sort and limit this way).

    Implementation notes:
        No permission check is needed beyond the role dispatch, because the
        scope is baked into which query you run. That is the point of the
        tool: the model cannot ask for someone else's orders through it.
    """
    if ctx.role == "support":
        return {
            "ok": False,
            "error": "invalid_argument",
            "reason": "support staff have no orders of their own; look up a specific order with get_order",
        }
    with db.connection() as conn:
        if ctx.role == "shopper":
            orders = db.list_orders_for_user(conn, ctx.user_id, limit=DEFAULT_ORDER_LIMIT)
        else:
            orders = db.list_orders_for_store(conn, ctx.store_id, limit=DEFAULT_ORDER_LIMIT)
    return {"ok": True, "orders": [o.to_public_dict() for o in orders], "count": len(orders)}


def cancel_order(ctx: AuthContext, order_id: int, reason: str) -> dict[str, Any]:
    """Cancel an order. Risk tier: write.

    This is the homework's write tool, and it must enforce two independent
    rules in this order:

    1. The access matrix (scope): use agent.auth.can_cancel_order. Shoppers
       may cancel only their own orders, merchants only their own store's
       orders, support any order. On failure return
       agent.auth.permission_denied(...) with a reason naming the role and
       the order id. Scope is checked before the status rule so that an
       out-of-scope caller learns nothing about the order's state.
    2. The pre-shipment rule (facts.yaml `cancel_cutoff`): only orders whose
       status is exactly "placed" can be cancelled, for every role. If the
       order is in scope but its status is not "placed", return
       {"ok": False, "error": "not_eligible", "reason": ...} that names the
       current status and states that orders can be cancelled only before
       shipment.

    Args:
        ctx: The caller's auth context.
        order_id: The order to cancel.
        reason: Free-text reason from the user; not validated.

    Returns:
        If no order has this id: {"ok": False, "error": "not_found",
        "reason": ...}.
        On success: {"ok": True, "order_id": order_id, "status": "cancelled"}
        after persisting the new status with agent.db.set_order_status.

    Implementation notes:
        Fetch with agent.db.get_order. Note the argument order of
        can_cancel_order(ctx, order_user_id, order_store_id).

    The Module 4 kill switch is checked first (before the scope and
    status rules and before your code), so that a paused write tool touches
    nothing. It is provided; the default ("off") returns None and falls
    through to your implementation.
    """
    paused = kill_switch("cancel_order")
    if paused is not None:
        return {"ok": False, "error": "paused", "reason": paused}
    with db.connection() as conn:
        order = db.get_order(conn, order_id)
        if order is None:
            return {"ok": False, "error": "not_found", "reason": f"no order #{order_id}"}
        if not can_cancel_order(ctx, order.user_id, order.store_id):
            return permission_denied(
                f"role '{ctx.role}' (user {ctx.user_id}) may not cancel order #{order_id}"
            )
        if order.status != "placed":
            return {
                "ok": False,
                "error": "not_eligible",
                "reason": (
                    f"order #{order_id} is '{order.status}'; "
                    "orders can be cancelled only before shipment"
                ),
            }
        db.set_order_status(conn, order_id, "cancelled")
    return {"ok": True, "order_id": order_id, "status": "cancelled"}


def find_order(ctx: AuthContext, query: str) -> dict[str, Any]:
    """Search the caller's orders by product name. Risk tier: read.

    Takes a natural-language query (e.g., "earmuffs I bought last week")
    and searches the authenticated user's orders for products whose name
    matches. Use fuzzy string matching (e.g., thefuzz.fuzz.partial_ratio
    or case-insensitive substring matching) to find orders whose product name is close to the
    query.

    Access rules: a shopper searches only the shopper's own orders, a
    merchant searches orders from the merchant's store, and support staff
    can search any orders. Use agent.db.list_order_search_candidates with
    user_id=ctx.user_id for shoppers, store_id=ctx.store_id for merchants,
    or all_orders=True only for support. Derive the scope from ctx, never
    from the query; reject unsupported roles or missing required identity.
    Use agent.db.list_products to map product IDs to product titles.

    The helper returns the complete authorised scope, newest first with
    order ID descending as the tie-breaker. Match product names first,
    preserve that order, then return at most five matches. Do not search
    only the 20 most recent orders. Convert matches with to_public_dict().

    Args:
        ctx: The caller's auth context.
        query: A natural-language description of the product.

    Returns:
        {"ok": True, "orders": [...]} with a list of matching orders
        (at most 5), each as the dict returned by agent.db. If no orders
        match, return {"ok": True, "orders": []}.
    """
    if ctx.role == "shopper" and ctx.user_id is not None:
        scope: dict[str, Any] = {"user_id": ctx.user_id}
    elif ctx.role == "merchant" and ctx.store_id is not None:
        scope = {"store_id": ctx.store_id}
    elif ctx.role == "support":
        scope = {"all_orders": True}
    else:
        return permission_denied(f"role '{ctx.role}' has no order search scope")

    terms = _search_terms(query)
    if not terms:
        return {"ok": True, "orders": []}

    with db.connection() as conn:
        candidates = db.list_order_search_candidates(conn, **scope)
        titles = {p.id: p.title for p in db.list_products(conn)}

    matches = [
        o for o in candidates if _title_matches(terms, titles.get(o.product_id, ""))
    ][:5]
    return {"ok": True, "orders": [o.to_public_dict() for o in matches]}


# Words that describe the purchase rather than the product ("the earmuffs I
# bought last week"); dropping them leaves the product words to match on.
_QUERY_STOPWORDS = frozenset(
    "a an and the i me my mine we our you it its this that those these some "
    "for from of in on at to with "
    "bought buy ordered order orders purchased purchase got get "
    "last week weeks month months year ago recently yesterday today".split()
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _search_terms(query: str) -> list[str]:
    return [
        w for w in _WORD_RE.findall(query.lower()) if len(w) >= 3 and w not in _QUERY_STOPWORDS
    ]


def _title_matches(terms: list[str], title: str) -> bool:
    """True when any query term matches a title word, tolerating plurals ("vases" ~ "vase")."""
    words = _WORD_RE.findall(title.lower())
    return any(
        term == word or (len(word) >= 3 and (term.startswith(word) or word.startswith(term)))
        for term in terms
        for word in words
    )


def summarize_my_orders(ctx: AuthContext) -> dict[str, Any]:
    """Summarize every order in the caller's own scope. Risk tier: read.

    Added beyond the five HW1 tools. list_my_orders returns at most
    DEFAULT_ORDER_LIMIT orders, so a model that totals or counts that list
    silently drops older orders and does the arithmetic itself. This tool
    computes the aggregates in code over the complete scope instead.

    Role behavior matches list_my_orders: a shopper summarizes the shopper's
    own orders, a merchant the merchant's store's orders, and support staff
    get {"ok": False, "error": "invalid_argument", ...} because they have no
    orders of their own. As with list_my_orders, the scope comes from ctx, so
    the model cannot summarize anyone else's orders.

    Returns:
        {"ok": True, "order_count": int, "total_usd": float, "by_status":
        {status: {"count": int, "total_usd": float}}, "refund_eligible_count":
        int, "store_count": int, "stores": [{"store_id": int, "store_name":
        str | None, "order_count": int}], "first_ordered_at": str | None,
        "last_ordered_at": str | None, "avg_days_to_delivery": float | None,
        "delivered_order_count": int, "cancelled_pct": float | None,
        "refunded_pct": float | None}. total_usd covers every order,
        including cancelled and refunded ones; by_status separates them.
        Stores are sorted by order_count descending, then store_id.

        avg_days_to_delivery is the mean of delivered_at minus ordered_at,
        rounded to one decimal, over the delivered_order_count orders that
        have a delivery date on or after the order date; orders without one
        (including records with missing or reversed dates) are left out
        rather than guessed. cancelled_pct and refunded_pct are the share of
        orders, by count, whose status is "cancelled" or "refunded", rounded
        to one decimal. A caller with no orders gets zero counts, empty
        collections, and None for the averages and percentages.
    """
    if ctx.role == "shopper":
        scope: dict[str, Any] = {"user_id": ctx.user_id}
    elif ctx.role == "merchant" and ctx.store_id is not None:
        scope = {"store_id": ctx.store_id}
    else:
        return {
            "ok": False,
            "error": "invalid_argument",
            "reason": "support staff have no orders of their own; look up a specific order with get_order",
        }

    with db.connection() as conn:
        orders = db.list_order_search_candidates(conn, **scope)
        store_ids = sorted({o.store_id for o in orders})
        store_names = {
            sid: store.name if (store := db.get_store(conn, sid)) else None for sid in store_ids
        }

    # Sum integer cents, not float dollars, so totals have no rounding drift.
    status_cents: dict[str, list[int]] = {}
    store_counts: dict[int, int] = {}
    for o in orders:
        status_cents.setdefault(o.status, []).append(o.total_cents)
        store_counts[o.store_id] = store_counts.get(o.store_id, 0) + 1
    stores = sorted(store_counts.items(), key=lambda item: (-item[1], item[0]))
    dates = sorted(o.ordered_at for o in orders)
    delivery_days = [
        (o.delivered_at - o.ordered_at).days
        for o in orders
        if o.delivered_at is not None and o.delivered_at >= o.ordered_at
    ]

    def pct(status: str) -> float | None:
        if not orders:
            return None
        return round(100 * len(status_cents.get(status, [])) / len(orders), 1)

    return {
        "ok": True,
        "order_count": len(orders),
        "total_usd": sum(o.total_cents for o in orders) / 100,
        "by_status": {
            status: {"count": len(cents), "total_usd": sum(cents) / 100}
            for status, cents in sorted(status_cents.items())
        },
        "refund_eligible_count": sum(o.refund_eligible for o in orders),
        "store_count": len(stores),
        "stores": [
            {"store_id": sid, "store_name": store_names[sid], "order_count": n}
            for sid, n in stores
        ],
        "first_ordered_at": dates[0].isoformat() if dates else None,
        "last_ordered_at": dates[-1].isoformat() if dates else None,
        "avg_days_to_delivery": (
            round(sum(delivery_days) / len(delivery_days), 1) if delivery_days else None
        ),
        "delivered_order_count": len(delivery_days),
        "cancelled_pct": pct("cancelled"),
        "refunded_pct": pct("refunded"),
    }


def get_current_date(ctx: AuthContext, since_date: str | None = None) -> dict[str, Any]:
    """Today's date in the Cartwheel world, optionally with days elapsed. Risk tier: read.

    Added beyond the five HW1 tools. The model has no clock and otherwise
    guesses "today" from its training data. Today is the world's fixed
    `world_asof` date, never the machine clock, because every refund_eligible
    flag and return window is computed from it; a real clock would contradict
    the order tools. The date is a calendar date in UTC.

    Every role may call it; it reads no user data.

    Args:
        ctx: The caller's auth context. Unused here, but every tool takes it.
        since_date: Optional ISO date (YYYY-MM-DD), e.g. an order's ordered_at
            or delivered_at. If given, the result includes days_since, computed
            in code. If it is not a valid ISO date, return {"ok": False,
            "error": "invalid_argument", "reason": ...}.

    Returns:
        {"ok": True, "today": "YYYY-MM-DD", "timezone": "UTC"}, plus
        "since_date" and "days_since" (today minus since_date; negative when
        since_date is in the future) when since_date is given.
    """
    since = None
    if since_date is not None:
        try:
            since = date.fromisoformat(since_date.strip())
        except ValueError:
            return {
                "ok": False,
                "error": "invalid_argument",
                "reason": f"since_date must be an ISO date (YYYY-MM-DD), got {since_date!r}",
            }
    with db.connection() as conn:
        today = db.world_asof(conn)
    result: dict[str, Any] = {"ok": True, "today": today.isoformat(), "timezone": "UTC"}
    if since is not None:
        result["since_date"] = since.isoformat()
        result["days_since"] = (today - since).days
    return result
