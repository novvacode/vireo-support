# If you pick this up on Monday: three things

**Where we are:**
- The client memo (`memo.md`) recommends: don't hire into Billing; fix routing first; hold the hires until the volume is confirmed; if hires are needed, they go to Logistics.
- All numbers re-run from `data/` (see README).
- What is shaky is listed in `docs/known_issues.md`. Read it before defending any figure.

## 1. Find out whether the export is complete (this decides the hires)
- **The gap:** the export holds 181.6 tickets a week; the submission form assumes 650. Everything (saving, capacity, which team needs people) changes if 650 is true.
- **Ask** Sameer Qureshi (helpdesk admin) for the helpdesk's own count of tickets created in June 2026.
- **Compare** it with the export's 776 for June 2026 (`docs/audit_output.txt`, "monthly Jan-Jun 2026").
- **If they match:** the memo stands as written.
- **If not:**
  - get the full export;
  - drop it into `data/` (the loader finds `*-tickets.csv` by name);
  - re-run every script in the README;
  - re-render `docs/business_case.md` with `python -m src.business_case`.

## 2. Run the new routing side by side before anyone books the saving
- **Status:** the Rs 36,587-a-quarter saving is a replay against past agent notes, not a live result.
- **Each week:**
  - run `python -m vireo.categorise --tickets <that week's export> --out outputs/week_N/`;
  - **do not change routing yet**;
  - compare `owner_team` with where tickets actually ended up (resolving agent's team) and with transfers and breaches.
- **Keep the bot's routing** for low-confidence tickets (`confidence` below 0.6, about 5.6%).
- **Decide after a few weeks:**
  - if transfers on "Billing-tagged but Logistics-owned" tickets would have dropped as predicted, switch on routing for that one category first;
  - if not, `docs/business_case.md` tells you which input to re-check.

## 3. Replace the AI labels with staff labels
- **The problem:** every accuracy figure was checked against labels written by the same AI that built the rules (`docs/validation.md` §2.5).
- **To fix it:**
  - give two agents (ideally one from Billing and one from Logistics) the blind sheet `labels/gold_v2_blind.csv`, which shows only ticket, channel and message, plus the 13 definitions in `vireo/taxonomy.py`;
  - have them label independently;
  - put their labels in `labels/gold_human_labels.csv` with the same columns as `labels/gold_v2_labels.csv`.
- **Then** re-run `python -m src.validate --tag v2` against them (copy them over `gold_v2_labels.csv` on a branch). Report agreement between the two agents first; if they disagree often, the taxonomy needs work before the tool does.

**Don't touch:** `labels/gold_v1_*`, `labels/gold_v2_*`, `validation_archive/rules_v1.py`. They are the frozen test record; changing them invalidates the validation history.
