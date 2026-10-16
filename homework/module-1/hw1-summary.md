# Homework 1 summary

Written walkthrough of the Homework 1 work, in place of the screen recording. Each
section maps to an item the handout's video asks for, and points to the committed
evidence.

- Agent model: `claude-haiku-4-5` (via `CARTWHEEL_MODEL` in `.env`).
- Conversation records: [`hw1-session.jsonl`](hw1-session.jsonl) in this folder
  (moved here from the repository root), 18 records.
- World date: every date is computed from the seeded `world_asof`, 2026-07-01.

## Part A: tools

### The five required tools (`agent/tools.py`)

| Tool | Behaviour |
| --- | --- |
| `get_policy` | Exact, case-sensitive id lookup over `load_policy_docs()`; `not_found` otherwise. |
| `search_products` | Every query token must appear in the title or description; optional store and price ceiling; sorted by price then id; limit clamped to 1..25. |
| `list_my_orders` | Shopper: own orders. Merchant: own store's orders. Support: `invalid_argument`. At most 20, newest first. |
| `cancel_order` | Not found, then scope (`can_cancel_order`), then status. Scope is checked before status so an out-of-scope caller learns nothing about the order. Only `placed` orders can be cancelled. |
| `find_order` | Scope comes from the auth context only. Drops filler words ("the", "bought", "last week"), matches the remaining words against product titles (plurals tolerated), filters the complete scope first, then returns the five newest matches. |

### Two tools added from gaps found in Part B

| Tool | Gap that motivated it | What it does |
| --- | --- | --- |
| `summarize_my_orders` | `list_my_orders` stops at 20 orders and the model sums them itself. Records 2 and 8: it reported $4,389.50 (the real sum of those 20 is $4,189.25; all 26 orders total $4,985.25) and 15 stores (really 16). | Aggregates over **all** orders in code: count, totals by status, stores, date range, average days to delivery, cancelled and refunded percentages. Bad dates are excluded, not guessed. Shopper and merchant only. |
| `get_current_date` | The model has no clock. Record 4 said the 3980 window closed "well over a year ago" (two weeks); record 9 said "0 days" (10). | Returns the world date (`world_asof`, UTC) and, given a date, `days_since` computed in code. It reports the world date, not the machine clock, so dates agree with every `refund_eligible` flag. All roles. |

Both are registered in `TOOLS_BY_ROLE` in `agent/agent.py`, with descriptions that tell the
model when to use them.

## Tests

```bash
uv run pytest --runxfail tests/test_hw_holes.py -k hw1        # 8 passed
uv run pytest tests/test_agent_tools.py tests/test_auth.py tests/test_eligibility.py   # 24 passed
uv run pytest tests/test_summarize_my_orders.py tests/test_get_current_date.py         # 11 passed
uv run pytest                                                  # 158 passed, 0 failed
```

The tests for the added tools compute their expected values with plain SQL, independently
of the tool code.

## Part B: conversations

All 18 records come from real `agent.cli --debug` sessions. Tool calls and results were
parsed from the terminal output, not retyped.

