"""Measure that speed / pitch / volume controls actually change the output.

    uv run python scripts/control_check.py

Clone voices are not shipped with the repo: point ARCHI_TTS_HOME at a home that has some
(e.g. ~/.archi-tts/home after add_voice).
"""

import json

import numpy as np
import soundfile as sf

from archi_tts.engines.omnivoice_engine import OmniVoiceEngine
from archi_tts.engines.vieneu_engine import VieNeuEngine
from archi_tts.pipeline import Renderer
from archi_tts.script import parse_script
from archi_tts.voices import VoiceRegistry

LINE = "Hôm nay chúng ta sẽ cùng nhau tìm hiểu về công nghệ mới."
reg = VoiceRegistry()
r = Renderer(reg, {"vieneu": VieNeuEngine(), "omnivoice": OmniVoiceEngine()})
CLONES = [v.id for v in reg.voices.values() if v.engine == "omnivoice"]
assert CLONES, "no clone voices: set ARCHI_TTS_HOME to a home with some (see docstring)"

variants = []
for voice in ["ngoc_huyen", CLONES[0]]:
    for opts in ["", "speed=0.8", "speed=1.25", "pitch=-3", "pitch=3", "volume=-6", "volume=6"]:
        variants.append((voice, opts))
script = "\n".join(f"[{v}{' | ' + o if o else ''}] {LINE}" for v, o in variants)
res = r.render(parse_script(script, reg.resolve, reg.default), "control_check")
manifest = json.load(open(res.wav.replace(".wav", "").rsplit("/", 1)[0] + "/manifest.json"))["chunks"]
audio, sr = sf.read(res.wav, dtype="float32")


def f0(x: np.ndarray) -> float:
    """Median pitch via autocorrelation over voiced 40 ms frames (rough)."""
    n = int(0.04 * sr)
    vals = []
    for i in range(0, len(x) - n, n):
        fr = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt(np.mean(fr ** 2)) < 0.02:
            continue
        ac = np.correlate(fr, fr, "full")[n - 1:]
        lo, hi = int(sr / 400), int(sr / 70)
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.3 * ac[0]:
            vals.append(sr / lag)
    return float(np.median(vals)) if vals else float("nan")


rows = {}
for (voice, opts), c in zip(variants, manifest):
    seg = audio[int(c["start"] * sr):int(c["end"] * sr)]
    rms_db = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)
    rows[(voice, opts)] = (c["end"] - c["start"], rms_db, f0(seg))

for voice in ["ngoc_huyen", CLONES[0]]:
    base_d, base_r, base_f = rows[(voice, "")]
    print(f"\n{voice}: base {base_d:.2f}s, {base_r:.1f} dBFS, f0 {base_f:.0f} Hz")
    for opts in ["speed=0.8", "speed=1.25", "pitch=-3", "pitch=3", "volume=-6", "volume=6"]:
        d, rd, f = rows[(voice, opts)]
        print(f"  {opts:11s} duration x{d / base_d:.2f}  level {rd - base_r:+.1f} dB  f0 {12 * np.log2(f / base_f):+.1f} st")
print("\n", res.wav)
