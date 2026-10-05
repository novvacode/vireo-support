"""Stage 5: the business case. Every number in docs/business_case.md is computed here.

    python -m src.business_case   -> outputs/business_case.csv + docs/business_case.md (rendered, not hand-typed)

Single monetisation method: NET EXCESS INTER-TEAM TRANSFERS avoided (policy s4, Rs 305 each).
Breach credits, repeat contacts, agent time and CSAT are deliberately NOT added (same underlying event).
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from src.gold_sample import frozen_predictions
from src.stage2 import prepare, wilson
from vireo import llm as llm_mod
from vireo.categorise import LLM_BELOW

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
DOC = ROOT / "docs" / "business_case.md"

# ---- documented policy figures (support-policy.pdf s3, s4, s5; Finance email) -------------------
TRANSFER_INR = 305
BREACH_INR = 350
CONTACT_INR = {"chat": 210, "email": 260, "voice": 520, "social": 240}
AGENT_HOUR_INR = 165
SHIFT_H = 8
TWO_HIRES_INR_YEAR = 900_000
# ---- assumptions (not in the data or the policy) --------------------------------------------------
SHIFTS_PER_MONTH = 22            # decision 13
FORM_WEEKLY = 650                # submission form's assumption
WEEKS_PER_MONTH = 52 / 12
CHARS_PER_TOKEN = 4              # rough token estimate for an LLM call that was never made
LLM_OUT_TOKENS = {"low": 50, "base": 300, "high": 1000}
RECENT = ("2026-01", "2026-06")  # most recent six months, all on the helpdesk (transfers known)

rows: list[dict] = []


def rec(key, value, unit, kind, note=""):
    """kind: measured | calculated | policy | assumption | estimate"""
    rows.append({"key": key, "value": value, "unit": unit, "type": kind, "note": note})
    return value


def mean_ci(s: pd.Series):
    s = s.dropna().astype(float)
    m, sd, n = s.mean(), s.std(ddof=1), len(s)
    h = 1.96 * sd / math.sqrt(n)
    return m, max(m - h, 0.0), m + h


def inr(x):
    """Indian digit grouping, e.g. 1,23,456."""
    neg, x = x < 0, int(round(abs(x)))
    s = str(x)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join([head[max(i - 2, 0):i] for i in range(len(head), 0, -2)][::-1])
        s = head + "," + tail
    return ("-Rs " if neg else "Rs ") + s


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def prange(s, d=0):
    lo, hi = pct(min(s), d), pct(max(s), d)
    return lo if lo == hi else f"{lo}-{hi}"


def main():
    v, _, raw = prepare()
    agents = raw["agents"]["team"].value_counts()
    _, pred = frozen_predictions("v2")
    v = v.merge(pred[["ticket_id", "new_category", "confidence"]], on="ticket_id", how="left")
    v["tool_delivery"] = v["new_category"].isin(["order_not_arrived", "damaged_or_wrong_item"])

    h1 = v[v["month"].astype(str).between(*RECENT)]
    months = rec("months_in_window", h1["month"].nunique(), "months", "measured", "Jan-Jun 2026")
    assert set(h1["source_system"]) == {"helpdesk"}

    # ------------------------------------------------------------------ baseline (measured)
    b = h1[h1["assigned_team"] == "Billing"]
    mis = b[b["work_type"] == "delivery"]
    non = b[b["work_type"] != "delivery"]
    lg = h1[h1["assigned_team"] == "Logistics"]
    gen = b[b["work_type"] == "billing"]
    n_b = rec("billing_tagged_h1", len(b), "tickets", "measured", "Billing-tagged, Jan-Jun 2026")
    n_mis = rec("delivery_in_billing_h1", len(mis), "tickets", "measured", "agent notes describe delivery work (stage 2 rule)")
    base_share = rec("baseline_share", n_mis / n_b, "share", "measured", "delivery work as share of Billing-tagged")
    rec("delivery_in_billing_resolved_by_billing_h1", int((mis["resolver_team"] == "Billing").sum()), "tickets", "measured",
        "Billing agents did the delivery work themselves: no transfer happened, so no transfer saving is counted")
    t_mis, t_mis_lo, t_mis_hi = mean_ci(mis["transfers"])
    t_log, t_log_lo, t_log_hi = mean_ci(lg["transfers"])
    t_gen, _, _ = mean_ci(gen["transfers"])
    rec("transfers_per_misrouted", t_mis, "transfers/ticket", "measured", f"n={len(mis)}; 95% CI {t_mis_lo:.3f}-{t_mis_hi:.3f}")
    rec("transfers_per_logistics_tagged", t_log, "transfers/ticket", "measured", f"n={len(lg)}; 95% CI {t_log_lo:.3f}-{t_log_hi:.3f}")
    rec("transfers_per_genuine_billing", t_gen, "transfers/ticket", "measured", f"n={len(gen)}")
    b_mis, b_log = mis["fr_breach"].mean(), lg["fr_breach"].mean()
    rec("breach_rate_misrouted", b_mis, "share", "measured")
    rec("breach_rate_logistics_tagged", b_log, "share", "measured")
    monthly_mis = mis.groupby("month").size()
    allb = v[v["assigned_team"] == "Billing"]
    mis_all, lg_all = allb[allb["work_type"] == "delivery"], v[v["assigned_team"] == "Logistics"]
    rep_mis = rec("repeat_rate_misrouted_all", mis_all["caused_repeat_by_category"].mean(), "share", "measured", "customer+category key, Jan 2025-Jun 2026")
    rep_lg = rec("repeat_rate_logistics_tagged_all", lg_all["caused_repeat_by_category"].mean(), "share", "measured")
    csat_mis = rec("csat_misrouted_all", float(mis_all["csat_score"].mean()), "1-5", "measured", f"n={int(mis_all['csat_score'].count())}, blanks excluded")
    csat_lg = rec("csat_logistics_tagged_all", float(lg_all["csat_score"].mean()), "1-5", "measured", f"n={int(lg_all['csat_score'].count())}")
    val = pd.concat([pd.read_csv(OUT / "validation_results.csv"), pd.read_csv(OUT / "validation_results_v2.csv")])
    own = val[(val["subset"] == "all gold") & (val["metric"] == "owner-team accuracy")]
    tool_own = own[own["system"] == "our tool"]["value"]
    bot_own = own[own["system"] == "intake bot"]["value"]
    hand = pd.read_csv(OUT / "routing_rule_vs_hand_labels.csv").iloc[0]
    hand_k, hand_n = int(hand["tp"] + hand["tn"]), int(hand["tp"] + hand["fp"] + hand["fn"] + hand["tn"])

    # ------------------------------------------------------------------ how well the fix would work (measured, full 18 months)
    ball = v[v["assigned_team"] == "Billing"]
    nd = ball["work_type"].eq("delivery")
    k_rec, n_rec = int((ball["tool_delivery"] & nd).sum()), int(nd.sum())
    k_fp, n_fp = int((ball["tool_delivery"] & ~nd).sum()), int((~nd).sum())
    recall, (rec_lo, rec_hi) = k_rec / n_rec, wilson(k_rec, n_rec)
    fp, (fp_lo, fp_hi) = k_fp / n_fp, wilson(k_fp, n_fp)
    rec("tool_recall_delivery", recall, "share", "measured", f"{k_rec}/{n_rec} Billing-tagged with delivery notes; CI {rec_lo:.3f}-{rec_hi:.3f}")
    rec("tool_false_positive_rate", fp, "share", "measured", f"{k_fp}/{n_fp} Billing-tagged without delivery notes sent to delivery; CI {fp_lo:.4f}-{fp_hi:.4f}")

    # ------------------------------------------------------------------ saving per quarter, three cases
    q_mis_base = n_mis / months * 3
    q_non = len(non) / months * 3
    cases = {
        "low": dict(q_mis=monthly_mis.min() * 3, recall=rec_lo, excess=max(t_mis_lo - t_log_hi, 0), fp=fp_hi),
        "base": dict(q_mis=q_mis_base, recall=recall, excess=t_mis - t_log, fp=fp),
        "high": dict(q_mis=monthly_mis.max() * 3, recall=rec_hi, excess=t_mis_hi - t_log_lo, fp=fp_lo),
    }
    calc = {}
    for name, c in cases.items():
        fixed = c["q_mis"] * c["recall"]
        avoided = fixed * c["excess"]
        fp_tickets = q_non * c["fp"]
        new_transfers = fp_tickets * (t_mis - t_gen)   # a genuine billing ticket wrongly sent to Logistics bounces back
        net = avoided - new_transfers
        saving_q = net * TRANSFER_INR
        residual = c["q_mis"] * (1 - c["recall"])
        new_queue = q_non * (1 - c["fp"]) + residual
        calc[name] = dict(c, fixed=fixed, avoided=avoided, fp_tickets=fp_tickets, new_transfers=new_transfers,
                          net=net, saving_q=saving_q, saving_y=saving_q * 4, target_share=residual / new_queue)
        for k, val in calc[name].items():
            rec(f"{name}_{k}", val, "", "calculated" if name == "base" else "estimate")
    base = calc["base"]
    rec("headline_saving_per_quarter", base["saving_q"], "INR/quarter", "calculated")
    rec("headline_saving_per_year", base["saving_y"], "INR/year", "calculated")
    rec("headline_target_share", base["target_share"], "share", "calculated")
    rec("saving_vs_two_hires", base["saving_y"] / TWO_HIRES_INR_YEAR, "ratio", "calculated")

    # robustness: correctly tagged tickets may be easier. Use payment-worded Logistics tickets as the "routed right" rate.
    from src.gold_sample import PAID
    lg_pay = lg[lg["customer_message"].str.lower().str.contains(PAID)]
    t_log_pay = rec("transfers_per_logistics_tagged_payment_worded", lg_pay["transfers"].astype(float).mean(),
                    "transfers/ticket", "measured", f"n={len(lg_pay)}; closer counterfactual for 'paid but...' messages")
    robust_q = (base["fixed"] * (t_mis - t_log_pay) - base["new_transfers"]) * TRANSFER_INR
    rec("robustness_saving_per_quarter_payment_worded_baseline", robust_q, "INR/quarter", "calculated",
        "same as base but excess transfers measured against payment-worded Logistics tickets")

    # alternative single method (NOT added): breach credits
    alt_breach_q = q_mis_base * recall * (b_mis - b_log) * BREACH_INR
    rec("alt_method_breach_credit_saving_per_quarter", alt_breach_q, "INR/quarter", "calculated",
        "alternative single method for the same events; NOT added to the headline")

    # ------------------------------------------------------------------ volume per week
    wk = v.set_index("created_at").resample("W-SUN").size()
    full = wk.iloc[1:-1]
    full = full[full.index >= pd.Timestamp("2026-01-05")]
    wk_mean, wk_min, wk_max = full.mean(), full.min(), full.max()
    rec("actual_weekly_mean", wk_mean, "tickets/week", "measured", f"{len(full)} full weeks Jan-Jun 2026")
    rec("actual_weekly_min", wk_min, "tickets/week", "measured")
    rec("actual_weekly_max", wk_max, "tickets/week", "measured")
    ratio = rec("form_to_actual_ratio", FORM_WEEKLY / wk_mean, "x", "calculated")
    rec("form_weekly_as_monthly", FORM_WEEKLY * WEEKS_PER_MONTH, "tickets/month", "calculated")
    rec("actual_weekly_as_monthly", wk_mean * WEEKS_PER_MONTH, "tickets/month", "calculated")
    rec("headline_saving_per_quarter_if_650", base["saving_q"] * ratio, "INR/quarter", "estimate",
        "only if the extra volume has the same mix and misroute rate")

    # ------------------------------------------------------------------ agent-hours: Billing vs Logistics
    avail = SHIFT_H * SHIFTS_PER_MONTH
    rec("available_hours_per_agent_month", avail, "hours", "assumption", "8 h x 22 shifts")
    hire_hours_month = TWO_HIRES_INR_YEAR / AGENT_HOUR_INR / 12
    rec("two_hires_as_agent_hours_per_month", hire_hours_month, "hours/month", "calculated", "Rs 9 lakh / Rs 165 / 12")
    hrs = []
    for view, col in [("bot tag", "assigned_team"), ("owner of the work", "true_owner")]:
        for team in ["Billing", "Logistics"]:
            x = h1[h1[col] == team]
            work = (x["contact_cost"].sum() + x["transfer_cost"].fillna(0).sum()) / AGENT_HOUR_INR / months
            n_ag = int(agents[team])
            r = {"view": view, "team": team, "agents": n_ag, "tickets_per_month": len(x) / months,
                 "workload_hours_per_month": work, "available_hours_per_month": n_ag * avail,
                 "load": work / (n_ag * avail), "load_with_2_more": work / ((n_ag + 2) * avail),
                 "load_if_650_per_week": work * ratio / (n_ag * avail)}
            r["tickets_per_agent_shift"] = r["tickets_per_month"] / n_ag / SHIFTS_PER_MONTH
            hrs.append(r)
            for k in ["tickets_per_month", "workload_hours_per_month", "load", "load_with_2_more", "load_if_650_per_week"]:
                rec(f"hours_{view.replace(' ', '_')}_{team}_{k}", r[k], "", "calculated")
    hrs = pd.DataFrame(hrs)
    moved_month = base["fixed"] / 3
    moved_hours = moved_month * mis["contact_cost"].mean() / AGENT_HOUR_INR
    rec("tickets_moved_to_logistics_per_month", moved_month, "tickets/month", "calculated")
    rec("hours_moved_to_logistics_per_month", moved_hours, "hours/month", "calculated", "contact cost of the moved tickets / Rs 165")
    rec("hours_moved_as_fte", moved_hours / avail, "FTE", "calculated")

    # ------------------------------------------------------------------ categorisation run cost
    unclear_share = (pred["confidence"] < LLM_BELOW).mean()
    rec("share_sent_to_llm_if_enabled", unclear_share, "share", "measured", "confidence < 0.6 after rules + TF-IDF (rules v2)")
    pin, pout = llm_mod.PRICE_USD_PER_MTOK[llm_mod.DEFAULT_MODEL]
    in_tok = (len(llm_mod.SYSTEM) + v["customer_message"].str.len().mean()) / CHARS_PER_TOKEN
    rec("llm_input_tokens_per_call", in_tok, "tokens", "estimate", "characters / 4; never measured")
    runcost = []
    for label, weekly in [("form: 650/week", FORM_WEEKLY), ("actual: mean", wk_mean),
                          ("actual: low week", wk_min), ("actual: high week", wk_max)]:
        calls = weekly * unclear_share
        r = {"scenario": label, "tickets_per_run": weekly, "offline_inr_per_run": 0.0, "offline_inr_per_month": 0.0,
             "llm_calls_per_run": calls}
        for case, out_tok in LLM_OUT_TOKENS.items():
            usd = calls * (in_tok * pin + out_tok * pout) / 1e6
            r[f"llm_{case}_inr_per_run"] = usd * llm_mod.USD_INR
            r[f"llm_{case}_inr_per_month"] = usd * llm_mod.USD_INR * WEEKS_PER_MONTH
        runcost.append(r)
        for k, val in r.items():
            if k != "scenario":
                rec(f"runcost_{label}_{k}", val, "", "estimate" if k.startswith("llm_") else "calculated")
    runcost = pd.DataFrame(runcost)

    pd.DataFrame(rows).to_csv(OUT / "business_case.csv", index=False)
    hrs.to_csv(OUT / "business_case_agent_hours.csv", index=False)
    runcost.to_csv(OUT / "business_case_run_cost.csv", index=False)
    render(locals())
    print(f"headline: cut {pct(base_share)} -> {pct(base['target_share'])}, {inr(base['saving_q'])}/quarter "
          f"(low {inr(calc['low']['saving_q'])}, high {inr(calc['high']['saving_q'])}); {inr(base['saving_y'])}/year")
    print(f"wrote {OUT / 'business_case.csv'} ({len(rows)} rows), {DOC}")


def render(L):
    c, base, hrs, rc = L["calc"], L["base"], L["hrs"], L["runcost"]
    lo, hi = c["low"], c["high"]
    f3 = lambda x: f"{x:.3f}"
    f1 = lambda x: f"{x:,.1f}"
    goal = (f"Cut delivery problems landing in Billing's queue from {pct(L['base_share'])} of Billing's tickets to about "
            f"{pct(base['target_share'])}, by routing them on the customer's words instead of the bot's tag, worth about "
            f"{inr(round(base['saving_q'], -3))} a quarter in avoided inter-team transfers "
            f"(range {inr(round(lo['saving_q'], -3))} to {inr(round(hi['saving_q'], -3))}).")
    arith = [
        ("1", "Delivery-work tickets tagged Billing, Jan-Jun 2026", "measured", f"{L['n_mis']:,}", ""),
        ("2", "Months in window", "measured", f"{L['months']}", ""),
        ("3", "Per quarter", "calculated", f1(L['q_mis_base']), "(1) / (2) x 3"),
        ("4", "Share the categoriser routes correctly (recall vs agent notes)", "measured", pct(L['recall']), f"{L['k_rec']}/{L['n_rec']}"),
        ("5", "Tickets fixed per quarter", "calculated", f1(base['fixed']), "(3) x (4)"),
        ("6", "Transfers per mis-tagged ticket today", "measured", f3(L['t_mis']), f"mean over {L['n_mis']} tickets"),
        ("7", "Transfers per correctly tagged delivery ticket", "measured", f3(L['t_log']), f"Logistics-tagged, n={len(L['lg'])}"),
        ("8", "Excess transfers per fixed ticket", "calculated", f3(base['excess']), "(6) - (7)"),
        ("9", "Transfers avoided per quarter", "calculated", f1(base['avoided']), "(5) x (8)"),
        ("10", "Genuine-billing tickets per quarter", "measured", f1(L['q_non']), "Billing-tagged, not delivery work"),
        ("11", "Wrongly sent to Logistics (false-positive rate)", "measured", pct(L['fp'], 2), f"{L['k_fp']}/{L['n_fp']}"),
        ("12", "New transfers created per quarter", "calculated", f1(base['new_transfers']),
         f"(10) x (11) x ({f3(L['t_mis'])} - {f3(L['t_gen'])})"),
        ("13", "Net transfers avoided per quarter", "calculated", f1(base['net']), "(9) - (12)"),
        ("14", "Policy cost per transfer", "policy", inr(TRANSFER_INR), "policy s4"),
        ("15", "**Saving per quarter**", "calculated", f"**{inr(base['saving_q'])}**", "(13) x (14)"),
        ("16", "Saving per year", "calculated", inr(base['saving_y']), "(15) x 4"),
        ("17", "Two hires per year", "Finance", inr(TWO_HIRES_INR_YEAR), "Arjun Mehta's email"),
        ("18", "Saving as share of two hires", "calculated", pct(base['saving_y'] / TWO_HIRES_INR_YEAR), "(16) / (17)"),
    ]
    arith_md = "\n".join(f"| {a} | {b} | {t} | {v} | {w} |" for a, b, t, v, w in arith)
    sens_md = "\n".join(
        f"| {k} | {f1(x['q_mis'])} | {pct(x['recall'])} | {f3(x['excess'])} | {pct(x['fp'], 2)} | {f1(x['net'])} | "
        f"{inr(x['saving_q'])} | {inr(x['saving_y'])} | {pct(x['target_share'])} |" for k, x in c.items())
    hrs_md = "\n".join(
        f"| {r.view} | {r.team} | {r.agents} | {f1(r.tickets_per_month)} | {f1(r.workload_hours_per_month)} | "
        f"{f1(r.available_hours_per_month)} | {pct(r.load, 0)} | {pct(r.load_with_2_more, 0)} | {pct(r.load_if_650_per_week, 0)} |"
        for r in hrs.itertuples())
    rc_md = "\n".join(
        f"| {r.scenario} | {f1(r.tickets_per_run)} | Rs 0 | Rs 0 | {f1(r.llm_calls_per_run)} | "
        f"Rs {r.llm_low_inr_per_run:,.2f} / {r.llm_base_inr_per_run:,.2f} / {r.llm_high_inr_per_run:,.2f} | "
        f"Rs {r.llm_low_inr_per_month:,.2f} / {r.llm_base_inr_per_month:,.2f} / {r.llm_high_inr_per_month:,.2f} |"
        for r in rc.itertuples())
    lg_owner = hrs[(hrs.view == "owner of the work") & (hrs.team == "Logistics")].iloc[0]
    bl_owner = hrs[(hrs.view == "owner of the work") & (hrs.team == "Billing")].iloc[0]
    bl_bot = hrs[(hrs.view == "bot tag") & (hrs.team == "Billing")].iloc[0]
    lg_bot = hrs[(hrs.view == "bot tag") & (hrs.team == "Logistics")].iloc[0]
    max_load = hrs["load"].max()
    own650 = hrs[hrs.view == "owner of the work"].set_index("team")["load_if_650_per_week"]
    over = [t for t, x in own650.items() if x > 1]
    under = [t for t, x in own650.items() if x <= 1]
    if over:
        at650 = (f"Counted by owner, {' and '.join(over)} would be over capacity "
                 f"({', '.join(f'{t} {pct(own650[t], 0)}' for t in over)})"
                 + (f" and {' and '.join(under)} would not ({', '.join(f'{t} {pct(own650[t], 0)}' for t in under)})" if under else "")
                 + f". The hiring question would then point to {' and '.join(over)}.")
    else:
        at650 = "Counted by owner, no team would be over capacity."

    md = f"""# Business case: one headline goal

