"""The client memo may only quote numbers that the scripts generated, and must stay plain-language."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMO = (ROOT / "memo.md").read_text(encoding="utf-8")
SOURCES = "\n".join((ROOT / p).read_text(encoding="utf-8") for p in [
    "docs/business_case.md", "docs/validation.md", "docs/findings_stage2.md"])


def numbers(text: str) -> set[str]:
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)          # chart link
    text = re.sub(r"^#+ \d+\. ", "", text, flags=re.M)    # section numbers
    return set(re.findall(r"Rs [\d,]+|\d[\d,]*(?:\.\d+)?(?:%-\d+(?:\.\d+)?%|%|x)?", text))


def test_every_memo_number_comes_from_a_generated_document():
    missing = sorted(n for n in numbers(MEMO) if n not in SOURCES)
    assert not missing, f"numbers in memo.md not found in script outputs: {missing}"


def test_memo_is_about_one_page_and_plain():
    words = re.findall(r"[A-Za-z0-9][^\s]*", re.sub(r"!\[.*?\]\(.*?\)", "", MEMO))
    assert len(words) <= 520
    for jargon in ["F1", "TF-IDF", "tfidf", "embedding", "classifier", "precision", "recall", "regex", "model"]:
        assert jargon.lower() not in MEMO.lower(), jargon


def test_memo_structure_and_chart():
    for h in ["## 1. The answer", "## 2. The number and what it is worth", "## 3. The two hires",
              "## 4. What I am not sure about, and how I checked", "## 5. One next step"]:
        assert h in MEMO
    chart = re.search(r"!\[.*?\]\((.*?)\)", MEMO).group(1)
    assert (ROOT / chart).exists()
