"""Tour virtual a partir das fotos do Airbnb.

- Foto panorâmica 360° (proporção 2:1): vira uma esfera e você olha para todos os lados.
- Foto comum: vira uma "parede curva" em 3D com profundidade, para explorar arrastando.
Os cômodos são ligados por portas (pontos clicáveis) e o tour pode virar vídeo ou um site.
"""
import base64
import io
import json
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

from . import ai, brand as brandkit

ROOT = Path(__file__).resolve().parent.parent
TOURS = ROOT / "data" / "tours"
TOURS.mkdir(parents=True, exist_ok=True)


def tour_dir(tid: str) -> Path:
    d = TOURS / tid
    if not tid.isalnum() or not (d / "tour.json").exists():
        raise FileNotFoundError(tid)
    return d


def load(tid: str) -> dict:
    return json.loads((tour_dir(tid) / "tour.json").read_text(encoding="utf-8"))


def save(tour: dict):
    f = TOURS / tour["id"] / "tour.json"
    f.write_text(json.dumps(tour, ensure_ascii=False, indent=2), encoding="utf-8")


def create(name: str) -> dict:
    tid = uuid.uuid4().hex[:10]
    (TOURS / tid / "photos").mkdir(parents=True)
    tour = {"id": tid, "name": name.strip() or "Meu Airbnb", "listing": {"title": "", "description": "", "highlights": []},
            "start": None, "rooms": []}
    save(tour)
    return tour


def list_tours() -> list:
    out = []
    for f in TOURS.glob("*/tour.json"):
        t = json.loads(f.read_text(encoding="utf-8"))
        out.append({"id": t["id"], "name": t["name"], "rooms": len(t["rooms"]),
                    "cover": t["rooms"][0]["photo"] if t["rooms"] else None})
    return out


def add_photo(tid: str, filename: str, raw: bytes) -> dict:
    from PIL import Image, ImageOps

    tour = load(tid)
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    w, h = img.size
    kind = "360" if 1.85 <= w / h <= 2.15 and w >= 2000 else "foto"
    img.thumbnail((6144, 3072) if kind == "360" else (3000, 3000))
    rid = uuid.uuid4().hex[:8]
    name = f"{rid}.jpg"
    d = tour_dir(tid)
    img.save(d / "photos" / name, quality=88)
    thumb = img.copy()
    thumb.thumbnail((360, 360))
    thumb.save(d / "photos" / f"{rid}_t.jpg", quality=80)
    room = {"id": rid, "name": Path(filename).stem[:40] or "Cômodo", "photo": name, "thumb": f"{rid}_t.jpg",
            "kind": kind, "ratio": round(img.width / img.height, 4), "desc": "", "links": [], "yaw": 0}
    tour["rooms"].append(room)
    tour["start"] = tour["start"] or rid
    save(tour)
    return tour


def update(tid: str, changes: dict) -> dict:
    tour = load(tid)
    ids = {r["id"]: r for r in tour["rooms"]}
    if "name" in changes:
        tour["name"] = str(changes["name"])[:80]
    if "listing" in changes and isinstance(changes["listing"], dict):
        tour["listing"].update({k: v for k, v in changes["listing"].items() if k in ("title", "description", "highlights")})
    if "rooms" in changes:
        rooms = []
        for r in changes["rooms"]:
            old = ids.get(r.get("id"))
            if not old:
                continue
            old["name"] = str(r.get("name", old["name"]))[:40]
            old["desc"] = str(r.get("desc", old["desc"]))[:600]
            old["kind"] = r.get("kind") if r.get("kind") in ("360", "foto") else old["kind"]
            old["yaw"] = float(r.get("yaw", old.get("yaw", 0)))
            old["links"] = [
                {"to": l["to"], "yaw": float(l["yaw"]), "pitch": float(l.get("pitch", 0)), "label": str(l.get("label", ""))[:30]}
                for l in r.get("links", old["links"]) if l.get("to") in ids
            ]
            rooms.append(old)
        removed = set(ids) - {r["id"] for r in rooms}
        for rid in removed:
            for f in (ids[rid]["photo"], ids[rid]["thumb"]):
                (tour_dir(tid) / "photos" / f).unlink(missing_ok=True)
        for r in rooms:
            r["links"] = [l for l in r["links"] if l["to"] not in removed]
        tour["rooms"] = rooms
    if changes.get("start") in {r["id"] for r in tour["rooms"]}:
        tour["start"] = changes["start"]
    if tour["start"] not in {r["id"] for r in tour["rooms"]}:
        tour["start"] = tour["rooms"][0]["id"] if tour["rooms"] else None
    save(tour)
    return tour


