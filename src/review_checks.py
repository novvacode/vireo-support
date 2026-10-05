"""Hostile-review checks.   python -m src.review_checks  -> outputs/review_checks.csv + .txt

1. Leakage: how many gold tickets' messages were printed during stage-2 exploration (reproducible samples only).
2. Owner-definition bias: bot owner accuracy if the arguable owner choices in our taxonomy are scored leniently.
3. Counterfactual: is the Logistics-tagged transfer rate (0.088 in the business case) a fair "routed right" baseline
   for delivery tickets that are worded like payment problems?
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import clean, routing
from src.gold_sample import PAID
from src.load import load_all
from src.stage2 import wilson

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
rows, lines = [], []


def rec(check, key, value, note=""):
    rows.append({"check": check, "key": key, "value": value, "note": note})
    lines.append(f"[{check}] {key}: {value}" + (f"  ({note})" if note else ""))


def main():
    t, _ = clean.clean_tickets(load_all())
    v = clean.analysis_view(t)
    gold = pd.concat([pd.read_csv(ROOT / "labels" / "gold_v1_labels.csv").assign(exp="v1"),
                      pd.read_csv(ROOT / "labels" / "gold_v2_labels.csv").assign(exp="v2")])

    # 1. leakage: reproducible message prints from stage 2 (Billing-tagged only)
    b = v[v["assigned_team"] == "Billing"]
    seen = set(b[b["resolver_team"] == "Billing"].sample(15, random_state=3)["ticket_id"])   # stage-2 message sample
    seen |= set(b.sample(60, random_state=2026)["ticket_id"])                               # 60 hand-label sample
    overlap = gold[gold["ticket_id"].isin(seen)]
    rec("leakage", "messages_printed_reproducibly_in_stage2", len(seen), "Billing-tagged only")
    rec("leakage", "gold_tickets_among_them", len(overlap), ", ".join(overlap["ticket_id"]) or "none")
    rec("leakage", "gold_total", len(gold))
    g_all = pd.concat([pd.read_csv(OUT / "gold_to_label.csv"), pd.read_csv(OUT / "gold_to_label_v2.csv")])
    clean_g = g_all[~g_all["ticket_id"].isin(seen)]
    rec("leakage", "tool_category_accuracy_all_gold", f"{int(g_all['tool_correct'].sum())}/{len(g_all)}")
    rec("leakage", "tool_category_accuracy_excluding_seen", f"{int(clean_g['tool_correct'].sum())}/{len(clean_g)}")
    rec("leakage", "not_reproducible", "further ad-hoc prints in stage-1/2 exploration (count cannot be reconstructed)",
        "earlier regex versions; Billing and duplicate-search views only")

    # 2. owner-definition bias (gold v1 + v2 tables written by src.validate)
    g = pd.concat([pd.read_csv(OUT / "gold_to_label.csv"), pd.read_csv(OUT / "gold_to_label_v2.csv")])
    device = {"sound_or_hardware", "battery_charging", "pairing_connection", "app_firmware_login"}
    arguable = (
        (g["bot_team"].eq("Escalations & Warranty") & g["gold_label"].isin(device))       # policy s6: Tier 2 owns escalated hardware
        | (g["bot_team"].eq("Logistics") & g["gold_label"].eq("cancel_or_change"))         # address change: arguably Logistics
        | (g["bot_team"].eq("Billing") & g["gold_label"].eq("refund_not_received"))        # refund money: arguably Billing
        | (g["bot_team"].eq("Returns Desk") & g["gold_label"].isin({"damaged_or_wrong_item", "invoice_or_price"}))
    )
    strict_k, n = int(g["bot_owner_correct"].sum()), len(g)
    lenient_k = int((g["bot_owner_correct"] | arguable).sum())
    tool_k = int(g["tool_owner_correct"].sum())
    for name, k in [("bot_owner_accuracy_strict", strict_k), ("bot_owner_accuracy_lenient", lenient_k),
                    ("tool_owner_accuracy", tool_k)]:
        lo, hi = wilson(k, n)
        rec("owner_definitions", name, f"{k}/{n} = {k / n:.1%}", f"95% CI {lo:.1%}-{hi:.1%}")
    rec("owner_definitions", "bot_errors_that_are_arguable_definitions", int((~g["bot_owner_correct"] & arguable).sum()))
    wrong = g[~g["bot_owner_correct"] & ~arguable]
    rec("owner_definitions", "remaining_bot_owner_errors_by_type",
        str(wrong.groupby(["bot_team", "gold_owner"]).size().sort_values(ascending=False).head(5).to_dict()))

    # 3. counterfactual transfer rate
    v = routing.label_work_type(v)
    h1 = v[v["created_at"].dt.to_period("M").astype(str).between("2026-01", "2026-06")]
    lg = h1[h1["assigned_team"] == "Logistics"]
    msg = lg["customer_message"].str.lower().str.contains(PAID)
    for name, x in [("logistics_tagged_all", lg), ("logistics_tagged_payment_worded", lg[msg]),
                    ("logistics_tagged_not_payment_worded", lg[~msg])]:
        rec("counterfactual", f"transfers_per_ticket_{name}", f"{x['transfers'].astype(float).mean():.3f}", f"n={len(x)}")

    pd.DataFrame(rows).to_csv(OUT / "review_checks.csv", index=False)
    (OUT / "review_checks.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
