"""Unit tests for src/clean.py and src/load.py using tiny hand-made fixtures."""
from pathlib import Path

import pandas as pd
import pytest

from src import clean
from src.load import load_tickets

TS = pd.Timestamp


def tickets(rows):
    """Build a ticket frame with sensible defaults; each row is a dict of overrides."""
    base = {
        "ticket_id": None, "created_at": TS("2025-03-01 10:00"),
        "first_response_at": TS("2025-03-01 10:05"), "resolved_at": TS("2025-03-01 12:00"),
        "status": "resolved", "channel": "chat", "customer_id": "C1", "order_id": None,
        "product_sku": "SKU1", "category": "Other", "assigned_team": "Chat Frontline",
        "agent_id": "A1", "transfers": pd.NA, "csat_score": pd.NA, "refund_amount_inr": pd.NA,
        "refund_reason_code": None, "replacement_issued": False,
        "customer_message": "hello", "agent_notes": "", "source_system": "helpdesk",
    }
    df = pd.DataFrame([{**base, "ticket_id": f"TK-{i}", **r} for i, r in enumerate(rows)])
    df["transfers"] = df["transfers"].astype("Int64")
    df["csat_score"] = df["csat_score"].astype("Int64")
    df["refund_amount_inr"] = df["refund_amount_inr"].astype("Float64")
    df["replacement_issued"] = df["replacement_issued"].astype("boolean")
    for c in ["created_at", "first_response_at", "resolved_at"]:
        df[c] = pd.to_datetime(df[c])
    return df


ORDERS = pd.DataFrame({
    "order_id": ["VR000001", "VR000002", "VR000003", "VR000004"],
    "customer_id": ["C1", "C2", "C2", "C3"],
    "sku": ["SKU1", "SKU1", "SKU1", "SKU1"],
    "order_date": pd.to_datetime(["2025-02-01", "2025-01-01", "2025-02-01", "2025-06-01"]),
    "order_value_inr": pd.array([1000, 1000, 1000, 1000], dtype="Float64"),
    "qty": pd.array([1, 1, 1, 1], dtype="Int64"),
    "lot_code": ["L1", "L2", "L3", "L4"],
})


# ---------------------------------------------------------------- load

def test_load_keeps_blanks_and_na_text(tmp_path: Path):
    csv = (
        "ticket_id,created_at,first_response_at,resolved_at,transfers,csat_score,"
        "refund_amount_inr,replacement_issued,customer_message\n"
        'TK-1,2025-01-01 10:00,2025-01-01 10:05,,,,,N,"line one\nline two"\n'
        "TK-2,2025-01-01 11:00,2025-01-01 11:05,2025-01-01 12:00,0,4,250,Y,NA\n"
    )
    (tmp_path / "abc-tickets.csv").write_text(csv, encoding="utf-8")
    t = load_tickets(tmp_path)
    assert len(t) == 2                                   # embedded newline is one row
    assert pd.isna(t.loc[0, "transfers"]) and t.loc[1, "transfers"] == 0  # blank != 0
    assert pd.isna(t.loc[0, "csat_score"])
    assert pd.isna(t.loc[0, "resolved_at"])
    assert t.loc[1, "customer_message"] == "NA"         # literal text, not missing
    assert t["replacement_issued"].tolist() == [False, True]


# ---------------------------------------------------------------- timestamps / scope

def test_shift_legacy_resolved_only_touches_legacy():
    t = tickets([
        {"source_system": "legacy_fd", "resolved_at": TS("2025-03-01 06:00")},
        {"source_system": "legacy_fd", "resolved_at": pd.NaT, "status": "open"},
        {"source_system": "helpdesk", "resolved_at": TS("2025-03-01 12:00")},
    ])
    out = clean.shift_legacy_resolved_to_ist(t)
    assert out.loc[0, "resolved_at"] == TS("2025-03-01 11:30")
    assert pd.isna(out.loc[1, "resolved_at"])
    assert out.loc[2, "resolved_at"] == TS("2025-03-01 12:00")
    assert out.loc[0, "resolved_at_raw"] == TS("2025-03-01 06:00")
    assert t.loc[0, "resolved_at"] == TS("2025-03-01 06:00")  # input not mutated


def test_flag_out_of_range_boundaries():
    t = tickets([
        {"created_at": TS("2024-12-31 23:59")},
        {"created_at": TS("2025-01-01 00:00")},
        {"created_at": TS("2026-06-30 23:59")},
        {"created_at": TS("2026-07-01 00:00")},
    ])
    assert clean.flag_out_of_range(t)["in_scope"].tolist() == [False, True, True, False]


