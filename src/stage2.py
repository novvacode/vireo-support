"""Stage 2: volume, workload, capacity and mis-routing. Writes CSVs + PNGs to outputs/ and prints
every number used in docs/findings_stage2.md.   Run:  python -m src.stage2
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src import clean, routing, workload as wl  # noqa: E402
from src.load import load_all  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "outputs"
WORK_MONTH_SHIFTS = 22  # assumption: 5-day week -> ~22 shifts per agent per month (decision 13)
RECENT = ("2026-01", "2026-06")
LABELS = Path(__file__).resolve().parent.parent / "labels" / "billing_sample60_hand_labels.csv"

# Reference palette (dataviz skill, light mode). Categorical order is fixed, never cycled.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
TIER1 = ["Chat Frontline", "Billing", "Logistics", "Email Frontline", "Returns Desk", "Voice Frontline"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n."""
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return c - h, c + h


def pct(x) -> str:
    return f"{100 * x:.1f}%"


def style(ax, title=None):
    ax.set_facecolor(SURFACE)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=9, color=INK, loc="left")


def save(fig, name):
    fig.patch.set_facecolor(SURFACE)
    fig.savefig(OUT / name, dpi=150, bbox_inches="tight")
    plt.close(fig)


def small_multiples(monthly: pd.DataFrame, title: str, name: str, highlight=()):
    """One panel per series, shared y. Single hue; highlighted panels use slot 2."""
    cols = list(monthly.columns)
    n = len(cols)
    ncol = 4 if n > 8 else 4 if n > 6 else 3
    nrow = -(-n // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.1 * ncol, 2.0 * nrow), sharex=True, sharey=True)
    x = monthly.index.to_timestamp()
    for ax, c in zip(axes.flat, cols):
        color = S2 if c in highlight else S1
        ax.plot(x, monthly[c], color=color, linewidth=2)
        style(ax, f"{c}  (total {int(monthly[c].sum()):,})")
        ax.tick_params(axis="x", rotation=0)
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%y"))
        ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=[1, 7]))
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    save(fig, name)


def prepare() -> pd.DataFrame:
    raw = load_all()
    t, _ = clean.clean_tickets(raw)
    v = clean.analysis_view(t).copy()
    v["handle_h"] = wl.handle_hours(v)
    v = wl.flag_repeat_contacts(v)
    v = v.join(wl.flag_repeat_contacts(v.drop(columns=["is_repeat", "caused_repeat", "prev_ticket_id"]),
                                       key=("customer_id", "category"))[["caused_repeat"]]
               .rename(columns={"caused_repeat": "caused_repeat_by_category"}))
    v = wl.add_costs(v)
    v = routing.label_work_type(v)
    v["true_owner"] = routing.true_owner(v)
    v["true_owner_high"] = routing.true_owner(v, move_confidence=("high",))
    v["created_shift"] = wl.created_shift(v)
    v["month"] = v["created_at"].dt.to_period("M")
    return v, t, raw


