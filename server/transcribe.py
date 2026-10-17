"""Transcrição local com faster-whisper (grátis, roda no seu PC, zero tokens).

Se o faster-whisper não estiver instalado, o vídeo é dividido pelos silêncios
e a IA trabalha só com os tempos (sem saber o que foi falado).
"""
import os
from pathlib import Path

from . import media

_model = None


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        size = os.environ.get("WHISPER_MODEL", "small")
        _model = WhisperModel(size, device="auto", compute_type="int8")
    return _model


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(path: Path, duration: float, language: str = "pt", on_progress=None) -> dict:
    if whisper_available():
        try:
            return _whisper(path, duration, language, on_progress)
        except Exception as exc:  # modelo não baixou, sem memória etc.
            fallback = _by_silence(path, duration)
            fallback["warning"] = f"Transcrição falhou ({exc}); usando cortes por silêncio."
            return fallback
    return _by_silence(path, duration)


def _whisper(path: Path, duration: float, language: str, on_progress) -> dict:
    model = _load_model()
    segments, _info = model.transcribe(
        str(path), language=language or None, word_timestamps=True,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
    )
    out = []
    for seg in segments:
        words = [
            {"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
            for w in (seg.words or []) if w.word.strip()
        ]
        start = words[0]["s"] if words else seg.start
        end = words[-1]["e"] if words else seg.end
        out.append({
            "id": len(out),
            "start": round(start, 3),
            "end": round(end, 3),
            "text": seg.text.strip(),
            "words": words,
        })
        if on_progress and duration:
            on_progress(min(0.99, seg.end / duration))
    return {"source": "whisper", "segments": out}


def _by_silence(path: Path, duration: float) -> dict:
    silences = media.detect_silences(path)
    ranges = media.speech_ranges(duration, silences)
    segments = [
        {"id": i, "start": s, "end": e, "text": "", "words": []}
        for i, (s, e) in enumerate(ranges)
    ]
    return {"source": "silence", "segments": segments}
