"""Long-job check through MCP stdio, in an isolated ARCHI_TTS_HOME/OUTPUT:
add_voice (with and without transcript), then a ~5-minute 3-voice script.
Reports per-chunk generation-time drift and the server's peak memory.

    uv run python scripts/long_check.py <clip_with_text.wav> "<its transcript>" <clip2.wav>
"""

import asyncio
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

PARA = [
    "Hà Nội vào thu là lúc thành phố đẹp nhất trong năm. Buổi sáng, sương mỏng phủ trên mặt hồ Gươm, những hàng cây bên đường bắt đầu chuyển sang màu vàng nhạt.",
    "Người ta thấy những gánh hàng rong chở đầy hoa cúc họa mi đi qua các con phố cổ, để lại một mùi hương rất nhẹ.",
    "Ở góc phố Hàng Bông, ông cụ bán cốm vẫn ngồi đó như mấy chục năm nay, gói từng nắm cốm xanh trong lá sen.",
    "Buổi trưa, nắng trở nên vàng hơn, trong hơn, không còn gay gắt như những ngày hè. Học sinh tan trường ríu rít trên vỉa hè.",
    "Chiều xuống, gió hồ Tây thổi lồng lộng, những đôi bạn trẻ ngồi bên bờ kè ngắm hoàng hôn đỏ rực cuối trời.",
]
DIALOG = [
    ("moi_nu", "vui", "Anh ơi, cuối tuần này mình đi Ba Vì đi, nghe nói đang mùa hoa dã quỳ đẹp lắm!"),
    ("moi_nam", "trung_tinh", "Ừ, nhưng dự báo thời tiết bảo có mưa đấy em."),
    ("moi_nu", "buon", "Thế thì tiếc quá, em mong chuyến đi này lâu lắm rồi."),
    ("moi_nam", "tuc_gian", "Anh đã nói bao nhiêu lần rồi, xem thời tiết trước khi lên kế hoạch chứ!"),
    ("moi_nu", None, "Thôi hai người đừng cãi nhau nữa, mình đi Tam Đảo cũng được mà."),
    ("moi_nam", None, "Ngày 15/8/2025, giá vé tăng 12,5%, khoảng 250.000 đồng một người."),
]


def build_script() -> str:
    lines = []
    # Each round prefixes every line differently so no chunk repeats (and hits the cache).
    openers = ["Lần thứ nhất,", "Lần thứ hai,", "Lần thứ ba,", "Lần thứ tư,", "Lần thứ năm,"]
    for rnd, op in enumerate(openers):
        lines.append(f"[ngoc_huyen] Phần {rnd + 1}. " + " ".join(f"{op} {p[0].lower()}{p[1:]}" for p in PARA))
        lines.append("")
        for v, emo, text in DIALOG:
            lines.append(f"[{v}{' | ' + emo if emo else ''}] {op} {text[0].lower()}{text[1:]}")
        lines.append("[ngoc_huyen] Các ứng dụng AI và GPU, chiếc iPhone 16 Pro giá 25 triệu đồng.")
        lines.append("")
    return "\n".join(lines)


def payload(res) -> dict:
    sc = getattr(res, "structured_content", None)
    if sc:
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(res.content[0].text)


def footprint(pid: int) -> str:
    out = subprocess.run(["vmmap", "-summary", str(pid)], capture_output=True, text=True).stdout
    return " | ".join(l.strip() for l in out.splitlines() if l.startswith("Physical footprint"))


async def main(clip1: str, text1: str, clip2: str) -> None:
    home = Path(tempfile.mkdtemp(prefix="archi_home_"))
    shutil.copytree(ROOT / "voices", home / "voices")
    shutil.copy(ROOT / "lexicon.yaml", home / "lexicon.yaml")
    env = {**os.environ, "ARCHI_TTS_HOME": str(home), "ARCHI_TTS_OUTPUT": str(home / "out")}
    # Reuse the real synthesis cache so earlier runs aren't redone? No: start clean to time everything.
    params = StdioServerParameters(command=str(ROOT / ".venv/bin/archi-tts"), args=[], cwd=str(ROOT), env=env)
    async with stdio_client(params, errlog=open(ROOT / "scripts/long_check.server.log", "w")) as streams:
        async with ClientSession(*streams[:2]) as s:
            await s.initialize()
            pid = int(subprocess.run(["pgrep", "-n", "-f", "bin/archi-tts"], capture_output=True, text=True).stdout)

            t = time.time()
            r = payload(await s.call_tool("add_voice", {"voice_id": "moi_nu", "audio_path": clip1, "transcript": text1,
                                                        "name": "Mới (nữ)", "gender": "nữ"}))
            print("add_voice with transcript:", json.dumps(r, ensure_ascii=False)[:300], f"{time.time() - t:.1f}s")
            t = time.time()
            r = payload(await s.call_tool("add_voice", {"voice_id": "moi_nam", "audio_path": clip2, "gender": "nam"}))
            print("add_voice auto-transcript:", json.dumps(r, ensure_ascii=False)[:400], f"{time.time() - t:.1f}s")
            print("footprint after add_voice:", footprint(pid))

            script = build_script()
            t0 = time.time()
            job = payload(await s.call_tool("synthesize_script", {"script": script, "output_name": "long_check",
                                                                  "wait_seconds": 5}))
            print("submitted:", {k: job.get(k) for k in ("job_id", "status", "progress", "hint")})
            while job.get("status") in ("queued", "running"):
                job = payload(await s.call_tool("job_status", {"job_id": job["job_id"], "wait_seconds": 45}))
                print(f"  {time.time() - t0:6.0f}s", job.get("status"), job.get("progress"), "eta", job.get("eta_s"),
                      flush=True)
            print("footprint at end:", footprint(pid))
            res = job["result"]
            print(json.dumps({k: res[k] for k in ("duration_s", "chunks", "elapsed_s", "voices", "warnings")},
                             ensure_ascii=False))

    man = json.loads((home / "out" / "long_check" / "manifest.json").read_text())["chunks"]
    for eng, ids in [("vieneu", {"ngoc_huyen"}), ("omnivoice", {"moi_nu", "moi_nam"})]:
        rows = [c for c in man if c["voice"] in ids and not c["cached"]]
        rtf = [c["gen_s"] / (c["end"] - c["start"]) for c in rows]
        third = max(1, len(rtf) // 3)
        print(f"{eng}: {len(rows)} chunks, RTF first third {statistics.median(rtf[:third]):.2f}, "
              f"last third {statistics.median(rtf[-third:]):.2f}, max {max(rtf):.2f}")
    print("output:", home / "out" / "long_check")


asyncio.run(main(*sys.argv[1:4]))
