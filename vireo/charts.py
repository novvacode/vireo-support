"""Client chart: monthly volume by new category and by true owning team (PNG + CSV)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE, INK, INK2, GRID, S1, S2 = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#eb6834"


def _small_multiples(m: pd.DataFrame, title: str, path: Path, highlight=()):
    n = len(m.columns)
    ncol = 4
    nrow = -(-n // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.1 * ncol, 2.0 * nrow), sharex=True, sharey=True, squeeze=False)
    x = m.index.to_timestamp()
    for ax, c in zip(axes.flat, m.columns):
        ax.plot(x, m[c], color=S2 if c in highlight else S1, linewidth=2)
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=7)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_title(f"{c}  (total {int(m[c].sum()):,})", fontsize=8.5, color=INK, loc="left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=INK)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def monthly_charts(res: pd.DataFrame, out: Path, date_from: str, date_to: str) -> int:
    ts = pd.to_datetime(res["created_at"], errors="coerce")
    keep = ts.between(pd.Timestamp(date_from), pd.Timestamp(date_to) + pd.Timedelta(days=1), inclusive="left")
    r = res[keep].assign(month=ts[keep].dt.to_period("M"))
    if r.empty:
        return 0
    for col, stem, title, hl in [
        ("new_category_name", "monthly_by_new_category", "Tickets per month by what the customer needed", ("Order not arrived",)),
        ("owner_team", "monthly_by_owner_team", "Tickets per month by the team that should own them", ("Billing", "Logistics")),
    ]:
        m = r.pivot_table(index="month", columns=col, values="ticket_id", aggfunc="count", fill_value=0)
        m = m[m.sum().sort_values(ascending=False).index]
        m.to_csv(out / f"{stem}.csv")
        _small_multiples(m, f"{title}, {date_from} to {date_to}", out / f"{stem}.png", hl)
    return len(r)
