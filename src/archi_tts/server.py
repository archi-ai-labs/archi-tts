"""archi-tts MCP server: Vietnamese TTS for video dubbing.

    archi-tts                     # stdio (Claude Code / Claude Desktop)
    archi-tts --http --port 8766  # streamable HTTP for other clients

Both modes also serve the voice-testing web UI at http://127.0.0.1:8770 from this same process
(shared models and job queue). --web-port / ARCHI_TTS_WEB_PORT changes it, 0 turns it off.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path as _Path


def _offline_if_cached() -> None:
    """Stay off the network once the models are on disk (must run before
    huggingface_hub is imported). Set HF_HUB_OFFLINE=0 to allow downloads."""
    hub = _Path(os.environ.get("HF_HUB_CACHE") or _Path(os.environ.get("HF_HOME", _Path.home() / ".cache/huggingface")) / "hub")
    needed = ["pnnbao-ump--VieNeu-TTS-v3-Turbo", "OpenMOSS-Team--MOSS-Audio-Tokenizer-Nano-ONNX"]
    if importlib.util.find_spec("omnivoice"):  # full install only
        needed.append("models--" + os.environ.get("ARCHI_TTS_OMNIVOICE_MODEL", "danhcao/v-omnivoice").replace("/", "--"))
    if all((hub / (n if n.startswith("models--") else f"models--{n}")).is_dir() for n in needed):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")


_offline_if_cached()

import argparse  # noqa: E402
import asyncio
import logging
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import config
from .pipeline import build_plan
from .script import Segment, ScriptError, normalize_emotion, parse_script, split_pauses
from .runtime import engines, jobs, registry, renderer
from .text import load_lexicon, normalize, save_lexicon_entry

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("archi-tts")

SCRIPT_GUIDE = """\
Kịch bản lồng tiếng — mỗi dòng một lượt nói:

    [giọng | cảm_xúc | speed=1.1 | pitch=-1 | volume=+2] Văn bản cần đọc.
    Dòng không có [..] ở đầu thì giữ giọng và cài đặt của dòng trước.
    Dòng trống = ngắt đoạn (nghỉ ~0.9s). Giữa các dòng nghỉ ~0.45s.

Trong câu:
    [ngắt 0.8s]   chèn khoảng lặng (hoặc [ngắt 500ms])
    *từ*          nhấn từ (ngắt nhẹ trước từ đó)
    [cười] [thở dài]  âm phi ngôn ngữ (thử nghiệm)

Tham số (đều tùy chọn): cảm_xúc = trung_tinh | vui | buon | tuc_gian (chỉ giọng clone);
speed 0.5–2.0; pitch -6..+6 nửa cung; volume -12..+12 dB.
Số, ngày, %, đơn vị, viết tắt (TP.HCM...) tự đọc thành chữ; từ tiếng Anh lạ thì thêm bằng add_lexicon_entry.

Ví dụ:
    [ngoc_huyen] Hôm nay chúng ta tìm hiểu về chip M4.
    [mai_anh | speed=1.1] Nó nhanh *gấp đôi* thế hệ trước! [ngắt 0.6s]
    [giong_clone | vui] Cảm xúc chỉ có ở giọng clone (thêm bằng add_voice).
    [pham_tuyen | pitch=-1] Giá bán dự kiến 25 triệu đồng.
