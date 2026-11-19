"""End-to-end check through the real MCP stdio transport.

    uv run python scripts/mcp_smoke.py
"""

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = """[ngoc_huyen] Chào mừng các bạn quay trở lại với kênh. Hôm nay, ngày 15/8/2025, chúng ta nói về chip AI.
[{nu} | vui | speed=1.05] Trời ơi, nó nhanh *gấp đôi* thế hệ trước luôn! [ngắt 0.6s]
[{nam} | buon] Tiếc là giá bán lên tới 25 triệu đồng.

[pham_tuyen | pitch=-1 | volume=+1] Vậy có nên mua hay không? Hãy cùng xem tiếp nhé.
"""


def payload(res) -> dict:
    if getattr(res, "structured_content", None):
        sc = res.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(res.content[0].text)


async def call(s: ClientSession, name: str, **args) -> dict:
    t = time.time()
    out = payload(await s.call_tool(name, args))
    print(f"\n## {name} ({time.time() - t:.1f}s)\n{json.dumps(out, ensure_ascii=False, indent=1)[:1500]}", flush=True)
    return out


async def wait_job(s: ClientSession, out: dict) -> dict:
    while out.get("status") in ("queued", "running"):
        out = await call(s, "job_status", job_id=out["job_id"], wait_seconds=45)
    return out


async def main() -> None:
    # ARCHI_TTS_SMOKE_CMD lets the same test drive the plugin launcher (bin/archi-tts-mcp).
    cmd = os.environ.get("ARCHI_TTS_SMOKE_CMD", str(ROOT / ".venv/bin/archi-tts"))
    params = StdioServerParameters(command=cmd, args=[], cwd=str(ROOT), env=dict(os.environ))
    async with stdio_client(params, errlog=open(ROOT / "scripts/mcp_smoke.server.log", "w")) as streams:
        async with ClientSession(*streams[:2]) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            print("tools:", tools)
            voices = await call(s, "list_voices")
            assert len(voices["voices"]) >= 15
            # Clone voices are the user's own (add_voice); fall back to built-in ones without them.
            clones = [v["id"] for v in voices["voices"] if v["engine"] == "omnivoice"] + ["mai_anh", "hai_dang"]
            script = SCRIPT.format(nu=clones[0], nam=clones[1])
            await call(s, "check_text", text="Ngày 15/8/2025, iPhone 16 Pro giá 25 triệu, GPU mạnh hơn 30%.")
            sp = await call(s, "speak", text="Xin chào, đây là giọng Ngọc Huyền.", voice="Ngọc Huyền", output_name="smoke_speak")
            assert sp["status"] == "done", sp

            r1 = await wait_job(s, await call(s, "synthesize_script", script=script, output_name="smoke_script"))
            assert r1["status"] == "done", r1
            r2 = await wait_job(s, await call(s, "synthesize_script", script=script, output_name="smoke_script"))
            assert r2["result"]["synthesized"] == 0, "re-render should come fully from cache"
            edited = script.replace("25 triệu", f"{random.randint(31, 999)} triệu")  # fresh line every run
            r3 = await wait_job(s, await call(s, "synthesize_script", script=edited, output_name="smoke_script_edit"))
            assert r3["result"]["synthesized"] == 1, r3["result"]
            bad = await call(s, "synthesize_script", script="[khong_ton_tai] xin chào")
            assert "error" in bad
            print("\nOK", file=sys.stderr)


asyncio.run(main())
