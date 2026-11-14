"""Send the public warmup recording through the running Docker backend."""
import argparse
import asyncio
import base64
import io
import json
import time
import uuid
import wave
from pathlib import Path
from urllib.request import urlopen

import websockets


async def verify(base_url, recording=None):
    with urlopen(base_url.rstrip('/') + '/health', timeout=10) as response:
        health = json.load(response)
    url = base_url.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/') + '/ws'
    root = Path(__file__).resolve().parents[1]
    audio = (recording or root / 'voices/warmup.wav').read_bytes()
    request_id = uuid.uuid4().hex
    sentences = 0
    started = time.monotonic()
    async with websockets.connect(url, max_size=32 * 1024**2, open_timeout=15) as socket:
        await socket.send(json.dumps({
            'type': 'request', 'request_id': request_id,
            'audio_b64': base64.b64encode(audio).decode(),
        }))
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), timeout=600))
            assert event.get('request_id') == request_id, 'Missing request ID'
            if event['type'] == 'error':
                raise RuntimeError('Backend inference failed; check container logs')
            if event['type'] == 'sentence':
                decoded = base64.b64decode(event['audio_b64'], validate=True)
                with wave.open(io.BytesIO(decoded)) as wav:
                    assert wav.getnframes() > 0 and wav.getframerate() > 0
                sentences += 1
            if event['type'] == 'done':
                assert event['response'].strip() and sentences > 0
                assert event['condition'] == health['condition']
                break
    report = {
        'passed': True, 'condition': health['condition'], 'audio_sentences': sentences,
        'language': event.get('language'),
        'seconds': round(time.monotonic() - started, 2),
        'scope': 'Real Whisper, Open WebUI/Ollama and TTS over WebSocket; no Unreal microphone or face animation.',
    }
    directory = root / '.eca/validation'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'e2e.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--audio', type=Path)
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.audio))
