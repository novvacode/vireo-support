"""Tests for src/routing.py and src/workload.py with tiny hand-made fixtures."""
import pandas as pd

from src import routing, workload as wl

TS = pd.Timestamp


def frame(rows):
    base = {"ticket_id": None, "assigned_team": "Billing", "resolver_team": "Billing",
            "agent_notes": "", "customer_message": "", "channel": "chat", "status": "resolved",
            "customer_id": "C1", "product_sku": "S1", "category": "Billing & Payments",
            "created_at": TS("2025-03-01 10:00"), "first_response_at": TS("2025-03-01 10:10"),
            "resolved_at": TS("2025-03-01 12:00"), "transfers": pd.NA, "fr_breach": False,
            "source_system": "helpdesk"}
    df = pd.DataFrame([{**base, "ticket_id": f"T{i}", **r} for i, r in enumerate(rows)])
    df["transfers"] = df["transfers"].astype("Int64")
    df["fr_breach"] = df["fr_breach"].astype("boolean")
    for c in ["created_at", "first_response_at", "resolved_at"]:
        df[c] = pd.to_datetime(df[c])
    return df


# ---------------------------------------------------------------- routing

def test_note_signals_word_boundaries_and_exclusions():
    s = routing.note_signals(pd.Series([
        "Checked AWB with courier. Re-shipped from warehouse.",          # delivery
        "checked pkp awb -> pickup done, refund initiated",              # reverse pickup, not delivery
        "Already shipped, advised RTO. Issue: cancel order.",           # cancellation, not delivery
        "Confirmed UTRs. Duplicate refunded to source.",                 # payment
        "upgraded the firmware",                                         # 'pg' inside a word: not payment
    ]))
    assert s["note_delivery"].tolist() == [True, False, False, False, False]
    assert s["note_payment"].tolist() == [False, False, True, True, False]


def test_label_work_type_cases():
    t = frame([
        {"agent_notes": "Bot tagged as billing, actually shipment issue. Moved to Logistics.",
         "resolver_team": "Logistics"},                                                   # delivery high
        {"agent_notes": "order not delivered | checked awb with courier -> re-shipped"},  # delivery medium
        {"agent_notes": "Cx reported double charge. Confirmed UTRs. Transferred to Logistics.",
         "resolver_team": "Logistics"},                                                   # billing medium
        {"agent_notes": "Asked for UTR. Refund processed to source."},                   # billing high
        {"agent_notes": "cx ok"},                                                         # unclear
    ])
    out = routing.label_work_type(t)
    assert list(zip(out["work_type"], out["confidence"])) == [
        ("delivery", "high"), ("delivery", "medium"), ("billing", "medium"),
        ("billing", "high"), ("unclear", "low")]


def test_true_owner_moves_only_billing_delivery_at_chosen_confidence():
    t = pd.DataFrame({
        "assigned_team": ["Billing", "Billing", "Billing", "Chat Frontline"],
        "work_type": ["delivery", "delivery", "billing", "delivery"],
        "confidence": ["high", "medium", "high", "high"],
    })
    assert routing.true_owner(t).tolist() == ["Logistics", "Logistics", "Billing", "Chat Frontline"]
    assert routing.true_owner(t, ("high",)).tolist() == ["Logistics", "Billing", "Billing", "Chat Frontline"]


def test_message_delivery_language():
    m = routing.message_delivery_language(pd.Series([
        "paid but package not delivered even after 12 days",
        "refund not received yet",            # refund, not a parcel
        "Rs debited on 26 Jan, still empty handed",
        "need GST invoice",
    ]))
    assert m.tolist() == [True, False, True, False]


# ---------------------------------------------------------------- workload

def test_handle_hours_only_for_resolved_or_closed():
    t = frame([{}, {"status": "open", "resolved_at": pd.NaT}])
    h = wl.handle_hours(t)
    assert round(h.iloc[0], 3) == round(110 / 60, 3) and pd.isna(h.iloc[1])


def test_repeat_contacts_window_and_open_previous():
    t = frame([
        {"created_at": TS("2025-03-01 10:00"), "resolved_at": TS("2025-03-02 10:00")},
        {"created_at": TS("2025-03-20 10:00"), "resolved_at": TS("2025-03-21 10:00")},   # 18d after: repeat
        {"created_at": TS("2025-06-01 10:00"), "resolved_at": pd.NaT, "status": "open"},  # >30d: not
        {"created_at": TS("2025-09-01 10:00"), "resolved_at": TS("2025-09-01 12:00")},   # prev open, 92d after its creation: not
        {"customer_id": "C2", "created_at": TS("2025-03-05 10:00")},                     # other customer
    ])
    out = wl.flag_repeat_contacts(t)
    assert out["is_repeat"].tolist() == [False, True, False, False, False]
    assert out["caused_repeat"].tolist() == [True, False, False, False, False]
    assert out.loc[1, "prev_ticket_id"] == "T0"


def test_costs_never_fill_unknown_transfers_as_known():
    t = frame([
        {"channel": "voice", "transfers": 2, "fr_breach": True},
        {"channel": "chat", "transfers": pd.NA, "source_system": "legacy_fd"},
    ])
    out = wl.add_costs(t)
    assert out.loc[0, "total_cost"] == 520 + 2 * 305 + 350
    assert pd.isna(out.loc[1, "transfer_cost"]) and out.loc[1, "total_cost"] == 210


def test_created_shift_boundaries():
    t = frame([{"created_at": TS(f"2025-03-01 {h:02d}:30")} for h in (5, 6, 13, 14, 21, 22)])
    assert wl.created_shift(t).tolist() == ["Night", "Morning", "Morning", "Day", "Day", "Night"]
