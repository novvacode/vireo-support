# Vireo Audio: support ticket categoriser and analysis

Categorises support tickets by **what the customer actually needs** (13 categories + Unclear), names the team that
should own each one, flags where the intake bot's tag disagrees, and draws the monthly chart by new category and by
owning team.

## Run it (clean machine, Python 3.10/3.11, no API key, no network)

```bash
pip install -r requirements.txt
```

```bash
python -m vireo.categorise --tickets data/99ca137e-844d-47d7-8ce8-bf60ce272ba3-tickets.csv --out outputs/
```

That one command writes to `outputs/`:

| File | What |
|---|---|
| `categorised_tickets.csv` | per ticket: `ticket_id, new_category, confidence, method, owner_team, bot_category, bot_disagrees, disagreement_reason, multi_issue, …` |
| `monthly_by_new_category.csv/.png` | the client chart by new category (Jan 2025 – Jun 2026; change with `--from/--to`) |
| `monthly_by_owner_team.csv/.png` | the same by the team that should own the work |
| `categorise_summary.txt` | counts, method mix, LLM cost line ("off" by default) |

**Quick check (under 2 minutes):**

```bash
python -m vireo.categorise --tickets sample/sample_tickets.csv --out outputs/sample/
```

```bash
python -m pytest -q
```

## How it works (cheap first)

1. **Rules** ([vireo/rules.py](vireo/rules.py)): normalise the text (IVR prefix, typos, Hinglish fillers, the
   "Issue:" line of templated emails), **strip closing demands** like "I want my money back" (they appear on every
   kind of complaint), then score typo-tolerant phrases per category, with explicit precedence for known overlaps
   (e.g. "paid but not delivered" goes to *Order not arrived*, "paid but no order created" to *Payment*).
2. **TF-IDF** ([vireo/tfidf.py](vireo/tfidf.py)): character n-gram logistic regression trained on the messages the
   rules labelled confidently, applied only where the rules were unsure.
3. **LLM (optional, off by default)** ([vireo/llm.py](vireo/llm.py)): for anything still below 0.6 confidence.

Only `customer_message` (plus channel/date for the owner and chart) is read. **`agent_notes` is never read** by
the categoriser; a test feeds poisoned notes and checks that the output doesn't change.

### Optional LLM mode

```bash
pip install -r requirements-llm.txt
```

Set `VIREO_LLM=1` and `ANTHROPIC_API_KEY` (or log in with `ant auth login`), then run the same command.
- Model: `claude-opus-5-5` at low effort. Override with `VIREO_LLM_MODEL`.
- Answers are cached in `outputs/llm_cache.json`, so a re-run costs nothing.
- Each run appends tokens, USD and INR to `outputs/llm_cost_log.csv`. USD→INR uses `VIREO_USD_INR`, default 88, which is an assumption.
- **Paid API use in this project so far: none.** Every result in `docs/` comes from the offline default.

## Analysis scripts (reproduce every number in docs/)

```bash
python -m src.audit
```

```bash
python -m src.stage2
```

```bash
python -m src.validate
```

```bash
python -m src.business_case
```

`docs/data_audit.md`, `docs/findings_stage2.md`, `docs/validation.md`, `docs/business_case.md` (rendered by the script) and `docs/decisions.md` explain the results.
