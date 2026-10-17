"""Converte o plano da IA na timeline que o editor mostra e que o ffmpeg renderiza.

A timeline tem dois relógios:
- tempo de ORIGEM (src_in/src_out): segundos no vídeo cru;
- tempo de SAÍDA (start/end): segundos no vídeo final, depois dos cortes.
"""
import uuid

from . import brand as brandkit
from .ai import FORMATS, TEXT_STYLES

MIN_CLIP = 0.3
PAD = 0.06  # respiro antes/depois de cada fala para não "comer" sílabas


def _id(prefix):
    return f"{prefix}{uuid.uuid4().hex[:6]}"


def local_plan(transcript: dict, preset: dict) -> dict:
    """Plano feito sem IA: mantém todas as falas e corta os silêncios entre elas."""
    return {
        "summary": "Cortei os silêncios entre as falas (edição local, sem IA).",
        "format": preset["format"],
        "captions": preset["captions"]["enabled"],
        "music": bool(preset.get("music_volume")),
        "clips": [
            {"start": s["start"], "end": s["end"], "zoom": 1.0, "label": "Vídeo"}
            for s in transcript["segments"]
        ],
        "texts": [],
        "scenes": [{"title": "Vídeo", "desc": "Todas as falas, sem as pausas."}],
    }


def build(plan: dict, transcript: dict, info: dict, preset: dict, previous: dict | None = None) -> dict:
    duration = info["duration"]
    clips = []
    for c in plan.get("clips", []):
        start = max(0.0, float(c["start"]) - PAD)
        end = min(duration, float(c["end"]) + PAD)
        if end - start < MIN_CLIP:
            continue
        zoom = min(1.4, max(1.0, float(c.get("zoom") or 1.0)))
        if clips and clips[-1]["src_in"] < start < clips[-1]["src_out"]:
            start = clips[-1]["src_out"]  # o respiro não pode repetir áudio do clip anterior
            if end - start < MIN_CLIP:
                continue
        clips.append({
            "id": _id("c"), "src_in": round(start, 3), "src_out": round(end, 3),
            "zoom": round(zoom, 3), "label": (c.get("label") or "Cena").strip()[:40],
        })
    if not clips:
        raise ValueError("O plano não tem nenhum trecho válido.")

    texts = []
    for t in plan.get("texts", []):
        idx = int(t.get("at_clip", 0))
        if not (0 <= idx < len(clips)) or not t.get("text", "").strip():
            continue
        texts.append({
            "id": _id("t"), "text": t["text"].strip(), "clip_id": clips[idx]["id"],
            "offset": max(0.0, float(t.get("offset", 0))),
            "length": min(15.0, max(0.6, float(t.get("duration", 2)))),
            "style": t["style"] if t.get("style") in TEXT_STYLES else "destaque",
        })

    fmt = plan.get("format") if plan.get("format") in FORMATS else preset["format"]
    captions = dict(preset["captions"])
    captions["enabled"] = bool(plan.get("captions", captions["enabled"]))
    music = (previous or {}).get("music") or {
        "enabled": False, "file": None, "volume": preset.get("music_volume") or 0.12, "duck": True,
    }
    music = dict(music, enabled=bool(plan.get("music")) and bool(music.get("file")))

    timeline = {
        "format": fmt,
        "clips": clips,
        "texts": texts,
        "captions": captions,
        "music": music,
        "logo": (previous or {}).get("logo", brandkit.load()["watermark"] and bool(brandkit.path("logo"))),
        "scenes": plan.get("scenes", []),
        "summary": plan.get("summary", ""),
        "preset": preset["id"],
    }
    return retime(timeline, transcript)


def retime(timeline: dict, transcript: dict) -> dict:
    """Recalcula os tempos de saída, as cenas e as legendas depois de qualquer mudança."""
    t = 0.0
    by_id = {}
    for c in timeline["clips"]:
        c["start"] = round(t, 3)
        t += c["src_out"] - c["src_in"]
        c["end"] = round(t, 3)
        by_id[c["id"]] = c
    timeline["duration"] = round(t, 3)

    kept = []
    for x in timeline["texts"]:
        clip = by_id.get(x.get("clip_id"))
        if clip is None:
            continue
        x["start"] = round(min(clip["start"] + x.get("offset", 0), t - 0.2), 3)
        x["end"] = round(min(x["start"] + x.get("length", 2), t), 3)
        kept.append(x)
    timeline["texts"] = kept

    timeline["scene_spans"] = _scene_spans(timeline)
    timeline["caption_words"] = _caption_words(timeline["clips"], transcript)
    return timeline


def _scene_spans(timeline):
    spans = []
    for c in timeline["clips"]:
        if spans and spans[-1]["label"] == c["label"]:
            spans[-1]["end"] = c["end"]
        else:
            spans.append({"label": c["label"], "start": c["start"], "end": c["end"]})
    descs = timeline.get("scenes") or []
    for i, s in enumerate(spans):
        s["code"] = f"S{i + 1:02d}"
        match = next((d for d in descs if d["title"].lower() == s["label"].lower()), None)
        s["desc"] = match["desc"] if match else ""
    return spans


def _caption_words(clips, transcript):
    """Mapeia cada palavra falada para o tempo do vídeo final."""
    words = [w for seg in transcript["segments"] for w in seg.get("words", [])]
    out = []
    for c in clips:
        offset = c["start"] - c["src_in"]
        for w in words:
            mid = (w["s"] + w["e"]) / 2
            if c["src_in"] <= mid <= c["src_out"]:
                out.append({
                    "w": w["w"],
                    "s": round(max(w["s"], c["src_in"]) + offset, 3),
                    "e": round(min(w["e"], c["src_out"]) + offset, 3),
                })
    return out


def caption_lines(words, per_line: int):
    """Agrupa palavras em blocos de legenda (quebra também em pausas e pontuação)."""
    lines, cur = [], []
    for w in words:
        if cur and (len(cur) >= per_line or w["s"] - cur[-1]["e"] > 0.6):
            lines.append(cur)
            cur = []
        cur.append(w)
        if w["w"][-1:] in ".!?":
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def output_size(fmt: str, info: dict) -> tuple[int, int]:
    sizes = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
    if fmt in sizes:
        return sizes[fmt]
    w, h = info["width"], info["height"]
    scale = min(1.0, 1920 / max(w, h))
    return int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