> Generated by `python -m src.business_case`. **Every number on this page is computed by that script** from `data/` and
> the policy figures; nothing here is typed by hand. The figures with their type (measured / calculated / policy /
> assumption / estimate) are in [outputs/business_case.csv](../outputs/business_case.csv).

## The goal

**{goal}**

This is a **routing fix, not a hire**. At the base case it is worth {inr(base['saving_y'])} a year, which is
{pct(base['saving_y'] / TWO_HIRES_INR_YEAR)} of the Rs 9 lakh Finance quotes for two hires. It does not pay for two
hires; it removes a cost that hiring into Billing would not touch (section 4).

## 1. Baseline (measured, Jan-Jun 2026)

- **Window:** the most recent six months. All of it is on the new helpdesk, so `transfers` is known for every ticket.
- **Delivery work in Billing:** {L['n_mis']:,} of {L['n_b']:,} Billing-tagged tickets ({pct(L['base_share'])}) were delivery work. Agent notes are the evidence (stage 2, F3).
- **Transfers, mis-tagged:** these averaged {f3(L['t_mis'])} transfers each.
- **Transfers, tagged right:** delivery tickets the bot sent straight to Logistics averaged {f3(L['t_log'])}.
- **Already handled in Billing:** {int(L['mis']['resolver_team'].eq('Billing').sum())} of the mis-tagged tickets were finished by Billing agents with no transfer. They are in the average, so they pull the saving *down*. That is correct: no transfer happened, so none can be saved.

