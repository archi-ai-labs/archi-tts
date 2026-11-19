"""Render emotion and emphasis samples to listen to, and measure them.

    uv run python scripts/expressive_check.py
Files land in ~/archi-tts-output/expressive_check_*/.

Clone voices are not shipped with the repo: point ARCHI_TTS_HOME at a home that has some
(e.g. ~/.archi-tts/home after add_voice).
"""

import json

import numpy as np
import soundfile as sf

from archi_tts import config
from archi_tts.engines.omnivoice_engine import OmniVoiceEngine
from archi_tts.engines.vieneu_engine import VieNeuEngine
from archi_tts.pipeline import Renderer
from archi_tts.script import parse_script
from archi_tts.voices import VoiceRegistry

reg = VoiceRegistry()
r = Renderer(reg, {"vieneu": VieNeuEngine(), "omnivoice": OmniVoiceEngine()})
CLONES = [v.id for v in reg.voices.values() if v.engine == "omnivoice"]
assert CLONES, "no clone voices: set ARCHI_TTS_HOME to a home with some (see docstring)"
SR = config.SAMPLE_RATE


def pitch_track(x: np.ndarray) -> np.ndarray:
    n = int(0.04 * SR)
    out = []
    for i in range(0, len(x) - n, n // 2):
        fr = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt(np.mean(fr ** 2)) < 0.02:
            continue
        ac = np.correlate(fr, fr, "full")[n - 1:]
        lo, hi = int(SR / 400), int(SR / 70)
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.3 * ac[0]:
            out.append(SR / lag)
    return np.array(out)


def render(voice: str, line: str, name: str) -> tuple[str, np.ndarray]:
    res = r.render(parse_script(f"[{voice}] {line}" if "[" not in line[:1] else line, reg.resolve, reg.default), name)
    audio, _ = sf.read(res.wav, dtype="float32")
    return res.wav, audio


report = {"emotion": {}, "emphasis": {}}

# Emotion: the same neutral sentence, only the reference clip changes.
SENT = "Hôm nay anh ấy đã về nhà sau một chuyến đi rất dài."
print("== emotion (same sentence, reference clip per emotion)")
for voice in CLONES[:2]:
    for emo in ["trung_tinh", "vui", "buon", "tuc_gian"]:
        wav, a = render(voice, f"[{voice} | {emo}] {SENT}", f"expressive_check_{voice}_{emo}")
        f0 = pitch_track(a)
        med = float(np.median(f0))
        spread = float(np.std(12 * np.log2(f0 / med)))
        report["emotion"][f"{voice}/{emo}"] = {"wav": wav, "dur_s": round(len(a) / SR, 2), "f0_hz": round(med),
                                               "f0_spread_st": round(spread, 2)}
        print(f"  {voice:7s} {emo:10s} dur {len(a) / SR:5.2f}s  f0 {med:4.0f} Hz  spread {spread:4.2f} st")

# Emphasis: same line with and without *...*; timing of the word comes from Whisper later.
LINE_PLAIN = "Bạn phải sao lưu dữ liệu trước khi cập nhật."
LINE_EMPH = "Bạn *phải* sao lưu dữ liệu trước khi cập nhật."
print("== emphasis")
for voice in ["ngoc_huyen", CLONES[0]]:
    for tag, line in [("plain", LINE_PLAIN), ("emph", LINE_EMPH)]:
        wav, a = render(voice, line, f"expressive_check_{voice}_{tag}")
        report["emphasis"][f"{voice}/{tag}"] = {"wav": wav, "dur_s": round(len(a) / SR, 2)}
        print(f"  {voice:10s} {tag:5s} dur {len(a) / SR:5.2f}s")

json.dump(report, open(config.OUTPUT_DIR / "expressive_check.json", "w"), ensure_ascii=False, indent=1)
print(config.OUTPUT_DIR / "expressive_check.json")
