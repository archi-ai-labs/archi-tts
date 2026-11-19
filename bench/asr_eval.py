"""Transcribe every synthesized unit with Whisper (MLX) and compute syllable
error rate against the normalized input text. Adds "wer" to metrics.json.

Run with bench/asr/.venv/bin/python (mlx-whisper + soe-vinorm).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import mlx_whisper

sys.path.insert(0, str(Path(__file__).parent / "common"))
from normalize import normalize  # noqa: E402

BENCH = Path(__file__).parent
RES = BENCH / "results"
MODEL = "mlx-community/whisper-large-v3-turbo"


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return s.split()


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def main() -> None:
    units = json.loads((RES / "units.json").read_text())
    metrics = json.loads((RES / "metrics.json").read_text())
    engines = sys.argv[1:] or [e for e in metrics if "error" not in metrics[e]]
    for e in engines:
        errs = total = 0
        per_test: dict[str, list[int]] = {}
        details = {}
        for u in units:
            wav = RES / e / "units" / f"{u['key']}.wav"
            hyp = mlx_whisper.transcribe(str(wav), path_or_hf_repo=MODEL, language="vi")["text"].strip()
            ref_w, hyp_w = words(u["text"]), words(normalize(hyp) if hyp else "")
            d = edit_distance(ref_w, hyp_w)
            errs += d
            total += len(ref_w)
            t = u["key"].split("__")[0]
            per_test.setdefault(t, [0, 0])
            per_test[t][0] += d
            per_test[t][1] += len(ref_w)
            details[u["key"]] = {"ref": u["text"], "hyp": hyp, "errors": d, "n": len(ref_w)}
        metrics[e]["wer"] = round(errs / total, 3)
        metrics[e]["wer_by_test"] = {t: round(a / b, 3) for t, (a, b) in per_test.items()}
        (RES / e / "asr.json").write_text(json.dumps(details, ensure_ascii=False, indent=1))
        print(e, metrics[e]["wer"], metrics[e]["wer_by_test"], flush=True)
        (RES / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == "__main__" and "--adjusted" not in sys.argv:
    main()


# --- Adjusted error rate -------------------------------------------------
# Whisper writes numbers/English as symbols and spells Northern mergers
# (tr/ch, r/d/gi, s/x) inconsistently, so the raw WER mostly measures
# Whisper. The adjusted rate skips t3 (all symbol notation), folds those
# initial consonants together, and ignores tokens containing digits.
MERGE = [(r"^tr", "ch"), (r"^gi(?=[^ìíỉĩịn]|$)", "d"), (r"^r", "d"), (r"^s", "x")]


def fold(w: str) -> str:
    for pat, rep in MERGE:
        w = re.sub(pat, rep, w)
    return w


def adjusted() -> None:
    metrics = json.loads((RES / "metrics.json").read_text())
    for e in [e for e in metrics if "error" not in metrics[e]]:
        d = json.loads((RES / e / "asr.json").read_text())
        errs = total = 0
        for k, v in d.items():
            if k.startswith("t3_"):
                continue
            ref = [fold(x) for x in words(v["ref"])]
            hyp = [fold(x) for x in words(v["hyp"]) if not re.search(r"\d", x)]
            errs += edit_distance(ref, hyp)
            total += len(ref)
        metrics[e]["wer_adj"] = round(errs / total, 3)
        print(e, "adjusted", metrics[e]["wer_adj"])
    (RES / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == "__main__" and "--adjusted" in sys.argv:
    adjusted()
