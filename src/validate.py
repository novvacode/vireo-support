"""Stage 4: validate the frozen categoriser against AI-adjudicated gold labels.

    python -m src.validate            # experiment 1 (gold v1)
    python -m src.validate --tag v2   # a later experiment on a fresh sample, if one exists

Gold labels were written by reading each message blind (no bot tag, prediction, notes or stratum shown) and
committed BEFORE this script was first run. They are AI-adjudicated, not independent human ground truth.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import routing  # noqa: E402
from src.gold_sample import HINGLISH, RULES_FOR_TAG, frozen_predictions  # noqa: E402
from src.stage2 import wilson  # noqa: E402
from src.workload import TRANSFER_COST_INR  # noqa: E402
from vireo.taxonomy import BOT_COMPATIBLE, LABELS, NAME, owner_team  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
LAB = ROOT / "labels"
SURFACE, INK, INK2, GRID, S1, S2 = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#eb6834"
SEQ = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DELIVERY = {"order_not_arrived", "damaged_or_wrong_item"}
BILLING = {"payment_issue", "invoice_or_price"}
FRONTLINE_TEAMS = {"Chat Frontline", "Email Frontline", "Voice Frontline"}


def team_family(t: str) -> str:
    return "Frontline" if t in FRONTLINE_TEAMS else t


def error_type(gold: str, pred: str) -> str:
    if gold == pred:
        return ""
    if pred == "unclear":
        return "abstained (Unclear)"
    if gold in DELIVERY and pred in BILLING:
        return "delivery labelled as Billing"
    if gold in BILLING and pred in DELIVERY:
        return "Billing labelled as delivery"
    if {gold, pred} <= {"payment_issue", "refund_not_received", "invoice_or_price"}:
        return "payment/refund confusion"
    if "cancel_or_change" in (gold, pred):
        return "cancel/change confusion"
    if {gold, pred} <= {"pairing_connection", "sound_or_hardware", "battery_charging", "app_firmware_login"}:
        return "device-fault confusion (same Frontline owner)"
    return f"other: {gold} -> {pred}"


def build_table(tag: str) -> pd.DataFrame:
    gold = pd.read_csv(LAB / f"gold_{tag}_labels.csv")
    strata = pd.read_csv(LAB / f"gold_{tag}_strata.csv")
    v, pred = frozen_predictions(RULES_FOR_TAG.get(tag, "v2"))
    v = routing.label_work_type(v)  # agent notes -> work type: WEAK PROXY, used only for the independent check
    meta = v.set_index("ticket_id")[["channel", "customer_message", "category", "assigned_team", "resolver_team",
                                     "agent_notes", "work_type", "confidence", "source_system"]]
    meta = meta.rename(columns={"category": "bot_category", "assigned_team": "bot_team", "confidence": "notes_confidence"})
    p = pred.set_index("ticket_id")[["new_category", "confidence", "method", "owner_team", "multi_issue", "rule_reason"]]
    p = p.rename(columns={"new_category": "tool_pred", "confidence": "tool_confidence", "method": "tool_method",
                          "owner_team": "tool_owner", "multi_issue": "tool_multi_issue"})
    d = gold.merge(strata[["ticket_id", "stratum"]], on="ticket_id").set_index("ticket_id").join(meta).join(p)
    d["gold_owner"] = [owner_team(g, c) for g, c in zip(d["gold_label"], d["channel"])]
    d["tool_correct"] = d["tool_pred"].eq(d["gold_label"])
    d["bot_compatible"] = [g in BOT_COMPATIBLE.get(b, set()) for g, b in zip(d["gold_label"], d["bot_category"])]
    d["tool_owner_correct"] = d["tool_owner"].eq(d["gold_owner"])
    d["bot_owner_correct"] = d["bot_team"].eq(d["gold_owner"])
    d["error_type"] = [error_type(g, t) for g, t in zip(d["gold_label"], d["tool_pred"])]
    d["costly_error"] = ~d["tool_owner_correct"]
    m = d["customer_message"].str.lower()
    d["hinglish"] = m.str.contains(HINGLISH)
    d["short"] = m.str.split().str.len() <= 6
    d["voice"] = d["channel"].eq("voice")
    return d.reset_index()


def rate_row(exp, subset, system, metric, s: pd.Series) -> dict:
    k, n = int(s.sum()), int(s.count())
    lo, hi = wilson(k, n) if n else (np.nan, np.nan)
    return {"experiment": exp, "subset": subset, "system": system, "metric": metric, "correct": k, "n": n,
            "value": k / n if n else np.nan, "ci95_low": lo, "ci95_high": hi,
            "error_rate": 1 - k / n if n else np.nan}


def confusion_png(cm: pd.DataFrame, title: str, path: Path, xlabel: str, ylabel: str):
    fig, ax = plt.subplots(figsize=(1.0 + 0.55 * cm.shape[1], 1.0 + 0.42 * cm.shape[0]))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", SEQ)
    ax.imshow(cm.values, cmap=cmap, aspect="auto", vmin=0, vmax=max(1, cm.values.max()))
    for (i, j), val in np.ndenumerate(cm.values):
        if val:
            ax.text(j, i, int(val), ha="center", va="center", fontsize=7.5,
                    color="white" if val > cm.values.max() * 0.55 else INK)
    ax.set_xticks(range(cm.shape[1]), cm.columns, rotation=55, ha="right", fontsize=7.5, color=INK)
    ax.set_yticks(range(cm.shape[0]), cm.index, fontsize=7.5, color=INK)
    ax.set_xlabel(xlabel, fontsize=8, color=INK2)
    ax.set_ylabel(ylabel, fontsize=8, color=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(title, fontsize=9.5, color=INK, loc="left")
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def accuracy_png(res: pd.DataFrame, path: Path, exp: str):
    sel = res[(res["experiment"] == exp) & res["subset"].isin(["random (population estimate)", "all gold"])
              & res["metric"].isin(["category accuracy", "owner-team accuracy"])]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    rows = list(sel.itertuples())
    for y, r in enumerate(rows):
        col = S1 if r.system == "our tool" else S2
        ax.plot([r.ci95_low, r.ci95_high], [y, y], color=col, linewidth=2)
        ax.plot(r.value, y, "o", color=col, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(r.ci95_high + 0.01, y, f"{r.value:.0%}  ({r.correct}/{r.n})", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(range(len(rows)), [f"{r.system} - {r.metric} - {r.subset}" for r in rows], fontsize=7.5, color=INK)
    ax.set_xlim(0, 1.15)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_facecolor(SURFACE)
    ax.set_title(f"Accuracy vs AI-adjudicated labels, 95% Wilson intervals ({exp})", fontsize=9.5, color=INK, loc="left")
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(tag: str):
    exp = f"experiment {tag}"
    d = build_table(tag)
    d.drop(columns=["agent_notes"]).to_csv(OUT / ("gold_to_label.csv" if tag == "v1" else f"gold_to_label_{tag}.csv"), index=False)
    print(f"== {exp}: {len(d)} gold tickets; labels {d['gold_label'].value_counts().to_dict()}")

    subsets = {"all gold": d, "random (population estimate)": d[d["stratum"] == "random"],
               "hard-case strata only": d[d["stratum"] != "random"]}
    for s in ["bot_disagree", "hinglish", "short", "voice", "multi_issue", "low_conf", "paid_but"]:
        subsets[f"stratum: {s}"] = d[d["stratum"] == s]
    for f in ["hinglish", "short", "voice", "ambiguous"]:
        subsets[f"any ticket with {f}"] = d[d[f]]
    rows = []
    for name, x in subsets.items():
        rows += [rate_row(exp, name, "our tool", "category accuracy", x["tool_correct"]),
                 rate_row(exp, name, "our tool", "owner-team accuracy", x["tool_owner_correct"]),
                 rate_row(exp, name, "intake bot", "category-compatible (lenient)", x["bot_compatible"]),
                 rate_row(exp, name, "intake bot", "owner-team accuracy", x["bot_owner_correct"])]
    res = pd.DataFrame(rows)
    # weak proxy rows: resolving team / agent notes (NOT ground truth)
    fam = lambda s: s.map(team_family)
    weak = [rate_row(exp, "all gold", "our tool", "WEAK PROXY: owner family == resolver family",
                     fam(d["tool_owner"]).eq(fam(d["resolver_team"]))),
            rate_row(exp, "all gold", "intake bot", "WEAK PROXY: assigned family == resolver family",
                     fam(d["bot_team"]).eq(fam(d["resolver_team"]))),
            rate_row(exp, "all gold", "AI gold label", "WEAK PROXY: gold owner family == resolver family",
                     fam(d["gold_owner"]).eq(fam(d["resolver_team"])))]
    res = pd.concat([res, pd.DataFrame(weak)], ignore_index=True)

    # population-wide weak check on Billing-tagged tickets (agent notes say delivery?)
    v, pred = frozen_predictions(RULES_FOR_TAG.get(tag, "v2"))
    v = routing.label_work_type(v).merge(pred[["ticket_id", "new_category", "confidence"]], on="ticket_id")
    b = v[v["assigned_team"] == "Billing"]
    notes_dlv = b["work_type"].eq("delivery")
    tool_dlv = b["new_category"].isin(DELIVERY)
    xt = pd.crosstab(notes_dlv.map({True: "notes: delivery work", False: "notes: not delivery"}),
                     tool_dlv.map({True: "tool: delivery category", False: "tool: other"}))
    xt.to_csv(OUT / ("validation_weak_check_billing_notes.csv" if tag == "v1" else f"validation_weak_check_billing_notes_{tag}.csv"))
    res = pd.concat([res, pd.DataFrame([
        rate_row(exp, "all Billing-tagged tickets (population)", "our tool",
                 "WEAK PROXY: tool says delivery when notes say delivery (recall)", tool_dlv[notes_dlv]),
        rate_row(exp, "all Billing-tagged tickets (population)", "our tool",
                 "WEAK PROXY: notes say delivery when tool says delivery (precision)", notes_dlv[tool_dlv]),
        rate_row(exp, "all tickets (population)", "our tool", "WEAK PROXY: owner family == resolver family",
                 v.assign(o=[owner_team(c, ch) for c, ch in zip(v["new_category"], v["channel"])])
                  .pipe(lambda x: fam(x["o"]).eq(fam(x["resolver_team"])))),
        rate_row(exp, "all tickets (population)", "intake bot", "WEAK PROXY: assigned family == resolver family",
                 fam(v["assigned_team"]).eq(fam(v["resolver_team"]))),
    ])], ignore_index=True)
    res.round(4).to_csv(OUT / ("validation_results.csv" if tag == "v1" else f"validation_results_{tag}.csv"), index=False)

    show = res[res["subset"].isin(["all gold", "random (population estimate)", "hard-case strata only",
                                   "all Billing-tagged tickets (population)", "all tickets (population)"])]
    print(show[["subset", "system", "metric", "correct", "n", "value", "ci95_low", "ci95_high"]].round(3).to_string(index=False))
    print("\n  by stratum / hard-case flag (tool category acc | tool owner acc | bot owner acc):")
    for name in subsets:
        if name.startswith(("stratum", "any")):
            r = res[res["subset"] == name].set_index(["system", "metric"])["value"]
            n = int(res[res["subset"] == name]["n"].iloc[0])
            print(f"    {name:32s} n={n:3d}  {r[('our tool', 'category accuracy')]:.0%} | "
                  f"{r[('our tool', 'owner-team accuracy')]:.0%} | {r[('intake bot', 'owner-team accuracy')]:.0%}")
    print("\n  weak check, Billing-tagged population (agent notes vs tool):")
    print(xt.to_string())

    # per-category P/R/F1 (tool)
    pc = []
    for c in LABELS:
        tp = int(((d["tool_pred"] == c) & (d["gold_label"] == c)).sum())
        fp = int(((d["tool_pred"] == c) & (d["gold_label"] != c)).sum())
        fn = int(((d["tool_pred"] != c) & (d["gold_label"] == c)).sum())
        if tp + fp + fn == 0:
            continue
        pr = tp / (tp + fp) if tp + fp else np.nan
        rc = tp / (tp + fn) if tp + fn else np.nan
        f1 = 2 * pr * rc / (pr + rc) if pr and rc and not np.isnan(pr) and not np.isnan(rc) else np.nan
        pc.append({"category": c, "name": NAME[c], "gold_n": tp + fn, "predicted_n": tp + fp, "tp": tp, "fp": fp,
                   "fn": fn, "precision": pr, "recall": rc, "f1": f1,
                   "recall_ci95_low": wilson(tp, tp + fn)[0] if tp + fn else np.nan,
                   "recall_ci95_high": wilson(tp, tp + fn)[1] if tp + fn else np.nan})
    pc = pd.DataFrame(pc)
    pc.round(3).to_csv(OUT / ("validation_per_category.csv" if tag == "v1" else f"validation_per_category_{tag}.csv"), index=False)
    print("\n  per category (tool):")
    print(pc[["category", "gold_n", "predicted_n", "precision", "recall", "f1"]].round(2).to_string(index=False))

    # confusion matrices
    order = [c for c in LABELS if c in set(d["gold_label"]) | set(d["tool_pred"])]
    cm = pd.crosstab(d["gold_label"], d["tool_pred"]).reindex(index=order, columns=order, fill_value=0)
    sfx = "" if tag == "v1" else f"_{tag}"
    cm.to_csv(OUT / f"validation_confusion_tool{sfx}.csv")
    confusion_png(cm, "Our tool vs AI-adjudicated label (rows = label, columns = tool)",
                  OUT / f"validation_confusion_tool{sfx}.png", "tool prediction", "AI-adjudicated label")
    cmb = pd.crosstab(d["gold_label"], d["bot_category"]).reindex(index=order, fill_value=0)
    cmb.to_csv(OUT / f"validation_confusion_bot{sfx}.csv")
    confusion_png(cmb, "Intake bot tag vs AI-adjudicated label (rows = label, columns = bot tag)",
                  OUT / f"validation_confusion_bot{sfx}.png", "bot tag", "AI-adjudicated label")
    accuracy_png(res, OUT / f"validation_accuracy{sfx}.png", exp)

    # errors
    err = d[~d["tool_correct"]].copy()
    err["cost_note"] = np.where(err["costly_error"],
                                f"wrong owner team -> likely transfer (Rs {TRANSFER_COST_INR}) + breach risk",
                                "same owner team -> no routing cost")
    err = err[["ticket_id", "stratum", "channel", "gold_label", "tool_pred", "tool_confidence", "tool_method",
               "error_type", "gold_owner", "tool_owner", "costly_error", "cost_note", "bot_category", "resolver_team",
               "ambiguous", "label_note", "hinglish", "short", "customer_message", "rule_reason"]]
    err.to_csv(OUT / f"validation_errors{sfx}.csv", index=False)
    print(f"\n  tool errors: {len(err)}; by type {err['error_type'].value_counts().to_dict()}; costly (wrong owner) {int(err['costly_error'].sum())}")
    for _, e in err.iterrows():
        print(f"    {e.ticket_id} [{e.stratum}] gold={e.gold_label} tool={e.tool_pred} ({e.tool_method} {e.tool_confidence:.2f}) "
              f"{'COSTLY' if e.costly_error else 'cheap'} | {str(e.customer_message).replace(chr(10), ' ')[:110]}")
    bot_wrong_owner = d[~d["bot_owner_correct"]]
    print(f"\n  bot owner errors: {len(bot_wrong_owner)}; of which gold delivery tagged Billing: "
          f"{int((bot_wrong_owner['gold_label'].isin(DELIVERY) & bot_wrong_owner['bot_team'].eq('Billing')).sum())}; "
          f"tool fixes {int(bot_wrong_owner['tool_owner_correct'].sum())} of them")
    both = pd.crosstab(d["bot_owner_correct"].map({True: "bot owner right", False: "bot owner wrong"}),
                       d["tool_owner_correct"].map({True: "tool owner right", False: "tool owner wrong"}))
    both.to_csv(OUT / f"validation_bot_vs_tool_owner{sfx}.csv")
    print(both.to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v1")
    main(ap.parse_args().tag)
