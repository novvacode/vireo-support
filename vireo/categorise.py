"""Categorise support tickets by what the customer actually needs, and say which team should own each.

    python -m vireo.categorise --tickets <tickets.csv> --out outputs/

Cheap-first: (1) keyword rules on the customer's message, (2) TF-IDF model for messages the rules
are unsure about, (3) optional LLM for whatever is still low-confidence (VIREO_LLM=1).
agent_notes is never read: it is written after the work and would leak the answer.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from vireo import llm as llm_mod
from vireo import rules, tfidf
from vireo.charts import monthly_charts
from vireo.taxonomy import BOT_COMPATIBLE, NAME, owner_team

INPUT_COLS = ["ticket_id", "created_at", "channel", "category", "assigned_team", "customer_message"]
TFIDF_MIN_PROB = 0.55
LLM_BELOW = 0.6


def read_tickets(path: Path) -> pd.DataFrame:
    """Read only the columns the categoriser is allowed to see (agent_notes is excluded on purpose)."""
    head = pd.read_csv(path, nrows=0).columns
    missing = {"ticket_id", "customer_message"} - set(head)
    if missing:
        raise SystemExit(f"{path}: missing required column(s) {sorted(missing)}")
    cols = [c for c in INPUT_COLS if c in head]
    df = pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False, na_values=[""])
    for c in INPUT_COLS:
        if c not in df:
            df[c] = pd.NA
    df["customer_message"] = df["customer_message"].fillna("")
    df["channel"] = df["channel"].fillna("chat")
    return df


def disagreement(bot_cat, new_cat: str, rule_reason: str) -> tuple[bool, str]:
    if pd.isna(bot_cat) or new_cat == "unclear":
        return False, ""
    if bot_cat == "Other":
        return True, f"bot used catch-all 'Other'; customer needs: {NAME[new_cat]}"
    if bot_cat not in BOT_COMPATIBLE:
        return False, ""
    if new_cat in BOT_COMPATIBLE[bot_cat]:
        return False, ""
    return True, f"bot tagged '{bot_cat}' but customer needs: {NAME[new_cat]} ({rule_reason})"


def categorise(df: pd.DataFrame, out_dir: Path | None = None, use_llm: bool | None = None) -> tuple[pd.DataFrame, dict]:
    msgs = df["customer_message"]
    rr = [rules.classify(m) for m in msgs]
    out = pd.DataFrame({
        "ticket_id": df["ticket_id"],
        "rule_category": [r.category for r in rr],
        "rule_confidence": [r.confidence for r in rr],
        "rule_reason": [r.reason for r in rr],
        "multi_issue": [r.multi_issue for r in rr],
    }, index=df.index)
    out["new_category"] = out["rule_category"]
    out["confidence"] = out["rule_confidence"]
    out["method"] = "rules"
    out.loc[out["rule_category"].eq("unclear"), "method"] = "none"

    # stage 2: TF-IDF where rules are unsure
    norm = msgs.map(rules.normalise)
    unsure = out["rule_confidence"] < LLM_BELOW
    lab, prob = tfidf.fit_predict(norm, out["rule_category"], out["rule_confidence"], unsure)
    take = prob[prob >= TFIDF_MIN_PROB].index
    better = [i for i in take if prob[i] * 0.85 > out.at[i, "confidence"]]
    out.loc[better, "new_category"] = lab[better]
    out.loc[better, "confidence"] = (prob[better] * 0.85).round(3)
    out.loc[better, "method"] = "tfidf"

    # stage 3: optional LLM for what is still low-confidence
    cost = {"llm": "off (offline default)"}
    if (llm_mod.enabled() if use_llm is None else use_llm):
        clf = llm_mod.LLMClassifier(out_dir or Path("outputs"))
        for i in out.index[out["confidence"] < LLM_BELOW]:
            cat, conf = clf.classify(msgs[i])
            if cat != "unclear":
                out.loc[i, ["new_category", "confidence", "method"]] = [cat, round(conf * 0.9, 3), "llm"]
        cost = clf.close()

    out["new_category_name"] = out["new_category"].map(NAME)
    out["owner_team"] = [owner_team(c, ch) for c, ch in zip(out["new_category"], df["channel"])]
    out["bot_category"] = df["category"]
    out["bot_team"] = df["assigned_team"]
    dis = [disagreement(b, n, r) for b, n, r in zip(df["category"], out["new_category"], out["rule_reason"])]
    out["bot_disagrees"] = [d[0] for d in dis]
    out["disagreement_reason"] = [d[1] for d in dis]
    out["owner_differs_from_bot_team"] = out["owner_team"].ne(df["assigned_team"]) & df["assigned_team"].notna()
    out["created_at"] = df["created_at"]
    out["channel"] = df["channel"]
    cols = ["ticket_id", "new_category", "new_category_name", "confidence", "method", "owner_team",
            "bot_category", "bot_team", "bot_disagrees", "disagreement_reason", "owner_differs_from_bot_team",
            "multi_issue", "rule_reason", "channel", "created_at"]
    return out[cols], cost


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickets", required=True, type=Path, help="tickets CSV (needs ticket_id, customer_message)")
    ap.add_argument("--out", default=Path("outputs"), type=Path, help="output folder")
    ap.add_argument("--from", dest="date_from", default="2025-01-01", help="chart start date (inclusive)")
    ap.add_argument("--to", dest="date_to", default="2026-06-30", help="chart end date (inclusive)")
    a = ap.parse_args(argv)
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    df = read_tickets(a.tickets)
    res, cost = categorise(df, a.out)
    res.to_csv(a.out / "categorised_tickets.csv", index=False)
    charted = monthly_charts(res, a.out, a.date_from, a.date_to)

    lines = [
        f"input: {a.tickets} ({len(df):,} tickets)",
        f"method: {res['method'].value_counts().to_dict()}",
        f"unclear: {int(res['new_category'].eq('unclear').sum()):,}",
        f"bot tag disagrees with customer need: {int(res['bot_disagrees'].sum()):,} "
        f"({res['bot_disagrees'].mean():.1%})",
        f"owner team differs from bot-assigned team: {int(res['owner_differs_from_bot_team'].sum()):,}",
        f"charted {charted:,} tickets created {a.date_from}..{a.date_to}",
        f"LLM / paid API: {cost}",
        f"runtime: {time.time() - t0:.1f}s",
        "new_category counts: " + str(res["new_category_name"].value_counts().to_dict()),
    ]
    (a.out / "categorise_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
