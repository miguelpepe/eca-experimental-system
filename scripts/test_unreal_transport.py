"""Check the running Unreal session against a local WebSocket stub, without AI inference."""

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess

import websockets


async def check(engine_root):
    root = Path(__file__).resolve().parents[1]
    project = root / "unreal/METAHUMAN_5_5.uproject"
    editor = engine_root / "Engine/Binaries/Win64/UnrealEditor-Cmd.exe"
    if not editor.is_file():
        raise RuntimeError("UE 5.6 not found; pass --engine-root or set UE_ROOT.")
    audio_path = root / "voices/warmup.wav"
    expected_audio = audio_path.read_bytes()
    received = []
    validation = root / "unreal/Saved/Validation"
    validation.mkdir(parents=True, exist_ok=True)
    log_path = validation / "eca-transport.log"

    async def handler(socket):
        async for raw in socket:
            message = json.loads(raw)
            if message["type"] != "request":
                continue
            assert base64.b64decode(message["audio_b64"], validate=True) == expected_audio
            request_id = message["request_id"]
            assert isinstance(request_id, str) and request_id
            received.append(request_id)
            # an old request's error must not cancel the current response
            await socket.send(json.dumps({"type": "error", "request_id": "stale-request"}))
            await socket.send(json.dumps({
                "type": "done", "request_id": request_id,
                "response": "transport verified",
            }))

    args = [str(editor), str(project), "/Game/ECA/ECA_Demo", "-game",
            "-nullrhi", "-nosound", "-unattended", "-nosplash", "-RenderOffscreen",
            "-NoShaderCompile", "-ECAPublicProfile", "-ECAExitWhenDone",
            "-ECAEndpoint=http://127.0.0.1:18765", f"-ECAAudioFile={audio_path}",
            "-stdout", "-FullStdOutLogOutput"]
    async with websockets.serve(handler, "127.0.0.1", 18765, max_size=4 * 1024 * 1024):
        with log_path.open("wb") as output:
            process = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                code = await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=90)
            except BaseException:
                process.kill()
                process.wait()
                raise

    log = log_path.read_text(encoding="utf-8", errors="replace")
    assert code == 0, f"Unreal exit {code}; see {log_path}"
    assert len(received) == 1, f"Expected one request, got {len(received)}"
    assert "ECA_SESSION_READY:" in log and "input=SpaceBar" in log
    assert "character=/Game/MetaHumans/Keiji/BP_Keiji.BP_Keiji_C" in log
    assert "ECA_RESPONSE_DONE: transport verified" in log
    report = {
        "passed": True, "requests": len(received),
        "scope": "Game startup, input binding, WAV upload, request IDs and stale-event filtering; no AI, microphone or facial inference.",
    }
    (validation / "eca-transport.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, default=Path(os.environ.get(
        "UE_ROOT", r"C:\Program Files\Epic Games\UE_5.6")))
    asyncio.run(check(parser.parse_args().engine_root))
