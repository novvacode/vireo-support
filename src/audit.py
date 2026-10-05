"""Print before/after counts for every cleaning step. Every number in docs/data_audit.md
comes from this script:  python -m src.audit
"""
from __future__ import annotations

import pandas as pd

from src import clean
from src.load import load_all


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def headline(t: pd.DataFrame) -> dict:
    """A few numbers that later analysis will lean on, to show how much each fix moves them."""
    done = t[t["status"].isin(["resolved", "closed"]) & t["resolved_at"].notna()]
    res_h = (done["resolved_at"] - done["created_at"]).dt.total_seconds() / 3600
    fr_m = (t["first_response_at"] - t["created_at"]).dt.total_seconds() / 60
    breach = fr_m > t["channel"].map(clean.FR_TARGET_MIN)
    return {
        "tickets": len(t),
        "billing_share": (t["assigned_team"] == "Billing").mean(),
        "logistics_share": (t["assigned_team"] == "Logistics").mean(),
        "median_resolution_h": res_h.median(),
        "negative_resolution": int((res_h < 0).sum()),
        "fr_breach_rate": breach.mean(),
        "csat_mean": t["csat_score"].mean(),
    }


def show(label: str, h: dict) -> None:
    print(f"  {label:34s} n={h['tickets']:>6,}  Billing={_pct(h['billing_share'])}  "
          f"Logistics={_pct(h['logistics_share'])}  med_res={h['median_resolution_h']:.2f}h  "
          f"neg_res={h['negative_resolution']:,}  breach={_pct(h['fr_breach_rate'])}  "
          f"csat={h['csat_mean']:.3f}")


