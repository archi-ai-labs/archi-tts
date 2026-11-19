"""Install helpers used by install.sh.

    archi-tts-setup doctor                 # check tools, models, memory
    archi-tts-setup download [--whisper]   # fetch models into the Hugging Face cache
    archi-tts-setup selftest               # render one line per engine
    archi-tts-setup register-desktop [--remove] [--config PATH]
"""

from __future__ import annotations

import os
import sys

# Downloads need the network even if the user exported HF_HUB_OFFLINE; set
# before anything imports huggingface_hub.
if sys.argv[1:2] == ["download"]:
    os.environ["HF_HUB_OFFLINE"] = "0"

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from . import config  # noqa: E402

MODELS = {
    "VieNeu-TTS v3 Turbo": "pnnbao-ump/VieNeu-TTS-v3-Turbo",
    "MOSS audio codec (VieNeu)": "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX",
    "OmniVoice VN": config.OMNIVOICE_MODEL,
}
WHISPER = "openai/whisper-large-v3-turbo"
DESKTOP_CONFIG = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"


def hub_dir() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"


def cached(repo: str) -> bool:
    return (hub_dir() / f"models--{repo.replace('/', '--')}").is_dir()


def server_command() -> str:
    return str(Path(sys.executable).with_name("archi-tts"))


# --- commands -----------------------------------------------------------------

def cmd_doctor(_: argparse.Namespace) -> int:
    ok = True
    print(f"Python      {sys.version.split()[0]} ({sys.executable})")
    from .dsp import find_bin

    for tool in ("ffmpeg", "rubberband"):
        try:
            print(f"{tool:11s} {find_bin(tool)}")
        except RuntimeError as e:
            print(f"{tool:11s} THIẾU — {e}")
            ok = False
    for name, repo in {**MODELS, "Whisper (tùy chọn)": WHISPER}.items():
        mark = "có" if cached(repo) else ("chưa tải" if "Whisper" not in name else "chưa tải (chỉ cần khi add_voice không có transcript)")
        print(f"{name:27s} {mark}")
        ok &= cached(repo) or "Whisper" in name
    mem = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout or 0) / 2**30
    print(f"RAM         {mem:.0f} GB" + ("  (khuyến nghị ≥16 GB)" if mem < 16 else ""))
    print(f"Output      {config.OUTPUT_DIR}")
    return 0 if ok else 1


def cmd_download(args: argparse.Namespace) -> int:
    from huggingface_hub import snapshot_download

    # VieNeu fetches only the files its ONNX/CPU path needs when constructed (~1 GB);
    # a full snapshot of its repo would add ~1 GB of unused variants (gguf, int8, torch).
    t = time.time()
    print("→ VieNeu-TTS v3 Turbo + MOSS codec ...", flush=True)
    from vieneu import Vieneu

    Vieneu()
    print(f"  xong ({time.time() - t:.0f}s)", flush=True)
    repos = {"OmniVoice VN": config.OMNIVOICE_MODEL}
    if args.whisper:
        repos["Whisper large-v3-turbo"] = WHISPER
    for name, repo in repos.items():
        t = time.time()
        print(f"→ {name} ({repo}) ...", flush=True)
        snapshot_download(repo)
        print(f"  xong ({time.time() - t:.0f}s)", flush=True)
    return 0


def cmd_selftest(_: argparse.Namespace) -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import tempfile

    import yaml

    from .engines.omnivoice_engine import OmniVoiceEngine
    from .engines.vieneu_engine import VieNeuEngine
    from .pipeline import Renderer
    from .script import parse_script
    from .voices import VoiceRegistry

    engines = {"vieneu": VieNeuEngine(), "omnivoice": OmniVoiceEngine()}
    t = time.time()

    def render(reg: VoiceRegistry, script: str, name: str):
        res = Renderer(reg, engines).render(parse_script(script, reg.resolve, reg.default), name)
        for p in (res.wav, res.mp3, res.srt):
            if not Path(p).is_file() or Path(p).stat().st_size == 0:
                raise RuntimeError(f"thiếu {p}")
        return res

    # OmniVoice clones the VieNeu line rendered first, so no reference clip has to ship with the repo.
    ref_text = "Xin chào, đây là giọng đọc có sẵn, chạy hoàn toàn trên máy của bạn."
    try:
        reg = VoiceRegistry()
        ref = render(reg, f"[ngoc_huyen] {ref_text}", "selftest_ref")
        data = yaml.safe_load(reg.path.read_text(encoding="utf-8")) or {}
        data.setdefault("voices", {})["selftest_clone"] = {
            "engine": "omnivoice", "name": "selftest clone",
            "refs": {"trung_tinh": {"wav": ref.wav, "text": ref_text}},
        }
        tmp = Path(tempfile.mkdtemp(prefix="archi-tts-selftest-")) / "voices.yaml"
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        res = render(VoiceRegistry(tmp), "[ngoc_huyen] Ngày 15/8/2025, giá tăng 12,5%.\n"
                                         "[selftest_clone] Còn đây là giọng clone, nghe có ổn không nào?", "selftest")
    except Exception as e:  # noqa: BLE001 - report any failure as a failed self-test
        print(f"LỖI: {e}")
        return 1
    print(f"OK: {res.duration_s}s audio trong {time.time() - t:.0f}s → {res.mp3}")
    return 0


def cmd_register_desktop(args: argparse.Namespace) -> int:
    path = Path(args.config).expanduser() if args.config else DESKTOP_CONFIG
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as e:
            print(f"LỖI: {path} không phải JSON hợp lệ ({e}); không sửa.")
            return 1
        backup = path.with_suffix(path.suffix + f".bak-{time.strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(path, backup)
        print(f"Đã sao lưu: {backup}")
    servers = data.setdefault("mcpServers", {})
    if args.remove:
        if servers.pop("archi-tts", None) is None:
            print("Claude Desktop chưa có archi-tts.")
            return 0
    elif args.command:
        servers["archi-tts"] = {"command": str(Path(args.command).expanduser()), "args": []}
    else:
        # The venv's own entry point needs to be told where voices/lexicon live.
        servers["archi-tts"] = {"command": server_command(), "args": [], "env": {"ARCHI_TTS_HOME": str(config.HOME)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(("Đã gỡ" if args.remove else "Đã thêm") + f" archi-tts trong {path}. Khởi động lại Claude Desktop để áp dụng.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="archi-tts-setup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    d = sub.add_parser("download")
    d.add_argument("--whisper", action="store_true", help="also fetch Whisper for add_voice without transcript")
    sub.add_parser("selftest")
    r = sub.add_parser("register-desktop")
    r.add_argument("--remove", action="store_true")
    r.add_argument("--config", help="config file (default: Claude Desktop's)")
    r.add_argument("--command", help="server command (default: this venv's archi-tts); "
                                     "pass bin/archi-tts-mcp from the plugin or repo")
    args = ap.parse_args()
    fn = {"doctor": cmd_doctor, "download": cmd_download, "selftest": cmd_selftest,
          "register-desktop": cmd_register_desktop}[args.cmd]
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
