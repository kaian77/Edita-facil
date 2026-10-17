"""ElevenLabs: clonar voz (com autorização) e gerar narração com tempos de cada palavra."""
import base64
import json
import urllib.error
import urllib.request
import uuid

API = "https://api.elevenlabs.io/v1"
TTS_MODEL = "eleven_multilingual_v2"


class VoiceError(Exception):
    pass


def _request(key: str, method: str, path: str, body: bytes | None = None, ctype: str | None = None, timeout=120):
    if not key:
        raise VoiceError("Coloque sua chave da ElevenLabs em ⚙️ Configurações.")
    req = urllib.request.Request(API + path, data=body, method=method)
    req.add_header("xi-api-key", key)
    req.add_header("Accept", "application/json")
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            d = json.loads(detail).get("detail")
            detail = d.get("message") if isinstance(d, dict) else d or detail
        except (ValueError, AttributeError):
            pass
        if exc.code == 401:
            raise VoiceError("Chave da ElevenLabs inválida.")
        raise VoiceError(f"ElevenLabs recusou ({exc.code}): {str(detail)[:300]}")
    except urllib.error.URLError as exc:
        raise VoiceError(f"Sem conexão com a ElevenLabs: {exc.reason}")


def list_voices(key: str) -> list:
    data = _request(key, "GET", "/voices")
    return [
        {"id": v["voice_id"], "name": v["name"], "category": v.get("category", ""),
         "preview": v.get("preview_url")}
        for v in data.get("voices", [])
    ]


def clone_voice(key: str, name: str, files: list[tuple[str, bytes]], description: str = "") -> str:
    """Clonagem instantânea: 1 a 25 amostras limpas (ideal: 1 a 3 minutos no total)."""
    boundary = uuid.uuid4().hex
    parts = []

    def field(k, v):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())

    field("name", name)
    field("description", description or "Voz clonada no Edita Fácil")
    field("remove_background_noise", "true")
    for filename, data in files:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    res = _request(key, "POST", "/voices/add", b"".join(parts), f"multipart/form-data; boundary={boundary}", 300)
    return res["voice_id"]


def delete_voice(key: str, voice_id: str):
    _request(key, "DELETE", f"/voices/{voice_id}")


def speak(key: str, voice_id: str, text: str) -> tuple[bytes, list]:
    """Gera a narração (MP3) e devolve também os tempos de cada palavra."""
    body = json.dumps({
        "text": text,
        "model_id": TTS_MODEL,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.85, "style": 0.2, "use_speaker_boost": True},
    }).encode()
    res = _request(key, "POST", f"/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128",
                   body, "application/json", 300)
    audio = base64.b64decode(res["audio_base64"])
    align = res.get("alignment") or res.get("normalized_alignment") or {}
    return audio, words_from_alignment(align)


def words_from_alignment(align: dict) -> list:
    chars = align.get("characters") or []
    starts = align.get("character_start_times_seconds") or []
    ends = align.get("character_end_times_seconds") or []
    words, cur, s, e = [], "", None, None
    for ch, cs, ce in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": round(s, 3), "e": round(e, 3)})
            cur, s = "", None
            continue
        if s is None:
            s = cs
        cur += ch
        e = ce
    if cur:
        words.append({"w": cur, "s": round(s, 3), "e": round(e, 3)})
    return words
