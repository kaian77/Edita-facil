"""Criar vídeo só com o tema: o Claude escreve o roteiro, a ElevenLabs narra (opcional)
e o ffmpeg anima tudo com as cores, a logo e o avatar da marca.

As animações são feitas com legendas ASS (rotação 3D \\frx/\\fry, \\move, escala, desfoque),
fundo em degradê animado e sobreposição do avatar/logo — tudo local, sem custo de IA.
"""
import json
import subprocess
from pathlib import Path

from . import ai, brand as brandkit, voices
from .timeline import output_size

VISUALS = ["texto", "lista", "numero", "citacao", "avatar", "logo"]
MOTIONS = ["pop", "giro3d", "flip3d", "deslizar", "zoom", "digitar"]

SCRIPT_SYSTEM = """Você é roteirista e diretor de motion design de vídeos curtos virais (Reels, TikTok, Shorts) no Brasil.
A partir de um TEMA você cria um vídeo completo dividido em cenas. Cada cena tem:
- narration: o que a voz fala (frases curtas, naturais, como gente falando; 8 a 25 palavras). Português do Brasil.
- screen_text: o texto grande animado na tela (máx. 7 palavras; NÃO é a narração inteira: é a ideia-chave).
- emphasis: UMA palavra do screen_text para destacar com a cor da marca (ou vazio).
- visual: texto | lista (use bullets, 2 a 4 itens curtos) | numero (screen_text começa com um número ou %, ex.: "87% erram isso") | citacao (frase de impacto) | avatar (mostra a foto da pessoa; ótimo no gancho e no CTA) | logo (só na última cena: assinatura da marca).
- bullets: itens da lista (vazio se não for lista; para numero, 1 item curto explicando o número).
- motion: pop | giro3d | flip3d | deslizar | zoom | digitar. Varie entre as cenas.
- title: nome curto da cena (Gancho, Problema, Dica 1, Prova, CTA...).

Regras de retenção: a primeira cena é um GANCHO forte em até 2 segundos (curiosidade, dor ou promessa).
Uma ideia por cena. Ritmo rápido. Termine com CTA claro e, se houver marca com logo, a última cena é visual "logo".
Não invente fatos, números ou estatísticas que você não tem certeza: prefira afirmações seguras ou exemplos.
Também devolva: title (título do vídeo), caption (legenda do post, 1 a 3 frases) e hashtags (5 a 8, sem #)."""

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "narration": {"type": "string"},
                    "screen_text": {"type": "string"},
                    "emphasis": {"type": "string"},
                    "visual": {"type": "string", "enum": VISUALS},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "motion": {"type": "string", "enum": MOTIONS},
                },
                "required": ["title", "narration", "screen_text", "emphasis", "visual", "bullets", "motion"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "caption", "hashtags", "scenes"],
    "additionalProperties": False,
}


