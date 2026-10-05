# Project: Vireo Audio support-ticket analysis (hiring task "Set E")

## Who and what
Client: Priya Raman, Head of Customer Experience, Vireo Audio (Bengaluru consumer audio/wearables brand, 44 support agents, Bengaluru + Indore, three shifts).
Her ask (verbatim intent): auto-categorise support tickets, give a monthly chart by category and by team, "whichever team has the most volume gets the next two hires." She has half-promised the hires to Billing. Finance (Arjun Mehta) says two hires is about Rs 9 lakh a year, wants the volume case in writing, and would rather fix a process than hire into it. Support Ops (Neha Kulkarni) believes Logistics is the team actually drowning. Helpdesk admin (Sameer Qureshi) supplied the exports.

## Deliverables (all required)
1. A working AI-assisted tool that runs from the README on a clean machine. Small and working beats large and broken.
2. One business goal stated as a number with a rupee value (e.g. "cut X from A% to B%, worth about Rs Y a quarter"). The number must be found in the data.
3. Evidence the tool works: how we know the output is correct, how often it is not, what kind of case it gets wrong.
4. A one-page non-technical memo to Priya (about 11 minutes of reading at most; aim for under 500 words plus one chart).
5. Notes for a screen recording (<= 3 min): prompts used, what changed between versions, what was thrown away.
6. Answers to the submission form (questions listed in docs/form_questions.md).

## Ground rules
- No invented numbers. Every figure in the memo or README must come from code in this repo that re-runs from the raw files in data/.
- Record every judgment call in docs/decisions.md as: Decision / Why / What it changes.
- If something in the brief is unclear: decide, write down the decision and the reason. There is nobody to ask.
- Python 3.11, pinned requirements.txt, one command to run the tool. The default path must work with no API key and no network. Any paid LLM call is optional, cached, and its cost is logged.
- Keep a running cost log (tokens and rupees) for any paid API use. If none, say none.
- Time-box: total effort target ~5 hours. Prefer cutting scope and writing down what was cut and why.
- After each stage, append 3 lines to docs/AI_LOG.md (asked / changed or rejected / discarded), and commit.

## Data facts from a quick first look (UNVERIFIED - re-derive each in code before relying on it)
- tickets.csv has 11,780 rows (the file has ~34k physical lines because messages contain line breaks; use a real CSV parser).
- Stated range is Jan 2025 to Jun 2026, but 139 rows (all legacy_fd) are dated Jun-Dec 2024. Decide and document how to treat them.
- source_system: helpdesk 7,728 rows (from 2025-09-14), legacy_fd 4,052 rows.
- Legacy resolved_at is in UTC while everything else is IST. In legacy rows 2,379 tickets show resolved_at earlier than created_at; helpdesk rows have 0. Shift legacy resolved_at by +5h30m and re-check. first_response_at looked fine in both systems.
- transfers is blank for every legacy row (unknown, not zero). Only helpdesk rows have it.
- category and assigned_team line up almost one-to-one. Billing & Payments = 2,564 tickets (21.8%), Delivery & Shipping/Logistics = 1,905 (16.2%) - these match the percentages in the client's emails.
- The category tag is set by an intake bot from the customer's opening answers; agents rarely re-tag.
- Many Billing-tagged messages are really delivery problems ("paid but not delivered", "payment done, order status not moved"). About 31% of Billing-tagged messages contain delivery-type language; about 795 of 2,564 Billing-assigned tickets were resolved by an agent whose team is Logistics; agent notes often say "misrouted - dlvry. xfer to logistics".
- In helpdesk rows Billing-assigned tickets average ~0.41 transfers vs ~0.07-0.14 for other teams; first-response breach rate for Billing is ~20% vs ~6-11% elsewhere.
- SLA credit: every first-response breach issues Rs 350. Targets: chat 15 min, voice 2 h, social 4 h, email 8 h. Rough overall breach rate ~11%.
- Roster: 44 agents (44 rows, 44 ids). Billing has only 4 agents; Chat Frontline 15; Email 7; Escalations & Warranty (Tier 2) 6; Logistics 5; Returns Desk 3; Voice 4. Two agents share the display name "Om Sharma": always use agent_id.
- Policy section 6: Tier 2 (Escalations & Warranty) must not be compared with Tier 1 on volume.
- CSAT: ~45% respond; blank = no response, exclude from averages, never treat as 0. Auto-closed tickets (status closed) are surveyed too.
- order_id is blank on ~34% of tickets; fallback join is customer_id + product_sku and can match more than one order.
- Refunds: 1,894 refund rows. Check legacy refund amounts for unit problems (policy section 9 says legacy used its own native unit) - a first look found no obvious scale difference, so verify before assuming. Policy says nobody gets both a refund and a replacement for the same order; check per order, not just per ticket.
- The final form asks about cost at "roughly 650 tickets a week", but the file shows roughly 730-850 tickets a month recently (about 170-195 a week). Flag this discrepancy and show cost both ways.
- Possible product/lot signal: some lots (e.g. Pulse 2, Nexa 2) show fault-ticket rates well above average per order. Exploratory only; do not let it derail the main question.

## Leads to test (hypotheses, not conclusions)
1. Billing's "biggest queue" status is inflated by delivery tickets mis-tagged by the intake bot, which cost transfers (Rs 305 each), SLA credits (Rs 350) and re-handling.
2. Logistics may be the team that is actually busiest once work is counted by who really did it.
3. The cheaper fix may be routing/tagging, not hiring - but the data decides, not this list.
4. Volume is not workload: channel mix, handle time, transfers, repeat contacts and Tier 2 multi-touch work all matter.