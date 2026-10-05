"""Cleaning steps for the Vireo tickets data.

Each fix is a small named function that takes DataFrames and returns a NEW DataFrame
(inputs are never mutated). Fixes that change values keep the raw value in a *_raw column.
Most functions only add a flag column: rows are never deleted here, so every downstream
number can say which rows it kept and why. `analysis_view` applies the agreed exclusions.

Decisions behind each step are recorded in docs/decisions.md; counts in docs/data_audit.md.
"""
from __future__ import annotations

import difflib
import re

import pandas as pd

IST_OFFSET = pd.Timedelta(hours=5, minutes=30)
SCOPE_START = pd.Timestamp("2025-01-01")
SCOPE_END = pd.Timestamp("2026-07-01")  # exclusive: stated range ends 30 Jun 2026
HELPDESK_GO_LIVE = pd.Timestamp("2025-09-14")
GOODWILL_CAP_INR = 500
FR_TARGET_MIN = {"chat": 15, "voice": 120, "social": 240, "email": 480}  # policy s3
ORDER_ID_RE = re.compile(r"\bVR\d{6}\b", re.IGNORECASE)


# ---------------------------------------------------------------- timestamps / scope

def shift_legacy_resolved_to_ist(t: pd.DataFrame) -> pd.DataFrame:
    """Legacy resolved_at was rebuilt from a UTC event log (policy s9). Add +5h30m.

    Applies to every legacy row with a resolved_at, not only the ones that look wrong.
    created_at and first_response_at are already IST in both systems.
    """
    t = t.copy()
    t["resolved_at_raw"] = t["resolved_at"]
    legacy = t["source_system"].eq("legacy_fd") & t["resolved_at"].notna()
    t.loc[legacy, "resolved_at"] = t.loc[legacy, "resolved_at"] + IST_OFFSET
    return t


def flag_out_of_range(t: pd.DataFrame, start=SCOPE_START, end=SCOPE_END) -> pd.DataFrame:
    """in_scope = created inside the stated range [1 Jan 2025, 1 Jul 2026)."""
    t = t.copy()
    t["in_scope"] = t["created_at"].ge(start) & t["created_at"].lt(end)
    return t


def flag_zero_minute_first_response(t: pd.DataFrame) -> pd.DataFrame:
    """first_response_at == created_at: 'human reply' in 0 minutes is suspicious, kept."""
    t = t.copy()
    t["fr_zero_minutes"] = t["first_response_at"].eq(t["created_at"])
    return t


def add_first_response_breach(t: pd.DataFrame) -> pd.DataFrame:
    """breach = first response later than the channel target (policy s3/s10)."""
    t = t.copy()
    mins = (t["first_response_at"] - t["created_at"]).dt.total_seconds() / 60
    target = t["channel"].map(FR_TARGET_MIN)
    t["fr_minutes"] = mins
    t["fr_breach"] = (mins > target).where(mins.notna() & target.notna()).astype("boolean")
    return t


# ---------------------------------------------------------------- duplicates

def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def text_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm_text(a), _norm_text(b)).ratio()


def find_duplicate_candidates(
    t: pd.DataFrame, max_hours: float = 48, min_text_sim: float = 0.85
) -> pd.DataFrame:
    """Pairs of tickets that look like the same contact recorded twice.

    Blocking key: same customer_id AND same product_sku (both systems pooled, so
    legacy<->helpdesk re-imports are covered). A pair is a duplicate when the opening
    messages are near-identical (normalised similarity >= min_text_sim) and the two
    created_at values are within max_hours of each other, OR exactly 5h30m apart
    (a re-import exported in UTC instead of IST).

    Returns one row per pair: ticket_id_a, ticket_id_b, hours_apart, text_sim, systems.
    """
    cols = ["ticket_id", "customer_id", "product_sku", "created_at", "customer_message", "source_system"]
    x = t[cols]
    m = x.merge(x, on=["customer_id", "product_sku"], suffixes=("_a", "_b"))
    m = m[m["ticket_id_a"] < m["ticket_id_b"]]
    hours = (m["created_at_b"] - m["created_at_a"]).dt.total_seconds().abs() / 3600
    close = hours.le(max_hours) | (hours - 5.5).abs().lt(1 / 60)
    m = m[close].assign(hours_apart=hours[close])
    m["text_sim"] = [
        text_similarity(a, b) for a, b in zip(m["customer_message_a"], m["customer_message_b"])
    ]
    m = m[m["text_sim"] >= min_text_sim]
    m["systems"] = m["source_system_a"] + "|" + m["source_system_b"]
    return m[["ticket_id_a", "ticket_id_b", "hours_apart", "text_sim", "systems"]].reset_index(drop=True)


