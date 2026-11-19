"""Pre-render one short sample per VieNeu voice into voices/samples/<id>.mp3 so the web UI can
play them instantly without synthesizing.

    uv run python scripts/make_samples.py            # only voices missing a sample
    uv run python scripts/make_samples.py --force    # re-render all
"""

from __future__ import annotations

import argparse
import shutil
import sys

from archi_tts import config
from archi_tts.engines.vieneu_engine import VieNeuEngine
from archi_tts.pipeline import Renderer
from archi_tts.script import Segment, split_pauses
from archi_tts.voices import VoiceRegistry

SAMPLES_DIR = config.VOICES_DIR / "samples"
TEXT = ("Xin chào, mình là {name}. Hôm nay ngày 20 tháng 11, trời Hà Nội se lạnh, "
        "rất hợp để đi dạo và thưởng thức một tách cà phê nóng.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    registry = VoiceRegistry()
    renderer = Renderer(registry, {"vieneu": VieNeuEngine()})
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    voices = [v for v in registry.voices.values() if v.engine == "vieneu"]
    for i, v in enumerate(voices, 1):
        dest = SAMPLES_DIR / f"{v.id}.mp3"
        if dest.exists() and not args.force:
            print(f"[{i}/{len(voices)}] {v.id}: có rồi, bỏ qua", file=sys.stderr)
            continue
        seg = Segment(voice=v.id, text_parts=split_pauses(TEXT.format(name=v.name)), line=1)
        r = renderer.render([seg], f"sample_{v.id}", formats=("wav", "mp3"))
        shutil.copyfile(r.mp3, dest)
        print(f"[{i}/{len(voices)}] {v.id}: {r.duration_s}s -> {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
