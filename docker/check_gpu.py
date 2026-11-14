import os
import sysconfig
from pathlib import Path


def cuda_environment():
    # CTranslate2 also needs the CUDA libraries installed by PyTorch
    root = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    libraries = [str(path) for path in root.glob("*/lib")]
    os.environ["LD_LIBRARY_PATH"] = ":".join(libraries + [os.environ.get("LD_LIBRARY_PATH", "")])


if __name__ == "__main__":
    cuda_environment()
    # use a fresh process so the loader sees LD_LIBRARY_PATH
    import subprocess
    subprocess.run(["python", "-c", (
        "import torch, ctranslate2; "
        "assert torch.cuda.is_available(), 'PyTorch cannot access the NVIDIA GPU'; "
        "assert ctranslate2.get_cuda_device_count() > 0, 'Whisper cannot access CUDA'; "
        "print('GPU ready:', torch.cuda.get_device_name(0))"
    )], check=True)