def flag_duplicates(t: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """is_duplicate = True on the copy to drop. Keep the helpdesk row (it has transfers);
    within the same system keep the earlier ticket_id."""
    t = t.copy()
    t["is_duplicate"] = False
    t["duplicate_of"] = pd.NA
    if pairs.empty:
        return t
    sysmap = t.set_index("ticket_id")["source_system"]
    for a, b in zip(pairs["ticket_id_a"], pairs["ticket_id_b"]):
        keep, drop = (a, b)
        if sysmap[a] == "legacy_fd" and sysmap[b] == "helpdesk":
            keep, drop = b, a
        t.loc[t["ticket_id"].eq(drop), ["is_duplicate", "duplicate_of"]] = [True, keep]
    return t


# ---------------------------------------------------------------- order join

def recover_order_id_from_message(t: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Blank order_id but the customer typed a VRnnnnnn id in the message: use it, but only
    if that order exists AND belongs to the same customer_id and sku. Adds order_id_source."""
    t = t.copy()
    t["order_id_source"] = pd.Series(pd.NA, index=t.index, dtype="string")
    t.loc[t["order_id"].notna(), "order_id_source"] = "explicit"
    blank = t["order_id"].isna()
    found = t.loc[blank, "customer_message"].str.extract(f"({ORDER_ID_RE.pattern})", flags=re.I)[0].str.upper()
    o = orders.set_index("order_id")[["customer_id", "sku"]]
    for idx, oid in found.dropna().items():
        if oid in o.index and o.at[oid, "customer_id"] == t.at[idx, "customer_id"] \
                and o.at[oid, "sku"] == t.at[idx, "product_sku"]:
            t.at[idx, "order_id"] = oid
            t.at[idx, "order_id_source"] = "message"
    return t


def join_orders(t: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Attach order fields. Explicit/recovered order_id first; otherwise fall back to
    customer_id + sku. If the fallback finds more than one order the ticket is flagged
    'fallback_ambiguous' and left unjoined (we do not guess); n_order_candidates says how many.

    order_match: explicit | message | fallback_unique | fallback_ambiguous | unmatched
    """
    t = t.copy()
    if "order_id_source" not in t:
        t["order_id_source"] = t["order_id"].notna().map({True: "explicit", False: pd.NA})
    cand = orders.groupby(["customer_id", "sku"])["order_id"].agg(list)
    t["n_order_candidates"] = pd.array([pd.NA] * len(t), dtype="Int64")
    t["order_match"] = t["order_id_source"].astype("string")
    for idx in t.index[t["order_id"].isna()]:
        ids = cand.get((t.at[idx, "customer_id"], t.at[idx, "product_sku"]), [])
        t.at[idx, "n_order_candidates"] = len(ids)
        if len(ids) == 1:
            t.at[idx, "order_id"] = ids[0]
            t.at[idx, "order_match"] = "fallback_unique"
        elif len(ids) > 1:
            t.at[idx, "order_match"] = "fallback_ambiguous"
        else:
            t.at[idx, "order_match"] = "unmatched"
    keep = ["order_id", "order_date", "order_value_inr", "qty", "lot_code"]
    out = t.merge(orders[keep], on="order_id", how="left", validate="many_to_one")
    out.index = t.index
    return out


def flag_ticket_before_order(t: pd.DataFrame, presale_days: int = 14) -> pd.DataFrame:
    """Ticket created before the linked order was placed.
    presale  = gap <= presale_days (plausible pre-purchase question);
    implausible = longer gap (the linked order is probably the wrong one)."""
    t = t.copy()
    gap = (t["order_date"] - t["created_at"].dt.normalize()).dt.days
    before = gap.gt(0)
    t["order_after_ticket"] = pd.Series(pd.NA, index=t.index, dtype="string")
    t.loc[before & gap.le(presale_days), "order_after_ticket"] = "presale"
    t.loc[before & gap.gt(presale_days), "order_after_ticket"] = "implausible"
    return t


# ---------------------------------------------------------------- agents

def join_agents(t: pd.DataFrame, agents: pd.DataFrame) -> pd.DataFrame:
    """Attach the resolving agent's team/tier/site by agent_id (never by name, two agents
    share a display name). Roster can hold several rows per agent with from/to dates:
    pick the row whose date range covers created_at. Raises if any ticket gets 0 or 2+ rows."""
    a = agents.rename(columns={"name": "agent_name", "team": "resolver_team",
                               "tier": "resolver_tier", "site": "resolver_site",
                               "shift": "resolver_shift"})
    tt = t.reset_index().rename(columns={"index": "_row"})
    m = tt.merge(a, on="agent_id", how="inner")
    start = m["from_date"].fillna(pd.Timestamp.min)
    end = m["to_date"].fillna(pd.Timestamp.max)
    m = m[start.le(m["created_at"]) & end.ge(m["created_at"].dt.normalize())]
    counts = m.groupby("_row").size().reindex(tt["_row"], fill_value=0)
    if (counts != 1).any():
        bad = tt.loc[counts.values != 1, "ticket_id"].head().tolist()
        raise ValueError(f"tickets with 0 or >1 roster rows for their agent_id: {bad}")
    m = m.set_index("_row").drop(columns=["from_date", "to_date"]).sort_index()
    m.index = t.index
    return m


def flag_resolver_team_mismatch(t: pd.DataFrame) -> pd.DataFrame:
    """resolved_by_other_team: resolving agent's team != first-assigned team.
    transfers_inconsistent: helpdesk row resolved by another team but transfers == 0."""
    t = t.copy()
    t["resolved_by_other_team"] = t["resolver_team"].ne(t["assigned_team"])
    t["transfers_inconsistent"] = (
        t["source_system"].eq("helpdesk") & t["resolved_by_other_team"] & t["transfers"].eq(0)
    ).fillna(False).astype(bool)
    return t


# ---------------------------------------------------------------- status / csat / refunds

def flag_stale_legacy_open(t: pd.DataFrame) -> pd.DataFrame:
    """Legacy (pre-migration) tickets still open/pending: the old tool is retired, so these
    were never closed out. Kept as volume (they were real contacts), flagged."""
    t = t.copy()
    t["stale_legacy_open"] = t["source_system"].eq("legacy_fd") & t["status"].isin(["open", "pending"])
    return t


def flag_csat_without_resolution(t: pd.DataFrame) -> pd.DataFrame:
    """Survey is sent on resolution (policy s8). A score on an open/pending ticket is suspect."""
    t = t.copy()
    t["csat_on_unresolved"] = t["csat_score"].notna() & t["status"].isin(["open", "pending"])
    return t


def flag_goodwill_over_cap(t: pd.DataFrame, cap: int = GOODWILL_CAP_INR) -> pd.DataFrame:
    t = t.copy()
    t["goodwill_over_cap"] = (
        t["refund_reason_code"].eq("GW-OTHER") & t["refund_amount_inr"].gt(cap)
    ).fillna(False).astype(bool)
    return t


def flag_refund_and_replacement_per_order(t: pd.DataFrame) -> pd.DataFrame:
    """Policy s5: never both a refund and a replacement on the same order. Checked per
    ORDER across all its tickets (only tickets with a confident order link)."""
    t = t.copy()
    linked = t["order_id"].notna()
    if "order_match" in t:
        linked &= t["order_match"].isin(["explicit", "message", "fallback_unique"])
    x = t[linked].assign(
        _ref=t["refund_amount_inr"].notna(),
        _rep=t["replacement_issued"].fillna(False).astype(bool),
    )
    g = x.groupby("order_id")[["_ref", "_rep"]].any()
    both = set(g.index[g["_ref"] & g["_rep"]])
    t["order_refund_and_replacement"] = linked & t["order_id"].isin(both)
    return t


def legacy_refund_scale(t: pd.DataFrame, products: pd.DataFrame) -> pd.Series:
    """Median refund / retail price by source_system. Used to test the policy s9 warning
    that legacy stored money in a 'native unit'. Similar medians => no conversion needed."""
    x = t[t["refund_amount_inr"].notna()].merge(
        products[["sku", "retail_price_inr"]], left_on="product_sku", right_on="sku")
    return (x["refund_amount_inr"] / x["retail_price_inr"]).groupby(x["source_system"]).median()


# ---------------------------------------------------------------- pipeline

def clean_tickets(raw: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run every step in order. Returns (tickets with fixes + flags, duplicate pairs)."""
    t = raw["tickets"]
    t = shift_legacy_resolved_to_ist(t)
    t = flag_out_of_range(t)
    t = flag_zero_minute_first_response(t)
    t = add_first_response_breach(t)
    pairs = find_duplicate_candidates(t)
    t = flag_duplicates(t, pairs)
    t = recover_order_id_from_message(t, raw["orders"])
    t = join_orders(t, raw["orders"])
    t = flag_ticket_before_order(t)
    t = join_agents(t, raw["agents"])
    t = flag_resolver_team_mismatch(t)
    t = flag_stale_legacy_open(t)
    t = flag_csat_without_resolution(t)
    t = flag_goodwill_over_cap(t)
    t = flag_refund_and_replacement_per_order(t)
    return t, pairs


def analysis_view(t: pd.DataFrame) -> pd.DataFrame:
    """Rows used for analysis: inside the stated date range and not a duplicate copy.
    Everything else is a flag the analysis can choose to use."""
    return t[t["in_scope"] & ~t["is_duplicate"]]


if __name__ == "__main__":
    from src.audit import main
    main()
