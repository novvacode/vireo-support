# Submission form answers

> **[FILL IN] The actual form questions are missing.** CLAUDE.md says they are in `docs/form_questions.md`, but that
> file has never existed in this repo (checked: not in the working tree or in any commit). The questions below are
> **reconstructed from the deliverables list in CLAUDE.md** and the one form question it quotes (cost at "roughly 650
> tickets a week"). Paste the real questions and re-map these answers before submitting.
>
> Every answer uses only facts from the repo's logs and outputs, with the source in brackets. Anything only you can
> supply is marked **[FILL IN]**. None of those values have been guessed.

---

**Q1. Link to your work / how to run the tool**
- Repo link: [FILL IN: where you host it].
- Run on a clean machine: create a virtual environment, `pip install -r requirements.txt`, then:
  `python -m vireo.categorise --tickets data/99ca137e-844d-47d7-8ce8-bf60ce272ba3-tickets.csv --out outputs/`
- Tested from scratch in a fresh Python 3.10 virtual environment: install about 3 minutes, run under a minute, all 65 tests pass. (README; this review)
- Python 3.11 was not tested. (docs/known_issues.md #10)

**Q2. Your one business goal, as a number with a rupee value**
- Cut delivery problems landing in Billing's queue from 34.9% of Billing's tickets to about 2.1%, worth about Rs 36,587 a quarter (range Rs 22,689 to Rs 53,146), counted as avoided inter-team transfers at the policy's Rs 305 each. (docs/business_case.md)
- Transfers only, with no breach-credit or repeat-contact double counting.
- A planning cost (agent time), not cash.
- A stricter counterfactual gives Rs 35,835 a quarter. (outputs/business_case.csv, `robustness_saving_per_quarter_payment_worded_baseline`)

**Q3. How do you know the output is correct, how often is it wrong, and what kind of case does it get wrong?**
- **Checked against AI-adjudicated labels, not human labels:**
  - Held-out test 1 (190 tickets): 94.2% correct category (CI 89.9–96.7%), 96.3% correct owner team.
  - Fresh test 2 (120 tickets): 92.5% category, 95.8% owner.
  - The intake bot gets the owner right 78.9% and 69.2% of the time on the same tickets. (docs/validation.md §1)
- **Checked against agents' own closing notes, which the tool never reads:** it catches 96.1% of delivery work hidden in Billing and wrongly moves 1.33% of genuine billing tickets. (outputs/business_case.csv)
- **Typical wrong case:** a new phrasing it hasn't seen, such as "keeps losing my phone if I walk to the other room". It then answers "Unclear" (16 of 20 errors). Offline, those go to Frontline. (docs/validation.md §4)
- **Limits:**
  - The same AI wrote the rules and the labels.
  - The data is built from stock phrases.
  - A post-test rule change gained only 2 tickets on fresh data, which is not significant. (docs/known_issues.md #1, #7; docs/validation.md §6)

**Q4. What does categorisation cost at roughly 650 tickets a week?**
- No paid calls were used; categorisation cost is therefore Rs 0 per run / Rs 0 per month for the offline path. This holds at 650 tickets a week and at the measured volume.
- The optional AI fallback was never run. Its *estimated* cost is Rs 9.79–70.47 per weekly run at 650 a week, and Rs 2.73–19.69 at the measured volume. (docs/business_case.md §6)
- **The 650 does not match the data:** the export holds 181.6 tickets a week, so the form's figure is 3.58x higher. If 650 is true, the saving and the staffing pressure both grow. (docs/business_case.md §5)

**Q5. What did you recommend to the client?**
- Do not put the two hires into Billing: over a third of Billing's queue is delivery work the intake bot sends to the wrong team.
- Fix routing first and hold the hires until the true ticket volume is confirmed. If hires are needed, the evidence points to Logistics.
- Counted by owned work, Billing's agents use 26% of their hours and Logistics' 44%. (memo.md)

**Q6. Which AI tools did you use, and for what?**
- [FILL IN: the tools you actually used, e.g. the assistant/IDE, and anything else.]
- **Fact from the repo:** the categoriser itself made **no** paid AI calls. No `outputs/llm_cost_log.csv` or `outputs/llm_cache.json` exists. The optional path would call `claude-opus-5-5`. (vireo/llm.py)
- **Fact from the repo:** docs/AI_LOG.md records what the AI assistant was asked, what was changed or rejected, and what was discarded at each stage.

**Q7. Total AI / API cost**
- **Categoriser (the tool):** Rs 0. No paid API calls. (outputs: no cost log exists)
- **Building the work with an AI assistant:** [FILL IN: your real assistant/subscription cost]. This repo has no record of it.

**Q8. Hours spent**
- [FILL IN].
- For reference only (not effort): git commits span 05:32 to 06:49 IST on 5 Oct 2026 (`git log`). They do not capture work outside commits.

**Q9. Screen recording**
- [FILL IN: link].
- Material for it: docs/AI_LOG.md (prompts asked, what changed between versions, what was discarded), and docs/validation.md §6 (v1 vs v2, and the discarded broad rule).

**Q10. What is wrong with what you are handing over / what would you do next?**
- **What's wrong:** see docs/known_issues.md. The largest open risk is whether the export contains every ticket (181.6 a week against 650).
- **Next:** see docs/handover_monday.md:
  - confirm the volume with Sameer;
  - run the routing side by side with the bot;
  - have staff label a sample to replace the AI labels.

**Q11. Judgment calls you made**
- 38 recorded decisions, each with Decision / Why / What it changes. (docs/decisions.md)
- Examples:
  - excluding the 139 rows from 2024 (all Billing);
  - shifting legacy resolution times from UTC to IST;
  - counting transfers only in the business case;
  - keeping the experiment-1 results unchanged.
