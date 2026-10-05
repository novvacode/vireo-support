# Decisions

Format: Decision / Why / What it changes.

## Stage 1: load, audit, clean (2026-10-05)

1. **Shift every legacy `resolved_at` by +5h30m, not just the negative ones.**
   Why: policy §9 says legacy resolution times were rebuilt from a UTC log. Shifting only the "impossible" rows would leave the rest wrong in a way we can't see. After the shift, legacy median resolution by channel matches helpdesk.
   What it changes: negative durations go from 2,379 to 0; median resolution goes from 1.32 h to 2.05 h. Raw value kept in `resolved_at_raw`.

2. **Exclude the 139 rows dated Jun–Dec 2024 from analysis (flag `in_scope=False`, don't delete).**
   Why: the data README states the range as 1 Jan 2025 – 30 Jun 2026, and these 139 rows are all legacy and all Billing & Payments, so a partial 2024 tail would distort one team only.
   What it changes: analysis rows go from 11,780 to 11,641; Billing share from 21.8% to 20.8%.

3. **Duplicate rule: same customer + SKU, text similarity ≥ 0.85, created within 48 h or exactly 5h30m apart. Keep the helpdesk copy.**
   Why: the policy warns of re-imports across systems. A re-import should repeat the customer, SKU and opening text. Same customer+SKU within an hour but with different text turned out (by reading them) to be separate issues. Keeping the helpdesk copy preserves `transfers`.
   What it changes: nothing today (0 pairs found). The function stays in the pipeline in case a future export has them.

4. **Order fallback join: use customer_id + SKU only when it gives exactly one order; flag 2+ as `fallback_ambiguous` and leave them unjoined.**
   Why: the brief says not to guess. Before the fallback, an order id the customer typed in the message is used if it belongs to the same customer and SKU.
   What it changes: confident order link goes from 65.9% to 94.5%; 649 tickets stay ambiguous.

5. **Tickets created before their linked order: flag, don't drop.** Gap ≤ 14 days = "presale", > 14 days = "implausible".
   Why: short gaps on Product Enquiry tickets look like pre-purchase questions. Long gaps mean the link is probably wrong. Neither affects team volume.
   What it changes: order/lot analysis should exclude the 101 "implausible" links.

6. **Join agents on agent_id with date-effective roster rows; fail loudly on 0 or 2+ matches.**
   Why: two agents are named Om Sharma (Chat vs Logistics), and the roster format allows several rows per agent.
   What it changes: none of the 765 tickets those two agents resolved can be mis-attributed.

7. **Keep `transfers` and `csat_score` as nullable integers; blanks are never 0.**
   Why: blank transfers means the field didn't exist (legacy); blank CSAT means no response (policy §8).
   What it changes: mean CSAT is 3.375, where blanks-as-0 would give 1.531; mean transfers is 0.168 (helpdesk) where blanks-as-0 would give 0.110.

8. **No currency conversion for legacy refunds.**
   Why: median refund ÷ retail price is 0.90 in both systems and no refund exceeds its order value, so the "native unit" in policy §9 is evidently rupees.
   What it changes: nothing. Documented so it isn't re-litigated.

9. **Anomalies that are facts about the operation, not data errors, are flags only:** resolved by another team, transfers = 0 despite a team change, stale legacy open tickets, CSAT on unresolved tickets, 0-minute first responses, goodwill over cap, refund + replacement on the same order.
   Why: this stage is about clean data, not conclusions. Later stages decide how to use each flag.
   What it changes: nothing yet.

10. **Python 3.10 used locally; code kept 3.10/3.11-compatible.**
    Why: this machine has only Python 3.10 (no 3.11 available via `py`). Nothing used is 3.11-specific.
    What it changes: README must say "tested on 3.10; 3.11 expected to work" until it is run on 3.11.

11. **Raw files are found by suffix (`*-tickets.csv`) rather than renamed.**
    Why: the pack ships with UUID-prefixed names; leaving `data/` untouched keeps it identical to what the client sent.
    What it changes: `src/load.find_file` errors if zero or several files match.

## Stage 2: volume, workload, capacity, mis-routing (2026-10-05)

12. **"True owner" = policy §6 owner of the work, judged from agent notes; only Billing-tagged tickets are re-assigned in the main ranking.**
    Why: the brief asks specifically about Billing. Notes are written after the work, so they are the best evidence of what the ticket was. "Other"-tagged delivery work (419 tickets) is reported but not moved, to keep the comparison conservative.
    What it changes: Logistics 2,826 vs Billing 1,504 (high + medium); 2,565 vs 1,765 (high only).

13. **Capacity assumes 22 shifts per agent a month (5-day week) at 8 h (policy §4).**
    Why: the roster has no working-day or leave data. 22 is a standard Indian 5-day-week figure.
    What it changes: absolute "hours available" only. Relative per-agent comparisons don't depend on it.

14. **Repeat contact = same customer, next contact within 30 days of the previous one's resolution (or of its creation, if it was never resolved). "Same issue" is reported two ways: customer + SKU (upper bound) and customer + category (lower bound).**
    Why: policy §10 doesn't define "same issue". 87% of customer+SKU repeats have a different category, so that key overstates. The category key misses re-tagged repeats.
    What it changes: overall 24.0% vs 4.3%; team rankings are reported on the category key.

15. **Workload cost = policy §4 contact cost by channel + Rs 305 per known transfer + Rs 350 per breach. Legacy transfers add nothing (unknown, not zero).**
    Why: the brief requires policy costs. Imputing legacy transfers would invent numbers.
    What it changes: transfer cost is a lower bound before Sep 2025.

16. **Mis-routing cost is stated as Jan–Jun 2026 × 2: transfers + breaches above the Logistics-tagged breach rate.**
    Why: the most recent six months, all on helpdesk (transfers known), reflect current routing. Excess over the correctly-routed rate avoids counting breaches that would have happened anyway.
    What it changes: about Rs 2.33 lakh a year. Re-handling time and CSAT are excluded, so it is a floor.

17. **Hand-label check: 60 Billing-tagged tickets drawn with `sample(60, random_state=2026)` and labelled delivery / not-delivery from the notes (message if notes were empty), stored in `labels/`.**
    Why: the brief asks how sure we are. The script asserts the label file matches the seeded draw, so it can't silently drift.
    What it changes: rule accuracy 60/60 (95% CI 94–100%). Flagged as optimistic because the same person wrote the rule and the labels.

18. **Charts are static PNG small multiples (one panel per team or category), with 3 series at most in comparison charts.**
    Why: 11 categories on one line chart can't be read, and the reference palette validates only 3 series all-pairs.
    What it changes: presentation only.

## Stage 3–4: categoriser and validation (2026-10-05)

19. **Taxonomy: 13 need-based categories + Unclear. Owners as approved: Cancel/change → Frontline; Refund not received → Returns Desk, except a refund for a double charge → Payment (Billing).**
    Why: designed from 208 real messages. Policy §6 names no owner for cancellations, and Frontline resolves most of them today.
    What it changes: owner_team in every output.

20. **The categoriser reads only customer_message (plus channel for the Frontline owner and date for the chart). agent_notes is excluded at read time and a test proves it.**
    Why: notes are written after the work and would leak the answer.
    What it changes: notes can serve as an independent weak check.

21. **Cheap-first: rules → TF-IDF trained at run time on rule-confident rows → optional LLM below 0.6 confidence. The LLM is off by default and uses claude-opus-5-5 at low effort.**
    Why: the brief requires an offline default. Shipping no model file keeps the repo small. The model follows the API guidance default, and `VIREO_LLM_MODEL` can override it.
    What it changes: about 4% of tickets end as Unclear offline (456 of 11,780 in the v2 run).

22. **USD→INR for the LLM cost log defaults to 88 (env `VIREO_USD_INR`).**
    Why: no rate is given in the brief.
    What it changes: the cost_inr column only. No paid calls have been made.

23. **Validation labels are AI-adjudicated (by Claude), blind to bot tag, prediction, notes and stratum, and committed before scoring.**
    Why: the user asked for no manual labelling, and there is no human ground truth.
    What it changes: accuracy figures are upper-bound estimates; see docs/validation.md §2.5.

24. **Owner-team accuracy is reported alongside category accuracy, and a wrong owner counts as a "costly" error.**
    Why: routing is the decision with a rupee cost (transfer Rs 305, breach risk). Category mix-ups inside one owner team cost nothing.
    What it changes: the headline comparison with the bot.

25. **Experiment-1 results are kept unchanged. Fixes motivated by them (rules v2) were evaluated only on a fresh gold v2 that excludes dev, gold v1 and the 30 pool tickets viewed while building v2.**
    Why: re-scoring a tuned model on the set it was tuned on is contamination.
    What it changes: v2's measured gain is +2 tickets on 120 (not significant), reported as such.

26. **Each experiment re-runs with the rules frozen for it. v1 is archived byte-for-byte in validation_archive/rules_v1.py.**
    Why: otherwise re-running experiment 1 would silently use v2.
    What it changes: `python -m src.validate --tag v1` reproduces 179/190.

## Stage 5: business case (2026-10-05)

27. **Headline goal: cut delivery work landing in Billing's queue from the measured Jan–Jun 2026 share to the share the categoriser leaves behind, monetised ONLY as net excess transfers avoided at Rs 305 each.**
    Why: a mis-tagged ticket's transfer, breach credit, repeat contact and agent time are consequences of one event. The transfer is the only one that the misroute causes mechanically, that is recorded on every helpdesk ticket, and that the policy prices.
    What it changes: the headline is smaller than stage 2's F10 (which added gross transfers and excess breaches). That figure is superseded by this one.

28. **Transfers are counted net: (transfers per mis-tagged ticket − transfers per correctly tagged Logistics ticket) × tickets the tool would fix − new transfers from the tool's false positives.**
    Why: a correctly routed ticket still sometimes transfers, and the tool would create some new misroutes.
    What it changes: the saving is lower than a gross transfer count (see `base_avoided`, `base_new_transfers` and `base_net` in outputs/business_case.csv).

29. **The target is the categoriser's measured recall and false-positive rate against agent notes, not a chosen percentage.**
    Why: the brief says do not invent a target. This is what routing on the customer's words already achieves on this data.
    What it changes: the target share is `headline_target_share` in outputs/business_case.csv. The low and high cases use the Wilson CI edges.

30. **Window: Jan–Jun 2026 only.**
    Why: the most recent period, all on the helpdesk, so transfers are known and nothing is imputed.
    What it changes: quarterly = six-month total / 2.

31. **Excluded from the rupee figure:** breach credits (shown as a non-additive alternative), agent-hours (inside the Rs 305 standard), repeat contacts (no measurable excess), contact cost, CSAT, "Other"-tagged delivery work, and the cost of making the change (no figure exists).

32. **Hiring comparison in policy-implied agent-hours = (contact + transfer cost) / Rs 165, against 8 h × 22 shifts per agent.**
    Why: the brief asks for agent-hours. No handle-effort data exists, so fully loaded cost ÷ fully loaded hourly rate is the only documented conversion.
    What it changes: these are cost-equivalent hours, labelled as such. No team's load at export volume (`hours_*_load` in the CSV) comes near capacity, so no hiring need can be inferred.

33. **The 650/week scenario is shown, never used for the headline.**
    Why: the export measures far fewer (`actual_weekly_mean`, `form_to_actual_ratio` in the CSV). Scaling assumes the same mix.
    What it changes: at 650/week the owner-view loads put Logistics over capacity, which should be confirmed with the helpdesk admin before any hiring decision.

34. **Categorisation run cost: offline Rs 0. The LLM path is estimated from characters ÷ 4 and assumed output tokens (50/300/1000), never measured.**
    Why: no paid calls were made.
    What it changes: the estimate is shown separately from the Rs 0 offline cost.

35. **docs/business_case.md is rendered by the script.**
    Why: the brief forbids hand-typed derived numbers.
    What it changes: a test checks that the doc has no unrendered placeholders, that its headline matches the CSV, and that the breach alternative is not added in.
