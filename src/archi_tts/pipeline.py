"""Script segments -> one mixed audio file + SRT.

Each chunk's raw engine output is cached by (engine, voice, reference clip,
normalized text, native speed), so editing one line of a script only
re-synthesizes that line. Pitch, volume and non-native speed are applied
after the cache, so tweaking them is cheap.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from . import config, dsp
from .engines.base import Engine
from .script import Pause, ScriptError, Segment, slug
from .text import Chunk, chunk_text, load_lexicon, subtitle_lines
from .voices import Voice, VoiceRegistry


@dataclass
class Gap:
    seconds: float
    explicit: bool = False


@dataclass
class Item:
    voice: Voice
    emotion: str | None
    speed: float
    pitch: float
    volume: float
    chunk: Chunk
    line: int


@dataclass
class RenderResult:
    name: str
    wav: str
    mp3: str
    srt: str
    duration_s: float
    chunks: int
    synthesized: int
    from_cache: int
    elapsed_s: float
    voices: list[str]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


ProgressFn = Callable[[int, int], None]


def _push_gap(plan: list, gap: Gap) -> None:
    if plan and isinstance(plan[-1], Gap):
        last = plan[-1]
        if gap.explicit or not last.explicit:
            plan[-1] = Gap(gap.seconds if gap.explicit else max(last.seconds, gap.seconds), gap.explicit or last.explicit)
        return
    if plan:
        plan.append(gap)


def build_plan(segments: list[Segment], registry: VoiceRegistry) -> tuple[list[Item | Gap], list[str]]:
    lexicons = {e: load_lexicon(engine=e) for e in ("vieneu", "omnivoice")}
    plan: list[Item | Gap] = []
    warnings: list[str] = []
    for seg in segments:
        voice = registry.get(seg.voice)
        if voice.engine == "omnivoice" and not config.has_omnivoice():
            raise ScriptError(f"Dòng {seg.line}: giọng '{voice.id}' là giọng clone. {config.full_hint()}")
        if seg.emotion and seg.emotion != "trung_tinh":
            if voice.engine == "vieneu":
                warnings.append(f"Dòng {seg.line}: giọng có sẵn '{voice.id}' không đổi cảm xúc "
                                f"(bỏ qua '{seg.emotion}'); dùng giọng clone nếu cần cảm xúc.")
            else:
                _, w = voice.ref_for(seg.emotion)
                if w:
                    warnings.append(f"Dòng {seg.line}: {w}")
        _push_gap(plan, Gap(config.PARAGRAPH_GAP_S if seg.paragraph_break else config.SEGMENT_GAP_S))
        for part in seg.text_parts:
            if isinstance(part, Pause):
                _push_gap(plan, Gap(part.seconds, explicit=True))
                continue
            for chunk in chunk_text(part, lexicons[voice.engine]):
                if plan and isinstance(plan[-1], Item):
                    plan.append(Gap(config.SENTENCE_GAP_S))
                plan.append(Item(voice, seg.emotion, seg.speed, seg.pitch, seg.volume, chunk, seg.line))
    while plan and isinstance(plan[-1], Gap):
        plan.pop()
    return plan, list(dict.fromkeys(warnings))


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_srt(cues: list[tuple[float, float, str]]) -> str:
    out = []
    for i, (start, end, text) in enumerate(cues, 1):
        out.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
    return "\n".join(out)


def chunk_cues(raw: str, start: float, end: float) -> list[tuple[float, float, str]]:
    lines = subtitle_lines(raw)
    if not lines:
        return []
    total = sum(len(x) for x in lines)
    cues, t = [], start
    for line in lines:
        d = (end - start) * len(line) / total
        cues.append((t, t + d, line))
        t += d
    return cues


class Renderer:
    def __init__(self, registry: VoiceRegistry, engines: dict[str, Engine]):
        self.registry = registry
        self.engines = engines
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, engine: Engine, item: Item, native_speed: float) -> Path:
        parts = engine.cache_key_parts(item.voice, item.emotion) + [item.chunk.norm, f"{native_speed:.3f}"]
        return config.CACHE_DIR / (hashlib.sha1("\x1f".join(parts).encode()).hexdigest() + ".wav")

    def _synth_item(self, item: Item) -> tuple[np.ndarray, bool]:
        engine = self.engines[item.voice.engine]
        native = item.speed if engine.native_speed else 1.0
        path = self._cache_path(engine, item, native)
        if path.exists():
            audio, sr = sf.read(path, dtype="float32")
            cached = True
        else:
            audio, sr = engine.synth(item.chunk.norm, item.voice, item.emotion, native), engine.sample_rate
            tmp = path.with_suffix(".tmp.wav")
            sf.write(tmp, audio, sr, subtype="FLOAT")
            tmp.replace(path)
            cached = False
        audio = dsp.trim_silence(audio, sr)
        post_speed = 1.0 if engine.native_speed else item.speed
        audio = dsp.stretch_and_shift(audio, sr, post_speed, item.pitch)
        audio = dsp.resample(audio, sr)
        audio = dsp.level_match(audio, config.SAMPLE_RATE)
        return dsp.gain(audio, item.volume), cached

    def render(self, segments: list[Segment], name: str | None = None, progress: ProgressFn | None = None,
               formats: tuple[str, ...] = ("wav", "mp3", "srt")) -> RenderResult:
        t0 = time.time()
        plan, warnings = build_plan(segments, self.registry)
        items = [p for p in plan if isinstance(p, Item)]
        if not items:
            raise ValueError("Không có câu nào để đọc.")
        name = slug(name or "") or datetime.now().strftime("tts_%Y%m%d_%H%M%S")
        out_dir = config.OUTPUT_DIR / name
        out_dir.mkdir(parents=True, exist_ok=True)

        sr = config.SAMPLE_RATE
        pieces: list[np.ndarray] = []
        cues: list[tuple[float, float, str]] = []
        manifest = []
        t = 0.0
        done = cached_n = 0
        for p in plan:
            if isinstance(p, Gap):
                pieces.append(dsp.silence(p.seconds, sr))
                t += len(pieces[-1]) / sr
                continue
            t_item = time.time()
            audio, cached = self._synth_item(p)
            gen_s = time.time() - t_item
            cached_n += cached
            pieces.append(audio)
            dur = len(audio) / sr
            cues.extend(chunk_cues(p.chunk.raw, t, t + dur))
            manifest.append({"line": p.line, "voice": p.voice.id, "emotion": p.emotion, "start": round(t, 3),
                             "end": round(t + dur, 3), "text": p.chunk.raw, "spoken": p.chunk.norm, "cached": cached,
                             "gen_s": round(gen_s, 2)})
            t += dur
            done += 1
            if progress:
                progress(done, len(items))

        audio = np.concatenate(pieces)
        wav, mp3, srt = out_dir / f"{name}.wav", out_dir / f"{name}.mp3", out_dir / f"{name}.srt"
        duration = dsp.export(audio, sr, wav, mp3 if "mp3" in formats else None)
        srt.write_text(make_srt(cues), encoding="utf-8")
        result = RenderResult(
            name=name, wav=str(wav), mp3=str(mp3) if "mp3" in formats else "", srt=str(srt),
            duration_s=round(duration, 2), chunks=len(items), synthesized=len(items) - cached_n, from_cache=cached_n,
            elapsed_s=round(time.time() - t0, 1), voices=sorted({i.voice.id for i in items}), warnings=warnings,
        )
        (out_dir / "manifest.json").write_text(json.dumps({"result": result.as_dict(), "chunks": manifest},
                                                          ensure_ascii=False, indent=1), encoding="utf-8")
        return result
