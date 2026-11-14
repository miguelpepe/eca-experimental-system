# defines experiment conditions (baseline/enhanced) as dicts and with shared values
from pathlib import Path
from avatar_backend.config.profile import load_profile

# get base prompt from txt for both conditions
_BASE_PROMPT = (
    (Path(__file__).resolve().parent / "system_prompt.txt")
    .read_text(encoding="utf-8")
    .strip()
)

# allow tags for enhanced condition and how to use them (for Omnovice)
TAG_RULES = [
    "Your speech synthesis supports OmniVoice reaction tags. When a short opening reaction fits, you may render it as a tag: a question with [question-en]/[question-ah]/[question-oh]/[question-ei]/[question-yi]; agreement with [confirmation-en]; something funny with [laughter]; something unexpected with [surprise-ah]/[surprise-oh]/[surprise-wa]/[surprise-yo]; something annoying with [dissatisfaction-hnn] or [sigh]. Match the tag to the situation, and always follow a tag with a comma: '[question-ah], ...'.",
    "When you do add a closing follow-up question, you may preface it with a question tag: '[question-ah], Wie kann ich Ihnen helfen?'.",
]

# whisper stt settings for both conditions
WHISPER = {
    "model": "turbo",  # only parameter that really should be changed, speed/quality tradeoff
    "device": "cuda",
    "compute_type": "float16",
}

# shared llm settings, further options are set in the Open WebUI model
LLM = {
    "model": "avatar",
    "timeout_seconds": 120,
    "stop": ["\nUser:", "\nSystem:", "\nAssistant:"],
}

# f5 tts settings for baseline condition, uses different models for en/de
F5_TTS = {
    "provider": "f5",
    "output_dir": "output_audio",  # where to put generated audio files
    "english": {
        "model_dir": "models/f5_english",  # must be downloaded separately due to size
        "checkpoint": "model.safetensors",
        "vocab": "vocab.txt",
        "ref_audio": "./voices/warmup.wav",  # english reference audio
        "ref_text": "Which are the major universities in Berlin?",
    },
    "german": {
        "model_dir": "models/f5_german",  # must be downloaded separately due to size
        "checkpoint": "model.safetensors",
        "vocab": "vocab.txt",
        "ref_audio": "./voices/warmup-de.wav",  # german reference audio
        "ref_text": "Welche sind die größten Universitäten in Berlin?",
    },
    "nfe_step": 16,  # numbrt of gen steps, lower=fastrer, but worse quality
    "speed": 1.0,  # speech speed (>1 faster, <1 slower)
    "cfg_strength": 2.0,  # how strong generation follows prompt (higher=more closely, but also more robotic)
    "ode_method": "euler",  # ODE solver for flow matching sampling
}

# OmniVoice tts settings for enhanced condition, single multilingual model
OMNIVOICE_TTS = {
    "provider": "omnivoice",
    "model_id": "k2-fsa/OmniVoice",  # huggingface model id
    "device_map": "cuda:0",  # run on cuda if available
    "sample_rate": 24000,
    "output_dir": "output_audio",  # where to put generated audio files
    "ref_audio": "./voices/warmup.wav",  # shared reference audio for en/de
    "ref_text": "Which are the major universities in Berlin?",
    # paramter for audio generation
    "generation": {
        "num_step": 20,  # lower=faster, higher= better quality
        "guidance_scale": 1.5,  # how strongly generation follows  prompt
        "t_shift": 0.1,  # see OmniVoice docs
        "position_temperature": 5.0,  # see OmniVoice docs
        "class_temperature": 0.0,  # token sampling temperature (0 = deterministic)
        "speed": 1.0,  # speech speed (>1 faster, <1 slower)
        "preprocess_prompt": False,  # preprocess the reference audio/text
        "postprocess_output": False,  # postprocess audio
        "audio_chunk_duration": 10.0,  # only important for long outputs
        "audio_chunk_threshold": 20.0,  # only important for long outputs
    },
}


# optional deployment profile; native defaults stay in this file
_PROFILE, _PROFILE_DIR = load_profile()
if _PROFILE_DIR:
    _BASE_PROMPT = (_PROFILE_DIR / "persona.txt").read_text(encoding="utf-8").strip()
    WHISPER["model"] = _PROFILE.get("stt", {}).get("model", WHISPER["model"])
    _VOICE = _PROFILE.get("voice", {})
    if _VOICE:
        _VOICE_FILE = Path(_VOICE["file"])
        if _VOICE_FILE.is_absolute() or ".." in _VOICE_FILE.parts:
            raise ValueError("voice.file must be a relative path inside voices/")
        OMNIVOICE_TTS["ref_audio"] = str(Path("voices") / _VOICE_FILE)
        OMNIVOICE_TTS["ref_text"] = _VOICE["text"]


# builds condition dict based on enhanced flag (.env)
def build_condition(enhanced: bool) -> dict:
    system_prompt = _BASE_PROMPT
    if enhanced:
        # add tag rules for omnivoice to system prompt for enhanced condition
        system_prompt += "\n\n" + "\n\n".join(TAG_RULES)
    return {
        "id": "enhanced" if enhanced else "baseline",  # active condition
        "stt": WHISPER,  # stt same for both
        "llm": LLM,  # llm same for both
        "tts": (
            OMNIVOICE_TTS if enhanced else F5_TTS
        ),  # tts omnivoice for enhanced, f5 for baseline
        "system_prompt": system_prompt,  # system prompt with tag rules for enhanced, without for baseline
    }
