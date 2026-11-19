"""F5-TTS-Vietnamese-ViVoice runner. Usage: runner.py jobs.json out_dir

The model was trained on lowercase text, so input and reference transcripts
are lowercased here.
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

import soundfile as sf
import torch
from huggingface_hub import snapshot_download

DEVICE = os.environ.get("F5_DEVICE") or ("mps" if torch.backends.mps.is_available() else "cpu")
STEPS = int(os.environ.get("F5_STEPS", "32"))

jobs = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

t0 = time.time()
from f5_tts.api import F5TTS  # noqa: E402

repo = Path(snapshot_download("hynt/F5-TTS-Vietnamese-ViVoice"))
# The repo ships the vocab under the wrong name (config.json); copy it locally.
vocab = Path(__file__).with_name("vocab.txt")
if not vocab.exists():
    shutil.copy(repo / "config.json", vocab)
tts = F5TTS(model="F5TTS_Base", ckpt_file=str(repo / "model_last.pt"), vocab_file=str(vocab), device=DEVICE)
load_s = time.time() - t0
SR = tts.target_sample_rate

timings = {"load_s": load_s, "sr": SR, "device": DEVICE, "steps": STEPS, "units": {}}
for u in jobs["units"]:
    t = time.time()
    wav, sr, _ = tts.infer(
        ref_file=u["ref_wav"],
        ref_text=u["ref_text"].lower(),
        gen_text=u["text"].lower(),
        nfe_step=STEPS,
        show_info=lambda *a, **k: None,
        progress=None,
        seed=1234,
    )
    gen = time.time() - t
    sf.write(out / f"{u['key']}.wav", wav, sr)
    timings["units"][u["key"]] = {"gen_s": gen, "dur_s": len(wav) / sr}
    print(f"{u['key']}: {gen:.1f}s for {len(wav) / sr:.1f}s", file=sys.stderr, flush=True)

(out / "timings.json").write_text(json.dumps(timings, indent=1))
