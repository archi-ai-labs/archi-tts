"""Parse dubbing scripts.

    [giong | cam_xuc | speed=1.1 | pitch=-1 | volume=+2] Văn bản...
    Dòng không có tag thì giữ giọng/cài đặt của dòng trước.
    [ngắt 0.8s] chèn khoảng lặng; *từ* nhấn; [cười] tag phi ngôn ngữ.
    Dòng trống = ngắt đoạn (nghỉ dài hơn).

Only a bracket at the start of a line whose first field names a known voice
(or that contains "|" or "=") is a header; [cười] at line start stays text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

PAUSE_RE = re.compile(r"\[\s*(?:ngắt|ngat|nghỉ|nghi|pause)\s*([\d.,]+)\s*(ms|s)?\s*\]", re.IGNORECASE)
HEADER_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(.*)$")

EMOTION_ALIASES = {
    "trung_tinh": "trung_tinh", "trungtinh": "trung_tinh", "binh_thuong": "trung_tinh", "neutral": "trung_tinh",
    "tin_tuc": "trung_tinh",
    "vui": "vui", "vui_ve": "vui", "hao_hung": "vui", "happy": "vui",
    "buon": "buon", "sad": "buon",
    "tuc_gian": "tuc_gian", "gian": "tuc_gian", "tuc": "tuc_gian", "angry": "tuc_gian",
}


# Inline non-verbal tags either engine understands; a line may start with one.
NONVERBAL_TAGS = {
    "cười", "thở dài", "hắng giọng", "laughter", "sigh", "confirmation-en", "dissatisfaction-hnn",
    "question-ah", "question-ei", "question-en", "question-oh", "question-yi",
    "surprise-ah", "surprise-oh", "surprise-wa", "surprise-yo",
}


class ScriptError(ValueError):
    pass


@dataclass
class Pause:
    seconds: float


@dataclass
class Segment:
    voice: str
    text_parts: list[str | Pause]
    emotion: str | None = None
    speed: float = 1.0
    pitch: float = 0.0       # semitones
    volume: float = 0.0      # dB
    line: int = 0
    paragraph_break: bool = False  # blank line before this segment


@dataclass
class _State:
    voice: str
    emotion: str | None = None
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 0.0
    extras: dict = field(default_factory=dict)


def slug(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", s.strip().lower()).replace("đ", "d")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def normalize_emotion(value: str | None) -> str | None:
    if not value:
        return None
    key = slug(value)
    if key not in EMOTION_ALIASES:
        raise ScriptError(f"Cảm xúc '{value}' không hỗ trợ. Dùng: trung_tinh, vui, buon, tuc_gian.")
    return EMOTION_ALIASES[key]


def split_pauses(text: str) -> list[str | Pause]:
    parts: list[str | Pause] = []
    pos = 0
    for m in PAUSE_RE.finditer(text):
        if text[pos:m.start()].strip():
            parts.append(text[pos:m.start()].strip())
        value = float(m.group(1).replace(",", "."))
        parts.append(Pause(value / 1000 if (m.group(2) or "s").lower() == "ms" else value))
        pos = m.end()
    if text[pos:].strip():
        parts.append(text[pos:].strip())
    return parts


def _num(key: str, value: str, lo: float, hi: float) -> float:
    try:
        v = float(value.replace(",", ".").replace("+", ""))
    except ValueError as e:
        raise ScriptError(f"{key}={value} không phải số") from e
    if not lo <= v <= hi:
        raise ScriptError(f"{key}={value} ngoài khoảng {lo}..{hi}")
    return v


def parse_header(fields: list[str], resolve_voice: Callable[[str], str | None], line_no: int) -> _State:
    voice = resolve_voice(fields[0])
    if voice is None:
        raise ScriptError(f"Dòng {line_no}: không có giọng '{fields[0]}'. Gọi list_voices để xem danh sách.")
    st = _State(voice=voice)
    for f in fields[1:]:
        if "=" in f:
            k, v = (x.strip() for x in f.split("=", 1))
            k = slug(k)
            if k in ("speed", "toc_do"):
                st.speed = _num(k, v, 0.5, 2.0)
            elif k in ("pitch", "cao_do"):
                st.pitch = _num(k, v, -6, 6)
            elif k in ("volume", "vol", "am_luong"):
                st.volume = _num(k, v, -12, 12)
            elif k in ("emotion", "cam_xuc"):
                st.emotion = normalize_emotion(v)
            else:
                raise ScriptError(f"Dòng {line_no}: tham số '{k}' không hỗ trợ (speed, pitch, volume, emotion).")
        elif f:
            try:
                st.emotion = normalize_emotion(f)
            except ScriptError as e:
                raise ScriptError(f"Dòng {line_no}: {e}") from None
    return st


def parse_script(script: str, resolve_voice: Callable[[str], str | None], default_voice: str) -> list[Segment]:
    segments: list[Segment] = []
    state = _State(voice=default_voice)
    blank_pending = False
    for i, line in enumerate(script.splitlines(), 1):
        if not line.strip():
            blank_pending = bool(segments)
            continue
        text = line
        m = HEADER_RE.match(line)
        if m and not PAUSE_RE.fullmatch(f"[{m.group(1)}]"):
            fields = [f.strip() for f in m.group(1).split("|")]
            is_header = "|" in m.group(1) or "=" in m.group(1) or resolve_voice(fields[0]) is not None
            if is_header:
                state = parse_header(fields, resolve_voice, i)
                text = m.group(2)
            elif m.group(1).strip().lower() not in NONVERBAL_TAGS:
                raise ScriptError(f"Dòng {i}: không có giọng '{fields[0]}'. Gọi list_voices để xem danh sách.")
        if not text.strip():
            continue
        parts = split_pauses(text)
        if not any(isinstance(p, str) for p in parts):
            # A line of only pauses: attach to the previous segment.
            if segments:
                segments[-1].text_parts.extend(parts)
            continue
        segments.append(Segment(voice=state.voice, text_parts=parts, emotion=state.emotion, speed=state.speed,
                                pitch=state.pitch, volume=state.volume, line=i, paragraph_break=blank_pending))
        blank_pending = False
    if not segments:
        raise ScriptError("Kịch bản trống.")
    return segments
