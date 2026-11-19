"""Web UI for testing voices and generating prompts that drive the archi-tts MCP tools.

Served by the MCP server process itself (see server.main): it shares the loaded models and the
job queue with the MCP tools, so no extra process or extra RAM. Default http://127.0.0.1:8770.
"""

from __future__ import annotations

import logging
import re
import socket
import threading
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from . import config
from .script import Pause, Segment, ScriptError, normalize_emotion, parse_script, slug, split_pauses
from .runtime import engines, jobs, registry, renderer
from .text import chunk_text, load_lexicon

log = logging.getLogger("archi-tts")

STATIC = Path(__file__).parent / "web_static"
SPEAK_MAX_CHARS = 800


# --- prompt building (pure, unit-tested) ---------------------------------------------------------

def _fmt_num(v: float, signed: bool) -> str:
    s = f"{v:g}"
    return f"+{s}" if signed and v > 0 else s


def script_header(voice: str, emotion: str | None = None, speed: float = 1.0, pitch: float = 0.0,
                  volume: float = 0.0) -> str:
    """Script line header for one voice config, defaults omitted: [giong_clone | vui | speed=1.1]."""
    fields = [voice]
    if emotion and emotion != "trung_tinh":
        fields.append(emotion)
    if abs(speed - 1.0) > 1e-9:
        fields.append(f"speed={_fmt_num(speed, False)}")
    if abs(pitch) > 1e-9:
        fields.append(f"pitch={_fmt_num(pitch, True)}")
    if abs(volume) > 1e-9:
        fields.append(f"volume={_fmt_num(volume, True)}")
    return "[" + " | ".join(fields) + "]"


def build_prompt(configs: list[dict] | None = None, text: str = "", task: str = "", output_name: str = "",
                 script: str = "") -> dict:
    """configs: [{voice, emotion, speed, pitch, volume, role?}]. Returns script lines + a Claude prompt.
    With `script`, voices come from the script itself and the script is used verbatim."""
    from_script = bool(script.strip())
    if from_script:
        seen: dict[tuple, dict] = {}
        for s in parse_script(script, registry.resolve, registry.default):
            key = (s.voice, s.emotion, s.speed, s.pitch, s.volume)
            seen.setdefault(key, {"voice": s.voice, "emotion": s.emotion, "speed": s.speed, "pitch": s.pitch,
                                  "volume": s.volume})
        configs = list(seen.values())
    if not configs:
        raise ScriptError("Chọn ít nhất một giọng.")
    norm = []
    for c in configs:
        vid = registry.resolve(c.get("voice") or "")
        if not vid:
            raise ScriptError(f"Không có giọng '{c.get('voice')}'.")
        v = registry.voices[vid]
        emo = normalize_emotion(c.get("emotion")) if v.engine == "omnivoice" else None
        norm.append({"voice": vid, "emotion": emo, "speed": float(c.get("speed", 1.0)),
                     "pitch": float(c.get("pitch", 0.0)), "volume": float(c.get("volume", 0.0)),
                     "role": (c.get("role") or "").strip()})

    headers = [script_header(c["voice"], c["emotion"], c["speed"], c["pitch"], c["volume"]) for c in norm]
    sample = text.strip() or "Xin chào, đây là đoạn đọc thử."
    single = not from_script and len(norm) == 1 and len(sample) <= SPEAK_MAX_CHARS
    if from_script:
        script_lines = script.strip().splitlines()
    elif len(norm) == 1:
        script_lines = [f"{headers[0]} {sample}"]
    else:
        # Hand sentences to roles in turn so the example script is renderable as-is.
        sents = [s for s in re.split(r"(?<=[.!?…])\s+", sample) if s.strip()]
        if len(sents) < len(norm):
            sents += [sents[-1]] * (len(norm) - len(sents))
        script_lines = [f"{headers[i % len(norm)]} {s}" for i, s in enumerate(sents)]
    first = f"{task.strip().rstrip('.')}.\n\n" if task.strip() else ""
    if single:
        c = norm[0]
        opts = [f"giọng {c['voice']}"]
        if c["emotion"] and c["emotion"] != "trung_tinh":
            opts.append(f"cảm xúc {c['emotion']}")
        for k in ("speed", "pitch", "volume"):
            if abs(c[k] - (1.0 if k == "speed" else 0.0)) > 1e-9:
                opts.append(f"{k}={_fmt_num(c[k], k != 'speed')}")
        prompt = f"{first}Dùng archi-tts đọc đoạn sau, {', '.join(opts)}. Gửi mình file MP3.\n\n{sample}\n"
    else:
        body = "\n".join(script_lines)
        prompt = f"{first}Dùng archi-tts đọc kịch bản sau. Gửi mình file MP3.\n\n```\n{body}\n```\n"
    return {"headers": headers, "script": "\n".join(script_lines), "prompt": prompt, "mode": "speak" if single else "script"}


# --- HTTP ---------------------------------------------------------------------------------------

def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


