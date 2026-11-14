import logging
import time

import soundfile as sf
import torch

from avatar_backend.config import PROJECT_ROOT

logger = logging.getLogger("tts")


# Omnivoice TTs service
class OmniVoiceService:

    def __init__(self):
        self._model = None  # lazy load model

    # load model if not already loaded, return model
    def _load_model(self, tts_config):
        if self._model is None:
            from omnivoice import OmniVoice  # heavy import, only first load

            logger.info("[TTS] OmniVoice loading model=%s", tts_config["model_id"])
            self._model = OmniVoice.from_pretrained(
                tts_config["model_id"],
                device_map=tts_config["device_map"],
                dtype=torch.float16,
            )
            logger.info("[TTS] OmniVoice ready model=%s", tts_config["model_id"])
        return self._model

    # synstehsize text to speech with omnivoice
    def synthesize(self, text: str, language: str, tts_config) -> tuple[str, float]:

        # output file path and name
        output_dir = PROJECT_ROOT / tts_config["output_dir"]
        output_dir.mkdir(exist_ok=True)
        out_path = output_dir / f"tts_{int(time.time())}.wav"

        # load model or cached
        model = self._load_model(tts_config)

        logger.info("[TTS] OmniVoice synth lang=%s", language)
        t0 = time.time()

        generation = tts_config[
            "generation"
        ]  # generation parameters from conditions.py

        audio = model.generate(
            text=text,  # input text to synthesize
            ref_audio=str(
                PROJECT_ROOT / tts_config["ref_audio"]
            ),  # reference audio for voice cloning
            ref_text=tts_config.get("ref_text")
            or None,  # reference text for voice cloning
            num_step=generation["num_step"],  # higher bette quality but slower
            guidance_scale=generation[
                "guidance_scale"
            ],  # higher more similar to reference voice but less diverse
            t_shift=generation["t_shift"],
            position_temperature=generation["position_temperature"],
            class_temperature=generation["class_temperature"],
            speed=generation["speed"],  # speed of gen speech
            preprocess_prompt=generation["preprocess_prompt"],
            postprocess_output=generation["postprocess_output"],
            audio_chunk_duration=generation["audio_chunk_duration"],
            audio_chunk_threshold=generation["audio_chunk_threshold"],
        )

        # save generated audio to file
        sf.write(str(out_path), audio[0], tts_config["sample_rate"])

        elapsed = time.time() - t0
        logger.info("[TTS] OmniVoice done %.2fs file=%s", elapsed, out_path.name)
        return str(out_path), elapsed


# singleton instance of the omnivoice service
_service: OmniVoiceService | None = None


# wrapper function to use the singleton service
def tts_with_omnivoice(text: str, lang: str, tts_config) -> tuple[str, float]:
    global _service
    if _service is None:
        _service = OmniVoiceService()
    return _service.synthesize(text, language=lang, tts_config=tts_config)