def main() -> None:
    raw = load_all()
    t0 = raw["tickets"]
    print("== Raw row counts")
    for k, v in raw.items():
        print(f"  {k:10s} {len(v):>7,}")
    print(f"  tickets by source: {t0['source_system'].value_counts().to_dict()}")
    print(f"  ticket_id unique: {t0['ticket_id'].is_unique}")

    print("\n== 1. Legacy resolved_at UTC -> IST")
    lg = t0["source_system"].eq("legacy_fd")
    neg = lambda d: int((d["resolved_at"] < d["created_at"]).sum())
    neg_fr = lambda d: int((d["resolved_at"] < d["first_response_at"]).sum())
    t1 = clean.shift_legacy_resolved_to_ist(t0)
    print(f"  legacy resolved < created : before {neg(t0[lg]):,}  after {neg(t1[lg]):,}")
    print(f"  legacy resolved < first_response: before {neg_fr(t0[lg]):,}  after {neg_fr(t1[lg]):,}")
    print(f"  helpdesk resolved < created: {neg(t0[~lg]):,}")
    print(f"  legacy rows shifted: {int(t0[lg]['resolved_at'].notna().sum()):,}")
    med = lambda d: ((d["resolved_at"] - d["created_at"]).dt.total_seconds() / 3600).groupby(d["channel"]).median().round(2).to_dict()
    print(f"  median resolution h by channel, legacy before: {med(t0[lg])}")
    print(f"  median resolution h by channel, legacy after : {med(t1[lg])}")
    print(f"  median resolution h by channel, helpdesk     : {med(t0[~lg])}")
    show("headline raw", headline(t0))
    show("headline after tz fix", headline(t1))

    print("\n== 2. Rows outside Jan 2025 - Jun 2026")
    t2 = clean.flag_out_of_range(t1)
    out = t2[~t2["in_scope"]]
    print(f"  out of range: {len(out):,}  by system {out['source_system'].value_counts().to_dict()}  "
          f"range {out['created_at'].min()} .. {out['created_at'].max()}")
    print(f"  out-of-range by category: {out['category'].value_counts().to_dict()}")
    show("headline in-scope only", headline(t2[t2["in_scope"]]))

    print("\n== 3. Duplicates / re-imports")
    pairs = clean.find_duplicate_candidates(t2)
    print(f"  strict pairs (same cust+sku, <=48h or 5h30m apart, text sim>=0.85): {len(pairs)}")
    loose = clean.find_duplicate_candidates(t2, max_hours=1, min_text_sim=0.0)
    print(f"  loose pairs (same cust+sku within 1h, any text): {len(loose)}  "
          f"max text sim {loose['text_sim'].max() if len(loose) else 'n/a'}")
    m = t2.merge(t2, on="customer_id", suffixes=("_a", "_b"))
    m = m[(m["ticket_id_a"] < m["ticket_id_b"]) & (m["source_system_a"] != m["source_system_b"])]
    print(f"  cross-system same-customer pairs: {len(m):,}; created exactly 5h30m apart: "
          f"{int(((m['created_at_b'] - m['created_at_a']).abs() == clean.IST_OFFSET).sum())}")
    sim = [clean.text_similarity(a, b) for a, b in zip(m["customer_message_a"], m["customer_message_b"])]
    print(f"  cross-system same-customer pairs with text sim >= 0.85: {sum(s >= 0.85 for s in sim)}")
    nt = t2.assign(nm=t2["customer_message"].map(clean._norm_text))
    xs = nt.merge(nt, on="nm", suffixes=("_a", "_b"))
    xs = xs[(xs["source_system_a"] == "legacy_fd") & (xs["source_system_b"] == "helpdesk")]
    print(f"  cross-system pairs with identical normalised text: {len(xs)}; same customer: "
          f"{int((xs['customer_id_a'] == xs['customer_id_b']).sum())}")
    oid = t2[t2["order_id"].notna()]
    xo = oid[oid["source_system"] == "legacy_fd"].merge(
        oid[oid["source_system"] == "helpdesk"], on="order_id", suffixes=("_a", "_b"))
    gap_d = (xo["created_at_b"] - xo["created_at_a"]).dt.total_seconds() / 86400
    xo_sim = [clean.text_similarity(a, b) for a, b in zip(xo["customer_message_a"], xo["customer_message_b"])]
    print(f"  order_ids on tickets in both systems: {xo['order_id'].nunique()} orders, {len(xo)} pairs, "
          f"min gap {gap_d.min():.1f} days, max text sim {max(xo_sim):.2f}")
    inv = {s: int((g.sort_values("ticket_id")["created_at"].diff().dt.total_seconds() < 0).sum())
           for s, g in t2.groupby("source_system")}
    print(f"  ticket_id ranges: {t2.groupby('source_system')['ticket_id'].agg(['min', 'max']).to_dict('index')}; "
          f"id-vs-time inversions {inv}")
    dup_text = t2[t2.duplicated("customer_message", keep=False)]
    print(f"  rows sharing an exact message text: {len(dup_text):,} across "
          f"{dup_text['customer_id'].nunique():,} customers (stock phrases)")

    print("\n== 4. Order join")
    tc, pairs = clean.clean_tickets(raw)
    print(f"  order_id blank in raw: {int(t0['order_id'].isna().sum()):,} ({_pct(t0['order_id'].isna().mean())})")
    print(f"  order_match: {tc['order_match'].value_counts().to_dict()}")
    amb = tc[tc["order_match"] == "fallback_ambiguous"]["n_order_candidates"]
    amb_counts = {int(k): int(v) for k, v in amb.value_counts().sort_index().items()}
    print(f"  ambiguous candidates per ticket: {amb_counts}")
    linked_before = t0["order_id"].notna().mean()
    linked_after = tc["order_match"].isin(["explicit", "message", "fallback_unique"]).mean()
    print(f"  tickets with a confident order link: before {_pct(linked_before)}  after {_pct(linked_after)}")
    print(f"  ticket created before linked order: {tc['order_after_ticket'].value_counts().to_dict()}")
    oat = tc[tc["order_after_ticket"].notna()]
    print(f"    by link type: {pd.crosstab(oat['order_match'], oat['order_after_ticket']).to_dict()}")
    print(f"    implausible by category: {oat[oat['order_after_ticket']=='implausible']['category'].value_counts().head(5).to_dict()}")
    print(f"    presale by category: {oat[oat['order_after_ticket']=='presale']['category'].value_counts().head(5).to_dict()}")

    print("\n== 5. Agents")
    a = raw["agents"]
    print(f"  roster rows {len(a)}, unique agent_id {a['agent_id'].nunique()}, unique names {a['name'].nunique()}")
    dn = a[a["name"].duplicated(keep=False)]
    print(f"  shared names: {dn[['agent_id','name','team']].values.tolist()}; tickets resolved: "
          f"{t0[t0['agent_id'].isin(dn['agent_id'])]['agent_id'].value_counts().to_dict()}")
    fl = t0[t0["assigned_team"].str.contains("Frontline")]
    print(f"  frontline team vs channel: {pd.crosstab(fl['channel'], fl['assigned_team']).to_dict()}")
    print(f"  categories per assigned team: {t0.groupby('assigned_team')['category'].nunique().to_dict()}")
    print(f"  roster rows with to_date: {int(a['to_date'].notna().sum())}; agents per team {a['team'].value_counts().to_dict()}")
    print(f"  tickets whose agent_id is missing from roster: {int((~t0['agent_id'].isin(a['agent_id'])).sum())}")
    print(f"  resolved by a team other than assigned: {int(tc['resolved_by_other_team'].sum()):,}")
    print(f"  Billing-assigned resolved by Logistics agent: "
          f"{int(((tc['assigned_team']=='Billing') & (tc['resolver_team']=='Logistics')).sum()):,}")
    hd = tc[tc["source_system"] == "helpdesk"]
    print(f"  helpdesk: other-team resolver but transfers==0: {int(tc['transfers_inconsistent'].sum()):,} "
          f"of {int(hd['resolved_by_other_team'].sum()):,} other-team resolutions")
    print(f"  helpdesk: same-team resolver but transfers>0: {int((~hd['resolved_by_other_team'] & hd['transfers'].gt(0)).sum()):,}")
    print(f"  mean transfers by assigned team (helpdesk): {hd.groupby('assigned_team')['transfers'].mean().round(3).to_dict()}")

    print("\n== 6. Status / CSAT / first response")
    print(f"  legacy open/pending (stale): {int(tc['stale_legacy_open'].sum())}")
    print(f"  status vs resolved_at blank: {pd.crosstab(t0['status'], t0['resolved_at'].isna()).to_dict()}")
    print(f"  CSAT response rate: {_pct(t0['csat_score'].notna().mean())}; on closed (auto) tickets "
          f"{_pct(t0[t0['status']=='closed']['csat_score'].notna().mean())}")
    print(f"  CSAT present on open/pending: {int(tc['csat_on_unresolved'].sum())}")
    print(f"  CSAT mean (blanks excluded) {t0['csat_score'].mean():.3f} vs blanks-as-0 (WRONG) "
          f"{t0['csat_score'].fillna(0).mean():.3f}")
    print(f"  first response at 0 minutes: {int(tc['fr_zero_minutes'].sum())} by channel "
          f"{tc[tc['fr_zero_minutes']]['channel'].value_counts().to_dict()}")
    print(f"  first_response blank: {int(t0['first_response_at'].isna().sum())}")
    print(f"  FR breach rate overall: {_pct(tc['fr_breach'].mean())} ({int(tc['fr_breach'].sum()):,})")
    print(f"  FR breach rate by assigned team (helpdesk): "
          f"{ {k: _pct(v) for k, v in hd.groupby('assigned_team')['fr_breach'].mean().items()} }")

    print("\n== 7. Transfers blank on legacy")
    print(f"  transfers blank by system: {t0.groupby('source_system')['transfers'].apply(lambda s: int(s.isna().sum())).to_dict()}")
    print(f"  mean transfers if blanks were 0 (WRONG): {t0['transfers'].fillna(0).mean():.3f} vs helpdesk only {t0['transfers'].mean():.3f}")

    print("\n== 8. Refunds")
    r = t0["refund_amount_inr"]
    print(f"  refund rows {int(r.notna().sum()):,}; by system {t0[r.notna()]['source_system'].value_counts().to_dict()}")
    print(f"  amount w/o code {int((r.notna() & t0['refund_reason_code'].isna()).sum())}, "
          f"code w/o amount {int((r.isna() & t0['refund_reason_code'].notna()).sum())}")
    print(f"  median refund / retail price by system: {clean.legacy_refund_scale(t0, raw['products']).round(3).to_dict()}")
    print(f"  refund amount quantiles by system: {t0.groupby('source_system')['refund_amount_inr'].quantile([0, .5, 1]).unstack().to_dict('index')}")
    j = tc[tc["order_match"].isin(["explicit", "message", "fallback_unique"]) & r.notna()]
    print(f"  refund > linked order value: {int((j['refund_amount_inr'] > j['order_value_inr']).sum())}")
    print(f"  GW-OTHER refunds: {int(t0['refund_reason_code'].eq('GW-OTHER').sum())}, over Rs 500 cap: {int(tc['goodwill_over_cap'].sum())}")
    print(f"  refund & replacement on same TICKET: {int((r.notna() & t0['replacement_issued']).sum())}")
    both = tc[tc["order_refund_and_replacement"]]
    print(f"  refund & replacement on same ORDER (explicit/message/unique-fallback links): "
          f"{both['order_id'].nunique()} orders, {len(both)} tickets on those orders")
    strict = clean.flag_refund_and_replacement_per_order(tc.assign(
        order_match=tc["order_match"].where(tc["order_match"].isin(["explicit", "message"]), "excluded")))
    print(f"  ... using only explicit/message order ids: "
          f"{strict[strict['order_refund_and_replacement']]['order_id'].nunique()} orders")

    print("\n== 9. Volume per week (for the '650 tickets a week' question)")
    v = clean.analysis_view(tc)
    wk = v.set_index("created_at").resample("W-SUN").size()
    full = wk.iloc[1:-1]  # drop partial first/last weeks
    print(f"  full weeks Jan-Jun 2026: mean {full['2026-01':].mean():.0f}, min {full['2026-01':].min()}, max {full['2026-01':].max()}")
    mon = v["created_at"].dt.to_period("M").astype(str)
    sel = v[mon.between("2025-06", "2025-10")]
    print(f"  Jun-Oct 2025 monthly total: {sel['created_at'].dt.to_period('M').astype(str).value_counts().sort_index().to_dict()}; "
          f"Pulse 2 (VA-EB-PL2): {sel[sel['product_sku']=='VA-EB-PL2']['created_at'].dt.to_period('M').astype(str).value_counts().sort_index().to_dict()}")
    print(f"  legacy monthly: {v[v['source_system']=='legacy_fd']['created_at'].dt.to_period('M').astype(str).value_counts().sort_index().to_dict()}")
    print(f"  monthly Jan-Jun 2026: {v[v['created_at']>='2026-01-01']['created_at'].dt.to_period('M').value_counts().sort_index().astype(int).to_dict()}")

    print("\n== BEFORE / AFTER")
    show("raw (all rows, as exported)", headline(t0))
    show("cleaned analysis view", headline(v))
    print(f"  rows: raw {len(t0):,} -> analysis view {len(v):,} "
          f"(out of range {int((~tc['in_scope']).sum())}, duplicates {int(tc['is_duplicate'].sum())})")


if __name__ == "__main__":
    main()