## 2. Target and why it is justified

- **The target is not a chosen percentage.** It is what the categoriser already achieves when routing on the customer's message.
- **Recall:** against agents' own notes, which the tool never reads, it routes {pct(L['recall'])} of Billing-tagged delivery tickets to a delivery category ({L['k_rec']}/{L['n_rec']}, 95% CI {pct(L['rec_lo'])} to {pct(L['rec_hi'])}).
- **False positives:** it wrongly sends {pct(L['fp'], 2)} of genuine billing tickets to delivery ({L['k_fp']}/{L['n_fp']}).
- **What remains:** delivery work that would still land in Billing, as a share of the smaller Billing queue, is the target: {pct(base['target_share'])}.
- **Independent support:** on AI-adjudicated gold samples the tool chose the right owner team for {prange(L['tool_own'])} of tickets, against {prange(L['bot_own'])} for the bot (docs/validation.md). Those labels are AI-made, so they are supporting evidence, not the basis of the number.

## 3. Arithmetic (base case, one monetisation method)

| # | Item | Type | Value | How |
|---|---|---|---:|---|
{arith_md}

### Why only transfers (no double counting)
A mis-tagged delivery ticket can lead to a transfer, a breach credit, a repeat contact, extra agent time and lower CSAT.
These are consequences of **one event**, so only one is monetised: the transfer.
- **Why the transfer:** the misroute causes it mechanically, it is recorded on every helpdesk ticket, and the policy prices it (Rs 305, "re-handling and administration").