def _clamp(v, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _ref_url(p: Path) -> str | None:
    try:
        return "/files/voices/" + str(p.resolve().relative_to(config.VOICES_DIR.resolve()))
    except ValueError:
        return None


def _out_url(path: str) -> str | None:
    if not path:
        return None
    try:
        return "/files/out/" + str(Path(path).resolve().relative_to(config.OUTPUT_DIR.resolve()))
    except ValueError:
        return None


def _job_dict(job) -> dict:
    d = job.as_dict()
    d["done"], d["total"] = job.done, job.total
    r = d.get("result")
    if r:
        r["wav_url"], r["mp3_url"], r["srt_url"] = _out_url(r["wav"]), _out_url(r["mp3"]), _out_url(r["srt"])
    return d


async def index(_: Request) -> Response:
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


async def api_voices(_: Request) -> Response:
    registry.reload()
    out = []
    for v in registry.voices.values():
        d = v.describe()
        d["emotions"] = sorted(v.refs) if v.engine == "omnivoice" else []
        d["refs"] = {e: {"url": _ref_url(r.wav), "text": r.text} for e, r in v.refs.items()}
        sample = config.VOICES_DIR / "samples" / f"{v.id}.mp3"
        d["sample"] = _ref_url(sample) if sample.exists() else None
        out.append(d)
    loaded = {k: e.loaded for k, e in engines.items()}
    return JSONResponse({"default_voice": registry.default, "voices": out, "engines_loaded": loaded})


async def api_check(request: Request) -> Response:
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return _err("Văn bản trống.")
    return JSONResponse({e: spoken_preview(text, e) for e in ("vieneu", "omnivoice")})


def spoken_preview(text: str, engine: str) -> str:
    """What the pipeline actually sends to an engine: pauses split out, emphasis and lexicon applied."""
    lex = load_lexicon(engine=engine)
    out = []
    for part in split_pauses(text):
        if isinstance(part, Pause):
            out.append(f"⏸ {part.seconds:g}s")
        else:
            out.extend(c.norm for c in chunk_text(part, lex))
    return " ‖ ".join(out)


async def api_speak(request: Request) -> Response:
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return _err("Văn bản trống.")
    if len(text) > SPEAK_MAX_CHARS:
        return _err(f"Dài hơn {SPEAK_MAX_CHARS} ký tự; dùng tab Kịch bản.")
    try:
        registry.reload()
        v = registry.get(body.get("voice"))
        emotion = normalize_emotion(body.get("emotion")) if v.engine == "omnivoice" else None
        seg = Segment(voice=v.id, text_parts=split_pauses(text), emotion=emotion,
                      speed=_clamp(body.get("speed"), 0.5, 2.0, 1.0), pitch=_clamp(body.get("pitch"), -6, 6, 0.0),
                      volume=_clamp(body.get("volume"), -12, 12, 0.0), line=1)
    except ScriptError as e:
        return _err(str(e))
    name = f"web_{v.id}_{emotion or 'base'}_{int(time.time() * 1000) % 10**9}"
    job = jobs.submit(name, lambda p: renderer.render([seg], name, p, formats=("wav", "srt")))
    return JSONResponse(_job_dict(job))


async def api_script(request: Request) -> Response:
    body = await request.json()
    try:
        registry.reload()
        segments = parse_script(body.get("script") or "", registry.resolve, registry.default)
    except ScriptError as e:
        return _err(str(e))
    name = slug(body.get("output_name") or "") or f"web_script_{int(time.time())}"
    job = jobs.submit(name, lambda p: renderer.render(segments, name, p))
    return JSONResponse(_job_dict(job) | {"segments": len(segments)})


async def api_job(request: Request) -> Response:
    job = jobs.get(request.path_params["job_id"])
    if not job:
        return _err("Không có job này (server đã khởi động lại?).", 404)
    d = _job_dict(job)
    d["engines_loaded"] = {k: e.loaded for k, e in engines.items()}
    return JSONResponse(d)


async def api_prompt(request: Request) -> Response:
    body = await request.json()
    try:
        registry.reload()
        return JSONResponse(build_prompt(body.get("configs") or [], body.get("text") or "",
                                         body.get("task") or "", body.get("output_name") or "",
                                         body.get("script") or ""))
    except ScriptError as e:
        return _err(str(e))


def _safe_file(base: Path, rel: str) -> Path | None:
    base = base.resolve()
    p = (base / rel).resolve()
    if base not in p.parents or not p.is_file():
        return None
    return p


async def files(request: Request) -> Response:
    base = {"out": config.OUTPUT_DIR, "voices": config.VOICES_DIR}.get(request.path_params["root"])
    p = _safe_file(base, request.path_params["path"]) if base else None
    if not p or p.suffix.lower() not in (".wav", ".mp3", ".srt", ".flac", ".ogg"):
        return _err("Không có file.", 404)
    media = "text/plain; charset=utf-8" if p.suffix == ".srt" else None
    return FileResponse(p, media_type=media)


app = Starlette(routes=[
    Route("/", index),
    Route("/api/voices", api_voices),
    Route("/api/check", api_check, methods=["POST"]),
    Route("/api/speak", api_speak, methods=["POST"]),
    Route("/api/script", api_script, methods=["POST"]),
    Route("/api/jobs/{job_id}", api_job),
    Route("/api/prompt", api_prompt, methods=["POST"]),
    Route("/files/{root}/{path:path}", files),
])


def start_in_background(host: str = "127.0.0.1", port: int = 8770) -> bool:
    """Serve the web UI on a daemon thread of the current (MCP server) process.
    Skips quietly when the port is taken, e.g. by another Claude session's archi-tts."""
    if port <= 0:
        return False
    with socket.socket() as s:
        try:
            s.bind((host, port))
        except OSError:
            log.warning("Web thử giọng: cổng %d đang bận, bỏ qua (có thể process archi-tts khác đã mở).", port)
            return False
    import uvicorn

    # log_config=None: keep uvicorn off stdout, which carries the MCP stdio protocol.
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None, access_log=False,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True, name="web-ui").start()
    log.info("Web thử giọng: http://%s:%d", host, port)
    return True
