"""Benchmark harness. Run with bench/common/.venv/bin/python.

  run_bench.py [engine ...]        # default: all engines in ENGINES

Steps per engine:
  1. Expand tests.yaml into synthesis units (normalized, sentence-chunked,
     pause/emphasis markers resolved) and write jobs.json.
  2. Run the engine's runner.py inside its own venv under /usr/bin/time -l
     to capture peak RSS.
  3. Stitch unit wavs into one file per test (silences, gain, loudnorm) and
     record metrics in results/metrics.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

sys.path.insert(0, str(Path(__file__).parent / "common"))
from normalize import load_lexicon, normalize  # noqa: E402

BENCH = Path(__file__).parent
RESULTS = BENCH / "results"
REFS = json.loads((BENCH / "refs" / "refs.json").read_text())

ENGINES = {
    "vieneu_preset": {"dir": "vieneu", "args": ["preset"], "hf": ["pnnbao-ump--VieNeu-TTS-v3-Turbo", "OpenMOSS-Team--MOSS-Audio-Tokenizer-Nano-ONNX"]},
    "vieneu_clone": {"dir": "vieneu", "args": ["clone"], "hf": ["pnnbao-ump--VieNeu-TTS-v3-Turbo", "OpenMOSS-Team--MOSS-Audio-Tokenizer-Nano-ONNX"]},
    "omnivoice": {"dir": "omnivoice", "args": [], "hf": ["danhcao--v-omnivoice"]},
    "f5": {"dir": "f5", "args": [], "hf": ["hynt--F5-TTS-Vietnamese-ViVoice", "charactr--vocos-mel-24khz"]},
}
VIENEU_PRESETS = {"nu": "Ngọc Huyền", "nam": "Phạm Tuyên"}

MAX_CHUNK = 200
SENT_PAUSE = 0.25


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) + 1 > MAX_CHUNK:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def expand(text: str, lex: dict[str, str]) -> list[dict]:
    """Turn raw text with [ngắt Xs] and *word* into a sequence of
    {"text": ...} and {"pause": seconds} items."""
    items: list[dict] = []
    for piece in re.split(r"(\[ngắt\s*[\d.]+\s*s\])", text):
        m = re.fullmatch(r"\[ngắt\s*([\d.]+)\s*s\]", piece)
        if m:
            items.append({"pause": float(m.group(1))})
            continue
        # Emphasis: a comma before the stressed word makes engines pause and
        # re-attack it. Splitting the chunk instead would leave lone words.
        piece = re.sub(r"(?<=[^\s,.;:!?])\s*\*([^*]+)\*", r", \1", piece)
        piece = piece.replace("*", "")
        if not piece.strip():
            continue
        for c in split_sentences(normalize(piece, lex)):
            items.append({"text": c})
    return items


def build_plan(tests: list[dict]) -> tuple[list[dict], dict]:
    lex = load_lexicon()
    units, plan = [], {}
    for t in tests:
        seq = []
        for si, seg in enumerate(t["segments"]):
            ref = REFS[seg["role"]].get(seg.get("emotion", "trung_tinh")) or REFS[seg["role"]]["trung_tinh"]
            for ii, it in enumerate(expand(seg["text"], lex)):
                if "pause" in it:
                    seq.append({"pause": it["pause"]})
                    continue
                key = f"{t['id']}__{si:02d}_{ii:02d}"
                units.append({
                    "key": key,
                    "text": it["text"],
                    "raw": it["text"],
                    "role": seg["role"],
                    "emotion": seg.get("emotion", "trung_tinh"),
                    "ref_wav": str(BENCH / "refs" / ref["wav"]),
                    "ref_text": ref["text"],
                })
                seq.append({"unit": key})
            seq.append({"pause": 0.5 if si < len(t["segments"]) - 1 else 0})
        plan[t["id"]] = seq
    return units, plan


def dir_size_gb(names: list[str]) -> float:
    hub = Path.home() / ".cache/huggingface/hub"
    total = 0
    for n in names:
        p = hub / f"models--{n}" / "blobs"
        if p.exists():
            total += sum(f.stat().st_size for f in p.iterdir() if f.is_file())
    return round(total / 1e9, 2)


def stitch(engine_out: Path, plan: dict, sr: int, dest: Path) -> dict[str, float]:
    durations = {}
    for test_id, seq in plan.items():
        parts = []
        for item in seq:
            if "pause" in item:
                parts.append(np.zeros(int(item["pause"] * sr), dtype=np.float32))
                continue
            wav, wsr = sf.read(engine_out / f"{item['unit']}.wav", dtype="float32")
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            assert wsr == sr, (wsr, sr)
            parts.append(wav)
            parts.append(np.zeros(int(SENT_PAUSE * sr), dtype=np.float32))
        audio = np.concatenate(parts)
        raw = dest / f"{test_id}.raw.wav"
        sf.write(raw, audio, sr)
        mp3 = dest / f"{test_id}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", "44100", "-b:a", "160k", str(mp3)], check=True)
        raw.unlink()
        durations[test_id] = round(len(audio) / sr, 2)
    return durations


def run_engine(name: str, units: list[dict], plan: dict) -> dict:
    cfg = ENGINES[name]
    edir = BENCH / "engines" / cfg["dir"]
    work = RESULTS / name / "units"
    work.mkdir(parents=True, exist_ok=True)
    jobs = work.parent / "jobs.json"
    jobs.write_text(json.dumps({"units": units, "presets": VIENEU_PRESETS}, ensure_ascii=False, indent=1))
    log = work.parent / "run.log"
    t = time.time()
    with log.open("w") as fh:
        rc = subprocess.run(["/usr/bin/time", "-l", str(edir / ".venv/bin/python"), str(edir / "runner.py"), str(jobs), str(work), *cfg["args"]],
                            stdout=fh, stderr=subprocess.STDOUT, cwd=edir).returncode
    wall = time.time() - t
    text = log.read_text(errors="replace")
    if rc != 0:
        return {"engine": name, "error": f"exit {rc}, see {log}"}
    m = re.search(r"(\d+)\s+maximum resident set size", text)
    peak_gb = round(int(m.group(1)) / 1e9, 2) if m else None
    timings = json.loads((work / "timings.json").read_text())
    gen = sum(u["gen_s"] for u in timings["units"].values())
    dur = sum(u["dur_s"] for u in timings["units"].values())
    durations = stitch(work, plan, timings["sr"], work.parent)
    return {
        "engine": name,
        "device": timings.get("device", "cpu"),
        "sample_rate": timings["sr"],
        "model_gb": dir_size_gb(cfg["hf"]),
        "peak_ram_gb": peak_gb,
        "load_s": round(timings["load_s"], 1),
        "gen_s": round(gen, 1),
        "audio_s": round(dur, 1),
        "rtf": round(gen / dur, 3) if dur else None,
        "est_15min_video_min": round(15 * gen / dur, 1) if dur else None,
        "wall_s": round(wall, 1),
        "tests": durations,
    }


def main() -> None:
    tests = yaml.safe_load((BENCH / "tests.yaml").read_text())
    units, plan = build_plan(tests)
    (RESULTS).mkdir(exist_ok=True)
    (RESULTS / "units.json").write_text(json.dumps(units, ensure_ascii=False, indent=1))
    metrics_path = RESULTS / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    for name in sys.argv[1:] or list(ENGINES):
        print(f"== {name}", flush=True)
        metrics[name] = run_engine(name, units, plan)
        print(json.dumps(metrics[name], ensure_ascii=False), flush=True)
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