**Excluded, deliberately:**
- **Breach credits (Rs 350).** Mis-tagged delivery tickets breach at {pct(L['b_mis'])} against {pct(L['b_log'])} when tagged right. Priced as an *alternative* single method that is **not added**, it gives {inr(L['alt_breach_q'])} a quarter. It is excluded because the link is correlation, not mechanism, and it overlaps the transfer delay.
- **Agent-hours (Rs 165).** Re-handling time is already inside the Rs 305 transfer standard.
- **Repeat contacts.** No measurable excess: {pct(L['rep_mis'])} for mis-tagged tickets against {pct(L['rep_lg'])} for correctly tagged delivery (customer + category key, all 18 months).
- **Contact cost.** The first contact happens whichever team receives it.
- **CSAT.** Lower ({L['csat_mis']:.2f} vs {L['csat_lg']:.2f}), but no policy rupee value.
- **"Other"-tagged delivery work (stage 2 F16).** Not counted; mostly handled inside Frontline without a transfer.
- **The cost of making the change** (bot intake change or running the categoriser in the helpdesk). Not costed: no figure exists. The offline categoriser itself costs Rs 0 to run (section 6).

### Sensitivity (low / base / high)

| Case | Mis-tagged per quarter | Recall | Excess transfers per ticket | False-positive rate | Net transfers avoided per quarter | Saving per quarter | Saving per year | Target share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{sens_md}

