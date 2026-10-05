"""Draw ~200 customer messages stratified by channel x source_system x bot category, for taxonomy design.
Run: python scripts/sample_messages.py  -> labels/taxonomy_sample200.csv
"""
import pandas as pd

from src import clean
from src.load import load_all

t, _ = clean.clean_tickets(load_all())
v = clean.analysis_view(t)
cells = v.groupby(["channel", "source_system", "category"])
# proportional allocation, at least 1 per non-empty cell, ~200 total
n = (cells.size() / len(v) * 200).round().clip(lower=1).astype(int)
parts = [g.sample(min(n[k], len(g)), random_state=2026) for k, g in cells]
s = pd.concat(parts)[["ticket_id", "channel", "source_system", "category", "customer_message"]]
s.to_csv("labels/taxonomy_sample200.csv", index=False)
print(len(s), "messages from", len(n), "cells")