def delete(tid: str):
    shutil.rmtree(tour_dir(tid))


DESCRIBE_SYSTEM = """Você é especialista em anúncios do Airbnb no Brasil. Você recebe as fotos de um imóvel, em ordem,
cada uma com um id. Para cada foto diga qual cômodo é, escreva uma descrição curta e vendedora (1 ou 2 frases, sem exageros
e sem inventar o que não aparece na foto) e quais outros cômodos fazem sentido ligar a ele (portas do tour).
Sugira também a ordem ideal da visita (começando pela entrada ou pela área mais bonita) e o texto do anúncio."""

DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "rooms": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "name": {"type": "string"}, "desc": {"type": "string"},
            "connects_to": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "name", "desc", "connects_to"], "additionalProperties": False}},
        "order": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "highlights": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rooms", "order", "title", "description", "highlights"],
    "additionalProperties": False,
}


def describe(tid: str, config: dict) -> tuple[dict, dict]:
    from PIL import Image

    tour = load(tid)
    if not tour["rooms"]:
        raise ai.AIError("Envie as fotos primeiro.")
    content = []
    for r in tour["rooms"][:20]:
        img = Image.open(tour_dir(tid) / "photos" / r["photo"])
        img.thumbnail((640, 640))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=70)
        content.append({"type": "text", "text": f"Foto id={r['id']} ({'panorâmica 360' if r['kind'] == '360' else 'foto'}):"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(buf.getvalue()).decode()}})
    content.append({"type": "text", "text": f"Imóvel: {tour['name']}. Descreva os cômodos e o anúncio."})
    result, usage = ai.call_json(config, DESCRIBE_SYSTEM, content, DESCRIBE_SCHEMA)

    by_id = {r["id"]: r for r in tour["rooms"]}
    for item in result["rooms"]:
        r = by_id.get(item["id"])
        if not r:
            continue
        r["name"] = item["name"][:40]
        r["desc"] = item["desc"][:600]
        existing = {l["to"] for l in r["links"]}
        new = [t for t in item["connects_to"] if t in by_id and t != r["id"] and t not in existing][:4]
        # espalha as portas sugeridas ao redor de quem está olhando
        for k, target in enumerate(new):
            r["links"].append({"to": target, "yaw": round(-40 + 80 * (k / max(1, len(new) - 1)) if len(new) > 1 else 0, 1),
                               "pitch": -8, "label": ""})
    order = [i for i in result["order"] if i in by_id]
    order += [i for i in by_id if i not in order]
    tour["rooms"] = [by_id[i] for i in order]
    tour["start"] = order[0]
    tour["listing"] = {"title": result["title"], "description": result["description"], "highlights": result["highlights"][:8]}
    save(tour)
    return tour, usage