def main():
    OUT.mkdir(exist_ok=True)
    v, t_all, raw = prepare()
    agents = raw["agents"]
    print(f"Analysis view: {len(v):,} tickets, {v['month'].min()} .. {v['month'].max()} "
          f"(excluded: {int((~t_all['in_scope']).sum())} pre-2025 rows, {int(t_all['is_duplicate'].sum())} duplicates)")

    # ------------------------------------------------------------------ 1. the chart she asked for
    print("\n== 1. Monthly volume by bot category and by assigned_team")
    by_cat = v.pivot_table(index="month", columns="category", values="ticket_id", aggfunc="count", fill_value=0)
    by_cat = by_cat[by_cat.sum().sort_values(ascending=False).index]
    by_team = v.pivot_table(index="month", columns="assigned_team", values="ticket_id", aggfunc="count", fill_value=0)
    by_team = by_team[by_team.sum().sort_values(ascending=False).index]
    by_cat.to_csv(OUT / "monthly_by_category.csv")
    by_team.to_csv(OUT / "monthly_by_assigned_team.csv")
    small_multiples(by_cat, "Tickets per month by bot category, Jan 2025 - Jun 2026", "monthly_by_category.png",
                    highlight=("Billing & Payments", "Delivery & Shipping"))
    small_multiples(by_team, "Tickets per month by first-assigned team, Jan 2025 - Jun 2026",
                    "monthly_by_assigned_team.png", highlight=("Billing", "Logistics"))
    share = v["assigned_team"].value_counts(normalize=True)
    print(f"  assigned share: { {k: pct(x) for k, x in share.items()} }")
    with_2024 = t_all[~t_all["is_duplicate"]]["assigned_team"].value_counts(normalize=True)
    print(f"  incl. 139 pre-2025 rows: Billing {pct(with_2024['Billing'])}, Logistics {pct(with_2024['Logistics'])}")
    rec = v[v["month"].astype(str).between(*RECENT)]
    rs = rec["assigned_team"].value_counts(normalize=True)
    print(f"  Jan-Jun 2026 assigned share: Billing {pct(rs['Billing'])}, Logistics {pct(rs['Logistics'])}, "
          f"Chat Frontline {pct(rs['Chat Frontline'])}")

    # ------------------------------------------------------------------ 2. by resolving team
    print("\n== 2. Monthly volume by RESOLVING team (agent_id -> roster)")
    by_res = v.pivot_table(index="month", columns="resolver_team", values="ticket_id", aggfunc="count", fill_value=0)
    by_res = by_res[by_res.sum().sort_values(ascending=False).index]
    by_res.to_csv(OUT / "monthly_by_resolver_team.csv")
    small_multiples(by_res, "Tickets per month by the team whose agent resolved them",
                    "monthly_by_resolver_team.png", highlight=("Billing", "Logistics"))
    cmp = pd.DataFrame({"assigned": v["assigned_team"].value_counts(),
                        "resolved_by": v["resolver_team"].value_counts()})
    cmp["diff"] = cmp["resolved_by"] - cmp["assigned"]
    cmp.to_csv(OUT / "assigned_vs_resolver_totals.csv")
    print(cmp.sort_values("resolved_by", ascending=False).to_string())
    flow = pd.crosstab(v["assigned_team"], v["resolver_team"])
    flow.to_csv(OUT / "assigned_to_resolver_flow.csv")
    print(f"  Billing-assigned resolved by Logistics: {flow.loc['Billing', 'Logistics']:,} "
          f"({pct(flow.loc['Billing', 'Logistics'] / flow.loc['Billing'].sum())} of Billing-assigned)")
    print(f"  into Logistics from other teams: {flow['Logistics'].sum() - flow.loc['Logistics', 'Logistics']:,}; "
          f"of which from Billing {flow.loc['Billing', 'Logistics']:,}")

    # ------------------------------------------------------------------ 3. workload
    print("\n== 3. Workload by team (Tier 2 reported separately)")
    for col, fname in [("assigned_team", "workload_by_assigned_team.csv"),
                       ("resolver_team", "workload_by_resolver_team.csv"),
                       ("true_owner", "workload_by_true_owner.csv")]:
        w = wl.team_workload(v, col)
        w.round(4).to_csv(OUT / fname)
    w = wl.team_workload(v, "assigned_team")
    show = ["tickets", "share", "median_handle_h", "p75_handle_h", "mean_transfers_helpdesk", "repeat_rate",
            "fr_breach_rate", "breaches", "csat_mean", "csat_n", "cost_per_ticket_inr", "total_cost_inr"]
    print("  by ASSIGNED team")
    print(w[w["tier"] == "Tier 1"][show].round(3).to_string())
    print("  Tier 2 (not ranked against Tier 1)")
    print(w[w["tier"] == "Tier 2"][show].round(3).to_string())
    print("  channel mix by assigned team")
    print(w[["chat", "email", "voice", "social"]].round(3).to_string())
    wr = wl.team_workload(v, "resolver_team")
    print("  by RESOLVER team")
    print(wr[show].round(3).to_string())
    print(f"  overall: median handle {v['handle_h'].median():.2f} h; repeat rate (cust+sku) {pct(v['caused_repeat'].mean())} "
          f"vs (cust+category) {pct(v['caused_repeat_by_category'].mean())}; breach {pct(v['fr_breach'].mean())}; "
          f"CSAT {v['csat_score'].mean():.2f} (n={v['csat_score'].count():,}, {pct(v['csat_score'].notna().mean())} response)")
    rep_cat = v.groupby("assigned_team")["caused_repeat_by_category"].mean()
    print(f"  repeat rate by assigned team (cust+category key): { {k: pct(x) for k, x in rep_cat.items()} }")
    print(f"  total policy cost in view: Rs {v['total_cost'].sum():,.0f}; breach credits Rs {v['breach_cost'].sum():,.0f}; "
          f"helpdesk transfer cost Rs {v['transfer_cost'].sum():,.0f}")

    # ------------------------------------------------------------------ 4. capacity
    print("\n== 4. Capacity (roster) and breach clustering")
    roster = pd.crosstab(agents["team"], agents["shift"])
    roster["agents"] = roster.sum(axis=1)
    roster.to_csv(OUT / "roster_team_shift.csv")
    print(roster.to_string())
    months_rec = rec["month"].nunique()
    rec = v[v["month"].astype(str).between(*RECENT)]
    cap_rows = []
    for col in ["assigned_team", "resolver_team", "true_owner"]:
        g = rec.groupby(col)
        work_h = (g["contact_cost"].sum() + g["transfer_cost"].sum()) / wl.AGENT_HOUR_INR / months_rec
        n_ag = agents["team"].value_counts()
        d = pd.DataFrame({
            "view": col, "agents": n_ag,
            "tickets_per_month": g.size() / months_rec,
        })
        d["tickets_per_agent_month"] = d["tickets_per_month"] / d["agents"]
        d["tickets_per_agent_shift"] = d["tickets_per_agent_month"] / WORK_MONTH_SHIFTS
        d["policy_cost_hours_per_agent_month"] = work_h / d["agents"]
        d["available_hours_per_agent_month"] = wl.SHIFT_HOURS * WORK_MONTH_SHIFTS
        d["load_index"] = d["policy_cost_hours_per_agent_month"] / d["available_hours_per_agent_month"]
        cap_rows.append(d)
    cap = pd.concat(cap_rows).rename_axis("team").reset_index()
    cap["tier"] = cap["team"].map(lambda x: "Tier 2" if x == wl.TIER2_TEAM else "Tier 1")
    cap.round(3).to_csv(OUT / "capacity_per_agent_jan_jun_2026.csv", index=False)
    print(f"  Jan-Jun 2026 ({months_rec} months), {WORK_MONTH_SHIFTS} shifts/agent/month assumed:")
    print(cap.sort_values(["view", "tickets_per_agent_month"], ascending=[True, False]).round(2).to_string(index=False))

    # per agent, per shift (resolver view)
    pa = rec.groupby(["resolver_team", "resolver_shift", "agent_id"]).size().div(months_rec).rename("tickets_per_month")
    pa.round(1).to_csv(OUT / "tickets_per_agent_month_jan_jun_2026.csv")
    pts = pa.groupby(["resolver_team", "resolver_shift"]).agg(["count", "mean", "min", "max"]).round(1)
    print("  tickets resolved per agent per month by team x shift (Jan-Jun 2026):")
    print(pts.to_string())

    # breach clustering
    by_hour = v.pivot_table(index="assigned_team", columns=v["created_at"].dt.hour, values="fr_breach",
                             aggfunc="mean").astype(float)
    by_hour.round(3).to_csv(OUT / "breach_rate_team_by_created_hour.csv")
    n_hour = v.pivot_table(index="assigned_team", columns=v["created_at"].dt.hour, values="ticket_id", aggfunc="count")
    n_hour.to_csv(OUT / "tickets_team_by_created_hour.csv")
    fig, ax = plt.subplots(figsize=(11, 3.6))
    order = TIER1 + [wl.TIER2_TEAM]
    m = by_hour.reindex(order)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", SEQ)
    im = ax.imshow(m.values, aspect="auto", cmap=cmap, vmin=0, vmax=0.4)
    ax.set_yticks(range(len(order)), order, fontsize=8, color=INK)
    ax.set_xticks(range(24), [f"{h:02d}" for h in range(24)], fontsize=7, color=INK2)
    ax.set_xlabel("Hour ticket was created (IST)", fontsize=8, color=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.ax.tick_params(labelsize=7, colors=INK2)
    cb.set_label("first-response breach rate", fontsize=8, color=INK2)
    ax.set_title("First-response breach rate by team and hour created (blank = no tickets)",
                 fontsize=10, color=INK, loc="left")
    save(fig, "breach_rate_by_team_hour.png")

    bs = v.pivot_table(index="assigned_team", columns="created_shift", values="fr_breach", aggfunc="mean").astype(float)
    bs.round(3).to_csv(OUT / "breach_rate_team_by_created_shift.csv")
    print("  breach rate by assigned team x shift the ticket was created in:")
    print(bs.round(3).to_string())
    br = v.groupby(["resolver_team", "resolver_shift"])["fr_breach"].agg(["mean", "sum", "count"])
    br.round(3).to_csv(OUT / "breach_rate_by_resolver_team_shift.csv")
    print("  breach rate by RESOLVING agent's team x shift (policy s3 reporting basis):")
    print(br.round(3).to_string())
    by_ch = v.pivot_table(index="assigned_team", columns="channel", values="fr_breach", aggfunc="mean").astype(float)
    by_ch.round(3).to_csv(OUT / "breach_rate_team_by_channel.csv")
    print("  breach rate by assigned team x channel:")
    print(by_ch.round(3).to_string())

    # ------------------------------------------------------------------ 5. mis-routing
    print("\n== 5. Mis-routing: Billing-tagged tickets that are delivery work")
    b = v[v["assigned_team"] == "Billing"]
    nb = len(b)
    print(f"  Billing-tagged tickets: {nb:,}")
    sig = pd.DataFrame({
        "note_misroute": b["note_misroute"], "note_delivery": b["note_delivery"],
        "note_payment": b["note_payment"], "resolver_logistics": b["resolver_team"].eq("Logistics"),
        "msg_delivery": b["msg_delivery"]})
    print(f"  signal prevalence: { {k: f'{int(s.sum()):,} ({pct(s.mean())})' for k, s in sig.items()} }")
    lab = pd.crosstab([b["work_type"], b["confidence"]], b["resolver_team"], margins=True)
    lab.to_csv(OUT / "billing_work_type_by_resolver.csv")
    print(lab.to_string())
    agree = pd.crosstab(b["work_type"], b["msg_delivery"].map({True: "msg says delivery", False: "msg does not"}))
    agree.to_csv(OUT / "billing_label_vs_message.csv")
    print("  label vs customer's message:")
    print(agree.to_string())
    dl = b["work_type"].eq("delivery")
    print(f"  delivery work: {int(dl.sum()):,} ({pct(dl.mean())}); high {int((dl & b['confidence'].eq('high')).sum()):,}, "
          f"medium {int((dl & b['confidence'].eq('medium')).sum()):,}")
    print(f"  message agrees on delivery tickets: {pct(b[dl]['msg_delivery'].mean())}; "
          f"message says delivery on billing-labelled tickets: {pct(b[b['work_type'].eq('billing')]['msg_delivery'].mean())}")
    hdb = b[b["source_system"] == "helpdesk"]
    print(f"  helpdesk only: delivery {pct(hdb['work_type'].eq('delivery').mean())} of {len(hdb):,}; "
          f"legacy: {pct(b[b['source_system']=='legacy_fd']['work_type'].eq('delivery').mean())}")
    mtrend = b.groupby("month")["work_type"].apply(lambda s: (s == "delivery").mean())
    mtrend.round(3).to_csv(OUT / "billing_delivery_share_by_month.csv")
    print(f"  monthly delivery share of Billing-tagged: min {pct(mtrend.min())}, max {pct(mtrend.max())}")

    # hand-label check: 60 Billing-tagged tickets drawn with sample(60, random_state=2026),
    # labelled by reading notes (message when notes were too thin), blind to the rule's output.
    hand = pd.read_csv(LABELS)
    drawn = b.sample(60, random_state=2026)["ticket_id"]
    assert set(drawn) == set(hand["ticket_id"]), "hand-label file does not match the seeded sample"
    hb = b.set_index("ticket_id").loc[hand["ticket_id"]].assign(hand=hand["hand_label"].values == "delivery")
    sigs = {
        "rule (notes + resolver)": hb["work_type"].eq("delivery"),
        "resolver team = Logistics only": hb["resolver_team"].eq("Logistics"),
        "customer message only": hb["msg_delivery"],
    }
    ev = []
    for name, pred in sigs.items():
        tp = int((pred & hb["hand"]).sum()); fp = int((pred & ~hb["hand"]).sum())
        fn = int((~pred & hb["hand"]).sum()); tn = int((~pred & ~hb["hand"]).sum())
        acc = (tp + tn) / len(hb)
        lo, hi = wilson(tp + tn, len(hb))
        ev.append({"signal": name, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "accuracy": acc,
                   "acc_95ci_low": lo, "acc_95ci_high": hi,
                   "precision": tp / (tp + fp) if tp + fp else float("nan"),
                   "recall": tp / (tp + fn) if tp + fn else float("nan")})
    ev = pd.DataFrame(ev)
    ev.round(3).to_csv(OUT / "routing_rule_vs_hand_labels.csv", index=False)
    print(f"  hand-labelled sample: {len(hb)} tickets, {int(hb['hand'].sum())} delivery by hand")
    print(ev.round(3).to_string(index=False))
    dis = hb[sigs["rule (notes + resolver)"] != hb["hand"]]
    print(f"  rule disagreements: {dis.index.tolist()} (rule label {dis['work_type'].tolist()})")

    # outcomes: misrouted vs genuine billing vs native Logistics delivery
    grp = pd.Series("other", index=v.index)
    grp[(v["assigned_team"] == "Billing") & v["work_type"].eq("delivery")] = "Billing-tagged, delivery work"
    grp[(v["assigned_team"] == "Billing") & v["work_type"].eq("billing")] = "Billing-tagged, billing work"
    grp[(v["assigned_team"] == "Billing") & v["work_type"].eq("unclear")] = "Billing-tagged, unclear"
    grp[v["assigned_team"] == "Logistics"] = "Logistics-tagged (bot got it right)"
    vv = v.assign(group=grp)
    vv = vv[vv["group"] != "other"]
    hd_ = vv["source_system"] == "helpdesk"
    oc = pd.DataFrame({
        "tickets": vv.groupby("group").size(),
        "fr_breach_rate": vv.groupby("group")["fr_breach"].mean().astype(float),
        "median_fr_minutes": vv.groupby("group")["fr_minutes"].median(),
        "median_handle_h": vv.groupby("group")["handle_h"].median(),
        "median_created_to_resolved_h": vv.assign(r=(vv["resolved_at"] - vv["created_at"]).dt.total_seconds() / 3600)
                                          .groupby("group")["r"].median(),
        "mean_transfers_helpdesk": vv[hd_].groupby("group")["transfers"].mean().astype(float),
        "helpdesk_n": vv[hd_].groupby("group").size(),
        "repeat_rate_cust_sku": vv.groupby("group")["caused_repeat"].mean(),
        "repeat_rate_cust_category": vv.groupby("group")["caused_repeat_by_category"].mean(),
        "csat_mean": vv.groupby("group")["csat_score"].mean().astype(float),
        "csat_n": vv.groupby("group")["csat_score"].count(),
        "cost_per_ticket_inr": vv.groupby("group")["total_cost"].mean(),
    })
    oc.round(3).to_csv(OUT / "misrouting_outcomes.csv")
    print(oc.round(3).to_string())
    mis = vv[vv["group"] == "Billing-tagged, delivery work"]
    mis_hd = mis[mis["source_system"] == "helpdesk"]
    print(f"  delivery-in-Billing tickets: breaches {int(mis['fr_breach'].sum()):,} (Rs {mis['breach_cost'].sum():,.0f}), "
          f"helpdesk transfers {int(mis_hd['transfers'].sum()):,} (Rs {mis_hd['transfer_cost'].sum():,.0f}) "
          f"over {mis_hd['month'].nunique()} helpdesk months")
    # excess breaches vs the bot-got-it-right Logistics rate
    lr = oc.loc["Logistics-tagged (bot got it right)", "fr_breach_rate"]
    excess = mis["fr_breach"].sum() - lr * len(mis)
    print(f"  excess breaches vs Logistics-tagged rate ({pct(lr)}): {excess:,.0f} over {mis['month'].nunique()} months "
          f"= Rs {excess * wl.BREACH_CREDIT_INR:,.0f}")
    rec_mis = mis[mis["month"].astype(str).between(*RECENT)]
    rec_mis_hd = rec_mis[rec_mis["source_system"] == "helpdesk"]
    print(f"  Jan-Jun 2026: {len(rec_mis):,} delivery-in-Billing tickets ({len(rec_mis)/6:.0f}/month), breaches "
          f"{int(rec_mis['fr_breach'].sum())}, transfers {int(rec_mis_hd['transfers'].sum())} "
          f"(Rs {rec_mis_hd['transfer_cost'].sum():,.0f}), breach credits Rs {rec_mis['breach_cost'].sum():,.0f}")

    lr_rec = rec[rec["assigned_team"] == "Logistics"]["fr_breach"].mean()
    ex_rec = rec_mis["fr_breach"].sum() - lr_rec * len(rec_mis)
    half = rec_mis_hd["transfer_cost"].sum() + ex_rec * wl.BREACH_CREDIT_INR
    print(f"  Jan-Jun 2026 avoidable cost if routed straight to Logistics: transfers Rs {rec_mis_hd['transfer_cost'].sum():,.0f} "
          f"+ excess breaches {ex_rec:.1f} x Rs 350 = Rs {ex_rec * wl.BREACH_CREDIT_INR:,.0f} -> Rs {half:,.0f} per 6 months, "
          f"~Rs {2 * half:,.0f} a year (vs Rs 9,00,000 a year for two hires)")
    print(f"  Jan-Jun 2026 Billing-tagged delivery tickets: {pct(len(rec_mis) / len(rec[rec['assigned_team'] == 'Billing']))} of Billing-tagged")

    # "Other"-tagged delivery work (same rule, not moved in the main ranking)
    oth = v[v["category"] == "Other"]
    print(f"  'Other'-tagged tickets with delivery work in notes: {int(oth['work_type'].eq('delivery').sum()):,} of {len(oth):,} "
          f"({pct(oth['work_type'].eq('delivery').mean())}); resolver teams "
          f"{oth[oth['work_type'].eq('delivery')]['resolver_team'].value_counts().to_dict()}")

    # ranking change
    views = {
        "first-assigned (bot tag)": v["assigned_team"],
        "resolving agent's team": v["resolver_team"],
        "true owner (Billing delivery work -> Logistics)": v["true_owner"],
        "true owner, high-confidence moves only": v["true_owner_high"],
    }
    rank = pd.DataFrame({k: s.value_counts() for k, s in views.items()}).reindex(TIER1 + [wl.TIER2_TEAM])
    n_ag = agents["team"].value_counts()
    for k in list(views):
        rank[f"{k} / agent"] = (rank[k] / n_ag.reindex(rank.index)).round(1)
    rank.to_csv(OUT / "team_ranking_by_view.csv")
    print("  team volume under each view (Tier 2 listed but not ranked):")
    print(rank.to_string())
    t1 = rank.loc[TIER1]
    for k in views:
        top = t1[k].sort_values(ascending=False)
        spec = top.drop(["Chat Frontline", "Email Frontline", "Voice Frontline"])
        print(f"  [{k}] Tier 1 order: {list(top.index)}; specialist order: {list(spec.index)}; "
              f"per-agent order: {list(t1[k + ' / agent'].sort_values(ascending=False).index)}")

    # ranking chart: Tier 1, three views, horizontal grouped bars
    sel = ["first-assigned (bot tag)", "resolving agent's team", "true owner (Billing delivery work -> Logistics)"]
    lab_short = ["Bot tag (what Priya's chart shows)", "Who resolved it", "Who owns the work (policy s6)"]
    d = t1[sel].sort_values(sel[0])
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    y = range(len(d))
    h = 0.26
    for i, (c, lbl, col) in enumerate(zip(sel, lab_short, [S1, S2, S3])):
        ys = [k + (1 - i) * (h + 0.02) for k in y]
        ax.barh(ys, d[c], height=h, color=col, label=lbl, edgecolor=SURFACE, linewidth=1)
        for yy, team, val in zip(ys, d.index, d[c]):
            if team in ("Billing", "Logistics"):
                ax.text(val + 30, yy, f"{int(val):,}", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(list(y), d.index, fontsize=9, color=INK)
    style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Tickets, Jan 2025 - Jun 2026 (Tier 1 teams only)", fontsize=8, color=INK2)
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=INK)
    ax.set_title("Billing's volume lead depends on counting by the bot's tag", fontsize=10, color=INK, loc="left")
    save(fig, "team_ranking_by_view.png")
    print("\nWrote:", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
