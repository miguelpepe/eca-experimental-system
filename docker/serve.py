import os
import sys
from pathlib import Path

from check_gpu import cuda_environment


def serve():
    cuda_environment()
    if os.environ.get("ECA_CUDA_READY") != "1":
        os.environ["ECA_CUDA_READY"] = "1"
        os.execv(sys.executable, [sys.executable, *sys.argv])

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from dotenv import load_dotenv

    runtime = Path(os.environ["ECA_RUNTIME_ENV"])
    if not runtime.is_file():
        raise RuntimeError("Backend setup is missing. Run Setup.bat or scripts/setup.ps1 again.")
    load_dotenv(runtime, override=True)

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("NVIDIA GPU unavailable. Check Docker's WSL 2 backend and GPU driver.")

    from avatar_backend.config import ENHANCED, PROJECT_ROOT
    from avatar_backend.config.conditions import build_condition
    if os.environ.get("ECA_PRELOAD_MODELS", "true").lower() == "true":
        from avatar_backend.stt.whisper_service import stt_with_whisper
        from avatar_backend.tts.router import synthesize_speech

        condition = build_condition(ENHANCED)
        print("Preparing Whisper and TTS; the first start downloads the models.", flush=True)
        stt_with_whisper(str(PROJECT_ROOT / "voices/warmup.wav"), condition["stt"])
        audio, _ = synthesize_speech("Hello.", "en", condition["tts"])
        Path(audio).unlink(missing_ok=True)
        print("Speech models ready.", flush=True)

    import uvicorn
    # keep the preloaded singleton models in this process
    from avatar_backend.main import app
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    serve()