- **Low:** the quietest month's misroute volume (x3), recall at its CI floor, excess transfers at the pessimistic CI edges, false positives at the CI ceiling.
- **High:** the reverse.
- **Base:** point estimates.
- **Robustness:** tickets the bot tags right may be easier than the ones it gets wrong. Using only Logistics-tagged tickets
  that are *worded like payment problems* as the "routed right" rate ({f3(L['t_log_pay'])} transfers per ticket,
  n={len(L['lg_pay'])}, against {f3(L['t_log'])}) gives {inr(L['robust_q'])} a quarter instead of {inr(base['saving_q'])}.

## 4. Against two hires, and Billing vs Logistics, in agent-hours

**Method.**
- **Workload:** policy-implied agent-hours, i.e. (contact cost + transfer cost) / Rs 165, per month, Jan-Jun 2026. Because the Rs 165 rate and the contact costs are both "fully loaded", these are cost-equivalent hours, not measured handle time.
- **Capacity:** agents x 8 h x 22 shifts (an assumption; the roster has no rota).
- **Two hires:** Rs 9 lakh / Rs 165 = {f1(L['hire_hours_month'])} agent-hours a month.

| View | Team | Agents | Tickets / month | Workload hours / month | Available hours / month | Load | Load with +2 hires | Load if 650/week |
|---|---|---:|---:|---:|---:|---:|---:|---:|
{hrs_md}

