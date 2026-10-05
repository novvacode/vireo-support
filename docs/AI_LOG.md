# AI log

## Stage 1: load, audit, clean
- Asked: read the brief/policy/emails; build typed loader, small named cleaning functions, pytest fixtures, and a data audit table; no classifier, no business interpretation.
- Changed/rejected: CLAUDE.md "category ~one-to-one with team" corrected (7 categories map to Frontline by channel); policy's re-import warning tested 4 ways and found 0 duplicates; tests caught a bug where an unknown agent_id silently passed the roster join (fixed).
- Discarded: TF-IDF duplicate search (needed sklearn, found only stock phrases; replaced by a dependency-free normalised-text check); dropping rows for anomalies (kept as flags instead).

## Stage 2: volume, workload, capacity, mis-routing
- Asked: her monthly chart (category, assigned team), the same by resolving team, workload (handle time, transfers, repeats, channel cost, breaches, CSAT), capacity by team and shift, mis-routing quantified with confidence, findings sorted by which decision they support.
- Changed/rejected: first repeat-contact rule counted every contact after a never-resolved ticket as a repeat (fixed: open tickets' window runs from creation); the message regex counted "refund not received" as delivery (fixed); "transferred to Logistics" alone was treated as delivery even when notes described a double charge (now needs no payment wording); a patch script wrote `\b` as backspace bytes into the regexes, silently breaking word boundaries (caught via byte count, file rewritten).
- Discarded: a hand-label check that the rule passes 60/60 is not claimed as real accuracy (same author for rule and labels); night-shift understaffing as the breach explanation (data shows no night clustering); 11-series line charts (replaced by small multiples).
