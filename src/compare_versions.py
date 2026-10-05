"""Score frozen rules v1 and current rules v2 on the same gold sample (fair only on gold v2,
which neither version saw).   python -m src.compare_versions --tag v2
validation_archive/rules_v1.py is a byte-for-byte copy of vireo/rules.py at commit 52f8a5e (frozen v1)."""
from __future__ import annotations

import argparse

import pandas as pd

from src.gold_sample import frozen_predictions
from src.stage2 import wilson
from src.validate import LAB, OUT
from vireo.taxonomy import owner_team


def score(tag: str, version: str) -> dict:
    v, pred = frozen_predictions(version)
    g = pd.read_csv(LAB / f"gold_{tag}_labels.csv").merge(pred, on="ticket_id")
    g["gold_owner"] = [owner_team(c, ch) for c, ch in zip(g["gold_label"], g["channel"])]
    out = {}
    for name, ok in [("category accuracy", g["new_category"].eq(g["gold_label"])),
                     ("owner-team accuracy", g["owner_team"].eq(g["gold_owner"])),
                     ("abstained (Unclear)", g["new_category"].eq("unclear"))]:
        k, n = int(ok.sum()), len(ok)
        lo, hi = wilson(k, n)
        out[name] = (k, n, k / n, lo, hi)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v2")
    tag = ap.parse_args().tag
    rows = []
    for ver, key in [("rules v1 (frozen 52f8a5e)", "v1"), ("rules v2 (frozen f7d0830)", "v2")]:
        for metric, (k, n, val, lo, hi) in score(tag, key).items():
            rows.append({"gold": tag, "version": ver, "metric": metric, "k": k, "n": n, "value": val,
                         "ci95_low": lo, "ci95_high": hi})
    r = pd.DataFrame(rows)
    r.round(4).to_csv(OUT / f"validation_version_comparison_{tag}.csv", index=False)
    print(r.round(3).to_string(index=False))
