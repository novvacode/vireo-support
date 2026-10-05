"""Draw the frozen validation ('gold') sample.   python -m src.gold_sample [--seed 4040] [--tag v1]

Pool: the cleaned analysis view, minus every ticket in the dev sample used to design/tune the rules
(labels/taxonomy_sample200.csv, which also contains the 60-row sample/ file) and minus any earlier gold sample.
Strata are filled in order; a ticket belongs to the first stratum that draws it.
  random        simple random sample of the pool  -> unbiased population estimate
  bot_disagree  frozen tool says the bot tag is wrong
  hinglish      Hinglish markers in the message
  short         <= 6 words
  voice         voice channel (IVR transcripts)
  multi_issue   frozen tool saw strong evidence for 2+ categories
  low_conf      frozen tool confidence < 0.8 or not decided by rules
  paid_but      payment words AND delivery words (the core Billing/Logistics ambiguity)
Writes outputs/gold_<tag>_blind.csv (ticket_id, channel, message only, shuffled - this is what gets labelled)
and outputs/gold_<tag>_strata.csv (ticket_id, stratum).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src import clean
from src.load import load_all
from vireo.categorise import categorise

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
STRATA = [("random", 80), ("bot_disagree", 25), ("hinglish", 15), ("short", 15), ("voice", 15),
          ("multi_issue", 15), ("low_conf", 15), ("paid_but", 10)]
STRATA_SMALL = [("random", 60), ("bot_disagree", 15), ("hinglish", 8), ("short", 8), ("voice", 8),
                ("multi_issue", 8), ("low_conf", 8), ("paid_but", 5)]  # experiment 2: 120 tickets
HINGLISH = r"\b(?:bhai|ji|kuch|pareshan|paisa|jaldi|abhi tak|karo|nahi|hai|hu|se)\b"
PAID = r"paid|payment|debited|deducted|money|transaction|rs ?\d"
DELIVERY = r"deliver|received|in hand|tracking|courier|show up|doorstep|where is my|processing|not moved"


# Each experiment is tied to the rules version that was frozen when it ran.
RULES_FOR_TAG = {"v1": "v1", "v2": "v2"}


def rules_module(version: str):
    if version == "v1":
        from validation_archive import rules_v1  # byte copy of vireo/rules.py at commit 52f8a5e
        return rules_v1
    from vireo import rules
    return rules


def frozen_predictions(rules_version: str = "v2") -> tuple[pd.DataFrame, pd.DataFrame]:
    import vireo.categorise as cat
    t, _ = clean.clean_tickets(load_all())
    v = clean.analysis_view(t).reset_index(drop=True)
    df = v[["ticket_id", "created_at", "channel", "category", "assigned_team", "customer_message"]].copy()
    df["created_at"] = df["created_at"].astype(str)
    current = cat.rules
    cat.rules = rules_module(rules_version)
    try:
        pred, _ = categorise(df, use_llm=False)
    finally:
        cat.rules = current
    return v, pred


def draw(seed: int, tag: str, exclude: set[str], strata_spec=STRATA) -> pd.DataFrame:
    v, pred = frozen_predictions(RULES_FOR_TAG.get(tag, "v2"))
    p = v[["ticket_id", "channel", "customer_message"]].merge(
        pred[["ticket_id", "bot_disagrees", "multi_issue", "confidence", "method"]], on="ticket_id")
    p = p[~p["ticket_id"].isin(exclude)]
    m = p["customer_message"].str.lower()
    masks = {
        "random": pd.Series(True, index=p.index),
        "bot_disagree": p["bot_disagrees"],
        "hinglish": m.str.contains(HINGLISH),
        "short": m.str.split().str.len() <= 6,
        "voice": p["channel"].eq("voice"),
        "multi_issue": p["multi_issue"],
        "low_conf": (p["confidence"] < 0.8) | p["method"].ne("rules"),
        "paid_but": m.str.contains(PAID) & m.str.contains(DELIVERY),
    }
    taken, rows = set(), []
    for name, n in strata_spec:
        cand = p[masks[name] & ~p["ticket_id"].isin(taken)]
        s = cand.sample(min(n, len(cand)), random_state=seed)
        taken |= set(s["ticket_id"])
        rows.append(pd.DataFrame({"ticket_id": s["ticket_id"], "stratum": name,
                                  "stratum_pool_size": int(masks[name].sum())}))
    strata = pd.concat(rows, ignore_index=True)
    blind = p.set_index("ticket_id").loc[strata["ticket_id"], ["channel", "customer_message"]].reset_index()
    blind = blind.sample(frac=1, random_state=seed + 1).reset_index(drop=True)  # shuffle: hide stratum order
    OUT.mkdir(exist_ok=True)
    blind.to_csv(OUT / f"gold_{tag}_blind.csv", index=False)
    strata.to_csv(OUT / f"gold_{tag}_strata.csv", index=False)
    print(f"gold {tag}: {len(strata)} tickets; pool {len(p):,}; strata {strata['stratum'].value_counts().to_dict()}")
    return strata


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4040)
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--exclude", nargs="*", default=[], help="CSVs with a ticket_id column to exclude (earlier gold, viewed lists)")
    ap.add_argument("--small", action="store_true", help="use the 120-ticket strata of experiment 2")
    a = ap.parse_args()
    excl = set(pd.read_csv(ROOT / "labels" / "taxonomy_sample200.csv")["ticket_id"])
    for f in a.exclude:
        excl |= set(pd.read_csv(f)["ticket_id"])
    draw(a.seed, a.tag, excl, STRATA_SMALL if a.small else STRATA)