"""

mcp = MCPServer(
    "archi-tts",
    instructions=(
        "Local Vietnamese text-to-speech for video dubbing (Northern accent). Output files land in "
        f"{config.OUTPUT_DIR}. Use list_voices first, then speak for a short line or synthesize_script "
        "for a multi-voice script (returns a job; poll job_status). Script syntax is in the "
        "synthesize_script description and the 'script_guide' prompt."
    ),
)


def _resolve(name: str) -> str | None:
    return registry.resolve(name)


@mcp.tool()
async def list_voices() -> dict:
    """List available voices. engine=vieneu: built-in presets (fast, fixed reading style, no emotion
    switching). engine=omnivoice: cloned voices (slower, better tone accuracy, one reference clip per
    emotion: trung_tinh, vui, buon, tuc_gian)."""
    registry.reload()
    full = config.has_omnivoice()
    voices = []
    for v in registry.voices.values():
        d = v.describe()
        if v.engine == "omnivoice" and not full:
            d["available"] = False
        voices.append(d)
    out = {
        "edition": config.edition(),
        "default_voice": registry.default,
        "voices": voices,
        "speed_hint": "Trên M1 Pro, 15 phút audio: vieneu ~4–5 phút, omnivoice ~40 phút.",
    }
    if not full:
        out["note"] = config.full_hint()
    return out


@mcp.tool()
async def speak(text: str, voice: str | None = None, emotion: str | None = None, speed: float = 1.0,
                pitch: float = 0.0, volume: float = 0.0, output_name: str | None = None) -> dict:
    """Synthesize a short passage (up to ~800 characters) with one voice and return file paths
    (WAV 48 kHz, MP3, SRT). Inline [ngắt 0.8s], *emphasis* and [cười] are supported.
    For longer or multi-voice text use synthesize_script.

    Args:
        text: Vietnamese text.
        voice: voice id or name from list_voices (default voice if omitted).
        emotion: trung_tinh | vui | buon | tuc_gian (cloned voices only).
        speed: 0.5–2.0. pitch: semitones -6..6. volume: dB -12..12.
        output_name: folder/file name for the result.
    """
    if len(text) > 800:
        return {"error": "Văn bản dài hơn 800 ký tự; dùng synthesize_script (chạy nền, theo dõi bằng job_status)."}
    try:
        registry.reload()
        v = registry.get(voice)
        seg = Segment(voice=v.id, text_parts=split_pauses(text), emotion=normalize_emotion(emotion),
                      speed=_clamp(speed, 0.5, 2.0), pitch=_clamp(pitch, -6, 6), volume=_clamp(volume, -12, 12), line=1)
        build_plan([seg], registry)  # fail fast (e.g. a cloned voice in the lite install)
    except ScriptError as e:
        return {"error": str(e)}
    job = jobs.submit(output_name or "speak", lambda p: renderer.render([seg], output_name, p))
    await asyncio.to_thread(job.event.wait, 50)
    out = job.as_dict()
    if job.status in ("queued", "running"):
        out["hint"] = "Đang xếp hàng sau job khác. Gọi job_status với job_id này để lấy kết quả."
    return out


@mcp.tool(description="Render a multi-voice dubbing script into one audio file + SRT subtitles. Runs in the "
                      "background: returns a job_id at once (or the finished result if it completes within "
                      "wait_seconds). Poll job_status until status is 'done'.\n\n" + SCRIPT_GUIDE)
async def synthesize_script(script: str, output_name: str | None = None, wait_seconds: float = 30) -> dict:
    try:
        registry.reload()
        segments = parse_script(script, _resolve, registry.default)
        build_plan(segments, registry)  # fail fast (e.g. a cloned voice in the lite install)
    except ScriptError as e:
        return {"error": str(e)}
    job = jobs.submit(output_name or "script", lambda p: renderer.render(segments, output_name, p))
    await asyncio.to_thread(job.event.wait, max(0.0, min(wait_seconds, 50)))
    out = job.as_dict()
    if job.status in ("queued", "running"):
        out["hint"] = "Đang chạy nền. Gọi job_status với job_id này để xem tiến độ."
    return out


@mcp.tool()
async def job_status(job_id: str, wait_seconds: float = 0) -> dict:
    """Progress of a synthesize_script job; when status is 'done', result holds the WAV/MP3/SRT paths.
    wait_seconds (max 50) blocks until the job finishes or the time runs out."""
    job = jobs.get(job_id)
    if not job:
        return {"error": f"Không có job {job_id} (server khởi động lại sẽ mất danh sách job; file đã xuất vẫn còn)."}
    if wait_seconds > 0:
        await asyncio.to_thread(job.event.wait, min(wait_seconds, 50))
    return job.as_dict()


@mcp.tool()
async def preview_voice(voice: str, emotion: str | None = None, text: str | None = None) -> dict:
    """Render a short sample sentence with a voice so the user can listen before using it."""
    text = text or "Xin chào, đây là giọng đọc thử cho video của bạn. Hôm nay trời Hà Nội se lạnh, rất hợp để đi dạo."
    v = registry.get(voice) if registry.resolve(voice) else None
    if not v:
        return {"error": f"Không có giọng '{voice}'."}
    return await speak(text, voice=v.id, emotion=emotion, output_name=f"preview_{v.id}_{emotion or 'trung_tinh'}")


@mcp.tool()
async def add_lexicon_entry(word: str, reading: str, engine: str | None = None) -> dict:
    """Teach how to read a word or abbreviation, e.g. word="Netflix", reading="nét-phlích".
    engine: "vieneu" or "omnivoice" to set it for one engine only (VieNeu often reads English
    words like GPU better left as-is; OmniVoice needs a Vietnamese spelling, hyphens help: "ây-ai").
    All-caps keys match case-sensitively; other keys match case-insensitively. Affects new syntheses."""
    if not word.strip() or not reading.strip():
        return {"error": "word và reading không được trống."}
    if engine not in (None, "vieneu", "omnivoice"):
        return {"error": "engine phải là vieneu, omnivoice hoặc bỏ trống (cả hai)."}
    save_lexicon_entry(word.strip(), reading.strip(), engine)
    return {"ok": True, "word": word, **_readings(f"Ví dụ: {word}.")}


def _readings(text: str) -> dict:
    return {f"spoken_{e}": normalize(text, load_lexicon(engine=e)) for e in ("vieneu", "omnivoice")}


@mcp.tool()
async def check_text(text: str) -> dict:
    """Show how text will be read by each engine after normalization (numbers, dates,
    abbreviations, lexicon) without synthesizing. Use it to catch misreadings before a long render."""
    return _readings(text)


@mcp.tool()
async def add_voice(voice_id: str, audio_path: str, transcript: str | None = None, emotion: str = "trung_tinh",
                    name: str | None = None, gender: str = "") -> dict:
    """Create or extend a cloned (OmniVoice) voice from a 3–10 s clean, single-speaker clip.
    Call again with the same voice_id and another emotion (vui, buon, tuc_gian) to add emotion clips.
    transcript: exact words spoken in the clip (strongly recommended; otherwise Whisper transcribes it).
    Only clone voices you have the right to use."""
    if not config.has_omnivoice():
        return {"error": config.full_hint()}
    transcribed = False
    try:
        registry.validate_clip(audio_path)
        if not transcript:
            try:
                transcript = await asyncio.to_thread(engines["omnivoice"].transcribe, str(Path(audio_path).expanduser()))
            except OSError as e:  # Whisper not cached while offline
                return {"error": f"Không nhận dạng được lời trong clip ({e}). Hãy truyền transcript, hoặc chạy "
                                 "server với HF_HUB_OFFLINE=0 một lần để tải Whisper."}
            transcribed = True
        v = registry.add_clone(voice_id, audio_path, transcript, emotion, name, gender)
    except ScriptError as e:
        return {"error": str(e)}
    out = {"ok": True, "voice": v.describe(), "transcript": transcript}
    if transcribed:
        out["hint"] = ("Transcript do Whisper nhận dạng; nếu sai chữ nào, gọi lại add_voice với transcript đúng "
                       "để giọng clone chuẩn hơn.")
    return out


@mcp.prompt()
def script_guide() -> str:
    """Syntax for dubbing scripts used by synthesize_script."""
    return SCRIPT_GUIDE


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def main() -> None:
    ap = argparse.ArgumentParser(prog="archi-tts")
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--preload", action="store_true", help="load both models at start-up")
    ap.add_argument("--web-port", type=int, default=int(os.environ.get("ARCHI_TTS_WEB_PORT", "8770")),
                    help="voice-testing web UI port, served from this process (0 = off)")
    args = ap.parse_args()
    from .web import start_in_background

    start_in_background(args.host, args.web_port)
    if args.preload:
        for e in engines.values():
            e.ensure_loaded()
    if args.http:
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
