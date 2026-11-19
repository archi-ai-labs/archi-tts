"""Shared Vietnamese text normalizer for the benchmark.

soe-vinorm expands numbers, dates, units and common abbreviations; a small
lexicon then spells out English words/acronyms the way a Northern speaker
would say them. Every engine receives the same normalized text so the
comparison is fair.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from soe_vinorm import normalize_text

LEXICON_PATH = Path(__file__).with_name("lexicon.yaml")


def load_lexicon(path: Path = LEXICON_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()}


def apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    # Longest keys first so "iPhone" wins over "i"; whole-word, case-sensitive
    # for all-caps acronyms, case-insensitive otherwise.
    for key in sorted(lexicon, key=len, reverse=True):
        flags = 0 if key.isupper() else re.IGNORECASE
        text = re.sub(rf"(?<!\w){re.escape(key)}(?!\w)", lexicon[key], text, flags=flags)
    return text


def tidy_spacing(text: str) -> str:
    text = re.sub(r"\s+([,.;:!?…])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def normalize(text: str, lexicon: dict[str, str] | None = None) -> str:
    lexicon = load_lexicon() if lexicon is None else lexicon
    # Lexicon before soe-vinorm protects tokens like "COVID-19" from being split
    # oddly; run it again after, for anything soe-vinorm surfaced.
    text = apply_lexicon(text, lexicon)
    text = normalize_text(text)
    text = apply_lexicon(text, lexicon)
    return tidy_spacing(text)


if __name__ == "__main__":
    import sys

    print(normalize(" ".join(sys.argv[1:]) or "Ngày 15/8/2025, giá tăng 12,5%, COVID-19, AI, GPU, TP.HCM, 3km."))
