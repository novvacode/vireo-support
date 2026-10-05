# AI log

## Stage 1: load, audit, clean
- Asked: read the brief/policy/emails; build typed loader, small named cleaning functions, pytest fixtures, and a data audit table; no classifier, no business interpretation.
- Changed/rejected: CLAUDE.md "category ~one-to-one with team" corrected (7 categories map to Frontline by channel); policy's re-import warning tested 4 ways and found 0 duplicates; tests caught a bug where an unknown agent_id silently passed the roster join (fixed).
- Discarded: TF-IDF duplicate search (needed sklearn, found only stock phrases; replaced by a dependency-free normalised-text check); dropping rows for anomalies (kept as flags instead).

## Stage 2: volume, workload, capacity, mis-routing
- Asked: her monthly chart (category, assigned team), the same by resolving team, workload (handle time, transfers, repeats, channel cost, breaches, CSAT), capacity by team and shift, mis-routing quantified with confidence, findings sorted by which decision they support.
- Changed/rejected: first repeat-contact rule counted every contact after a never-resolved ticket as a repeat (fixed: open tickets' window runs from creation); the message regex counted "refund not received" as delivery (fixed); "transferred to Logistics" alone was treated as delivery even when notes described a double charge (now needs no payment wording); a patch script wrote `\b` as backspace bytes into the regexes, silently breaking word boundaries (caught via byte count, file rewritten).
- Discarded: a hand-label check that the rule passes 60/60 is not claimed as real accuracy (same author for rule and labels); night-shift understaffing as the breach explanation (data shows no night clustering); 11-series line charts (replaced by small multiples).

## Stage 3: categoriser build (frozen before validation)
- Asked: a 13-category taxonomy from about 200 real messages (approved), then a cheap-first CLI (rules → TF-IDF → optional LLM) that never reads agent_notes, with owner team, bot-disagreement flag, chart, a sample file and a test.
- Changed/rejected: rules tuned ONLY on the 208-message dev sample (labels/taxonomy_sample200.csv). Fixes from dev: 'pair of earbuds' fired the pairing rule, 'card charged' fired battery, 'commute' contained 'mute', 'tried cancel button' fired the hardware rule, and Tried-steps ('I updated the app') fired the app rule, so app/update words were demoted to supporting evidence.
- Discarded: shipping a pre-trained model file (TF-IDF is trained at run time on the rule-confident rows instead); raw-HTTP LLM calls (switched to the official SDK, imported only in LLM mode).
