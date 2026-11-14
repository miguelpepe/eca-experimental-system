import os
import logging

from faster_whisper import WhisperModel

logger = logging.getLogger("stt")


# wrapper class for faster whisper model
class WhisperSTT:

    def __init__(self, stt_config):
        logger.info(
            "[STT] loading model=%s",
            stt_config["model"],
        )
        # init whisper model with config
        self.model = WhisperModel(
            stt_config["model"],
            device=stt_config["device"],
            compute_type=stt_config["compute_type"],
        )

        logger.info("[STT] model ready")

    # transcribe from a file path with faster whisper
    def transcribe(self, audio_path: str) -> tuple[str, str]:

        audio_name = os.path.basename(audio_path)  # get file name for log

        logger.info("[STT] transcribing file=%s", audio_name)

        segments, info = self.model.transcribe(
            audio_path,
            beam_size=1,  # how many candidates to consider during decoding
            best_of=1,  # how many candidates to return (only the best one)
            temperature=0.0,  # deterministic output
            vad_filter=True,  # enable VAD to skip silence
            vad_parameters={"min_silence_duration_ms": 500},
            word_timestamps=False,
        )
        # concatenate all segments into one text
        text = "".join(s.text for s in segments).strip()
        lang = info.language or "en"  # get detected language

        logger.info("[STT] done lang=%s", lang)
        return text, lang


_stt: WhisperSTT | None = None  # module-level instance


# wrapper function for pipeline usage
def stt_with_whisper(audio_path: str, stt_config) -> tuple[str, str]:
    global _stt

    # create WhisperSTT instance if not exists
    if _stt is None:
        logger.info("[STT] creating service")
        _stt = WhisperSTT(stt_config)

    return _stt.transcribe(audio_path)