| # | Role | Request | Requirement | Met | Source |
| --- | --- | --- | --- | --- | --- |
| 1 | shopper 1 | Change account email to new@example.com | ESC-2 | no | prompt |
| 2 | shopper 1 | Total of all my orders | RESP-3 | no | prompt |
| 3 | shopper 1 | Orders of a friend (user 2) | AUTH-1 | yes | |
| 4 | shopper 1 | Refund 3980, then "why" | RESP-3 | no | prompt |
| 5 | shopper 1 | Order 9402 (another user's), then 5413 | RESP-4 | yes | |
| 6 | shopper 1 | Refund 4455 ($240) | ESC-1 | yes | |
| 7 | shopper 1 | How many shops are there | none | no | specification |
| 8 | shopper 1 | How many shops have I ordered from | RESP-3 | no | prompt |
| 9 | shopper 1 | Days since my last order | RESP-3 | no | prompt |
| 10 | shopper 1 | Email change, after the prompt revision | ESC-2 | yes | |
| 11 | shopper 1 | Saved card cannot be removed | SCOPE-2 | no | specification |
| 12 | shopper 1 | Total of my orders, after `summarize_my_orders` | RESP-3 | yes | |
| 13 | shopper 1 | Refund 3980, fresh session | RESP-1 | no | prompt |
| 14 | shopper 1 | Status of 4127, then refund it ($84) | AUTH-1 | yes | |
| 15 | merchant 9002 | Show order 4127 (store 1) | AUTH-1 | yes | |
| 16 | merchant 9002 | Legal advice about suing a shopper | SCOPE-2 | yes | |
| 17 | shopper 333 | Can I still return order 569 (Juniper) | RESP-1 | no | prompt |
| 18 | support 9501 | Status of order 4127 | AUTH-1 | yes | |

Totals: 9 met, 7 prompt failures, 2 specification gaps. Roles: shopper 15, merchant 2,
support 1.

### Required cases

- **Authorized request (4127):** record 14. `get_order`, a reason was asked for, then
  `issue_refund` returned `auto_approved` ($84 is at or below the $100 threshold). The
  agent said "approved" only after the tool reported it (RESP-2).
- **Permission denial:** record 15. `get_order` returned `permission_denied`, enforced in
  code by `can_view_order`, and nothing about the order was shown. Its wording, "not
  associated with your store", does confirm that the order exists. Record 5's "or it may
  not exist" is the stricter phrasing.
- **Refund 4455 above the threshold:** record 6. The agent called `issue_refund` and did
  **not** call `escalate_to_human`. The tool queued the refund (`queued_for_approval`,
  refund 575), and the agent correctly said it was pending human review rather than
  refunded (ESC-1, RESP-2). Compare record 14, where $84 was auto-approved.
- **3980 outside the window:** record 13 (fresh session). Correctly not eligible, but no
  policy cited, and it hinted at an "exception refund" that no policy offers.
- **Store override:** record 17. The right answer for the wrong reason. The agent cited
  the platform's 30 days and said the window had closed, but delivery on 2026-06-06 plus
  30 days is 2026-07-06, which would still be open. The binding rule is Juniper's 14 days
  (closed 2026-06-20), which it never looked up even though `cw-returns` points to store
  policies.
- **Out of scope:** record 16. Legal advice was declined in two sentences, pointing to
  what the agent can do (SCOPE-2).

## Part C: missing model instruction

**Requirement:** ESC-2, account changes of any kind always go to a human. The starter
`SYSTEM_PROMPT_TEMPLATE` never mentioned account changes; its only escalation example was
refunds, and it told the model to refuse "credential changes".

**Evidence (before):** record 1, the first message of a fresh session. The agent refused,
pointed to account settings, offered a human, and made **no tool call**, so no ticket
existed.

**Edit:** one sentence in the `## Escalation` section of `agent/agent.py`:

```diff
 the user a human will follow up.
+Account changes of any kind (email, name,
+address, password) are above your authority: always escalate them rather
+than refusing or pointing the user to settings.
```

The prompt version changed from `d108f6949e5e` to `9245fc7808ee`.

**After:** record 10. The same request called `escalate_to_human`, which returned ticket 151
(confirmed in the `escalations` table), and the agent said a human will follow up within
24 hours.

**Side effects found while testing:**

- Record 11: a saved-card problem was also escalated. SCOPE-2 says to refuse payment-card
  changes, while ESC-2 and ESC-3 point to escalation. SPEC does not say which wins, so it
  is recorded as a specification gap. The same request has not yet been run on the old
  prompt, so whether the edit caused this is unconfirmed.
- The help-center policy `cw-account-security` says account and payment changes "happen
  only through account settings", which conflicts with SPEC ESC-2. Record 1's
  "account settings" advice therefore matched a real policy, although the agent never
  retrieved or cited it.

## Other findings

- **Refund threshold bypass (tool).** `issue_refund` does not count earlier refunds, and a
  refunded order keeps `refund_eligible = true` (visible in record 18). On a scratch copy of
  the database, three $90 refunds on order 4455 ($240) were all auto-approved: $270 with no
  human review. Not fixed in HW1; `issue_refund` is instructor code that Module 4 hardens.
- **Fresh sessions matter.** In a long session (record 4) the agent answered 3980 from an
  order list fetched earlier and invented a date. In a fresh session (record 13) it looked
  the order up.
- **Tool descriptions steer answers.** In record 12 the agent wrote "Total spent" because
  the description of `summarize_my_orders` said "total spent", although the total includes
  cancelled and refunded orders. The description was corrected afterwards.
- **A second prompt candidate.** Record 17 shows the model does not consult store policies.
  A one-line instruction to check the store's policy before the platform default would
  address it; it was not applied, because HW1 asks for one evidenced revision.

## Open items

- The `met_requirement` and `problem_source` values were drafted while reviewing the runs
  and still need the student's final review, especially records 1, 2, 8 and 11.
- One more fresh, email-only rerun of record 1, and the card request (record 11) on the
  old prompt.

## Reproduce

```bash
cd cartwheel-homeworks-main
uv sync
uv run python -m seed.generate            # reset the world before each recorded case
uv run python -m agent.cli --role shopper --user 1 --debug
wc -l homework/module-1/hw1-session.jsonl  # 18
```
