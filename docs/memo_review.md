# Memo review: questions from Finance (Arjun) and Support Ops (Neha)

The first draft of `memo.md` was read twice, once as a sceptical finance controller and once as the operations manager.
Their likely questions are below. **In final memo?** says whether the revised memo answers each one, and where. Every
figure quoted in an answer comes from a script output: [docs/business_case.md](business_case.md),
[outputs/business_case.csv](../outputs/business_case.csv) and [docs/validation.md](validation.md).

## Arjun Mehta, Finance Controller

| # | Question | Short answer | In final memo? |
|---|---|---|---|
| A1 | Is Rs 36,587 a quarter cash I can take out of the budget? | No. Rs 305 per transfer is the policy's *planning* cost of re-handling and administration, mostly agent time. The saving frees capacity; it does not cut payroll unless headcount changes. The cash item (Rs 350 breach credits, worth Rs 14,435 a quarter on its own) is left out. | Yes, section 2 |
| A2 | Why stop at transfers? Breach credits are real money. | A misrouted ticket's transfer, breach credit and repeat contact are one event. Adding them would double count. Transfers are the only cost the misroute causes mechanically and that is recorded on every ticket, so the headline uses the smaller, firmer number. | Yes, section 2 |
| A3 | What does the routing fix cost to build? | Running it costs Rs 0 (it runs offline; no paid services). The effort of changing the intake bot or helpdesk rules is **not costed**: no figure exists in the data. | Yes, section 3 ("costs nothing to run"; build effort not costed) |
| A4 | So does the fix pay for the two hires? | No. Rs 1,46,347 a year is 16.3% of Rs 9 lakh. It is a separate decision, and the memo says it is not a substitute for people. | Yes, section 3 |
| A5 | How sure is the range Rs 22,689 to Rs 53,146? | It moves the misroute volume between the quietest and busiest month, and the routing accuracy and transfer rates across their statistical ranges. It does not cover the risk that the export is incomplete. | Partly: range in section 2; volume risk in section 4 |
| A6 | Which volume is real, 650 a week or 181.6? | Unknown. That is the one question to settle before hiring. If 650 is right and the mix holds, the saving scales to about Rs 1,30,955 a quarter. That figure is an estimate and is not used as the headline. | Yes, sections 4 and 5 |
| A7 | Is the saving achievable, or just what a spreadsheet says? | It assumes the routing performs live as it did against historical agent notes (96.1% caught, 1.33% wrongly moved). That has not been tested live. A side-by-side trial is the way to prove it. | Yes, sections 3 and 4 |
| A8 | Your loads say agents are at 26% and 44% of capacity. Are we overstaffed? | Not a safe conclusion. The hours are cost-equivalent (policy cost ÷ Rs 165), not timed work, and capacity assumes 22 shifts a month. Low loads are more likely a sign the export is incomplete. | Partly: memo flags the volume gap; detail is in business_case.md section 4 |
| A9 | Who decided which tickets were "really" delivery? | A rule reading agents' closing notes, cross-checked against the customer's own words. The checks were done by AI, not by staff. | Yes, section 4 |

## Neha Kulkarni, Support Operations Manager

| # | Question | Short answer | In final memo? |
|---|---|---|---|
| N1 | How much extra work lands on Logistics? | Less than it looks. Of the 314 misrouted tickets in Jan–Jun 2026, only 92 were finished by Billing; the rest already end with Logistics after a transfer. In total about 50.3 tickets, or 68.7 agent-hours, a month change first owner, about 0.39 of one agent. | Yes, section 3 |
| N2 | My team already takes a day-plus. Will this make it worse? | They get these tickets first-hand instead of after a transfer, so they lose the hand-off delay. When the bot tags them right today, these tickets resolve faster than when they go via Billing (docs/findings_stage2.md F9). | Not in memo (space); see F9 |
| N3 | Will the new routing create new mistakes? | Yes, a few. Against agent notes it would wrongly send 1.33% of genuine billing tickets to Logistics. That is counted against the saving. | Yes, section 4 |
| N4 | What happens to unclear or mixed messages? | 5.6% of tickets don't reach a confident answer. In a trial those should keep today's routing or go to a person, not be guessed. | Yes, section 3 |
| N5 | Billing agents chase couriers themselves (the 92). Is that a skills or process issue? | It is unclear from the data. Either way it is Logistics work, and routing fixes the cause. | Not in memo (space) |
| N6 | What should happen before staffing changes? | (1) Confirm the true volume with Sameer. (2) Run the new routing alongside the bot and compare transfers and breaches before switching. (3) Then decide hires on the corrected numbers. | Yes, sections 3 and 5 |
| N7 | Will breaches fall? | Very likely: misrouted delivery tickets breach at 36.3% against 9.0% when routed right. Not counted in the rupee figure, to avoid double counting. | Partly: mentioned as excluded |
| N8 | Do the night shifts explain Billing's breaches? | No. Billing's breach rate is about the same day and night (stage 2 F14). It follows the misrouting. | Not in memo (space) |

## Changes made to the memo after this review
- **Section 2:** says the Rs 305 is a planning cost (mostly agent time), not cash. Names the excluded cash item, breach credits, and why it is excluded (A1, A2).
- **Section 3:** adds how little work actually moves (92 of 314 finished by Billing today; 0.39 of one agent) (N1). Says the build effort is not costed (A3). Adds a side-by-side trial before committing hires (A7, N6).
- **Section 4:** adds that 1.33% of genuine billing tickets would be wrongly moved (N3), and that the 5.6% of unclear tickets stay on today's routing (N4). Names the 650/week saving as an estimate only (A6).
- **Kept to about one page:** shortened wording elsewhere so the memo stays near 450 words.
