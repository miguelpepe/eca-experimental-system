from avatar_backend.tts.audio_post import normalize_audio_file
from avatar_backend.tts.f5_service import tts_with_f5
from avatar_backend.tts.omnivoice_service import tts_with_omnivoice


# tts router function, select provider based on condition
def synthesize_speech(text: str, lang: str, tts_config) -> tuple[str, float]:

    # f5 for baseline condition
    if tts_config["provider"] == "f5":
        path, elapsed = tts_with_f5(text, lang, tts_config=tts_config)
    # omnivoice for enhanced condition
    elif tts_config["provider"] == "omnivoice":
        path, elapsed = tts_with_omnivoice(text, lang, tts_config=tts_config)
    else:
        raise ValueError(f"Unsupported TTS provider: {tts_config['provider']}")

    # normalize loudness / limit peaks
    normalize_audio_file(path)

    return path, elapsed