def test_first_response_breach_uses_channel_targets():
    c = TS("2025-03-01 10:00")
    t = tickets([
        {"channel": "chat", "created_at": c, "first_response_at": c + pd.Timedelta(minutes=15)},
        {"channel": "chat", "created_at": c, "first_response_at": c + pd.Timedelta(minutes=16)},
        {"channel": "email", "created_at": c, "first_response_at": c + pd.Timedelta(hours=8)},
        {"channel": "voice", "created_at": c, "first_response_at": c + pd.Timedelta(hours=3)},
    ])
    assert clean.add_first_response_breach(t)["fr_breach"].tolist() == [False, True, False, True]


def test_zero_minute_first_response():
    c = TS("2025-03-01 10:00")
    t = tickets([{"created_at": c, "first_response_at": c}, {}])
    assert clean.flag_zero_minute_first_response(t)["fr_zero_minutes"].tolist() == [True, False]


# ---------------------------------------------------------------- duplicates

def test_duplicates_found_across_systems_and_helpdesk_copy_kept():
    t = tickets([
        {"source_system": "legacy_fd", "created_at": TS("2025-08-01 10:00"),
         "customer_message": "Payment done, order status not moved. VR123456"},
        {"source_system": "helpdesk", "created_at": TS("2025-08-01 15:30"),   # 5h30m later
         "customer_message": "payment done order status not moved VR123456"},
        {"source_system": "helpdesk", "created_at": TS("2025-08-01 10:10"),   # same time,
         "customer_message": "speaker crackles at high volume"},             # different issue
        {"customer_id": "C9", "created_at": TS("2025-08-01 10:00"),           # other customer
         "customer_message": "Payment done, order status not moved. VR123456"},
    ])
    pairs = clean.find_duplicate_candidates(t)
    assert len(pairs) == 1
    assert set(pairs.loc[0, ["ticket_id_a", "ticket_id_b"]]) == {"TK-0", "TK-1"}
    out = clean.flag_duplicates(t, pairs)
    assert out["is_duplicate"].tolist() == [True, False, False, False]  # legacy copy dropped
    assert out.loc[0, "duplicate_of"] == "TK-1"


def test_duplicates_ignore_same_text_far_apart():
    t = tickets([
        {"created_at": TS("2025-03-01 10:00"), "customer_message": "my order has not been delivered yet"},
        {"created_at": TS("2025-06-01 10:00"), "customer_message": "my order has not been delivered yet"},
    ])
    assert clean.find_duplicate_candidates(t).empty


def test_flag_duplicates_no_pairs():
    t = tickets([{}, {}])
    out = clean.flag_duplicates(t, clean.find_duplicate_candidates(t.iloc[:0]))
    assert not out["is_duplicate"].any()


# ---------------------------------------------------------------- orders

def test_recover_order_id_only_when_customer_and_sku_match():
    t = tickets([
        {"customer_id": "C1", "customer_message": "where is vr000001 ??"},   # valid
        {"customer_id": "C1", "customer_message": "order VR000004 late"},   # belongs to C3
        {"customer_id": "C1", "customer_message": "VR999999 missing"},      # not in orders
        {"customer_id": "C1", "order_id": "VR000001", "customer_message": "VR000004"},  # already set
    ])
    out = clean.recover_order_id_from_message(t, ORDERS)
    assert out["order_id"].fillna("-").tolist() == ["VR000001", "-", "-", "VR000001"]
    assert out["order_id_source"].fillna("-").tolist() == ["message", "-", "-", "explicit"]


def test_join_orders_fallback_unique_ambiguous_unmatched():
    t = tickets([
        {"customer_id": "C1", "order_id": "VR000001"},   # explicit
        {"customer_id": "C1"},                           # one candidate
        {"customer_id": "C2"},                           # two candidates -> ambiguous
        {"customer_id": "C4"},                           # none
    ])
    t["order_id_source"] = pd.array(["explicit", pd.NA, pd.NA, pd.NA], dtype="string")
    out = clean.join_orders(t, ORDERS)
    assert out["order_match"].tolist() == ["explicit", "fallback_unique", "fallback_ambiguous", "unmatched"]
    assert out.loc[1, "order_id"] == "VR000001"
    assert pd.isna(out.loc[2, "order_id"])              # ambiguous: no guess
    assert out.loc[2, "n_order_candidates"] == 2
    assert out.loc[0, "lot_code"] == "L1" and pd.isna(out.loc[2, "lot_code"])
    assert len(out) == len(t)


def test_ticket_before_order_presale_vs_implausible():
    t = tickets([
        {"created_at": TS("2025-03-01 10:00")},
        {"created_at": TS("2025-03-01 10:00")},
        {"created_at": TS("2025-03-01 10:00")},
        {"created_at": TS("2025-03-01 10:00")},
    ])
    t["order_date"] = pd.to_datetime(["2025-02-01", "2025-03-01", "2025-03-10", "2025-06-01"])
    out = clean.flag_ticket_before_order(t)
    assert out["order_after_ticket"].fillna("-").tolist() == ["-", "-", "presale", "implausible"]