def _ass_time(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def make_video(tid: str, out: Path, seconds_per_room: float = 4.0, music: Path | None = None) -> Path:
    """Vídeo do tour: movimento de câmera em cada foto (ou giro na 360°) com o nome do cômodo."""
    tour = load(tid)
    rooms = tour["rooms"]
    if not rooms:
        raise ValueError("O tour não tem fotos.")
    d = tour_dir(tid)
    W, H, fps = 1080, 1920, 30
    frames = int(seconds_per_room * fps)
    b = brandkit.load()
    acc = brandkit.ass_color(b["colors"]["accent"])
    inputs, graph, labels = [], [], []
    for i, r in enumerate(rooms):
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{seconds_per_room}", "-i", str(d / "photos" / r["photo"])]
        if r["kind"] == "360":
            # gira a câmera dentro da panorâmica (recorte deslizando na horizontal)
            graph.append(
                f"[{i}:v]scale=-2:{H},crop={W}:{H}:x='(iw-{W})*t/{seconds_per_room}':y=0,setsar=1,format=yuv420p[r{i}]")
        else:
            zoom_in = i % 2 == 0
            z = f"'min(1.0+0.0009*on,1.25)'" if zoom_in else f"'max(1.25-0.0009*on,1.0)'"
            graph.append(
                f"[{i}:v]scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                f"zoompan=z={z}:x='iw/2-(iw/zoom/2)+{'1' if i % 3 else '-1'}*on*0.6':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={fps},"
                f"setsar=1,format=yuv420p[r{i}]")
        labels.append(f"[r{i}]")
    # transições suaves entre os cômodos
    cur = labels[0]
    offset = seconds_per_room
    for i in range(1, len(labels)):
        offset_x = offset - 0.5 * i
        graph.append(f"{cur}{labels[i]}xfade=transition=fade:duration=0.5:offset={offset_x:.3f}[x{i}]")
        cur = f"[x{i}]"
        offset += seconds_per_room
    total = seconds_per_room * len(rooms) - 0.5 * (len(rooms) - 1)

    base = W
    ass = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           f"Style: Room,Inter,{int(base * 0.085)},&H00FFFFFF,{acc},&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,0,4,1,80,80,240,1",
           f"Style: Desc,Inter,{int(base * 0.04)},&H00FFFFFF,{acc},&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,0,3,1,80,80,170,1",
           f"Style: Title,Inter,{int(base * 0.075)},&H00FFFFFF,{acc},&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,0,4,5,80,80,0,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    t = 0.0
    for i, r in enumerate(rooms):
        a, e = t + 0.3, t + seconds_per_room - 0.3
        ass.append(f"Dialogue: 1,{_ass_time(a)},{_ass_time(e)},Room,,0,0,0,,{{\\fad(250,250)\\move(40,{H - 240},80,{H - 240},0,400)}}{r['name']}")
        if r.get("desc"):
            short = r["desc"].split(". ")[0][:90]
            ass.append(f"Dialogue: 1,{_ass_time(a + 0.3)},{_ass_time(e)},Desc,,0,0,0,,{{\\fad(250,250)}}{short}")
        t += seconds_per_room - 0.5
    title = tour["listing"].get("title") or tour["name"]
    ass.append(f"Dialogue: 2,{_ass_time(0)},{_ass_time(2.2)},Title,,0,0,0,,{{\\fad(0,300)\\fry-90\\t(0,500,\\fry0)}}{title}")
    (d / "tour.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")
    graph.append(f"{cur}ass=tour.ass[vout]")
    n = len(rooms)
    if music and music.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music.resolve())]
        graph.append(f"[{n}:a]volume=0.6,atrim=duration={total:.2f},afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5[aout]")
    else:
        graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={total:.2f}[aout]")
    (d / "tour.filter").write_text(";\n".join(graph), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex_script", "tour.filter", "-map", "[vout]",
           "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out.resolve())]
    res = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {res.stderr[-600:]}")
    return out


def export_zip(tid: str, web_dir: Path) -> bytes:
    """Um site pronto (pasta .zip) para publicar em qualquer hospedagem grátis (Netlify, GitHub Pages…)."""
    tour = load(tid)
    d = tour_dir(tid)
    buf = io.BytesIO()
    html = (web_dir / "tour.html").read_text(encoding="utf-8").replace(
        "<!--STATIC-->", "<script>window.TOUR_STATIC = true;</script>")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", html)
        z.writestr("tour.json", json.dumps(tour, ensure_ascii=False))
        for f in ("tour.css", "tour.js", "vendor/three.module.min.js", "vendor/three.LICENSE"):
            z.write(web_dir / f, f)
        for r in tour["rooms"]:
            z.write(d / "photos" / r["photo"], f"photos/{r['photo']}")
            z.write(d / "photos" / r["thumb"], f"photos/{r['thumb']}")
    return buf.getvalue()
