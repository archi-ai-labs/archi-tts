"""Voice registry backed by voices/voices.yaml.

Two kinds of voice:
  engine: vieneu     -> a VieNeu built-in preset (fast, fixed reading style)
  engine: omnivoice  -> cloned from reference clips, one clip per emotion
"""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

import soundfile as sf
import yaml

from . import config
from .script import EMOTION_ALIASES, ScriptError, normalize_emotion, slug


@dataclass
class Ref:
    wav: Path
    text: str | None


@dataclass
class Voice:
    id: str
    engine: str
    name: str
    gender: str = ""
    accent: str = "Bắc"
    style: str = ""
    preset: str | None = None
    refs: dict[str, Ref] = field(default_factory=dict)
    note: str = ""

    def ref_for(self, emotion: str | None) -> tuple[Ref, str | None]:
        """Reference clip for an emotion, plus a warning if it had to fall back."""
        emotion = emotion or "trung_tinh"
        if emotion in self.refs:
            return self.refs[emotion], None
        fallback = self.refs.get("trung_tinh") or next(iter(self.refs.values()))
        return fallback, f"Giọng '{self.id}' chưa có clip cảm xúc '{emotion}', dùng clip trung tính."

    def describe(self) -> dict:
        d = {"id": self.id, "name": self.name, "engine": self.engine, "gender": self.gender, "accent": self.accent}
        if self.style:
            d["style"] = self.style
        d["emotions"] = sorted(self.refs) if self.engine == "omnivoice" else ["(cố định theo giọng)"]
        if self.note:
            d["note"] = self.note
        return d


class VoiceRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or config.VOICES_FILE
        self._lock = threading.Lock()
        self.reload()

    def reload(self) -> None:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.default = data.get("default_voice")
        self.voices: dict[str, Voice] = {}
        for vid, v in (data.get("voices") or {}).items():
            refs = {
                emo: Ref(self.path.parent / r["wav"], r.get("text"))
                for emo, r in (v.get("refs") or {}).items()
            }
            self.voices[vid] = Voice(id=vid, engine=v["engine"], name=v.get("name", vid), gender=v.get("gender", ""),
                                     accent=v.get("accent", "Bắc"), style=v.get("style", ""), preset=v.get("preset"),
                                     refs=refs, note=v.get("note", ""))
        if self.default not in self.voices:
            self.default = next(iter(self.voices), None)

    def resolve(self, name: str) -> str | None:
        """Match by id or by display name, ignoring case and diacritics."""
        key = slug(name)
        if key in self.voices:
            return key
        for v in self.voices.values():
            if slug(v.name) == key or (v.preset and slug(v.preset) == key):
                return v.id
        return None

    def get(self, name: str | None) -> Voice:
        vid = self.resolve(name) if name else self.default
        if vid is None:
            raise ScriptError(f"Không có giọng '{name}'. Gọi list_voices để xem danh sách.")
        return self.voices[vid]

    @staticmethod
    def validate_clip(audio_path: str) -> Path:
        src = Path(audio_path).expanduser()
        if not src.exists():
            raise ScriptError(f"Không thấy file {src}.")
        try:
            info = sf.info(str(src))
        except RuntimeError as e:
            raise ScriptError(f"Không đọc được audio {src.name} (cần WAV/FLAC/MP3/OGG): {e}") from None
        if not 2.5 <= info.duration <= 12:
            raise ScriptError(f"Clip dài {info.duration:.1f}s; cần 3–10 giây giọng sạch, một người nói.")
        return src

    def add_clone(self, voice_id: str, audio_path: str, transcript: str | None, emotion: str = "trung_tinh",
                  name: str | None = None, gender: str = "", note: str = "") -> Voice:
        voice_id = slug(voice_id)
        if not voice_id:
            raise ScriptError("voice_id không hợp lệ.")
        emotion = normalize_emotion(emotion) or "trung_tinh"
        src = self.validate_clip(audio_path)
        with self._lock:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            voices = data.setdefault("voices", {})
            existing = voices.get(voice_id)
            if existing and existing.get("engine") != "omnivoice":
                raise ScriptError(f"'{voice_id}' là giọng có sẵn của VieNeu, chọn tên khác.")
            dest_dir = self.path.parent / voice_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{emotion}{src.suffix.lower()}"
            shutil.copyfile(src, dest)
            entry = existing or {"engine": "omnivoice", "name": name or voice_id, "gender": gender, "accent": "Bắc",
                                 "refs": {}}
            if name:
                entry["name"] = name
            if gender:
                entry["gender"] = gender
            if note:
                entry["note"] = note
            entry.setdefault("refs", {})[emotion] = {"wav": f"{voice_id}/{dest.name}", "text": transcript}
            voices[voice_id] = entry
            self.path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.reload()
        return self.voices[voice_id]


EMOTIONS = sorted(set(EMOTION_ALIASES.values()))
