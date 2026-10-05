# Data audit: load, audit, clean

Every count below is printed by `python -m src.audit` (full output saved in [audit_output.txt](audit_output.txt)).
The cleaning functions are in [src/clean.py](../src/clean.py) and the tests in [tests/test_clean.py](../tests/test_clean.py).
Rows are never deleted. Each fix either corrects a value (the raw value is kept in a `*_raw` column) or adds a flag.
`analysis_view()` then drops only two kinds of row: those outside the stated date range and duplicate copies.

"Headline" here means the numbers later stages will rely on: ticket count, Billing and Logistics share of
`assigned_team`, median resolution hours (resolved/closed tickets), first-response breach rate and mean CSAT.
This stage does not interpret them.

## Before / after

| | Rows | Billing share | Logistics share | Median resolution | Negative resolutions | FR breach | CSAT mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| Raw export | 11,780 | 21.8% | 16.2% | 1.32 h | 2,379 | 11.4% | 3.375 |
| Cleaned analysis view | 11,641 | 20.8% | 16.4% | 2.03 h | 0 | 11.1% | 3.384 |

## Issues

| # | Issue | Rows | How detected | What I did | How much it moves the headline |
|---|---|---:|---|---|---|
| 1 | **Legacy `resolved_at` is UTC, everything else IST** | 3,853 legacy rows with a resolved_at (2,379 had resolved < created; 2,575 had resolved < first response) | Negative durations occur only in legacy rows (helpdesk has 0). Policy §9 says legacy resolution times were rebuilt from a UTC log. | `shift_legacy_resolved_to_ist`: +5h30m on **every** legacy resolved_at, not just the negative ones. Raw value kept in `resolved_at_raw`. | Negative durations go from 2,379 to 0. Median resolution goes from 1.32 h to 2.05 h. Check: after the shift, legacy medians by channel match helpdesk (chat 0.63 vs 0.60 h, email 5.20 vs 4.97, social 2.28 vs 2.52, voice 1.31 vs 1.20). Team shares are unchanged. |
| 2 | **Rows outside Jan 2025 – Jun 2026** | 139 (all legacy_fd, 20 Jun – 31 Dec 2024) | `created_at` compared with the range stated in the data README | `flag_out_of_range` sets `in_scope=False`, and the analysis view excludes these rows. | **New: all 139 are tagged Billing & Payments.** Keeping them inflates Billing alone: its share goes from 20.8% to 21.8%, and Logistics from 16.4% to 16.2%. The client's "22%" comes from the unfiltered file. |
| 3 | **Re-imported duplicate tickets** (policy §9 warns of these) | **0 found** | Four searches: (a) same customer + SKU, text similarity ≥ 0.85, created within 48 h or exactly 5h30m apart; (b) same customer, any SKU, all 3,655 cross-system pairs: 0 exactly 5h30m apart, 1 with text ≥ 0.85 (a stock phrase, different SKU, 9 months apart); (c) identical normalised text across systems, ignoring customer: 430 pairs, only 1 with the same customer (the stock phrase from (b)); (d) 181 order_ids appear on tickets in both systems (293 pairs): different issues, ≥ 3.4 days apart, max text similarity 0.71. Ticket ID ranges are disjoint (legacy TK-240001–245080, helpdesk TK-245081–254672) and in time order in each system. | `find_duplicate_candidates` + `flag_duplicates` (would keep the helpdesk copy). Nothing flagged. The 12 "same customer+SKU within 1 h" pairs were read by eye: they are different issues (max text similarity 0.62). | None. The policy's warning does not show up in this export. If re-imports exist, they share no customer, text or timing signal we can see. |
| 4 | **Blank `order_id`** | 4,017 (34.1%) | Count of blanks | `recover_order_id_from_message`: 197 recovered from a VRnnnnnn id typed in the message (accepted only if the order's customer and SKU match). `join_orders` fallback on customer + SKU: 3,171 unique matches; **649 ambiguous** (538 with 2 candidates, 98 with 3, 5 with 4, 8 with 5), which are flagged `fallback_ambiguous` and left unjoined. 0 unmatched. | Confident order link goes from 65.9% to 94.5% of tickets. Affects only order/lot/refund-per-order analysis, not team volume. |
| 5 | **Ticket created before its linked order** (new) | 302 | `order_date` > ticket date after the join | `flag_ticket_before_order`: **201 "presale"** (gap ≤ 14 days; 166 of them Product Enquiry, so plausibly pre-purchase questions) and **101 "implausible"** (gap > 14 days, up to 481; 79 of these are on an explicit order_id). Flag only. | Volume unaffected. Lot/product analysis should drop the 101 implausible links. |
| 6 | **Two agents share the name "Om Sharma"** | A3006 Chat Frontline (136 tickets), A3029 Logistics (629 tickets) | Duplicate names in the roster | `join_agents` joins only on agent_id and raises if any ticket matches 0 or 2+ roster rows. | Joining by name would move up to 765 tickets between Chat Frontline and Logistics. |
| 7 | **Roster has no history** (new) | 44 rows = 44 agents, no `to_date` set | Roster inspection | `join_agents` handles from/to dates, but there is nothing to resolve: every ticket postdates its agent's from_date. | None now. Caveat: if anyone changed team before this export, the roster shows only the current team. |
| 8 | **Ticket resolved by a team other than the one first assigned** | 2,063 tickets; **795** Billing-assigned tickets resolved by a Logistics agent | `assigned_team` compared with the resolving agent's roster team | `flag_resolver_team_mismatch` adds `resolved_by_other_team` and `resolver_team`. Not "fixed", because it is a fact about routing, not an error. | Not applied yet. Counting by resolver instead of first assignment changes team volumes, which is a later-stage question. |
| 9 | **`transfers` blank on all legacy rows** | 4,052 | Blank by source_system | Kept as NA (nullable Int64), never 0. | Treating blanks as 0 would give a mean of 0.110 instead of 0.168 (helpdesk only). |
| 10 | **`transfers` = 0 although another team resolved the ticket** (new) | 341 of 1,293 helpdesk tickets resolved by another team; plus 138 same-team tickets with transfers > 0 (possibly round trips) | Cross-check of #8 against `transfers` | `transfers_inconsistent` flag. Not corrected. | Helpdesk transfer counts are probably a **lower bound** on hand-offs. |
| 11 | **Legacy tickets still open/pending** (new) | 199 | Legacy rows with status open/pending although that tool was retired in Sep 2025 | `stale_legacy_open` flag. Kept in volume (they were real contacts) and excluded from any resolution-time measure (no resolved_at). | Volume unaffected. |
| 12 | **CSAT score on open/pending tickets** (new) | 247 | Policy §8: the survey is sent on resolution | `csat_on_unresolved` flag. Kept. | Small. Blanks stay NA: mean 3.375, whereas blanks-as-0 would give 1.531. |
| 13 | **First response at 0 minutes** (new) | 222, all chat | `first_response_at == created_at` | `fr_zero_minutes` flag. Possibly a bot reply logged as "human". | These count as non-breaches, so the breach rate could be slightly understated. |
| 14 | **Legacy refund "native unit"** (policy §9) | 656 legacy refunds | Median refund ÷ retail price: 0.90 in both systems. Ranges are Rs 32–13,998 legacy and Rs 36–12,998 helpdesk. 0 refunds exceed the linked order value. | `legacy_refund_scale` check only, **no conversion**. | None. Confirms the CLAUDE.md first look. |
| 15 | **GW-OTHER refunds above the Rs 500 goodwill cap** (new) | 29 of 35 | Policy §5 cap | `goodwill_over_cap` flag. The code is labelled "Goodwill / Other", so some may be non-goodwill refunds filed under it. | Small money; a policy-compliance note, not a cleaning fix. |
| 16 | **Refund and replacement on the same order** (policy §5) | 2 on the same ticket; **78 orders** using explicit/message order ids; 131 orders when unique fallback links are included | Checked per order across all of its tickets | `order_refund_and_replacement` flag. | A per-ticket check would have found 2 instead of 78. |
| 17 | **Volume step-up in Aug 2025** | Legacy monthly count rises from ~460 to 695 | Monthly counts | None needed: the rise is the Pulse 2 launch (VA-EB-PL2 tickets go from 58 to 217 a month), not a migration artefact. | None. |
| 18 | **Multi-line messages** | 11,780 rows in 34,211 physical lines | Line count vs parsed rows | `pandas.read_csv` with `keep_default_na=False, na_values=[""]`, so only empty cells are missing. | Checked: pandas' default NA list would have blanked 0 cells here, but the safe setting stays. |

## Checking the "known facts" in CLAUDE.md

Correct as stated: 11,780 rows; 139 rows from 2024 (all legacy); helpdesk has 7,728 rows from 2025-09-14 and legacy has 4,052;
2,379 legacy negative durations and 0 in helpdesk; the +5h30m shift fixes them; first_response_at is fine; transfers are blank on legacy;
Billing 2,564 (21.8%) and Logistics 1,905 (16.2%); 795 Billing tickets resolved by Logistics; Billing transfers 0.41 vs 0.07–0.14 for other teams;
overall breach ~11% (11.4%); roster of 44 with the two Om Sharmas; CSAT response ~45% (45.4%); order_id blank ~34% (34.1%); 1,894 refunds;
no legacy refund scale issue; ~730–850 tickets a month in 2026 (733–832) and ~182 a week.

Partly wrong or incomplete:
- **"category and assigned_team line up almost one-to-one."** Four categories map exactly one-to-one: Billing & Payments → Billing,
  Delivery & Shipping → Logistics, Returns & Refunds → Returns Desk, Warranty & Repair → Escalations & Warranty. The other
  **seven categories all go to Frontline**, split by channel (chat + social → Chat, email → Email, voice → Voice). The mapping is
  exact, not "almost", but Frontline teams are defined by channel, not by category.
- **"Breach rate ~6–11% for other teams."** The actual range is 4.8% (Voice) to 11.8% (Email). Returns Desk is 11.6%. Billing is 19.2%, not ~20%.
- **The 139 out-of-range rows** are not just old: every one of them is Billing & Payments (see #2).
- **Re-imported duplicates** (from the policy, repeated in the brief): none detectable in this export (see #3).
- **Not yet verified:** "~31% of Billing messages contain delivery language". That needs the classifier stage.
