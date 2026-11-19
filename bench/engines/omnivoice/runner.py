"""OmniVoice (Vietnamese fine-tune) runner. Usage: runner.py jobs.json out_dir

Voice cloning from each unit's ref_wav/ref_text. Clone prompts are cached per
reference clip so a voice is only encoded once.
"""

import json
import os
import sys
import time
from pathlib import Path

import soundfile as sf
import torch

MODEL = os.environ.get("OMNIVOICE_MODEL", "danhcao/v-omnivoice")
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
STEPS = int(os.environ.get("OMNIVOICE_STEPS", "32"))

jobs = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

t0 = time.time()
from omnivoice import OmniVoice  # noqa: E402

model = OmniVoice.from_pretrained(MODEL, device_map=DEVICE, dtype=torch.float16 if DEVICE == "mps" else torch.float32)
load_s = time.time() - t0
SR = 24000

prompts = {}
timings = {"load_s": load_s, "sr": SR, "device": DEVICE, "steps": STEPS, "units": {}}
for u in jobs["units"]:
    t = time.time()
    if u["ref_wav"] not in prompts:
        prompts[u["ref_wav"]] = model.create_voice_clone_prompt(ref_audio=u["ref_wav"], ref_text=u["ref_text"])
    audio = model.generate(text=u["text"], voice_clone_prompt=prompts[u["ref_wav"]], num_step=STEPS)[0]
    gen = time.time() - t
    sf.write(out / f"{u['key']}.wav", audio, SR)
    timings["units"][u["key"]] = {"gen_s": gen, "dur_s": len(audio) / SR}
    print(f"{u['key']}: {gen:.1f}s for {len(audio) / SR:.1f}s", file=sys.stderr, flush=True)

(out / "timings.json").write_text(json.dumps(timings, indent=1))
