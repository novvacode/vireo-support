# Stage 2 findings: volume, workload, capacity, mis-routing

**Re-run:** `python -m src.stage2`. It writes every table and chart to `outputs/`, and the full console output is in
[outputs/stage2_output.txt](../outputs/stage2_output.txt). Every number below appears in that file.

**Data:** the cleaned analysis view from stage 1: 11,641 tickets, Jan 2025 – Jun 2026.
The 139 rows from 2024 are excluded because they fall outside the stated range (decision 2). All 139 are Billing & Payments,
so including them would raise Billing's share from 20.8% to 21.8%. That is the figure in Priya's email.

**Code map**
- Signals and the routing rule: [src/routing.py](../src/routing.py)
- Workload measures: [src/workload.py](../src/workload.py)
- Section numbers (§1–§5) below refer to the sections of [src/stage2.py](../src/stage2.py)

Tier 2 (Escalations & Warranty) is reported on its own and left out of every volume ranking (policy §6).

---

## Findings

### A. The chart Priya asked for

**F1. On her own measure, Billing is the second-largest queue, not "biggest by a mile".**
- Share of tickets by first-assigned team: Chat Frontline 26.0%, Billing 20.8%, Logistics 16.4%, Email Frontline 15.5%,
  Returns Desk 9.0%, Voice Frontline 7.7%, Tier 2 4.5%.
- Jan–Jun 2026 only: Billing 19.2%, Logistics 15.7%, Chat Frontline 27.6%.
- Among the specialist teams (Billing, Logistics, Returns), Billing is the largest.
- Code: §1; [monthly_by_assigned_team.csv](../outputs/monthly_by_assigned_team.csv) / [.png](../outputs/monthly_by_assigned_team.png), [monthly_by_category.csv](../outputs/monthly_by_category.csv) / [.png](../outputs/monthly_by_category.png).
- Caveat: Frontline teams are defined by channel, not topic, so comparing Billing with Chat Frontline mixes two kinds of queue.

### B. Who actually did the work

