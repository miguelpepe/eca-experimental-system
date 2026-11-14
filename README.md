# ECA Experimental System

Spoken MetaHuman avatar with a Python backend and an Unreal Engine 5.6 frontend.

## Quick setup (Windows + Docker)

Install Docker Desktop with its WSL 2 backend and an NVIDIA GPU driver. For the
frontend, also install Unreal Engine 5.6, C++ build tools and the NVIDIA plugins
listed in the [Unreal guide](docs/unreal.md).

1. Clone this repository or download its source ZIP. Git LFS is not required.
2. Run **`Setup.bat`** and choose **Backend**, **Frontend**, or **Both**.
3. Edit `.eca/config/persona.txt` for the persona. Put documents in `RAG/`.
   For a custom voice, add a recording to `voices/` and set its filename and exact
   transcript in `.eca/config/avatar.toml`.
4. Run **`Start.bat`**, open the demo scene in Unreal and press **Play**.
   Hold **Space** to record, then release it to send.

The Docker setup defaults to **Enhanced / OmniVoice**. It configures Ollama,
Open WebUI, the `avatar` model and the knowledge collection automatically.
The first start builds images and downloads models; later starts reuse them.
`Start.bat` also imports changed RAG documents. `Update-RAG.bat` imports them
without opening Unreal; `Stop.bat` stops the containers without deleting data.

When choosing Frontend or Both, setup also downloads the public Unreal content
from the pinned [asset release](https://github.com/miguelpepe/eca-experimental-system/releases/tag/unreal-assets-v1),
verifies its checksums and installs it locally. Backend-only setup skips these downloads.
Existing local asset edits and the private MetaHuman variant are preserved.

Local Docker settings and credentials live in the ignored `.eca/` directory;
the existing native `.env` is left intact. Your private Unreal profile remains
local. Docker runs the backend; the Unreal Editor runs directly on Windows.

See the **[Docker setup and customization guide](docs/docker.md)** for requirements,
separate machines, commands, voice settings and troubleshooting.

## Existing project layout and manual setup

- Backend: `avatar_backend/` (setup below).
- Unreal project: `unreal/METAHUMAN_5_5.uproject`.
- Frontend setup and customization: [Unreal guide](docs/unreal.md).

The public scene `ECA_Demo` uses a neutral example MetaHuman. Choose your own
under **Project Settings > ECA > Avatar > MetaHuman Blueprint**. The existing
specific character and `Main` scene remain in the ignored local variant.

For the local Unreal project, run `unreal/Setup.bat` once, start the backend,
then run `unreal/Open.bat`. BlueprintWebsockets and RuntimeAudioImporter source
copies are included with their licenses. Install the NVIDIA plugins and models
separately as described in the Unreal guide.

Third-party code retains its original licenses; see
[third-party notices](THIRD_PARTY_NOTICES.md).

FastAPI backend for a spoken avatar:

```text
audio upload -> Whisper STT -> Open WebUI LLM + RAG -> TTS -> streamed audio response
```

The conversation endpoint is:

```text
WebSocket /ws
```

It receives base64 encoded audio and streams JSON response events. Each sentence event contains text plus base64 encoded WAV audio.

## Requirements

- Python 3.11
- CUDA-capable GPU
- ffmpeg installed and available on `PATH`
- Open WebUI running separately
- Ollama running separately if Open WebUI uses Ollama models
- F5 model files for the baseline condition
- Voice reference files in `voices/`

## Setup

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your local environment (see `.env.example`) file as:

```
.env
```

Edit `.env` and set your Open WebUI values.

## Open WebUI

This backend does not run the LLM itself. It calls Open WebUI through its API.
In the current setup, Open WebUI uses Ollama as the model backend.

You need:

- an Open WebUI API key
- a model in Open WebUI with the model ID `avatar`
- a Knowledge/RAG collection
- the collection ID in `.env`
- Ollama with the base model used by the Open WebUI model

Setup:

1. Start Ollama.
2. Pull the base model used by the Open WebUI model.
3. Start Open WebUI.
4. Create or import the model used by the backend with the model ID `avatar` (not just the display name).
5. Create a Knowledge collection.
6. Upload the RAG documents for the avatar.
7. Copy the collection ID into `OPEN_WEBUI_KNOWLEDGE_ID`.
8. Copy an API key into `OPEN_WEBUI_API_KEY`.

Example:

```bash
ollama serve
ollama pull qwen3.5:9b # used here
```


The backend sends its own system prompt from:

```text
avatar_backend/config/system_prompt.txt
```

The active LLM model name is configured in:

```text
avatar_backend/config/conditions.py
```

## TTS Files

Baseline uses F5-TTS. The expected local files are configured in:

```text
avatar_backend/config/conditions.py
```

By default model files are expected under:

```text
models/f5_english/
models/f5_german/
```

Reference voices are expected under:

```text
voices/
```

The default references are `voices/warmup.wav` (English and Enhanced) and
`voices/warmup-de.wav` (German baseline). To use your own voice, change `ref_audio`
and `ref_text` in `avatar_backend/config/conditions.py`. The text must match the recording.

Private reference recordings (`reference_en.wav`, `reference_de.wav`, `enhanced.wav`)
are ignored by Git.

Enhanced mode uses OmniVoice and loads the model from:

```text
k2-fsa/OmniVoice
```

## Run Backend

```bash
uvicorn avatar_backend.main:app --host 127.0.0.1 --port 8000
```

Use `.env` to select the condition:

```env
ENHANCED=false
```

- `false`: baseline, F5-TTS
- `true`: enhanced, OmniVoice + reaction tags

## Connect a Client

Connect your Unreal Engine client or another WebSocket client to:

```text
ws://127.0.0.1:8000/ws
```

Send an audio request as JSON:

```json
{"type":"request","audio_b64":"<base64 encoded audio>"}
```

Send `{"type":"stop"}` to cancel the active response. A new request also cancels
the previous response. The connection stays open for further requests.

Clients can include an optional string `request_id` in each request. Response
events echo that ID so a client can discard late events from cancelled requests.
Requests without an ID retain the original response format.

## API Response Format

Sentence event:

```json
{"type":"sentence","index":0,"text":"...","audio_b64":"..."}
```

Final event:

```json
{"type":"done","user":"...","response":"...","language":"de","condition":"baseline","timings":{}}
```

Cancellation returns `{"type":"stopped"}`. Errors return
`{"type":"error","message":"..."}`.

## Notes

- `.env`, model files, uploads, and generated audio are not committed
- Open WebUI data is not part of this repo
- RAG documents and the private `system_prompt.local.txt` backup are not committed
- Replace the placeholders in `avatar_backend/config/system_prompt.txt` with your persona before use

