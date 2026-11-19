"""Post-processing: resample, trim, tempo/pitch (Rubber Band), gain, loudness."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

from . import config


def resample(audio: np.ndarray, sr: int, target: int = config.SAMPLE_RATE) -> np.ndarray:
    if sr == target:
        return audio
    return soxr.resample(audio, sr, target).astype(np.float32)


def trim_silence(audio: np.ndarray, sr: int, threshold_db: float = -42.0, margin_s: float = 0.04) -> np.ndarray:
    """Cut leading/trailing silence so gaps are controlled by the pipeline."""
    if audio.size == 0:
        return audio
    frame = max(1, int(sr * 0.01))
    n = len(audio) // frame
    if n == 0:
        return audio
    rms = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    peak = rms.max()
    loud = np.where(20 * np.log10(rms / peak + 1e-12) > threshold_db)[0]
    if loud.size == 0:
        return audio
    margin = int(margin_s * sr)
    start = max(0, loud[0] * frame - margin)
    end = min(len(audio), (loud[-1] + 1) * frame + margin)
    return audio[start:end]


def find_bin(name: str) -> str:
    """Absolute path to a CLI tool. GUI-launched MCP clients (Claude Desktop) often
    start servers without Homebrew on PATH, so check the usual prefixes too."""
    found = shutil.which(name)
    if found:
        return found
    for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
        cand = Path(prefix) / name
        if cand.exists():
            return str(cand)
    raise RuntimeError(f"Không tìm thấy '{name}'. Cài bằng: brew install {name}")


def has_rubberband() -> bool:
    try:
        find_bin("rubberband")
        return True
    except RuntimeError:
        return False


def stretch_and_shift(audio: np.ndarray, sr: int, speed: float = 1.0, semitones: float = 0.0) -> np.ndarray:
    """Change tempo without pitch change and/or pitch without tempo change."""
    if abs(speed - 1.0) < 1e-3 and abs(semitones) < 1e-3:
        return audio
    if not has_rubberband():
        raise RuntimeError("Cần cài rubberband để chỉnh tốc độ/cao độ: brew install rubberband")
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in.wav", Path(d) / "out.wav"
        sf.write(src, audio, sr, subtype="FLOAT")
        cmd = [find_bin("rubberband"), "-q", "-3", "-t", f"{1.0 / speed:.5f}", "-p", f"{semitones:.3f}", str(src), str(dst)]
        subprocess.run(cmd, check=True, capture_output=True)
        out, _ = sf.read(dst, dtype="float32")
    return out.reshape(-1) if out.ndim == 1 else out.mean(axis=1)


def speech_rms_db(audio: np.ndarray, sr: int) -> float:
    """RMS over voiced frames only, so pauses don't drag the level down."""
    frame = max(1, int(sr * 0.02))
    n = len(audio) // frame
    if n == 0:
        return -120.0
    rms = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    active = rms[20 * np.log10(rms / rms.max()) > -30]
    return float(20 * np.log10(np.sqrt(np.mean(active ** 2)) + 1e-12))


def level_match(audio: np.ndarray, sr: int, target_db: float = -20.0) -> np.ndarray:
    """Bring every chunk to the same speech level so voices/engines match."""
    if audio.size == 0:
        return audio
    return gain(audio, float(np.clip(target_db - speech_rms_db(audio, sr), -20, 20)))


def gain(audio: np.ndarray, db: float) -> np.ndarray:
    return audio if abs(db) < 1e-3 else audio * np.float32(10 ** (db / 20))


def silence(seconds: float, sr: int = config.SAMPLE_RATE) -> np.ndarray:
    return np.zeros(max(0, int(round(seconds * sr))), dtype=np.float32)


def measure_lufs(path: Path) -> float:
    """Integrated loudness via ffmpeg's loudnorm analysis pass."""
    out = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-af", "loudnorm=print_format=json",
                          "-f", "null", "-"], check=True, capture_output=True, text=True).stderr
    data = json.loads(out[out.rindex("{"):out.rindex("}") + 1])
    return float(data["input_i"])


def export(audio: np.ndarray, sr: int, wav_path: Path, mp3_path: Path | None, lufs: float = config.TARGET_LUFS) -> float:
    """Normalize loudness with one static gain plus a peak limiter, write WAV (+ MP3).

    A static gain keeps per-line volume differences intact; single-pass
    loudnorm is dynamic and flattened a +6 dB line to +1 dB.
    """
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "raw.wav"
        sf.write(raw, audio, sr, subtype="FLOAT")
        current = measure_lufs(raw)
        g = 0.0 if not np.isfinite(current) else lufs - current
        af = f"volume={g:.2f}dB,alimiter=limit=0.84:attack=5:release=50:level=disabled"
        subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-i", str(raw), "-af", af, "-ar", str(sr),
                        "-c:a", "pcm_s16le", str(wav_path)], check=True)
    if mp3_path:
        subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-i", str(wav_path), "-b:a", "192k", str(mp3_path)],
                       check=True)
    return len(audio) / sr
