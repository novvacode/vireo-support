# Known issues: what is wrong with what I am handing over

A hostile review of the whole repo, ranked by **how much damage each issue could do to the recommendation** in
`memo.md`. Items 1–5 were checked or fixed in this pass; items 6–10 and the minor items are open. Numbers come from
[outputs/review_checks.txt](../outputs/review_checks.txt) (`python -m src.review_checks`) and the earlier stage outputs.

## Checked or fixed in this pass

### 1. One author wrote the rules, the "truth" and the checks (circular evidence)
- **Problem:** the same AI wrote all four of these:
  - the categoriser's rules;
  - the agent-notes rule that defines "delivery work", which sets the 34.9% baseline and the recall used for the target;
  - the 60-ticket hand check of that rule;
  - all 310 gold labels.
- **Leakage:** some Billing messages were also read during stage 2, before the gold samples were drawn.
- **Checked:** 3 of the 310 gold tickets had their message printed in a reproducible stage-2 sample. All 3 were classified correctly; excluding them gives 287/307 instead of 290/310, so there is no change in errors.
  - Further ad-hoc prints in stage 1 and 2 used earlier code and cannot be reconstructed exactly. They were Billing-only and duplicate-search views.
- **Still open:** the circularity itself. Agreement between the tool, the notes rule and the gold labels is partly agreement of one author with itself.
  - **Only independent human labelling fixes this** (docs/validation.md §8).

### 2. The owner definitions favoured the tool over the bot
- **Problem:** my taxonomy makes several debatable owner choices:
  - device faults go to Frontline, although policy §6 gives "escalated hardware cases" to Tier 2;
  - address changes go to Frontline;
  - refunds go to Returns Desk.
- **Effect:** where the bot chose the other defensible owner, it was scored wrong.
- **Checked:** scoring those 21 arguable cases as correct for the bot lifts its owner accuracy from 75.2% to 81.9% (CI 77.3–85.8%) across both gold samples. The tool is at 96.1% (CI 93.4–97.8%). **The gap survives.**
  - Most remaining bot errors are Billing → Logistics (33 tickets), the misrouting this whole case is about.

### 3. The "routed right" transfer rate might flatter the saving
- **Problem:** the saving compares mis-tagged delivery tickets (0.904 transfers) with tickets the bot tagged *correctly* (0.088). Those may be easier tickets.
- **Fixed:** the business case now also uses only Logistics-tagged tickets *worded like payment problems* (0.105 transfers, n=86). The saving moves from Rs 36,587 to Rs 35,835 a quarter. That is inside the stated low–high range, and the headline stands.
  - It is shown as a robustness line in docs/business_case.md.
  - n=86 is small.

### 4. The memo stated capacity loads as if they were measured
- **Problem:** "Logistics would be at 158% of capacity" rests on two things:
  - hours derived from *policy cost* (contact cost ÷ Rs 165), not timed work;
  - an *assumed* 22 shifts per agent a month.
- **Fixed:** the wording now reads "on policy cost standards, Logistics would need 158% of its current hours". The underlying limitation stays (item 6).

### 5. Two memo wording slips
- **Fixed:** "Unclear messages (5.6%)" now reads "Low-confidence messages (5.6%)". 5.6% is the share below 0.6 confidence; only 3.9% (456) end as Unclear.
- **Fixed:** "Billing looks biggest" now reads "biggest *specialist* queue". On Priya's own bot-tag chart, Chat Frontline (26.0%) is larger than Billing (20.8%).

## Still open, handed over honestly

### 6. The export may not be all the tickets (largest open risk)
- 181.6 tickets a week against the form's 650 (3.58x).
- Agents in the export handle at most 1.7 tickets per 8-hour shift, which is implausibly low.
- If the export is a sample or a subset:
  - every rupee figure scales;
  - the capacity picture changes (Logistics is over capacity at 650/week);
  - the 34.9% misroute share may not hold.
- **Nothing in the repo can resolve this.** It needs Sameer.

### 7. Stock-phrase data and small samples flatter accuracy
- **Stock phrases:** messages are built from recurring phrases (430 rows share an exact text). A phrase-matching tool scores well here and worse on real free text.
- **Sample sizes:** gold samples are 190 and 120. Some categories have 3–6 examples (Warranty, Product question, Payment in v2), so per-category rates are anecdotes.
- **Strata:** stratum results rest on 5–25 tickets each.

### 8. The target is a historical replay, not a live result
- The 96.1% catch rate and 1.33% wrong-move rate are measured against past agent notes.
- Nobody has run the routing live.
- The cost of building it into the helpdesk or bot is **not costed**: no figure exists.
- The saving is a planning cost (agent time), not cash.
- A side-by-side trial is needed before anyone books the saving.

### 9. The optional LLM path has never called the real API
- `vireo/llm.py` is unit-tested only with a fake client.
- Request parameters (model, `output_config` effort) follow the current API documentation but are unverified against a live key.
- Its cost figures are estimates from characters ÷ 4.
- The offline default does not depend on it.

### 10. Tested only on Python 3.10, on Windows
- The brief asks for 3.11. No 3.11 interpreter was available on this machine, and I did not download one.
- The clean-venv test (README) passed on 3.10.
- Nothing 3.11-specific is used, but **3.11 and macOS/Linux are untested**.

## Minor issues (low damage, known)
- **Re-imported duplicates:** the policy warns of them, but 0 were found by four searches. If they exist with different customer IDs, volumes are slightly overstated.
- **The 139 rows from 2024** are excluded (all Billing). Including them adds 1 point to Billing's share.
- **`transfers` undercounts:** 341 helpdesk tickets changed team with 0 transfers. This makes the transfer saving conservative.
- **Repeat contacts** depend on how "same issue" is defined (4.3%–24.0%). They are not used in the headline.
- **First responses:** 222 at 0 minutes, possibly bot replies. Breach rates may be slightly low.
- **TF-IDF trains at run time on the input file's own rule labels.** No gold labels are involved, but results on very small input files differ from the full-file run.
- **Agent-hour loads** treat transfer cost as workload of the first-assigned team.
- **Stage-2 figure superseded:** stage 2's "Rs 2.33 lakh a year avoidable cost" (F10) double counted transfers and breaches. It is superseded by docs/business_case.md, but still appears in docs/findings_stage2.md as historical record.
- **Text-only nondeterminism:** in frozen rules v1, the "tie between …" reason text order depends on Python's hash seed. Predictions are unaffected (checked across seeds). Fixed in v2.
