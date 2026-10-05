"""Workload measures per policy definitions (support-policy.pdf s3, s4, s10)."""
from __future__ import annotations

import pandas as pd

CONTACT_COST_INR = {"chat": 210, "email": 260, "voice": 520, "social": 240}  # s4
TRANSFER_COST_INR = 305       # s4
BREACH_CREDIT_INR = 350       # s3
AGENT_HOUR_INR = 165          # s4
SHIFT_HOURS = 8               # s4
TIER2_TEAM = "Escalations & Warranty"
SHIFT_OF_HOUR = {**{h: "Morning" for h in range(6, 14)}, **{h: "Day" for h in range(14, 22)},
                 **{h: "Night" for h in [22, 23, 0, 1, 2, 3, 4, 5]}}  # s7


def handle_hours(t: pd.DataFrame) -> pd.Series:
    """s10 handle time = first response -> resolution, hours. NaN when not resolved/closed."""
    done = t["status"].isin(["resolved", "closed"])
    h = (t["resolved_at"] - t["first_response_at"]).dt.total_seconds() / 3600
    return h.where(done).rename("handle_h")


def flag_repeat_contacts(t: pd.DataFrame, key=("customer_id", "product_sku"), window_days: int = 30) -> pd.DataFrame:
    """s10: a repeat contact is the same customer contacting again about the same issue within
    30 days of the previous contact's resolution. 'Same issue' = same `key` (default customer+SKU).
    If the previous contact was never resolved (open/pending), its window runs from its creation,
    so a stale open ticket does not turn every later contact into a "repeat".

    Adds: is_repeat (this ticket is a repeat), caused_repeat (the NEXT contact on this key was a
    repeat, i.e. this ticket failed first-contact resolution), prev_ticket_id.
    """
    key = list(key)
    t = t.copy()
    s = t.sort_values(key + ["created_at", "ticket_id"])
    g = s.groupby(key, sort=False)
    has_prev = g["created_at"].shift().notna()
    prev_end = g["resolved_at"].shift().fillna(g["created_at"].shift())
    s["is_repeat"] = has_prev & s["created_at"].le(prev_end + pd.Timedelta(days=window_days))
    s["prev_ticket_id"] = g["ticket_id"].shift().where(s["is_repeat"])
    nxt = s.groupby(key, sort=False)["is_repeat"].shift(-1)
    s["caused_repeat"] = nxt.astype("boolean").fillna(False).astype(bool)
    return t.join(s[["is_repeat", "caused_repeat", "prev_ticket_id"]])


def add_costs(t: pd.DataFrame) -> pd.DataFrame:
    """Policy-standard rupee cost per ticket. transfers cost only where transfers is known
    (helpdesk); legacy blanks contribute nothing, so transfer cost is a lower bound pre-Sep 2025."""
    t = t.copy()
    t["contact_cost"] = t["channel"].map(CONTACT_COST_INR).astype(float)
    t["transfer_cost"] = (t["transfers"].astype("Float64") * TRANSFER_COST_INR).astype(float)
    t["breach_cost"] = t["fr_breach"].astype(float) * BREACH_CREDIT_INR
    t["total_cost"] = t["contact_cost"] + t["transfer_cost"].fillna(0) + t["breach_cost"].fillna(0)
    return t


def created_shift(t: pd.DataFrame) -> pd.Series:
    return t["created_at"].dt.hour.map(SHIFT_OF_HOUR).rename("created_shift")


def team_workload(t: pd.DataFrame, team_col: str) -> pd.DataFrame:
    """One row per team: volume and workload measures. transfers use helpdesk rows only
    (blank never treated as 0); CSAT excludes blanks."""
    hd = t["source_system"].eq("helpdesk")
    g = t.groupby(team_col)
    out = pd.DataFrame({
        "tickets": g.size(),
        "share": g.size() / len(t),
        "chat": g["channel"].apply(lambda s: (s == "chat").mean()),
        "email": g["channel"].apply(lambda s: (s == "email").mean()),
        "voice": g["channel"].apply(lambda s: (s == "voice").mean()),
        "social": g["channel"].apply(lambda s: (s == "social").mean()),
        "median_handle_h": g["handle_h"].median(),
        "p75_handle_h": g["handle_h"].quantile(0.75),
        "helpdesk_tickets": t[hd].groupby(team_col).size(),
        "mean_transfers_helpdesk": t[hd].groupby(team_col)["transfers"].mean().astype(float),
        "repeat_rate": g["caused_repeat"].mean(),
        "fr_breach_rate": g["fr_breach"].mean().astype(float),
        "breaches": g["fr_breach"].sum().astype(int),
        "breach_credit_inr": g["breach_cost"].sum(),
        "csat_mean": g["csat_score"].mean().astype(float),
        "csat_n": g["csat_score"].count(),
        "contact_cost_inr": g["contact_cost"].sum(),
        "transfer_cost_inr_helpdesk": t[hd].groupby(team_col)["transfer_cost"].sum(),
        "total_cost_inr": g["total_cost"].sum(),
        "cost_per_ticket_inr": g["total_cost"].mean(),
    })
    out["tier"] = ["Tier 2" if i == TIER2_TEAM else "Tier 1" for i in out.index]
    return out.sort_values(["tier", "tickets"], ascending=[True, False])
