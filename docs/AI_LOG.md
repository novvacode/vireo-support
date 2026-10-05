# AI log

## Stage 1: load, audit, clean
- Asked: read the brief/policy/emails; build typed loader, small named cleaning functions, pytest fixtures, and a data audit table; no classifier, no business interpretation.
- Changed/rejected: CLAUDE.md "category ~one-to-one with team" corrected (7 categories map to Frontline by channel); policy's re-import warning tested 4 ways and found 0 duplicates; tests caught a bug where an unknown agent_id silently passed the roster join (fixed).
- Discarded: TF-IDF duplicate search (needed sklearn, found only stock phrases; replaced by a dependency-free normalised-text check); dropping rows for anomalies (kept as flags instead).