def write_script(config: dict, theme: str, seconds: int, style: dict | None, extra: str,
                 has_avatar: bool, has_logo: bool) -> tuple[dict, dict]:
    parts = [f"TEMA DO VÍDEO: {theme.strip()}", f"Duração alvo: ~{seconds} segundos (≈{int(seconds * 2.6)} palavras de narração no total)."]
    if b := brandkit.prompt_block():
        parts.append(b)
    parts.append("Recursos disponíveis: " + ", ".join(
        x for x in ["foto/avatar da pessoa" if has_avatar else "", "logo da marca" if has_logo else ""] if x
    ) if (has_avatar or has_logo) else "Sem foto e sem logo: não use os visuais avatar nem logo.")
    if style:
        parts.append(f"ESTILO A SEGUIR ({style['name']}):\n{style['instructions']}")
        if style.get("structure"):
            parts.append("Estrutura de cenas do estilo: " + " → ".join(style["structure"]))
    if extra.strip():
        parts.append(f"PEDIDO EXTRA DO USUÁRIO: {extra.strip()}")
    script, usage = ai.call_json(config, SCRIPT_SYSTEM, [{"type": "text", "text": "\n\n".join(parts)}], SCRIPT_SCHEMA)
    scenes = [s for s in script.get("scenes", []) if s.get("screen_text") or s.get("narration")]
    for s in scenes:
        if s["visual"] == "avatar" and not has_avatar:
            s["visual"] = "texto"
        if s["visual"] == "logo" and not has_logo:
            s["visual"] = "texto"
    if not scenes:
        raise ai.AIError("A IA não devolveu nenhuma cena. Tente detalhar mais o tema.")
    script["scenes"] = scenes[:16]
    return script, usage


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def voice_scenes(script: dict, workdir: Path, el_key: str, voice_id: str, on_progress=None) -> list:
    """Narra cada cena (se houver voz) e calcula início/fim de cada uma."""
    scenes, t = [], 0.0
    total = len(script["scenes"])
    for i, s in enumerate(script["scenes"]):
        scene = dict(s, words=[], audio=None)
        if voice_id and s["narration"].strip():
            audio, words = voices.speak(el_key, voice_id, s["narration"])
            f = workdir / f"voz_{i:02d}.mp3"
            f.write_bytes(audio)
            spoken = probe_duration(f) or (words[-1]["e"] if words else 2)
            dur = max(2.0, spoken + 0.35)
            scene["audio"] = f.name
            scene["words"] = [{"w": w["w"], "s": round(w["s"] + t, 3), "e": round(w["e"] + t, 3)} for w in words]
        else:
            on_screen = len(s["screen_text"].split()) + sum(len(b.split()) for b in s.get("bullets", []))
            dur = max(2.4, 1.3 + 0.38 * on_screen)
        scene["start"], scene["end"] = round(t, 3), round(t + dur, 3)
        t += dur
        scenes.append(scene)
        if on_progress:
            on_progress((i + 1) / total)
    return scenes


# ---------------- animação (ASS) ----------------

def _t(x: float) -> str:
    x = max(0.0, x)
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _emph(text: str, word: str, accent: str, base: str) -> str:
    text = _clean(text)
    if not word.strip():
        return text
    out = []
    target = word.strip().lower().strip(".,!?")
    done = False
    for w in text.split(" "):
        if not done and w.lower().strip(".,!?:;") == target:
            out.append(r"{\c" + accent + "}" + w + r"{\c" + base + "}")
            done = True
        else:
            out.append(w)
    return " ".join(out)


def _motion(kind: str, x: int, y: int, W: int, dur_ms: int) -> str:
    pos = rf"\pos({x},{y})"
    drift = rf"\t(500,{dur_ms},\fscx104\fscy104)"
    if kind == "giro3d":
        return pos + r"\fry-90\t(0,480,\fry0)" + rf"\t(480,{dur_ms},\fry6)"
    if kind == "flip3d":
        return pos + r"\frx-90\t(0,420,\frx0)" + drift
    if kind == "deslizar":
        return rf"\move({x + int(W * 0.35)},{y},{x},{y},0,350)\blur3\t(0,350,\blur0)"
    if kind == "zoom":
        return pos + r"\fscx170\fscy170\blur8\t(0,450,\fscx100\fscy100\blur0)" + rf"\t(450,{dur_ms},\fscx106\fscy106)"
    return pos + r"\fscx40\fscy40\t(0,220,\fscx108\fscy108)\t(220,330,\fscx100\fscy100)" + drift  # pop


