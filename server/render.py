"""Renderiza a timeline com ffmpeg: cortes, reenquadramento, zoom, legendas, textos e música."""
import math
import re
import subprocess
from pathlib import Path

from . import brand as brandkit, overlays
from .timeline import caption_lines, output_size

WHITE = "&H00FFFFFF"
BLACK = "&H00000000"


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(timeline: dict, width: int, height: int, brand: dict | None = None) -> str:
    colors = (brand or brandkit.load())["colors"]
    ACCENT = brandkit.ass_color(colors["accent"])
    PRIMARY = brandkit.ass_color(colors["primary"])
    base = min(width, height)
    cap = timeline["captions"]
    cap_style = cap.get("style", "viral")
    # Alinhamento ASS: 2 = embaixo, 5 = centro, 8 = topo.
    cap_align = {"bottom": 2, "middle": 2, "top": 8}.get(cap.get("position"), 2)
    cap_margin = int(height * (0.30 if cap.get("position") == "middle" else 0.08))
    cap_size = int(base * (0.085 if cap_style == "viral" else 0.06))
    if cap_style == "palavra":
        cap_margin = int(height * {"middle": 0.24, "top": 0.1}.get(cap.get("position"), 0.15))
        cap_size = int(base * 0.09)

    styles = [
        # Nome, fonte, tamanho, cor, cor da borda, cor do fundo, negrito, borda, contorno, sombra, alinhamento, margem vertical
        ("Legenda", cap_size, WHITE, BLACK, "&H80000000", -1, 1, max(3, cap_size // 9), 2, cap_align, cap_margin),
        ("gancho", int(base * 0.10), WHITE, BLACK, "&H80000000", -1, 1, int(base * 0.012), 3, 8, int(height * 0.12)),
        ("titulo", int(base * 0.11), WHITE, BLACK, "&H00000000", -1, 1, int(base * 0.004), 0, 5, 0),
        ("destaque", int(base * 0.07), BLACK, ACCENT, ACCENT, -1, 3, int(base * 0.02), 0, 5, 0),
        ("rodape", int(base * 0.05), WHITE, PRIMARY, PRIMARY, -1, 3, int(base * 0.018), 0, 1, int(height * 0.06)),
        ("cta", int(base * 0.075), BLACK, ACCENT, ACCENT, -1, 3, int(base * 0.022), 0, 2, int(height * 0.18)),
    ]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    margin_h = int(width * 0.07)
    if cap_style == "palavra":
        styles[0] = ("Legenda", cap_size, WHITE, "&H00202020", "&H90000000", -1, 1, max(2, cap_size // 22), 3, cap_align, cap_margin)
    for name, size, primary, outline, back, bold, border, out_w, shadow, align, mv in styles:
        lines.append(
            f"Style: {name},Inter,{size},{primary},{ACCENT},{outline},{back},{bold},0,0,0,"
            f"100,100,0,0,{border},{out_w},{shadow},{align},{margin_h},{margin_h},{mv},1"
        )
    lines.append(overlays.ass_style(width))
    lines += ["", "[Events]",
              "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    pop = r"{\fad(120,120)\fscx85\fscy85\t(0,140,\fscx100\fscy100)}"
    for t in timeline["texts"]:
        if t["style"] in overlays.RICH_STYLES:
            lines += overlays.events(t, width, height, brand)
            continue
        text = _esc(t["text"])
        if t["style"] in ("gancho", "titulo", "cta"):
            text = text.upper() if t["style"] != "titulo" else text
        lines.append(f"Dialogue: 2,{_ass_time(t['start'])},{_ass_time(t['end'])},{t['style']},,0,0,0,,{pop}{text}")

    if cap.get("enabled"):
        for group in caption_lines(timeline["caption_words"], int(cap.get("words") or 3)):
            if cap_style == "palavra":
                # uma palavra por vez, entrando com um pulinho
                for w in group:
                    lines.append(f"Dialogue: 1,{_ass_time(w['s'])},{_ass_time(max(w['e'], w['s'] + 0.12))},Legenda,,0,0,0,,"
                                 + r"{\fscx88\fscy88\t(0,90,\fscx100\fscy100)}" + _esc(w["w"]))
            elif cap_style == "viral":
                # Um evento por palavra: a palavra que está sendo falada fica amarela.
                for i, w in enumerate(group):
                    end = group[i + 1]["s"] if i + 1 < len(group) else w["e"] + 0.15
                    parts = []
                    for j, other in enumerate(group):
                        word = _esc(other["w"]).upper()
                        parts.append(r"{\c" + ACCENT + r"\fscx108\fscy108}" + word + r"{\r}" if j == i else word)
                    lines.append(f"Dialogue: 1,{_ass_time(w['s'])},{_ass_time(end)},Legenda,,0,0,0,,{' '.join(parts)}")
            else:
                text = " ".join(_esc(w["w"]) for w in group)
                lines.append(f"Dialogue: 1,{_ass_time(group[0]['s'])},{_ass_time(group[-1]['e'] + 0.15)},Legenda,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def build_srt(timeline: dict) -> str:
    out = []
    groups = caption_lines(timeline["caption_words"], int(timeline["captions"].get("words") or 6))
    for n, g in enumerate(groups, 1):
        def ts(t):
            ms = int(round(t * 1000))
            return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        out.append(f"{n}\n{ts(g[0]['s'])} --> {ts(g[-1]['e'])}\n{' '.join(w['w'] for w in g)}\n")
    return "\n".join(out)


def build_filter(timeline: dict, info: dict, width: int, height: int, fps: int,
                 ass_name: str | None, music_input: bool, logo_input: int | None = None,
                 rich: dict | None = None) -> str:
    src_w, src_h = info["width"], info["height"]
    parts, labels = [], []
    for i, c in enumerate(timeline["clips"]):
        a, b, z = c["src_in"], c["src_out"], c["zoom"]
        scale = max(width / src_w, height / src_h) * z
        sw = max(width, math.ceil(src_w * scale / 2) * 2)
        sh = max(height, math.ceil(src_h * scale / 2) * 2)
        parts.append(
            f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,"
            f"scale={sw}:{sh},crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v{i}]"
        )
        dur = b - a
        if info["has_audio"]:
            fade = min(0.03, dur / 4)
            parts.append(
                f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates=48000:channel_layouts=stereo,"
                f"afade=t=in:d={fade},afade=t=out:st={dur - fade:.3f}:d={fade}[a{i}]"
            )
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={dur}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=1[vc][ac]")
    cur = "vc"
    if rich and (rich["glass"] or rich["images"]):
        cur = _rich_filters(parts, cur, rich)
    parts.append(f"[{cur}]ass={ass_name}[vs]" if ass_name else f"[{cur}]null[vs]")
    if logo_input is not None:
        lw = int(width * 0.16) // 2 * 2
        margin = int(width * 0.04)
        parts.append(f"[{logo_input}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa=0.85[lg]")
        parts.append(f"[vs][lg]overlay=W-w-{margin}:{margin}[vout]")
    else:
        parts.append("[vs]null[vout]")

    music = timeline["music"]
    if music_input:
        vol = float(music.get("volume") or 0.12)
        parts.append(f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol}[m]")
        if music.get("duck", True):
            # A música abaixa sozinha quando você fala.
            parts.append("[ac]asplit=2[voz][chave]")
            parts.append("[m][chave]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md]")
            parts.append("[voz][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
        else:
            parts.append("[ac][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    else:
        parts.append("[ac]anull[aout]")
    return ";\n".join(parts)


def _rich_filters(parts: list, cur: str, rich: dict) -> str:
    """Vidro fosco (desfoque real do vídeo atrás do card) e imagens de antes/depois com cantos redondos."""
    glass = [g for g in rich["glass"] if not g.get("dim")]
    dims = [g for g in rich["glass"] if g.get("dim")]
    if glass:
        parts.append(f"[{cur}]split=2[rb][rbl0]")
        parts.append(f"[rbl0]boxblur=22:3,split={len(glass)}" + "".join(f"[gb{k}]" for k in range(len(glass))))
        cur = "rb"
        for k, g in enumerate(glass):
            a, b = g["a"], g["b"]
            parts.append(
                f"[gb{k}]crop={g['w']}:{g['h']}:{g['x']}:{g['y']},format=rgba[gc{k}];"
                f"[gc{k}][{g['mask']}:v]alphamerge,fade=t=in:st={a:.3f}:d=0.2:alpha=1,"
                f"fade=t=out:st={max(a, b - 0.2):.3f}:d=0.2:alpha=1[gm{k}];"
                f"[{cur}][gm{k}]overlay={g['x']}:{g['y']}:enable='between(t,{a:.3f},{b:.3f})'[go{k}]")
            cur = f"go{k}"
    for k, g in enumerate(dims):
        en = f"between(t,{g['a']:.3f},{g['b']:.3f})"
        parts.append(f"[{cur}]boxblur=12:2:enable='{en}',drawbox=c=black@0.55:t=fill:enable='{en}'[gd{k}]")
        cur = f"gd{k}"
    for k, im in enumerate(rich["images"]):
        a, b = im["a"], im["b"]
        parts.append(
            f"[{im['input']}:v]scale={im['w']}:{im['h']}:force_original_aspect_ratio=increase,crop={im['w']}:{im['h']},"
            f"setsar=1,format=rgba[ii{k}];[ii{k}][{im['mask']}:v]alphamerge,fade=t=in:st={a:.3f}:d=0.3:alpha=1,"
            f"fade=t=out:st={max(a, b - 0.2):.3f}:d=0.2:alpha=1[im{k}];"
            f"[{cur}][im{k}]overlay={im['x']}:{im['y']}:enable='between(t,{a:.3f},{b:.3f})'[io{k}]")
        cur = f"io{k}"
    return cur


def render(project_dir: Path, source: Path, timeline: dict, info: dict, music_path: Path | None,
           out_name: str, quality: str = "alta", on_progress=None) -> Path:
    width, height = output_size(timeline["format"], info)
    fps = 30 if info["fps"] > 31 or info["fps"] < 23 else round(info["fps"])
    ass_name = None
    if timeline["captions"].get("enabled") or timeline["texts"]:
        ass_name = "render.ass"
        (project_dir / ass_name).write_text(build_ass(timeline, width, height, brandkit.load()), encoding="utf-8")
    (project_dir / "legendas.srt").write_text(build_srt(timeline), encoding="utf-8")

    use_music = bool(timeline["music"].get("enabled") and music_path and music_path.exists())
    logo = brandkit.path("logo") if timeline.get("logo") else None
    logo_input = (2 if use_music else 1) if logo else None
    extra_inputs = []
    next_input = 1 + int(use_music) + int(bool(logo))
    rich = {"glass": [], "images": []}
    total_t = f"{timeline['duration'] + 1:.2f}"
    for t in timeline["texts"]:
        if t["style"] not in overlays.RICH_STYLES:
            continue
        glass, images = overlays.regions(t, width, height, project_dir)
        for item in glass + images:
            if item.get("dim"):
                continue
            mask = overlays.mask_png(project_dir, item["w"], item["h"], item["r"])
            extra_inputs += ["-loop", "1", "-t", total_t, "-i", str(mask.resolve())]
            item["mask"] = next_input
            next_input += 1
        for im in images:
            extra_inputs += ["-loop", "1", "-t", total_t, "-i", str(Path(im["path"]).resolve())]
            im["input"] = next_input
            next_input += 1
        rich["glass"] += glass
        rich["images"] += images
    graph = build_filter(timeline, info, width, height, fps, ass_name, use_music, logo_input, rich)
    (project_dir / "render.filter").write_text(graph, encoding="utf-8")

    crf = {"alta": "18", "media": "21", "rapida": "25"}.get(quality, "20")
    preset = {"alta": "medium", "media": "veryfast", "rapida": "ultrafast"}.get(quality, "veryfast")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error", "-progress", "pipe:1", "-i", source.name]
    if use_music:
        cmd += ["-stream_loop", "-1", "-i", str(music_path.resolve())]
    if logo:
        cmd += ["-i", str(logo.resolve())]
    cmd += extra_inputs
    cmd += [
        "-filter_complex_script", "render.filter", "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(timeline["duration"]),
        out_name,
    ]
    # Roda dentro da pasta do projeto para o filtro de legenda achar o .ass sem escapar caminhos.
    proc = subprocess.Popen(cmd, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    total = max(0.1, timeline["duration"])
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and on_progress:
            on_progress(min(0.99, int(m.group(1)) / 1e6 / total))
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg falhou: {err.strip()[-800:]}")
    return project_dir / out_name