**F2. Counted by the resolving agent's team, Logistics is larger than Billing: 2,574 vs 1,798.**
- 696 Billing-assigned tickets (28.7%) were resolved by a Logistics agent.
- Logistics received 783 tickets from other teams in total; 696 of them came from Billing.
- Code: §2; [assigned_vs_resolver_totals.csv](../outputs/assigned_vs_resolver_totals.csv), [assigned_to_resolver_flow.csv](../outputs/assigned_to_resolver_flow.csv), [monthly_by_resolver_team.png](../outputs/monthly_by_resolver_team.png).
- Caveat: the roster is a single snapshot with no history (audit #7), so an agent who changed team would be counted under their current team.

### C. Mis-routing

**F3. 921 of 2,425 Billing-tagged tickets (38.0%) were delivery work.**
- 660 are high confidence and 261 medium.
- The share is stable over time (30.5%–45.5% by month) and the same in both systems (helpdesk 37.2%, legacy 39.3%).
- Signals used:
  - agent notes describing the work (AWB, courier, re-shipped, RTO, "not a billing issue", "parcel stuck"), excluding reverse-pickup and cancellation wording;
  - the resolving agent's team;
  - the customer's message, kept separate as a cross-check.
- How sure:
  - The rule matched my hand labels on a seeded random sample of 60 Billing tickets: 60/60, 95% CI 94–100%.
  - The customer's message agrees on 89.9% of the delivery-labelled tickets and on none of the billing-labelled ones.
  - Resolver team alone would have missed 5 of the 21 delivery tickets in the sample.
- Code: §5; [routing.py](../src/routing.py) `label_work_type`; [billing_work_type_by_resolver.csv](../outputs/billing_work_type_by_resolver.csv), [routing_rule_vs_hand_labels.csv](../outputs/routing_rule_vs_hand_labels.csv), hand labels in [labels/](../labels/billing_sample60_hand_labels.csv).
- Caveat: I wrote the rule and the hand labels after reading this data's notes, so the 60/60 is an optimistic upper bound. An independent labeller is the next check.

**F4. 261 of those delivery tickets never left Billing: Billing agents chased the courier themselves.**
- This is the medium-confidence group: notes describe delivery work, but a Billing agent resolved it.
- It means part of Billing's workload is real effort, but it is Logistics' work.
- Code: §5, `billing_work_type_by_resolver.csv`, the "delivery / medium" row.
- Caveat: medium confidence rests on notes alone. In the hand-checked sample, all 5 such tickets were genuine delivery work.

**F5. Moving the delivery work to its owner (policy §6) flips the specialist ranking.**

| Basis | Logistics | Billing | Logistics per agent | Billing per agent |
|---|---:|---:|---:|---:|
| Bot tag (her chart) | 1,905 | 2,425 | 381 | 606 |
| Resolving agent's team | 2,574 | 1,798 | 515 | 450 |
| Owner of the work (high + medium moved) | **2,826** | **1,504** | **565** | **376** |
| Owner, high-confidence moves only | 2,565 | 1,765 | 513 | 441 |

- Tier 1 order on the owner basis: Chat Frontline, Logistics, Email Frontline, Billing, Returns Desk, Voice Frontline.
- Per agent, Logistics is first on every basis except the bot tag.
- Code: §5; [team_ranking_by_view.csv](../outputs/team_ranking_by_view.csv), [team_ranking_by_view.png](../outputs/team_ranking_by_view.png).
- Caveat: only Billing-tagged tickets are re-assigned. "Other"-tagged delivery work (F16) is left where it is, so Logistics' figure is conservative.

### D. Workload, not just volume

**F6. Billing's high breach rate comes from mis-routed tickets. Genuine billing work breaches at a normal rate.**
- Billing-assigned breach rate is 19.7%, against 5.7%–11.0% for the other Tier 1 teams.
- Split by work type:

| Group | Breach rate |
|---|---:|
| Billing-tagged, billing work | 9.2% |
| Billing-tagged, delivery work | **36.3%** |
| Logistics-tagged delivery (bot got it right) | 9.7% |

- That is 334 breaches, or Rs 1,16,900 in credits. Against the 9.7% baseline, 245 of them are excess.
- Code: §3 and §5; [misrouting_outcomes.csv](../outputs/misrouting_outcomes.csv), [workload_by_assigned_team.csv](../outputs/workload_by_assigned_team.csv).
- Caveat: 222 chat tickets have a 0-minute first response (audit #13), so breach rates may be slightly understated everywhere.

**F7. Transfers are a mis-routing cost.**
- Helpdesk transfers per ticket:

| Group | Transfers per ticket |
|---|---:|
| Delivery work tagged Billing | 0.919 |
| Billing work tagged Billing | 0.093 |
| Logistics-tagged | 0.091 |

- Over the 10 helpdesk months, delivery work tagged Billing cost 533 transfers, or Rs 1,62,565.
- Code: §5; `misrouting_outcomes.csv`.
- Caveats:
  - Helpdesk rows only; legacy blanks are unknown, never 0.
  - 341 helpdesk tickets changed team with transfers = 0 (audit #10), so the true number is probably higher.

**F8. Customers whose delivery problem was tagged Billing are the least satisfied group.**
- CSAT 2.35 (n=432), against 3.53 for genuine billing and 3.13 for correctly tagged delivery.
- Code: §5; `misrouting_outcomes.csv`.
- Caveat: about 45% respond and blanks are excluded. Non-response may not be random.

**F9. Mis-routing nearly doubles resolution time, and Logistics' "day plus" is confirmed.**
- Median creation-to-resolution: 48.4 h for delivery tickets tagged Billing, 25.8 h when the bot tagged them Delivery.
- Median handle time (first response to resolution) for Logistics-assigned tickets is 24.4 h, which bears out Neha's "a day plus".
- Code: §3 and §5; `workload_by_assigned_team.csv`, `misrouting_outcomes.csv`.
- Caveat: handle time is elapsed time, much of it waiting on couriers. It is not agent effort, so it can't size staffing on its own.

**F10. Mis-routing costs about Rs 2.3 lakh a year, about a quarter of the Rs 9 lakh for two hires.**
- Jan–Jun 2026: 314 delivery tickets tagged Billing (52 a month).
- Avoidable cost in that half-year: transfers Rs 86,620 + excess breach credits Rs 30,045 = Rs 1,16,665, or about Rs 2,33,330 a year.
- Code: §5, the line starting "avoidable cost".
- Caveats:
  - The estimate excludes agent re-handling time and CSAT damage, so it is a floor.
  - Fixing routing does not by itself remove the delivery work; that work moves to Logistics.

**F11. Repeat contacts depend heavily on how "same issue" is defined, but Billing's are in its own work.**
- Policy §10 rate is 4.3% if "same issue" means customer + category, and 24.0% if it means customer + SKU.
- Most customer+SKU "repeats" are about a different category, so 24.0% overstates.
- On the customer + category basis, Billing-assigned tickets are highest at 8.8% (Logistics 5.3%, others 1.1%–3.1%).
- Within Billing, genuine billing work repeats at 11.4% and mis-routed delivery work at 5.2%. Notes often promise "refund in 5–7 working days", and customers chase.
- Code: §3 and §5; [workload.py](../src/workload.py) `flag_repeat_contacts`; `misrouting_outcomes.csv`.
- Caveat: the customer+category key misses a repeat that the bot tags differently the second time. Treat both rates as bounds.

**F12. Channel mix and policy cost.**
- Billing-assigned tickets are 53% chat, 27% email, 9% voice, 10% social.
- Average policy cost per ticket (contact + transfers + breach credits): Billing Rs 404, Logistics Rs 331, Chat Frontline Rs 266. Voice Frontline is Rs 568, driven by the Rs 520 voice cost.
- Billing's premium over its contact cost comes from breaches and transfers (F6, F7).
- Code: §3; `workload_by_assigned_team.csv` (columns `chat`…`social`, `cost_per_ticket_inr`).
- Caveat: these are policy planning rates, not actuals.

### E. Capacity

**F13. Per agent, Logistics carries the most once work is counted by owner. But no team looks near capacity in this export.**
- Jan–Jun 2026, tickets per agent per month:

| Basis | Logistics | Billing |
|---|---:|---:|
| Bot tag | 24.5 | 37.5 |
| Resolving team | 32.1 | 28.8 |
| Owner of the work | **35.0** | **24.4** |

- In absolute terms that is 0.65–1.7 tickets per agent per 8-hour shift. Policy cost converted to hours (Rs ÷ 165/hour) comes to at most 48% of available hours, even on the bot-tag basis.
- Code: §4; [capacity_per_agent_jan_jun_2026.csv](../outputs/capacity_per_agent_jan_jun_2026.csv), [roster_team_shift.csv](../outputs/roster_team_shift.csv).
- Caveats:
  - Assumes 22 shifts per agent a month (decision 13).
  - Either this export is not all of the agents' work, or there is real slack. The data can't tell which, so absolute utilisation is inconclusive.

**F14. Breaches do not cluster by shift or hour. They cluster by mis-routing.**
- Billing-assigned breach rate: 18.0% for tickets created at night, 19.7% day, 20.1% morning, so missing night cover doesn't explain it.
- By channel, Billing chat tickets breach 27.4% against the 15-minute target. Chat is where a misroute is hit by the shortest SLA.
- By resolving agent's shift: Logistics Morning 18.1% and Day 14.4%; Billing Morning 16.4% and Day 9.3%.
- Code: §4; [breach_rate_by_team_hour.png](../outputs/breach_rate_by_team_hour.png), `breach_rate_team_by_created_shift.csv`, `breach_rate_by_resolver_team_shift.csv`, `breach_rate_team_by_channel.csv`.
- Caveat: some hour cells hold only a handful of tickets (e.g. Returns Desk at 02:00), so ignore single dark cells.

**F15. Billing's Day shift is one person.**
- One agent covers 14:00–22:00 and resolves 49.5 tickets a month, against 21.9 for each of the three Morning agents.
- Code: §4; [tickets_per_agent_month_jan_jun_2026.csv](../outputs/tickets_per_agent_month_jan_jun_2026.csv).
- Caveat: these are single-agent figures; the gap could be individual speed rather than demand.

### F. Other things noticed

**F16. A second mis-tagging source: 419 of 1,622 "Other"-tagged tickets (25.8%) are delivery work.**
- Most are resolved in Frontline: Chat 231, Email 113, Voice 53. They are not moved in F5.
- Code: §5, the "'Other'-tagged" line.
- Caveat: same rule and same optimism as F3, and not hand-checked for this category.

**F17. Tier 2 (Escalations & Warranty) is reported separately.**
- 525 assigned and 650 resolved; median handle time 121 h; breach rate 8.2%; CSAT 3.28.
- Not compared with Tier 1, per policy §6.
- Code: §3; `workload_by_*.csv`, where `tier` = "Tier 2".
- Caveat: it should be measured on resolution days, which needs a dedicated view not built yet.

---

## What each finding supports

| Supports | Findings | Why |
|---|---|---|
| **Hiring into Billing** | F1; partly F4 and F11 | Only the bot-tag count (her chart) puts Billing first. F4 shows Billing agents doing real extra work, but it is delivery work. F11 shows genuine billing repeats, which points to a refund-communication fix more than headcount. |
| **Hiring into Logistics** | F2, F5, F13 (relative), partly F9 | Counted by who did the work or who should own it, Logistics is the busiest specialist team in total and per agent: 35.0 vs 24.4 tickets per agent a month in 2026. Its day-plus resolution times fit, but they are mostly courier waiting time. |
| **Fixing routing** | F3, F6, F7, F8, F9, F10, F16 | Over a third of Billing's queue is mis-tagged delivery work. That work accounts for Billing's breach excess, most of its transfers, the worst CSAT, and about Rs 2.3 lakh a year in avoidable cost. Genuine billing work performs normally. |
| **Inconclusive** | F11 (definition), F12, F13 (absolute), F14, F15, F17 | Repeat rate depends on the "same issue" definition. Absolute capacity implies slack the data can't explain. Breaches show no shift pattern. Day-shift figures rest on single agents. Tier 2 isn't comparable. |

Not concluded here (left for the memo): whether to hire at all. If Logistics gets the work it owns, it needs capacity
for 52 more tickets a month (2026 rate). Whether that needs two people, given F13's low absolute load, is still open.
