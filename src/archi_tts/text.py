"""Vietnamese text preparation: lexicon, normalization, emphasis, chunking.

Inline tags such as [cười] or [laughter] are kept out of the normalizer and
re-inserted untouched. Chunks keep both the raw text (for subtitles) and the
normalized text (for the engine).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import config

TAG_RE = re.compile(r"\[[^\[\]]{1,30}\]")
SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class Chunk:
    raw: str    # what the subtitle shows
    norm: str   # what the engine reads


# --- lexicon ----------------------------------------------------------------

LEXICON_HEADER = """\
# Cách đọc từ. Key viết HOA toàn bộ thì khớp đúng hoa-thường, còn lại khớp không phân biệt.
# Giá trị là chuỗi (mọi engine) hoặc theo engine: {vieneu: ..., omnivoice: ...}.
# Cách đọc được gửi nguyên văn tới engine, không qua bộ chuẩn hóa.
# VieNeu học song ngữ nên thường đọc từ tiếng Anh viết nguyên (GPU, Pro) tốt hơn phiên âm;
# OmniVoice cần phiên âm, gạch nối giúp đọc liền mạch hơn (ây-ai).
"""


def _raw_lexicon(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_lexicon(path: Path | None = None, engine: str | None = None) -> dict[str, str]:
    """Flat {word: reading} for one engine (per-engine entries win over plain ones)."""
    out: dict[str, str] = {}
    for k, v in _raw_lexicon(path or config.LEXICON_FILE).items():
        if isinstance(v, dict):
            v = v.get(engine) if engine else next(iter(v.values()), None)
            if v is None:
                continue
        reading = str(v)
        if engine == "vieneu":
            reading = reading.replace("-", " ")   # VieNeu's own normalizer mangles hyphens
        out[str(k)] = reading
    return out


def save_lexicon_entry(word: str, reading: str, engine: str | None = None, path: Path | None = None) -> None:
    path = path or config.LEXICON_FILE
    data = _raw_lexicon(path)
    if engine:
        cur = data.get(word)
        entry = dict(cur) if isinstance(cur, dict) else ({"vieneu": cur, "omnivoice": cur} if cur else {})
        entry[engine] = reading
        data[word] = entry
    else:
        data[word] = reading
    body = yaml.safe_dump(dict(sorted(data.items(), key=lambda kv: str(kv[0]).lower())), allow_unicode=True,
                          sort_keys=False, default_flow_style=None)
    path.write_text(LEXICON_HEADER + body, encoding="utf-8")


def apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    for key in sorted(lexicon, key=len, reverse=True):
        flags = 0 if key.isupper() else re.IGNORECASE
        text = re.sub(rf"(?<!\w){re.escape(key)}(?!\w)", lexicon[key], text, flags=flags)
    return text


# --- normalization ------------------------------------------------------------

@lru_cache(maxsize=1)
def _normalizer():
    from sea_g2p import Normalizer

    return Normalizer(lang="vi")


def _lexicon_re(lexicon: dict[str, str]) -> re.Pattern | None:
    if not lexicon:
        return None
    keys = sorted(lexicon, key=len, reverse=True)
    # Case-sensitive for all-caps keys, insensitive otherwise (inline flag per alternative).
    alts = [re.escape(k) if k.isupper() else f"(?i:{re.escape(k)})" for k in keys]
    return re.compile(rf"(?<!\w)(?:{'|'.join(alts)})(?!\w)")


def _lookup(lexicon: dict[str, str], word: str) -> str:
    if word in lexicon:
        return lexicon[word]
    low = word.lower()
    return next(v for k, v in lexicon.items() if not k.isupper() and k.lower() == low)


# Hyphens/dashes stay with the core: "-5" must reach the normalizer to become "âm năm".
EDGE_PUNCT_RE = re.compile(r"^([\s,.;:!?…\"'()]*)(.*?)([\s,.;:!?…\"'()]*)$", re.S)


def _sea(text: str, lexicon: dict[str, str]) -> str:
    """Normalize one stretch between lexicon matches, keeping its edge punctuation
    (the normalizer drops a lone ", " or a leading comma)."""
    lead, core, trail = EDGE_PUNCT_RE.match(text).groups()
    if core.strip():
        core = re.sub(r"</?en>", "", _normalizer().normalize(core))  # sea-g2p marks English spans
        core = apply_lexicon(core, lexicon)                            # words the normalizer surfaced
    return f"{lead}{core}{trail}"


def _normalize_plain(text: str, lexicon: dict[str, str]) -> str:
    """Lexicon matches bypass the normalizer so readings stay exactly as written
    (sea-g2p would e.g. drop the hyphen in "ây-ai")."""
    if not text.strip():
        return text
    pattern = _lexicon_re(lexicon)
    parts, pos = [], 0
    for m in pattern.finditer(text) if pattern else []:
        parts.append(_sea(text[pos:m.start()], lexicon))
        parts.append(_lookup(lexicon, m.group(0)))
        pos = m.end()
    parts.append(_sea(text[pos:], lexicon))
    out = "".join(parts)
    out = re.sub(r"\s+([,.;:!?…])", r"\1", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def normalize(text: str, lexicon: dict[str, str] | None = None) -> str:
    """Normalize text while leaving [tags] untouched."""
    lexicon = load_lexicon() if lexicon is None else lexicon
    parts, pos = [], 0
    for m in TAG_RE.finditer(text):
        parts.append(_normalize_plain(text[pos:m.start()], lexicon))
        parts.append(m.group(0))
        pos = m.end()
    parts.append(_normalize_plain(text[pos:], lexicon))
    return re.sub(r"\s{2,}", " ", " ".join(p for p in parts if p)).strip()


# --- emphasis and chunking ----------------------------------------------------

def apply_emphasis(text: str) -> str:
    """*word* -> a comma before the word so the engine pauses and re-attacks it.

    Splitting the chunk instead would leave lone words, which engines read badly.
    """
    text = re.sub(r"(?<=[^\s,.;:!?(\[])\s*\*([^*]+)\*", r", \1", text)
    return text.replace("*", "")


def split_sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END_RE.split(text.strip()) if s]


def _display(source: str) -> str:
    return re.sub(r"\s{2,}", " ", TAG_RE.sub("", source).replace("*", "")).strip()


def _group(sentences: list[str], lexicon: dict[str, str], depth: int = 0) -> list[Chunk]:
    """Greedily join sentences while the normalized text fits MAX_CHUNK_CHARS.

    Works on source strings (still holding * and [tags]) so each chunk can be
    rendered both for display and for the engine.
    """
    def spoken(src: str) -> str:
        return normalize(apply_emphasis(src), lexicon)

    sources, cur = [], ""
    for s in sentences:
        cand = f"{cur} {s}".strip()
        if cur and len(spoken(cand)) > config.MAX_CHUNK_CHARS:
            sources.append(cur)
            cur = s
        else:
            cur = cand
    if cur:
        sources.append(cur)

    out: list[Chunk] = []
    for src in sources:
        norm = spoken(src)
        if depth < 3 and len(norm) > config.MAX_CHUNK_CHARS * 1.4 and len(src.split()) > 3:
            out.extend(_group(_split_long(src), lexicon, depth + 1))
        else:
            out.append(Chunk(_display(src), norm))
    return out


def _split_long(source: str) -> list[str]:
    """Split one over-long sentence at commas/semicolons, else in half by words."""
    pieces = [p for p in re.split(r"(?<=[,;:])\s+", source) if p.strip()]
    if len(pieces) == 1:
        words = source.split()
        half = max(1, len(words) // 2)
        pieces = [" ".join(words[:half]), " ".join(words[half:])]
    return pieces


def chunk_text(text: str, lexicon: dict[str, str] | None = None) -> list[Chunk]:
    """Text without pause tags -> engine-sized chunks (display + normalized)."""
    lexicon = load_lexicon() if lexicon is None else lexicon
    return [c for c in _group(split_sentences(text), lexicon) if c.norm]


def subtitle_lines(raw: str, max_chars: int | None = None) -> list[str]:
    """Break one chunk's display text into subtitle-sized lines."""
    max_chars = max_chars or config.SUBTITLE_MAX_CHARS
    if len(raw) <= max_chars:
        return [raw] if raw else []
    lines, cur = [], ""
    for piece in re.split(r"(?<=[,;:.!?…])\s+", raw):
        for word in [piece] if len(piece) <= max_chars else piece.split():
            cand = f"{cur} {word}".strip()
            if cur and len(cand) > max_chars:
                lines.append(cur)
                cur = word
            else:
                cur = cand
    if cur:
        lines.append(cur)
    return lines
