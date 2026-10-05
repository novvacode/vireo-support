"""Optional stage 3: ask Claude about the low-confidence messages only.

Off by default. Turned on with VIREO_LLM=1 (needs the `anthropic` package and credentials, see README).
Every answer is cached on disk by a hash of (model, prompt version, message), so re-runs cost nothing,
and every run appends tokens and cost to outputs/llm_cost_log.csv.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from vireo.taxonomy import CATEGORIES, LABELS

PROMPT_VERSION = "v1"
DEFAULT_MODEL = "claude-opus-5-5"
# USD per million tokens (input, output) - Anthropic list prices, cached 2026-09-25.
PRICE_USD_PER_MTOK = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0)}
USD_INR = float(os.environ.get("VIREO_USD_INR", "88.0"))  # assumption, override via env

SYSTEM = (
    "You categorise customer-support messages for Vireo Audio (earbuds, headphones, speakers, smartwatches; India). "
    "Messages may contain typos, Hinglish and IVR transcripts. Ignore closing demands such as 'I want my money back' - "
    "classify what went wrong, not the remedy asked for. Reply with JSON only: "
    '{"category": "<key>", "confidence": <0..1>}. Categories:\n'
    + "\n".join(f"- {k}: {v[0]} - {v[2]}" for k, v in CATEGORIES.items())
)


def enabled() -> bool:
    return os.environ.get("VIREO_LLM", "") == "1"


class LLMClassifier:
    def __init__(self, out_dir: Path, model: str | None = None, client=None):
        self.model = model or os.environ.get("VIREO_LLM_MODEL", DEFAULT_MODEL)
        self.cache_path = out_dir / "llm_cache.json"
        self.cache = json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path.exists() else {}
        self.log_path = out_dir / "llm_cost_log.csv"
        self.calls = self.hits = self.in_tok = self.out_tok = 0
        if client is None:
            import anthropic  # optional dependency, only needed in LLM mode
            client = anthropic.Anthropic()
        self.client = client

    def _key(self, msg: str) -> str:
        return hashlib.sha256(f"{self.model}|{PROMPT_VERSION}|{msg}".encode()).hexdigest()

    def classify(self, msg: str) -> tuple[str, float]:
        k = self._key(msg)
        if k in self.cache:
            self.hits += 1
            return tuple(self.cache[k])
        resp = self.client.messages.create(
            model=self.model, max_tokens=2000, system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": msg[:4000]}],
        )
        self.calls += 1
        self.in_tok += resp.usage.input_tokens
        self.out_tok += resp.usage.output_tokens
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            d = json.loads(text[text.index("{"): text.rindex("}") + 1])
            cat, conf = d.get("category"), float(d.get("confidence", 0.5))
        except (ValueError, json.JSONDecodeError):
            cat, conf = "unclear", 0.0
        if cat not in LABELS:
            cat, conf = "unclear", 0.0
        self.cache[k] = [cat, conf]
        return cat, conf

    def cost_usd(self) -> float:
        pin, pout = PRICE_USD_PER_MTOK.get(self.model, (float("nan"), float("nan")))
        return self.in_tok / 1e6 * pin + self.out_tok / 1e6 * pout

    def close(self) -> dict:
        self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")
        row = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "model": self.model,
               "api_calls": self.calls, "cache_hits": self.hits, "input_tokens": self.in_tok,
               "output_tokens": self.out_tok, "cost_usd": round(self.cost_usd(), 4),
               "cost_inr": round(self.cost_usd() * USD_INR, 2), "usd_inr": USD_INR}
        new = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)
        return row
