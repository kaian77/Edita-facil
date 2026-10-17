"""Copiar o ESTILO de um vídeo que você gostou (estrutura, ritmo, tipo de texto), nunca o conteúdo.

O ritmo de cortes e a fala são medidos no seu PC. Para a IA vão só números, a transcrição e,
se você quiser, 6 quadros pequenos do vídeo (~4 mil tokens) para ela entender o visual.
"""
import base64
import json
import re
import subprocess
import uuid
from pathlib import Path

from . import ai, media, transcribe

ROOT = Path(__file__).resolve().parent.parent
USER_PRESETS = ROOT / "data" / "presets"
USER_PRESETS.mkdir(parents=True, exist_ok=True)

STYLE_SYSTEM = """Você é um diretor criativo que faz engenharia reversa de vídeos curtos que performam bem.
Você recebe medidas de um vídeo de referência (duração, cortes, ritmo de fala), a transcrição e às vezes alguns quadros.
Descreva o ESTILO de forma que outra pessoa consiga reproduzir com OUTRO tema: estrutura das cenas, tipo de gancho,
ritmo, como os textos aparecem, estilo de legenda, clima da música.
Nunca copie as frases do vídeo: o objetivo é reaproveitar a fórmula, não o conteúdo.
Escreva tudo em português do Brasil, de forma prática."""

STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "summary": {"type": "string"},
        "structure": {"type": "array", "items": {"type": "string"}},
        "hook": {"type": "string"},
        "pacing": {"type": "string"},
        "text_style": {"type": "string"},
        "music_mood": {"type": "string"},
        "format": {"type": "string", "enum": ai.FORMATS},
        "captions_enabled": {"type": "boolean"},
        "caption_style": {"type": "string", "enum": ["viral", "limpa", "apple"]},
        "caption_position": {"type": "string", "enum": ["middle", "bottom", "top"]},
        "caption_words": {"type": "integer"},
        "edit_instructions": {"type": "string"},
        "script_instructions": {"type": "string"},
        "max_seconds": {"type": "integer"},
    },
    "required": ["name", "summary", "structure", "hook", "pacing", "text_style", "music_mood", "format",
                 "captions_enabled", "caption_style", "caption_position", "caption_words",
                 "edit_instructions", "script_instructions", "max_seconds"],
    "additionalProperties": False,
}


def scene_cuts(path: Path) -> list:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "scale=240:-2,select='gt(scene,0.32)',showinfo",
         "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [round(float(m), 2) for m in re.findall(r"pts_time:([\d.]+)", out.stderr)]


def keyframes(path: Path, duration: float, n: int = 6) -> list:
    frames = []
    for i in range(n):
        t = duration * (i + 0.5) / n
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
             "-vf", "scale=360:-2", "-q:v", "5", "-f", "image2", "-c:v", "mjpeg", "-"], capture_output=True)
        if out.stdout:
            frames.append(base64.b64encode(out.stdout).decode())
    return frames


def analyze(path: Path, config: dict, use_frames: bool = True, on_status=None) -> tuple[dict, dict]:
    say = on_status or (lambda *_: None)
    say("Medindo cortes e ritmo…", 0.1)
    info = media.probe(path)
    cuts = scene_cuts(path)
    say("Ouvindo a fala…", 0.3)
    tr = transcribe.transcribe(path, info["duration"]) if info["has_audio"] else {"source": "none", "segments": []}
    words = sum(len(s["text"].split()) for s in tr["segments"])
    shots = len(cuts) + 1
    stats = {
        "duracao_s": round(info["duration"], 1),
        "formato": f"{info['width']}x{info['height']}",
        "cortes": len(cuts),
        "tempo_medio_por_plano_s": round(info["duration"] / shots, 2),
        "palavras_por_minuto": round(words / info["duration"] * 60) if words else 0,
        "momentos_dos_cortes_s": cuts[:60],
    }
    lines = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in tr["segments"] if s["text"]]
    text = ("MEDIDAS DO VÍDEO DE REFERÊNCIA:\n" + json.dumps(stats, ensure_ascii=False)
            + "\n\nTRANSCRIÇÃO:\n" + ("\n".join(lines) if lines else "(sem fala ou transcrição indisponível)"))
    content = []
    if use_frames:
        say("Olhando alguns quadros…", 0.6)
        for b64 in keyframes(path, info["duration"]):
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
        text += f"\n\nAcima estão {len(content)} quadros espalhados pelo vídeo, em ordem."
    content.append({"type": "text", "text": text + "\n\nDescreva o estilo para eu reproduzir com o meu tema."})
    say("A IA está decifrando o estilo…", 0.75)
    style, usage = ai.call_json(config, STYLE_SYSTEM, content, STYLE_SCHEMA)
    style["stats"] = stats
    return style, usage


def save_as_preset(style: dict) -> dict:
    pid = "ref-" + uuid.uuid4().hex[:6]
    preset = {
        "id": pid,
        "name": f"Estilo: {style['name']}"[:50],
        "icon": "🎯",
        "order": 50,
        "user": True,
        "description": style["summary"],
        "format": style["format"],
        "captions": {"enabled": style["captions_enabled"], "style": style["caption_style"],
                     "position": style["caption_position"], "words": max(1, min(8, style["caption_words"]))},
        "music_volume": 0.12 if style["music_mood"] else 0.0,
        "max_seconds": max(0, style["max_seconds"]),
        "instructions": style["edit_instructions"]
        + f"\nGancho: {style['hook']}\nRitmo: {style['pacing']}\nTextos na tela: {style['text_style']}",
        "script_instructions": style["script_instructions"],
        "structure": style["structure"],
        "style": {k: style[k] for k in ("hook", "pacing", "text_style", "music_mood", "stats")},
    }
    (USER_PRESETS / f"{pid}.json").write_text(json.dumps(preset, ensure_ascii=False, indent=2), encoding="utf-8")
    return preset
