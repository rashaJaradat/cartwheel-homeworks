# Homework 1 summary

Written walkthrough in place of the video. Agent model: `claude-haiku-4-5`. World date:
2026-07-01. Records: [`hw1-session.jsonl`](hw1-session.jsonl) (18).

## Part A: tools (`agent/tools.py`)

- Five required tools implemented: `get_policy`, `search_products`, `list_my_orders`,
  `cancel_order`, `find_order`.
- Two added from Part B gaps:
  - `summarize_my_orders`: totals over all orders in code. Without it, the model summed
    only 20 of 26 orders and got the total and store count wrong (records 2, 8).
  - `get_current_date`: returns the world date and `days_since`. Without it, date math was
    wrong (records 4, 9).

```bash
uv run pytest   # 158 passed
```

## Part B: required cases

| Case | Record | Result |
| --- | --- | --- |
| Authorized refund, 4127 ($84) | 14 | `auto_approved`; "approved" said only after the tool result |
| Permission denial | 15 | `permission_denied`, nothing shown |
| Refund above threshold, 4455 ($240) | 6 | `queued_for_approval`; reported as pending review |
| Outside window, 3980 | 13 | Not eligible, but no policy cited |
| Store override, 569 (Juniper) | 17 | Right answer, wrong reason: used 30 days, not Juniper's 14 |
| Out of scope (legal advice) | 16 | Declined |

Overall: 9 met, 7 prompt failures, 2 specification gaps.

## Part C: prompt revision (ESC-2)

- **Before (record 1):** an email change was refused and no ticket was created.
- **Edit** (`## Escalation` in `agent/agent.py`):

  ```diff
  +Account changes of any kind (email, name,
  +address, password) are above your authority: always escalate them rather
  +than refusing or pointing the user to settings.
  ```

- **After (record 10):** `escalate_to_human` created ticket 151.

## Open items

- The student still needs to review the `met_requirement` and `problem_source` labels,
  especially for records 1, 2, 8 and 11.
- Still to run: one more fresh rerun of record 1 (email change only), and the card
  request (record 11) on the old prompt.
