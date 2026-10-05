"""Tests for the business-case helpers and the 'one monetisation method' arithmetic."""
from pathlib import Path

import pandas as pd
import pytest

from src import business_case as bc

ROOT = Path(__file__).resolve().parent.parent


def test_inr_uses_indian_grouping():
    assert bc.inr(146347) == "Rs 1,46,347"
    assert bc.inr(900000) == "Rs 9,00,000"
    assert bc.inr(305) == "Rs 305"
    assert bc.inr(-12345678) == "-Rs 1,23,45,678"


def test_prange_collapses_equal_ends():
    assert bc.prange([0.9632, 0.9583]) == "96%"
    assert bc.prange([0.69, 0.79]) == "69%-79%"


def test_mean_ci_ignores_blanks():
    m, lo, hi = bc.mean_ci(pd.Series([1, 1, 0, 2, None], dtype="Float64"))
    assert m == pytest.approx(1.0) and lo < m < hi


def test_policy_figures_are_the_documented_ones():
    assert (bc.TRANSFER_INR, bc.BREACH_INR, bc.AGENT_HOUR_INR, bc.TWO_HIRES_INR_YEAR) == (305, 350, 165, 900_000)
    assert bc.CONTACT_INR == {"chat": 210, "email": 260, "voice": 520, "social": 240}


def test_rendered_doc_and_csv_are_consistent():
    """The committed doc must be the script's output: no template braces, headline equals the CSV value."""
    doc = (ROOT / "docs" / "business_case.md").read_text(encoding="utf-8")
    csv = pd.read_csv(ROOT / "outputs" / "business_case.csv").set_index("key")["value"]
    assert "{" not in doc and "}" not in doc
    q = float(csv["headline_saving_per_quarter"])
    assert bc.inr(q) in doc
    # one method only: the headline must not include the breach-credit alternative
    alt = float(csv["alt_method_breach_credit_saving_per_quarter"])
    assert bc.inr(q + alt) not in doc
    # arithmetic identity: net transfers x Rs 305 = saving
    assert float(csv["base_net"]) * 305 == pytest.approx(q)