# ---------------------------------------------------------------- agents

AGENTS = pd.DataFrame({
    "agent_id": ["A1", "A2", "A3", "A3"],
    "name": ["Om Sharma", "Om Sharma", "Riya", "Riya"],
    "site": ["Indore", "Bengaluru", "Indore", "Bengaluru"],
    "team": ["Chat Frontline", "Logistics", "Billing", "Logistics"],
    "shift": ["Day"] * 4,
    "tier": pd.array([1, 1, 1, 1], dtype="Int64"),
    "from_date": pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-01", "2025-06-01"]),
    "to_date": pd.to_datetime([None, None, "2025-05-31", None]),
})


def test_join_agents_by_id_not_name_and_by_date():
    t = tickets([
        {"agent_id": "A1"},
        {"agent_id": "A2"},
        {"agent_id": "A3", "created_at": TS("2025-03-01 10:00")},
        {"agent_id": "A3", "created_at": TS("2025-07-01 10:00")},
    ])
    out = clean.join_agents(t, AGENTS)
    assert out["resolver_team"].tolist() == ["Chat Frontline", "Logistics", "Billing", "Logistics"]
    assert len(out) == 4


def test_join_agents_raises_on_unknown_agent():
    with pytest.raises(ValueError):
        clean.join_agents(tickets([{"agent_id": "A99"}]), AGENTS)


def test_resolver_team_mismatch_and_transfer_inconsistency():
    t = tickets([
        {"assigned_team": "Billing", "transfers": 0, "source_system": "helpdesk"},
        {"assigned_team": "Billing", "transfers": 1, "source_system": "helpdesk"},
        {"assigned_team": "Billing", "transfers": pd.NA, "source_system": "legacy_fd"},
        {"assigned_team": "Logistics", "transfers": 0, "source_system": "helpdesk"},
    ])
    t["resolver_team"] = "Logistics"
    out = clean.flag_resolver_team_mismatch(t)
    assert out["resolved_by_other_team"].tolist() == [True, True, True, False]
    assert out["transfers_inconsistent"].tolist() == [True, False, False, False]  # legacy unknown


# ---------------------------------------------------------------- status / csat / refunds

def test_stale_legacy_open_and_csat_on_unresolved():
    t = tickets([
        {"source_system": "legacy_fd", "status": "open", "csat_score": 4},
        {"source_system": "helpdesk", "status": "pending"},
        {"source_system": "legacy_fd", "status": "resolved", "csat_score": 2},
    ])
    assert clean.flag_stale_legacy_open(t)["stale_legacy_open"].tolist() == [True, False, False]
    assert clean.flag_csat_without_resolution(t)["csat_on_unresolved"].tolist() == [True, False, False]


def test_goodwill_over_cap():
    t = tickets([
        {"refund_reason_code": "GW-OTHER", "refund_amount_inr": 500},
        {"refund_reason_code": "GW-OTHER", "refund_amount_inr": 501},
        {"refund_reason_code": "CANCEL", "refund_amount_inr": 2000},
        {},
    ])
    assert clean.flag_goodwill_over_cap(t)["goodwill_over_cap"].tolist() == [False, True, False, False]


def test_refund_and_replacement_checked_per_order_not_per_ticket():
    t = tickets([
        {"order_id": "VR1", "refund_amount_inr": 999},           # refund on one ticket...
        {"order_id": "VR1", "replacement_issued": True},         # ...replacement on another
        {"order_id": "VR2", "refund_amount_inr": 999},
        {"order_id": None, "replacement_issued": True},
    ])
    t["order_match"] = ["explicit", "explicit", "explicit", "fallback_ambiguous"]
    out = clean.flag_refund_and_replacement_per_order(t)
    assert out["order_refund_and_replacement"].tolist() == [True, True, False, False]


def test_legacy_refund_scale():
    t = tickets([
        {"source_system": "legacy_fd", "refund_amount_inr": 900},
        {"source_system": "helpdesk", "refund_amount_inr": 900},
    ])
    p = pd.DataFrame({"sku": ["SKU1"], "retail_price_inr": [1000]})
    assert clean.legacy_refund_scale(t, p).round(2).to_dict() == {"helpdesk": 0.9, "legacy_fd": 0.9}


def test_analysis_view_drops_out_of_scope_and_duplicates():
    t = tickets([{}, {}, {}])
    t["in_scope"] = [True, False, True]
    t["is_duplicate"] = [False, False, True]
    assert clean.analysis_view(t)["ticket_id"].tolist() == ["TK-0"]
