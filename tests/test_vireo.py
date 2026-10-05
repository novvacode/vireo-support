"""Tests for the vireo categoriser (rules, no-leak input, flags, optional LLM with a fake client, CLI)."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from vireo import categorise as cat_mod
from vireo import llm, rules
from vireo.taxonomy import owner_team

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample" / "sample_tickets.csv"


@pytest.mark.parametrize("msg,expected", [
    ("paid but package not delivered even after 8 days", "order_not_arrived"),
    ("Rs debited on 28/08, still empty handed", "order_not_arrived"),                 # paid-but-not-here
    ("hello payment was deducted but no order was created pls reply", "payment_issue"),  # no order exists
    ("two entrise of Rs 4999 on my statement for one pair of earbuds", "payment_issue"),  # 'pair' is not pairing
    ("Orbit Mini purchased recently. card charged two times.", "payment_issue"),      # 'charged' is not charging
    ("change of mind, please stop the shipment. I already tried cancel button", "cancel_or_change"),
    ("Update my shipping address. I tried editing in app.", "cancel_or_change"),
    ("bhai left side has no audio at all bahut pareshan hu ??", "sound_or_hardware"),
    ("goes from full to empty during one commute", "battery_charging"),               # 'commute' is not 'mute'
    ("you picked up the item 8 days ago and my money hasn't come back", "refund_not_received"),
    ("nobody came for the pickup. i rescheduled pickup twice", "return_pickup"),
    ("HELLO JI WHAT IS THE STATSU OF MY WARANTY CLAIM", "warranty_status"),
    ("[IVR transcript] helo firmware update is stuck at 67%", "app_firmware_login"),
    ("my dad has an old Nokia, will the watch app run", "product_question"),
    ("box was crushed and the strata 3 is cracked", "damaged_or_wrong_item"),
    ("need the bill with my firm's GSTIN on it", "invoice_or_price"),
    ("hello??", "unclear"),
])
def test_rules_core_cases(msg, expected):
    assert rules.classify(msg).category == expected


def test_closing_demands_do_not_drive_category():
    # 'I want my money back' on a coupon complaint must not become a refund
    r = rules.classify("Coupon code not working. I tried in caps. I want my money back.")
    assert r.category == "invoice_or_price"
    assert "money back" not in rules.normalise("Coupon not working. I want my money back")


def test_template_issue_line_is_used():
    t = rules.normalise("Product: Pulse 2 Order: VR1 Issue: nobody came for the pickup Tried: called courier Expected: refund")
    assert t.startswith("nobody came for the pickup") and "refund" not in t


def test_agent_notes_never_read(tmp_path):
    df = pd.read_csv(SAMPLE, dtype=str)
    poisoned = df.assign(agent_notes="misrouted - dlvry. xfer to logistics. warranty claim. invoice.")
    p = tmp_path / "poisoned.csv"
    poisoned.to_csv(p, index=False)
    read = cat_mod.read_tickets(p)
    assert "agent_notes" not in read.columns
    a, _ = cat_mod.categorise(cat_mod.read_tickets(SAMPLE), use_llm=False)
    b, _ = cat_mod.categorise(read, use_llm=False)
    assert a["new_category"].tolist() == b["new_category"].tolist()


def test_disagreement_flag_and_owner():
    assert cat_mod.disagreement("Billing & Payments", "order_not_arrived", "x")[0] is True
    assert cat_mod.disagreement("Billing & Payments", "payment_issue", "x")[0] is False
    assert cat_mod.disagreement("Other", "cancel_or_change", "x")[0] is True
    assert cat_mod.disagreement("Other", "unclear", "x")[0] is False
    assert owner_team("order_not_arrived", "chat") == "Logistics"
    assert owner_team("pairing_connection", "email") == "Email Frontline"
    assert owner_team("cancel_or_change", "social") == "Chat Frontline"


class FakeClient:
    def __init__(self):
        self.n = 0
        self.messages = self

    def create(self, **kw):
        self.n += 1
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            content=[SimpleNamespace(type="text", text='{"category": "battery_charging", "confidence": 0.9}')])


def test_llm_cache_and_cost_log(tmp_path):
    fake = FakeClient()
    c = llm.LLMClassifier(tmp_path, model="claude-opus-5-5", client=fake)
    assert c.classify("dies by lunch") == ("battery_charging", 0.9)
    assert c.classify("dies by lunch") == ("battery_charging", 0.9)  # cached
    row = c.close()
    assert fake.n == 1 and row["cache_hits"] == 1
    assert row["cost_usd"] == pytest.approx(1000 / 1e6 * 4 + 100 / 1e6 * 20)
    assert (tmp_path / "llm_cost_log.csv").exists()
    # a second classifier re-uses the on-disk cache: zero API calls
    c2 = llm.LLMClassifier(tmp_path, model="claude-opus-5-5", client=FakeClient())
    c2.classify("dies by lunch")
    assert c2.calls == 0
    assert json.loads((tmp_path / "llm_cache.json").read_text())


def test_cli_runs_on_sample_quickly(tmp_path):
    t0 = time.time()
    assert cat_mod.main(["--tickets", str(SAMPLE), "--out", str(tmp_path)]) == 0
    assert time.time() - t0 < 120
    out = pd.read_csv(tmp_path / "categorised_tickets.csv")
    assert len(out) == 60
    assert {"ticket_id", "new_category", "confidence", "owner_team", "bot_disagrees", "disagreement_reason"} <= set(out.columns)
    for f in ["monthly_by_new_category.png", "monthly_by_new_category.csv",
              "monthly_by_owner_team.png", "monthly_by_owner_team.csv", "categorise_summary.txt"]:
        assert (tmp_path / f).exists(), f


@pytest.mark.parametrize("msg,expected", [
    # rules v2 (post-test changes, validated only on fresh gold v2)
    ("wrong product delivered. i checked the invoice. what do i do now?", "damaged_or_wrong_item"),
    ("[IVR transcript] got a different colour than ordered - what do i do now?", "damaged_or_wrong_item"),
    ("Ordered black, got white, not what I asked for.", "damaged_or_wrong_item"),
    ("ordered the wrong colour, don't ship it", "cancel_or_change"),        # customer's own mistake: still cancel/change
    ("the promised 30 hours is nowhere close, i get maybe 2", "battery_charging"),
    ("hello ji the reutrn was accepted but the amount is nowhere in my account", "refund_not_received"),
    ("need GST invoice for my order. I already tried different browser.", "invoice_or_price"),  # invoice still works
])
def test_rules_v2_cases(msg, expected):
    assert rules.classify(msg).category == expected
