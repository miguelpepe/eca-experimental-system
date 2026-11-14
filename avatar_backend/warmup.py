# avatar_backend/warmup.py

import time
import logging

from avatar_backend.config import ENHANCED, WARMUP, PROJECT_ROOT
from avatar_backend.stt.whisper_service import stt_with_whisper
from avatar_backend.llm.openwebui_client import stream_llm
from avatar_backend.tts.router import synthesize_speech
from avatar_backend.config.conditions import build_condition

logger = logging.getLogger("warmup")

# warmup audio files for whisper
WARMUP_EN = PROJECT_ROOT / "voices" / "warmup.wav"
WARMUP_DE = PROJECT_ROOT / "voices" / "warmup-de.wav"


# warm up stt
def _warm_stt(lang: str, audio_path, stt_config):
    try:
        t0 = time.perf_counter()
        stt_with_whisper(str(audio_path), stt_config)
        logger.info("[WARMUP] STT %s done %.2fs", lang, time.perf_counter() - t0)
    except Exception as e:
        logger.warning("[WARMUP] STT %s failed: %s", lang, e)


# warmup llm
def _warm_llm(lang: str, llm_config):
    try:
        t0 = time.perf_counter()
        # short prompt to warm the model/connection
        text = "Hello" if lang == "en" else "Hallo"
        messages = [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": text},
        ]
        # drain the token stream just to warm the model/connection
        for _ in stream_llm(messages=messages, lang=lang, llm_config=llm_config):
            pass  # output doesnt matter for warmup
        logger.info("[WARMUP] LLM %s done %.2fs", lang, time.perf_counter() - t0)
    except Exception as e:
        logger.warning("[WARMUP] LLM %s failed: %s", lang, e)


# warumup tts with model for condition
def _warm_tts(lang: str, tts_config):
    try:
        t0 = time.perf_counter()
        text = (
            "Hello, this is a warmup." if lang == "en" else "Hallo, das ist ein Warmup."
        )
        synthesize_speech(text, lang, tts_config=tts_config)
        logger.info("[WARMUP] TTS %s done %.2fs", lang, time.perf_counter() - t0)
    except Exception as e:
        logger.warning("[WARMUP] TTS %s failed: %s", lang, e)


# main warmup function to run all stages at startup
def run_warmup():
    if not WARMUP:
        logger.info("[WARMUP] disabled")
        return

    logger.info("[WARMUP] start")
    t0 = time.perf_counter()
    condition = build_condition(ENHANCED)
    logger.info("[WARMUP] condition=%s", condition["id"])

    # warm every stage in both languages, f5 uses different models for en/de
    for lang, audio in (("en", WARMUP_EN), ("de", WARMUP_DE)):
        if audio.is_file():
            _warm_stt(lang, audio, condition["stt"])
        else:
            logger.warning("[WARMUP] missing %s", audio.name)
        _warm_llm(lang, condition["llm"])
        _warm_tts(lang, condition["tts"])

    logger.info("[WARMUP] done %.2fs", time.perf_counter() - t0)
