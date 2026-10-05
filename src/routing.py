"""Signals for deciding what kind of work a ticket really was (rule-based, no ML).

Three independent signals, used to label Billing-tagged tickets as delivery / billing / unclear:
  1. agent_notes  - what the agent wrote at closure (best evidence: written after the work)
  2. resolver_team - which team's agent closed it (from agent_id -> roster)
  3. customer_message - the customer's own words (what the intake bot saw)

The label comes from notes + resolver. The message signal is kept separate so we can measure
how often the customer's words agree with what the work turned out to be.
"""
from __future__ import annotations

import pandas as pd

# Agent explicitly says the ticket was in the wrong queue / was delivery, not billing.
NOTE_MISROUTE = (
    r"misrout|not a billing is+ue|bot tagged|actually (?:a )?(?:shipment|deliver|dlvry)"
    r"|this is a (?:dlvry|delivery)|parcel stuck|shipment issue"
)
# Agent says they handed the ticket to Logistics (weaker: the work itself may still be payment).
NOTE_XFER_LOGISTICS = r"(?:xfer|xefr|transferr?(?:ed|ing)?|moved|via|sending)(?: to)? logistics"
# Agent describes forward-delivery work. Reverse-pickup and cancellation wording are excluded on
# purpose: those are Returns Desk / Billing work that use the same courier vocabulary.
NOTE_DELIVERY = (
    r"\bawb\b|courier|\bcrr\b|re-?shipped|reship|\brto\b|lost in transit|shipment not"
    r"|not deliver|dlvry|delivery delayed|delivery for"
)
NOTE_PICKUP = r"\bpkp\b|pickup|pick-up|reverse"
NOTE_CANCEL = r"cancel"
# Agent describes payment / invoice / refund-to-source work.
NOTE_PAYMENT = (
    r"\butrs?\b|payment gateway|\bpg\b|charged twice|double|duplicate|invoice|\bgst|coupon|promo"
    r"|disc?o+u?n+t|debited|deducted|failed ord|txn|\barn\b|cancel|price"
)
# Customer's message talks about a parcel that has not arrived.
MSG_DELIVERY = (
    r"not (?:been )?deliver|delievre|not received (?:my|the) (?:order|parcel|package)|haven'?t received my order"
    r"|tracking|courier|out for delivery|shipped|dispatch|doorstep|dooorstep|at my door|front door"
    r"|nothing (?:in hand|at my door)|in hand|empty handed|show up|not with me|box never came"
    r"|where is my (?:order|parcel|stuff)|parcel|package|still (?:says )?processing|status (?:has )?not moved"
)


def _has(s: pd.Series, pattern: str) -> pd.Series:
    return s.fillna("").str.lower().str.contains(pattern, regex=True)


def note_signals(notes: pd.Series) -> pd.DataFrame:
    pickup = _has(notes, NOTE_PICKUP)
    return pd.DataFrame({
        "note_misroute": _has(notes, NOTE_MISROUTE),
        "note_xfer_logistics": _has(notes, NOTE_XFER_LOGISTICS),
        "note_delivery": _has(notes, NOTE_DELIVERY) & ~pickup & ~_has(notes, NOTE_CANCEL),
        "note_payment": _has(notes, NOTE_PAYMENT),
    }, index=notes.index)


def message_delivery_language(msgs: pd.Series) -> pd.Series:
    return _has(msgs, MSG_DELIVERY).rename("msg_delivery")


def label_work_type(t: pd.DataFrame) -> pd.DataFrame:
    """Add work_type (delivery | billing | unclear) and confidence (high | medium | low).

    delivery        : notes say misrouted, OR notes describe forward-delivery work, OR notes say
                      "transferred to Logistics" with no payment wording
      high          : ... and the notes name the misroute / hand-off, or a Logistics agent resolved it
      medium        : delivery work done by a non-Logistics agent (a Billing agent chased the courier)
    billing         : notes describe payment work and none of the above
      high          : resolved by Billing;  medium: resolved elsewhere
    unclear/low     : notes too thin to tell ("sorted", "see prev", refund-status only)
    """
    t = t.copy()
    t = t.join(note_signals(t["agent_notes"]))
    t["msg_delivery"] = message_delivery_language(t["customer_message"])
    by_log = t["resolver_team"].eq("Logistics")
    dlv = t["note_misroute"] | t["note_delivery"] | (t["note_xfer_logistics"] & ~t["note_payment"])
    pay = t["note_payment"] & ~dlv

    t["work_type"] = "unclear"
    t["confidence"] = "low"
    t.loc[dlv, "work_type"] = "delivery"
    t.loc[dlv, "confidence"] = "medium"
    t.loc[dlv & (t["note_misroute"] | t["note_xfer_logistics"] | by_log), "confidence"] = "high"
    t.loc[pay, "work_type"] = "billing"
    t.loc[pay, "confidence"] = "medium"
    t.loc[pay & t["resolver_team"].eq("Billing"), "confidence"] = "high"
    return t


def true_owner(t: pd.DataFrame, move_confidence=("high", "medium")) -> pd.Series:
    """Team that owns the work per policy s6: Billing-tagged tickets whose work was delivery
    (at the given confidence levels) belong to Logistics; everything else keeps assigned_team."""
    move = t["assigned_team"].eq("Billing") & t["work_type"].eq("delivery") \
        & t["confidence"].isin(move_confidence)
    return t["assigned_team"].where(~move, "Logistics").rename("true_owner")