What this shows:
- **Hiring into Billing.** Counted by the bot's tag, Billing's load is {pct(bl_bot.load, 0)}. Counted by the work it actually owns, it is {pct(bl_owner.load, 0)}.
  - Two Billing hires would mostly add capacity for delivery work that Billing then transfers out anyway.
  - It would not remove the transfers or breach credits above, because those come from the routing, not from Billing being short-staffed.
- **Hiring into Logistics.** Counted by owner, Logistics carries the most per agent ({pct(lg_owner.load, 0)}, against Billing's {pct(bl_owner.load, 0)}).
  - The routing fix moves about {f1(L['moved_month'])} tickets, or {f1(L['moved_hours'])} agent-hours, a month into Logistics: {L['moved_hours'] / L['avail']:.2f} of one agent.
  - That is well under the {f1(L['hire_hours_month'])} hours two hires would buy.
- **Cannot be concluded.** At the volume in this export, no team's policy-implied load exceeds {pct(max_load, 0)} of the assumed available hours.
  - The data therefore **does not show that either team needs two hires**; ticket volume alone is not evidence of a staffing gap.
  - If the true volume is 650 a week (section 5), the last column applies. {at650}

## 5. Volume per week: 650 vs the data

| | Tickets / week | Tickets / month (x 52/12) |
|---|---:|---:|
| Submission form's assumption | {FORM_WEEKLY:,} | {f1(FORM_WEEKLY * WEEKS_PER_MONTH)} |
| This export, mean of full weeks Jan-Jun 2026 | {f1(L['wk_mean'])} | {f1(L['wk_mean'] * WEEKS_PER_MONTH)} |
| This export, lowest / highest full week | {L['wk_min']:,} / {L['wk_max']:,} | |
| **Ratio, form / data** | **{L['ratio']:.2f}x** | |

**Implications:**
1. **Every rupee figure above uses the measured volume.** If 650 a week is right and the extra tickets have the same mix, the saving scales to about {inr(L['base']['saving_q'] * L['ratio'])} a quarter. That is an *estimate* and is not used as the headline.
2. **The gap may explain the capacity puzzle.** In this export, Billing and Logistics agents handle at most {L['hrs']['tickets_per_agent_shift'].max():.1f} tickets per 8-hour shift. A {L['ratio']:.1f}x higher true volume would explain that, and would change the staffing conclusion (section 4, last column).
3. **This is the first thing to confirm with Sameer (helpdesk admin):** is the export complete, or a sample?

## 6. Cost of running the categoriser

**No paid calls were used; categorisation cost is therefore Rs 0 per run / Rs 0 per month for the offline path.**

- **Optional LLM path:** for tickets still below {LLM_BELOW} confidence ({pct(L['unclear_share'])} of tickets).
- **It was built but never run,** so its cost below is an *estimate, not a measurement*:
  - model {llm_mod.DEFAULT_MODEL} at ${llm_mod.PRICE_USD_PER_MTOK[llm_mod.DEFAULT_MODEL][0]:.0f} / ${llm_mod.PRICE_USD_PER_MTOK[llm_mod.DEFAULT_MODEL][1]:.0f} per million input / output tokens;
  - about {L['in_tok']:.0f} input tokens per call (characters / 4);
  - {LLM_OUT_TOKENS['low']} / {LLM_OUT_TOKENS['base']} / {LLM_OUT_TOKENS['high']} output tokens per call (low / base / high, including thinking);
  - USD to INR at {llm_mod.USD_INR:.0f} (assumption);
  - one run = one week's tickets, one month = 52/12 runs.

| Scenario | Tickets per run | Offline per run | Offline per month | LLM calls per run | LLM per run (low / base / high) | LLM per month (low / base / high) |
|---|---:|---:|---:|---:|---:|---:|
{rc_md}

## 7. What is measured, calculated, assumed
- **Measured:** ticket counts, transfers, breach rates, recall and false-positive rate against agent notes, weekly volumes.
- **Policy:** Rs 305, Rs 350, contact costs, Rs 165, 8-hour shift. **Finance:** Rs 9 lakh for two hires.
- **Assumptions:** 22 shifts per agent a month; a false positive bounces back with the same transfer pattern as a misroute; USD to INR 88; token counts for the unrun LLM path.
- **Weakest link:** "delivery work" is identified from agent notes by a rule (stage 2). Its hand-check ({L['hand_k']}/{L['hand_n']}) was AI-labelled, see docs/validation.md.
"""
    DOC.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
