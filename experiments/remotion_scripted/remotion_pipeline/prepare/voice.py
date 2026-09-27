from __future__ import annotations

import base64
import json
import uuid
import wave
from pathlib import Path

import requests


def synthesize_narration(project: dict, output: Path, values: dict[str, str]) -> float:
    key = values.get("DOUBAO_TTS_ACCESS_KEY") or values.get("DOUBAO_TTS_API_KEY")
    if not key:
        raise ValueError("narration requires DOUBAO_TTS_ACCESS_KEY or DOUBAO_TTS_API_KEY")
    text = " ".join([project.get("voice", ""), *(shot["voice"] for shot in project["shots"])]).strip()
    body = {"user": {"uid": "scripted-remotion"}, "req_params": {
        "text": text,
        "speaker": values.get("DOUBAO_TTS_SPEAKER", "zh_female_shuangkuaisisi_uranus_bigtts"),
        "audio_params": {"format": "pcm", "sample_rate": 24000, "speech_rate": 5},
    }}
    response = requests.post(
        "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse",
        headers={"Content-Type": "application/json", "X-Api-Key": key,
                 "X-Api-Resource-Id": values.get("DOUBAO_TTS_RESOURCE_ID", "seed-tts-2.0"),
                 "X-Api-Request-Id": str(uuid.uuid4())},
        json=body, stream=True, timeout=(15, 180),
    )
    response.raise_for_status()
    chunks: list[bytes] = []
    for raw in response.iter_lines(decode_unicode=True):
        if not raw:
            continue
        line = raw[5:].strip() if raw.startswith("data:") else raw.strip()
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        for value in (payload.get("data"), payload.get("audio"), payload.get("audio_data")):
            if isinstance(value, str):
                try:
                    chunks.append(base64.b64decode(value))
                except ValueError:
                    continue
    if not chunks:
        raise RuntimeError("Doubao TTS returned no audio data")
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"".join(chunks))
    with wave.open(str(output), "rb") as wav:
        return wav.getnframes() / wav.getframerate()
