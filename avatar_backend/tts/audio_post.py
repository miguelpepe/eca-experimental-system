import logging

import numpy as np
import soundfile as sf

logger = logging.getLogger("tts")


# post-process a generated tts wav in place: normalize loudness to a fixed
# target rms and hard-limit peaks. this keeps perceived loudness consistent
# across sentences and across tts providers (f5/omnivoice) and prevents the
# occasional "unusually loud" burst that diffusion tts can produce.
def normalize_audio_file(
    path: str,
    target_rms: float = 0.1,  # target loudness (matches f5 target_rms)
    peak_ceiling: float = 0.97,  # hard peak limit to avoid clipping/bursts
    max_gain: float = 4.0,  # cap boost so near-silent clips are not over-amplified
) -> None:
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception as exc:  # pragma: no cover - defensive, never break the pipeline
        logger.warning("[TTS] normalize skipped (read failed) file=%s err=%s", path, exc)
        return

    if data.size == 0:
        return

    # measure loudness on a mono view (average channels if needed)
    mono = data if data.ndim == 1 else data.mean(axis=1)
    rms = float(np.sqrt(np.mean(np.square(mono))))
    if rms < 1e-6:
        return  # essentially silence, leave untouched

    # loudness normalization toward target rms, but never boost more than max_gain
    gain = min(target_rms / rms, max_gain)
    data = data * gain

    # peak limiter: scale down if any sample exceeds the ceiling
    peak = float(np.max(np.abs(data)))
    if peak > peak_ceiling:
        data = data * (peak_ceiling / peak)

    np.clip(data, -1.0, 1.0, out=data)

    try:
        sf.write(path, data, sr)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[TTS] normalize skipped (write failed) file=%s err=%s", path, exc)