def build_motion_ass(scenes: list, W: int, H: int, brand: dict, total: float) -> str:
    c = brand["colors"]
    ACC, PRI, TXT = brandkit.ass_color(c["accent"]), brandkit.ass_color(c["primary"]), brandkit.ass_color(c["text"])
    base = min(W, H)
    mh = int(W * 0.08)
    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Big,Inter,{int(base * 0.115)},{TXT},{ACC},&H00000000,&H90000000,-1,0,0,0,100,100,-1,0,1,0,{max(2, base // 160)},5,{mh},{mh},0,1",
        f"Style: Mid,Inter,{int(base * 0.07)},{TXT},{ACC},&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,0,{max(2, base // 200)},5,{mh},{mh},0,1",
        f"Style: Item,Inter,{int(base * 0.062)},{TXT},{ACC},&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,0,2,4,{mh},{mh},0,1",
        f"Style: Small,Inter,{int(base * 0.036)},{TXT},{ACC},&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,0,0,2,{mh},{mh},0,1",
        f"Style: Box,Inter,{int(base * 0.055)},&H00101010,{ACC},{ACC},{ACC},-1,0,0,0,100,100,0,0,3,{int(base * 0.022)},0,5,{mh},{mh},0,1",
        f"Style: Shape,Inter,20,{ACC},{ACC},{ACC},{ACC},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ev = []

    def add(layer, a, b, style, text):
        ev.append(f"Dialogue: {layer},{_t(a)},{_t(b)},{style},,0,0,0,,{text}")

    # barra de progresso que enche durante o vídeo
    bar_h = max(6, int(H * 0.006))
    add(6, 0, total, "Shape",
        rf"{{\pos(0,{H - bar_h})\c{ACC}\alpha&H20&\clip(0,0,0,{H})\t(0,{int(total * 1000)},\clip(0,0,{W},{H}))\p1}}m 0 0 l {W} 0 {W} {bar_h} 0 {bar_h}{{\p0}}")
    if brand.get("handle"):
        add(5, 0, total, "Small", rf"{{\an2\pos({W // 2},{int(H * 0.955)})\alpha&H50&}}{_clean(brand['handle'])}")

    for i, s in enumerate(scenes):
        a, b = s["start"], s["end"]
        dur_ms = int((b - a) * 1000)
        fade = r"\fad(120,200)"
        # formas geométricas girando em 3D ao fundo
        for k in range(2):
            size = int(base * (0.22 if k == 0 else 0.14))
            sx = int(W * (0.12 + 0.7 * ((i * 37 + k * 53) % 100) / 100))
            sy = int(H * (0.1 + 0.75 * ((i * 61 + k * 29) % 100) / 100))
            spin = 120 if (i + k) % 2 else -120
            add(0, a, b, "Shape",
                rf"{{\pos({sx},{sy})\org({sx + size // 2},{sy + size // 2})\alpha&HD8&{fade}\frx20\t(0,{dur_ms},\frz{spin}\fry{spin * 1.5:.0f})\p1}}"
                f"m 0 0 l {size} 0 {size} {size} 0 {size}{{\\p0}}")

        cx, cy = W // 2, int(H * 0.46)
        vis = s["visual"]
        text = _emph(s["screen_text"], s.get("emphasis", ""), ACC, TXT)
        if vis == "lista":
            add(3, a, b, "Mid", "{" + _motion(s["motion"], cx, int(H * 0.24), W, dur_ms) + fade + "}" + text)
            items = [x for x in s.get("bullets", []) if x.strip()][:4] or [s["narration"][:40]]
            step = (b - a) * 0.75 / max(1, len(items))
            for j, item in enumerate(items):
                ia = a + 0.35 + j * step
                y = int(H * (0.36 + 0.1 * j))
                x = int(W * 0.12)
                add(3, ia, b, "Item",
                    rf"{{\an4\move({x - int(W * 0.15)},{y},{x},{y},0,300)\fad(200,200)\blur2\t(0,300,\blur0)}}"
                    + r"{\c" + ACC + r"}● {\c" + TXT + "}" + _clean(item))
        elif vis == "numero":
            raw = s["screen_text"].strip()
            num = ""
            for ch in raw:
                if ch.isdigit() or (num and ch in ".,"):
                    num += ch
                elif num:
                    break
            rest = raw[raw.find(num) + len(num):] if num else raw
            big = int(base * 0.26)
            if num and num.replace(".", "").replace(",", "").isdigit() and float(num.replace(",", ".")) >= 2:
                target = float(num.replace(",", "."))
                steps = 12
                for k in range(steps):
                    val = target * (k + 1) / steps
                    shown = (f"{val:.1f}".replace(".", ",") if "," in num or "." in num else str(int(round(val))))
                    ka = a + k * 0.06
                    kb = a + (k + 1) * 0.06 if k < steps - 1 else b
                    add(3, ka, kb, "Big", rf"{{\pos({cx},{int(H * 0.4)})\fs{big}\c{ACC}{r'\fad(120,0)' if k == 0 else ''}{r'\fad(0,200)' if k == steps - 1 else ''}}}{shown}{_clean(rest[:1]) if rest[:1] in '%x' else ''}")
                rest = rest[1:] if rest[:1] in "%x" else rest
            else:
                add(3, a, b, "Big", rf"{{\pos({cx},{int(H * 0.4)})\fs{big}\c{ACC}{fade}}}{_clean(raw)}")
                rest = ""
            label = rest.strip() or (s.get("bullets") or [""])[0]
            if label:
                add(3, a + 0.4, b, "Mid", "{" + _motion("flip3d", cx, int(H * 0.56), W, dur_ms) + fade + "}" + _clean(label))
        elif vis == "citacao":
            add(2, a, b, "Big", rf"{{\pos({int(W * 0.18)},{int(H * 0.3)})\fs{int(base * 0.4)}\c{ACC}\alpha&H40&\frz-8{fade}}}“")
            add(3, a, b, "Mid", r"{\i1" + _motion(s["motion"], cx, cy, W, dur_ms) + fade + "}" + text)
        elif vis == "avatar":
            add(3, a, b, "Mid", "{" + _motion(s["motion"], cx, int(H * 0.68), W, dur_ms) + fade + "}" + text)
        elif vis == "logo":
            if brand.get("name"):
                add(3, a + 0.3, b, "Mid", "{" + _motion("giro3d", cx, int(H * 0.6), W, dur_ms) + fade + "}" + _clean(brand["name"]))
            cta = s["screen_text"] or brand.get("cta") or ""
            if cta:
                add(4, a + 0.7, b, "Box", rf"{{\pos({cx},{int(H * 0.7)})\fscx60\fscy60\t(0,250,\fscx100\fscy100){fade}}}{_clean(cta).upper()}")
        elif s["motion"] == "digitar":
            words = text.split(" ")
            step = min(0.18, (b - a) * 0.5 / max(1, len(words)))
            for k in range(len(words)):
                shown = " ".join(words[:k + 1]) + r"{\alpha&HFF&} " + " ".join(words[k + 1:])
                ka = a + k * step
                kb = a + (k + 1) * step if k < len(words) - 1 else b
                add(3, ka, kb, "Big", rf"{{\pos({cx},{cy}){r'\fad(0,200)' if k == len(words) - 1 else ''}}}" + shown)
        else:
            add(3, a, b, "Big", "{" + _motion(s["motion"], cx, cy, W, dur_ms) + fade + "}" + text)
    return "\n".join(header + ev) + "\n"


def _darken(hex_color: str, f: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"0x{int(r * f):02x}{int(g * f):02x}{int(b * f):02x}"


def render_motion(scenes: list, workdir: Path, fmt: str, brand: dict, music: Path | None,
                  out_name: str = "source.mp4", on_progress=None) -> Path:
    W, H = output_size(fmt, {"width": 1080, "height": 1920})
    total = scenes[-1]["end"]
    (workdir / "motion.ass").write_text(build_motion_ass(scenes, W, H, brand, total), encoding="utf-8")
    c = brand["colors"]
    inputs = ["-f", "lavfi", "-i",
              f"gradients=s={W}x{H}:r=30:d={total:.3f}:nb_colors=3:speed=0.012:"
              f"c0={_darken(c['primary'], 0.55)}:c1={_darken(c['secondary'], 0.45)}:c2=0x0b0b10:type=linear"]
    graph = ["[0:v]vignette=PI/4,format=yuv420p[bg]"]
    cur = "bg"
    n_in = 1
    fps = 30

    avatar = brandkit.BRAND_DIR / "avatar_round.png"
    av_scenes = [s for s in scenes if s["visual"] == "avatar"]
    if av_scenes and avatar.exists():
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{total:.3f}", "-i", str(avatar)]
        aw = int(min(W, H) * 0.58) // 2 * 2
        graph.append(f"[{n_in}:v]scale={aw}:{aw},format=rgba,split={len(av_scenes)}" + "".join(f"[av{k}]" for k in range(len(av_scenes))))
        for k, s in enumerate(av_scenes):
            a, b = s["start"], s["end"]
            graph.append(f"[av{k}]fade=t=in:st={a:.3f}:d=0.35:alpha=1,fade=t=out:st={max(a, b - 0.3):.3f}:d=0.3:alpha=1[avf{k}]")
            graph.append(f"[{cur}][avf{k}]overlay=x=(W-w)/2:y={int(H * 0.36)}-h/2+14*sin(2*t):enable='between(t,{a:.3f},{b:.3f})'[o{n_in}_{k}]")
            cur = f"o{n_in}_{k}"
        n_in += 1

    logo = brandkit.path("logo")
    if logo:
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{total:.3f}", "-i", str(logo)]
        lg_scenes = [s for s in scenes if s["visual"] == "logo"]
        graph.append(f"[{n_in}:v]format=rgba,split=2[lga][lgb]")
        small = int(W * 0.16) // 2 * 2
        not_logo = "+".join(f"between(t,{s['start']:.3f},{s['end']:.3f})" for s in lg_scenes) or "0"
        if brand.get("watermark", True):
            graph.append(f"[lga]scale={small}:-1,colorchannelmixer=aa=0.85[lgs]")
            graph.append(f"[{cur}][lgs]overlay=W-w-{int(W * 0.04)}:{int(W * 0.04)}:enable='not({not_logo})'[wm]")
            cur = "wm"
        else:
            graph.append("[lga]nullsink")
        if lg_scenes:
            big = int(min(W, H) * 0.5) // 2 * 2
            graph.append(f"[lgb]scale={big}:-1,split={len(lg_scenes)}" + "".join(f"[lb{k}]" for k in range(len(lg_scenes))))
            for k, s in enumerate(lg_scenes):
                a, b = s["start"], s["end"]
                graph.append(f"[lb{k}]fade=t=in:st={a:.3f}:d=0.5:alpha=1[lbf{k}]")
                graph.append(f"[{cur}][lbf{k}]overlay=(W-w)/2:{int(H * 0.4)}-h/2:enable='between(t,{a:.3f},{b:.3f})'[lo{k}]")
                cur = f"lo{k}"
        else:
            graph.append("[lgb]nullsink")
        n_in += 1
    graph.append(f"[{cur}]ass=motion.ass[vout]")

    # áudio: narração de cada cena no seu tempo + música opcional
    voiced = [s for s in scenes if s.get("audio")]
    for s in voiced:
        inputs += ["-i", s["audio"]]
    labels = []
    for k, s in enumerate(voiced):
        idx = n_in + k
        delay = int(s["start"] * 1000)
        graph.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}|{delay}[n{k}]")
        labels.append(f"[n{k}]")
    n_in += len(voiced)
    graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={total:.3f}[sil]")
    graph.append(f"[sil]{''.join(labels)}amix=inputs={len(labels) + 1}:duration=first:normalize=0[voz]")
    if music and music.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music.resolve())]
        vol = 0.12 if voiced else 0.5
        graph.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},atrim=duration={total:.3f}[m]")
        if voiced:
            graph.append("[voz]asplit=2[v1][v2]")
            graph.append("[m][v2]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md]")
            graph.append("[v1][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
        else:
            graph.append(f"[voz][m]amix=inputs=2:duration=first:normalize=0,afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[aout]")
    else:
        graph.append("[voz]anull[aout]")

    (workdir / "motion.filter").write_text(";\n".join(graph), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error", "-progress", "pipe:1", *inputs,
           "-filter_complex_script", "motion.filter", "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", out_name]
    proc = subprocess.Popen(cmd, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if line.startswith("out_time_us=") and on_progress:
            try:
                on_progress(min(0.99, int(line.split("=")[1]) / 1e6 / total))
            except ValueError:
                pass
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg falhou: {err.strip()[-800:]}")
    return workdir / out_name


def transcript_from_scenes(scenes: list) -> dict:
    segs = []
    for i, s in enumerate(scenes):
        words = s.get("words") or []
        segs.append({"id": i, "start": s["start"], "end": s["end"],
                     "text": s["narration"] if words else s["screen_text"], "words": words})
    return {"source": "tts" if any(s.get("words") for s in scenes) else "roteiro", "segments": segs}


def save_script(workdir: Path, script: dict, scenes: list):
    clean = [{k: v for k, v in s.items() if k != "words"} for s in scenes]
    (workdir / "script.json").write_text(json.dumps({**script, "scenes": clean}, ensure_ascii=False, indent=2), encoding="utf-8")

