"""Load the raw Vireo data pack into typed DataFrames.

Rules:
- Real CSV parser (messages contain embedded line breaks).
- Only an empty cell is missing. pandas' default NA strings ("NA", "null", "N/A", ...)
  are NOT treated as missing, because they can legitimately appear in free text.
- Blanks stay NaN/NA. transfers and csat_score are nullable integers and are never
  filled with 0 (blank transfers = field did not exist; blank csat = no response).
- Raw files carry a UUID prefix (e.g. "99ca...-tickets.csv"), so files are found by suffix.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TICKET_TS = ["created_at", "first_response_at", "resolved_at"]


def find_file(name: str, data_dir: Path = DATA_DIR) -> Path:
    """Return the single file in data_dir whose name is `name` or ends with `-name`."""
    hits = [p for p in data_dir.iterdir() if p.name == name or p.name.endswith("-" + name)]
    if len(hits) != 1:
        raise FileNotFoundError(f"expected exactly one '{name}' in {data_dir}, found {len(hits)}")
    return hits[0]


def _read(name: str, data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(
        find_file(name, data_dir),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        encoding="utf-8",
    )


def _yn_to_bool(s: pd.Series) -> pd.Series:
    out = s.map({"Y": True, "N": False})
    unknown = s.notna() & out.isna()
    if unknown.any():
        raise ValueError(f"unexpected Y/N values: {sorted(s[unknown].unique())}")
    return out.astype("boolean")


def _to_ts(s: pd.Series, fmt: str) -> pd.Series:
    out = pd.to_datetime(s, format=fmt, errors="coerce")
    bad = s.notna() & out.isna()
    if bad.any():
        raise ValueError(f"unparseable timestamps in {s.name}: {s[bad].head().tolist()}")
    return out


def load_tickets(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    t = _read("tickets.csv", data_dir)
    for c in TICKET_TS:
        t[c] = _to_ts(t[c], "%Y-%m-%d %H:%M")
    t["transfers"] = pd.to_numeric(t["transfers"]).astype("Int64")
    t["csat_score"] = pd.to_numeric(t["csat_score"]).astype("Int64")
    t["refund_amount_inr"] = pd.to_numeric(t["refund_amount_inr"]).astype("Float64")
    t["replacement_issued"] = _yn_to_bool(t["replacement_issued"])
    return t


def load_orders(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    o = _read("orders.csv", data_dir)
    o["order_date"] = _to_ts(o["order_date"], "%Y-%m-%d")
    o["qty"] = pd.to_numeric(o["qty"]).astype("Int64")
    o["order_value_inr"] = pd.to_numeric(o["order_value_inr"]).astype("Float64")
    return o


def load_customers(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    c = _read("customers.csv", data_dir)
    c["signup_date"] = _to_ts(c["signup_date"], "%Y-%m-%d")
    c["care_plus"] = _yn_to_bool(c["care_plus"])
    return c


def load_products(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    p = _read("products.csv", data_dir)
    p["launch_date"] = _to_ts(p["launch_date"], "%Y-%m-%d")
    for c in ["unit_cost_inr", "retail_price_inr", "warranty_months"]:
        p[c] = pd.to_numeric(p[c]).astype("Int64")
    return p


def load_agents(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    a = _read("agents.csv", data_dir)
    a["from_date"] = _to_ts(a["from_date"], "%Y-%m-%d")
    a["to_date"] = _to_ts(a["to_date"], "%Y-%m-%d")  # blank = current assignment
    a["tier"] = pd.to_numeric(a["tier"]).astype("Int64")
    return a


def load_all(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    return {
        "tickets": load_tickets(data_dir),
        "orders": load_orders(data_dir),
        "customers": load_customers(data_dir),
        "products": load_products(data_dir),
        "agents": load_agents(data_dir),
    }


if __name__ == "__main__":
    for name, df in load_all().items():
        print(f"{name:10s} {df.shape[0]:>6,} rows x {df.shape[1]} cols")
