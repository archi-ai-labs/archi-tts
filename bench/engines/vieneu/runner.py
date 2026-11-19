"""VieNeu-TTS v3 Turbo runner. Usage: runner.py jobs.json out_dir [preset|clone]

jobs.json: {"units": [{"key", "text", "role", "emotion", "ref_wav", "ref_text"}],
            "presets": {"nu": "...", "nam": "..."}}
Writes <out_dir>/<key>.wav and <out_dir>/timings.json.
"""

import json
import sys
import time
from pathlib import Path

import soundfile as sf

jobs = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "preset"
out.mkdir(parents=True, exist_ok=True)

t0 = time.time()
from vieneu import Vieneu  # noqa: E402

tts = Vieneu()
load_s = time.time() - t0
SR = 48000

timings = {"load_s": load_s, "sr": SR, "units": {}}
for u in jobs["units"]:
    t = time.time()
    if mode == "preset":
        audio = tts.infer(u["text"], voice=jobs["presets"][u["role"]])
    else:
        audio = tts.infer(u["text"], ref_audio=u["ref_wav"], denoise=False)
    gen = time.time() - t
    sf.write(out / f"{u['key']}.wav", audio, SR)
    timings["units"][u["key"]] = {"gen_s": gen, "dur_s": len(audio) / SR}
    print(f"{u['key']}: {gen:.1f}s for {len(audio) / SR:.1f}s", file=sys.stderr, flush=True)

(out / "timings.json").write_text(json.dumps(timings, indent=1))
