import time
import logging
import torch

from avatar_backend.config import PROJECT_ROOT

logger = logging.getLogger("tts")

F5TTS = None  # modul-level variable


# lazy load f5 to avoid long import
def _get_f5tts_class():
    global F5TTS

    if F5TTS is None:
        from f5_tts.api import F5TTS as _F5TTS

        F5TTS = _F5TTS

    return F5TTS


# F5 TTS Service
class F5TTSService:

    # init model and device
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("[TTS] F5 init")

        self._models: dict[tuple, object] = {}

        logger.info("[TTS] F5 ready")

    # load model
    def _load_model(self, lang: str, tts_config):
        # choose language-specific config
        lang_cfg = tts_config["german"] if lang == "de" else tts_config["english"]
        cache_key = (
            tts_config["provider"],
            lang,
            lang_cfg["model_dir"],
            lang_cfg["checkpoint"],
            lang_cfg["vocab"],
            tts_config["ode_method"],
        )
        # check if model is already loaded
        if cache_key in self._models:
            return self._models[cache_key]

        # pathes for model files and ref audio foir voice cloning
        model_dir = PROJECT_ROOT / lang_cfg["model_dir"]
        ckpt = model_dir / lang_cfg["checkpoint"]
        vocab = model_dir / lang_cfg["vocab"]
        ref_audio = PROJECT_ROOT / lang_cfg["ref_audio"]

        logger.info("[TTS] F5 loading lang=%s", lang)

        # load model
        model = _get_f5tts_class()(
            model="F5TTS_v1_Base",  # base model architecture
            ckpt_file=str(ckpt),  # model checkpoint
            vocab_file=str(vocab),  # vocab file
            device=self.device,
            use_ema=True,
            ode_method=tts_config["ode_method"],
        )

        self._models[cache_key] = model

        logger.info("[TTS] F5 model ready lang=%s", lang)

        return model

    # synthesize text to speech
    def synthesize(self, text: str, language: str, tts_config) -> tuple[str, float]:

        # load model for en/de language
        lang = language
        lang_cfg = tts_config["german"] if lang == "de" else tts_config["english"]
        model = self._load_model(lang, tts_config)

        out_name = f"tts_{int(time.time())}.wav"  # generate output file name
        output_dir = PROJECT_ROOT / tts_config["output_dir"]
        output_dir.mkdir(exist_ok=True)
        out_path = output_dir / out_name  # output file path

        logger.info("[TTS] F5 synth lang=%s", lang)

        t0 = time.time()

        # synthesize speech
        model.infer(
            ref_file=str(PROJECT_ROOT / lang_cfg["ref_audio"]),
            ref_text=lang_cfg["ref_text"].strip(),
            gen_text=text,  # text to synthesize
            file_wave=str(out_path),
            target_rms=0.1,  # target loudness
            speed=tts_config["speed"],  # controls speed of the generated speech
            nfe_step=tts_config[
                "nfe_step"
            ],  # number of function evaluations (higher = better quality but slower)
            cfg_strength=tts_config[
                "cfg_strength"
            ],  # classifier-free guidance strength (higher = more faithful to text but less natural)
        )

        elapsed = time.time() - t0

        logger.info("[TTS] F5 done %.2fs file=%s", elapsed, out_name)

        return str(out_path), elapsed


# singleton instance of the f5 service
_tts_service: F5TTSService | None = None


# wrapper function to use the singleton service
def tts_with_f5(text: str, lang: str, tts_config) -> tuple[str, float]:
    global _tts_service

    if _tts_service is None:
        logger.info("[TTS] creating F5 service")
        _tts_service = F5TTSService()

    return _tts_service.synthesize(text, language=lang, tts_config=tts_config)
