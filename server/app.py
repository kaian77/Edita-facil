"""Edita Fácil — servidor local. Rode com:  python -m server  (na pasta do projeto)."""
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, media, render, timeline as tl, transcribe

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
MUSIC = ROOT / "music"
WEB = ROOT / "web"
PRESETS = Path(__file__).resolve().parent / "presets"
CONFIG = ROOT / "config.json"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}

PROJECTS.mkdir(exist_ok=True)
MUSIC.mkdir(exist_ok=True)
_lock = threading.Lock()

app = FastAPI(title="Edita Fácil")


# ---------- armazenamento ----------

def load_config() -> dict:
    cfg = {"api_key": "", "model": ai.DEFAULT_MODEL, "effort": "medium", "language": "pt"}
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    if not cfg["api_key"]:
        cfg["api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    return cfg


def load_presets() -> dict:
    items = [json.loads(p.read_text(encoding="utf-8")) for p in PRESETS.glob("*.json")]
    return {p["id"]: p for p in sorted(items, key=lambda p: p.get("order", 99))}


def project_dir(pid: str) -> Path:
    d = PROJECTS / pid
    if not pid.isalnum() or not (d / "project.json").exists():
        raise HTTPException(404, "Projeto não encontrado.")
    return d


def load_project(pid: str) -> dict:
    return json.loads((project_dir(pid) / "project.json").read_text(encoding="utf-8"))


def save_project(p: dict):
    with _lock:
        path = PROJECTS / p["id"] / "project.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def update_project(pid: str, **fields) -> dict:
    p = load_project(pid)
    p.update(fields)
    save_project(p)
    return p


def load_transcript(pid: str) -> dict:
    return json.loads((PROJECTS / pid / "transcript.json").read_text(encoding="utf-8"))


def public(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k != "history"}
    out["can_undo"] = bool(p.get("history"))
    return out


# ---------- análise em segundo plano ----------

def analyze(pid: str):
    d = PROJECTS / pid
    p = load_project(pid)
    try:
        source = d / p["source"]
        update_project(pid, status="analisando", status_text="Lendo o vídeo…", progress=0.05)
        info = media.probe(source)
        update_project(pid, info=info, status_text="Gerando miniaturas…", progress=0.08)
        media.make_thumbnails(source, d / "thumbs")
        update_project(pid, status_text="Preparando o preview…", progress=0.12)
        if media.make_proxy(source, d / "preview.mp4"):
            update_project(pid, preview="preview.mp4")
        peaks = media.waveform_peaks(source) if info["has_audio"] else []
        (d / "peaks.json").write_text(json.dumps(peaks))
        update_project(pid, status_text="Transcrevendo a fala (local, sem gastar tokens)…", progress=0.2)

        def prog(x):
            update_project(pid, progress=round(0.2 + 0.75 * x, 3))

        if info["has_audio"]:
            tr = transcribe.transcribe(source, info["duration"], load_config().get("language", "pt"), prog)
        else:
            tr = {"source": "silence", "segments": [{"id": 0, "start": 0, "end": info["duration"], "text": "", "words": []}]}
        (d / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False))

        presets = load_presets()
        preset = presets.get(p.get("preset")) or next(iter(presets.values()))
        first = tl.build(tl.local_plan(tr, preset), tr, info, preset)
        first["summary"] = ""
        notes = []
        if tr["source"] != "whisper":
            notes.append(tr.get("warning") or "Transcrição indisponível: instale o faster-whisper para legendas e cortes inteligentes.")
        update_project(
            pid, status="pronto", status_text="Pronto", progress=1.0, timeline=first,
            transcript_source=tr["source"], transcript_text=" ".join(s["text"] for s in tr["segments"]).strip(),
            notes=notes,
        )
    except Exception as exc:
        update_project(pid, status="erro", status_text=f"Erro ao analisar: {exc}")


# ---------- API ----------

class ConfigIn(BaseModel):
    api_key: str | None = None
    model: str | None = None
    effort: str | None = None
    language: str | None = None


class EditIn(BaseModel):
    preset: str
    request: str = ""
    fresh: bool = False  # True = começar do zero, ignorando o plano atual


class TimelineIn(BaseModel):
    timeline: dict


class RenderIn(BaseModel):
    quality: str = "media"


@app.get("/api/config")
def get_config():
    cfg = load_config()
    key = cfg["api_key"]
    return {
        "has_key": bool(key), "key_hint": f"…{key[-4:]}" if key else "",
        "model": cfg["model"], "effort": cfg["effort"], "language": cfg["language"],
        "models": [{"id": k, "name": v[0]} for k, v in ai.MODELS.items()],
        "whisper": transcribe.whisper_available(),
    }


@app.post("/api/config")
def set_config(body: ConfigIn):
    cfg = load_config() if CONFIG.exists() else {}
    for k, v in body.model_dump(exclude_none=True).items():
        cfg[k] = v.strip() if isinstance(v, str) else v
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return get_config()


@app.get("/api/presets")
def get_presets():
    return list(load_presets().values())


@app.get("/api/projects")
def list_projects():
    out = []
    for f in PROJECTS.glob("*/project.json"):
        p = json.loads(f.read_text(encoding="utf-8"))
        out.append({k: p.get(k) for k in ("id", "name", "created", "status", "info")})
    return sorted(out, key=lambda p: p["created"], reverse=True)


@app.post("/api/projects")
async def create_project(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(400, "Formato não suportado. Use MP4, MOV, MKV, WEBM ou AVI.")
    pid = uuid.uuid4().hex[:12]
    d = PROJECTS / pid
    d.mkdir()
    with open(d / f"source{ext}", "wb") as out:
        while chunk := await file.read(1 << 20):
            out.write(chunk)
    p = {
        "id": pid, "name": Path(file.filename).stem[:60], "created": time.time(),
        "source": f"source{ext}", "status": "analisando", "status_text": "Enviado", "progress": 0,
        "preset": next(iter(load_presets())), "chat": [], "history": [], "usage_total": 0.0,
    }
    save_project(p)
    threading.Thread(target=analyze, args=(pid,), daemon=True).start()
    return public(p)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return public(load_project(pid))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    shutil.rmtree(project_dir(pid))
    return {"ok": True}


@app.get("/api/projects/{pid}/peaks")
def get_peaks(pid: str):
    f = project_dir(pid) / "peaks.json"
    return json.loads(f.read_text()) if f.exists() else []


@app.post("/api/projects/{pid}/edit")
async def ai_edit(pid: str, body: EditIn):
    p = load_project(pid)
    if p["status"] != "pronto":
        raise HTTPException(409, "O vídeo ainda está sendo analisado.")
    presets = load_presets()
    preset = presets.get(body.preset)
    if not preset:
        raise HTTPException(400, "Modelo de edição não encontrado.")
    tr = load_transcript(pid)
    current = None if body.fresh or not p["chat"] else p["timeline"]
    user_msg = body.request.strip() or f"Editar com o modelo “{preset['name']}”"
    try:
        plan, usage = await run_in_threadpool(
            ai.request_plan, load_config(), tr, p["info"], preset, body.request, current)
        new_tl = tl.build(plan, tr, p["info"], preset, previous=p["timeline"])
    except ai.AIError as exc:
        raise HTTPException(400, str(exc))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(500, f"Não consegui montar a edição: {exc}")

    p = load_project(pid)  # recarrega: a análise/render pode ter mudado o arquivo
    p["history"] = (p.get("history") or [])[-19:] + [p["timeline"]]
    p["timeline"] = new_tl
    p["preset"] = preset["id"]
    p["usage_total"] = round(p.get("usage_total", 0) + usage["cost_usd"], 5)
    p["chat"].append({"role": "user", "text": user_msg})
    p["chat"].append({"role": "ai", "text": plan.get("summary", ""), "scenes": new_tl["scene_spans"],
                      "usage": usage, "duration": new_tl["duration"]})
    save_project(p)
    return public(p)


@app.put("/api/projects/{pid}/timeline")
def put_timeline(pid: str, body: TimelineIn):
    p = load_project(pid)
    t = body.timeline
    if not t.get("clips"):
        raise HTTPException(400, "A timeline precisa de pelo menos um clip.")
    for c in t["clips"]:
        c["src_in"] = max(0.0, float(c["src_in"]))
        c["src_out"] = min(p["info"]["duration"], float(c["src_out"]))
        if c["src_out"] - c["src_in"] < 0.1:
            raise HTTPException(400, "Clip curto demais.")
    p["history"] = (p.get("history") or [])[-19:] + [p["timeline"]]
    p["timeline"] = tl.retime(t, load_transcript(pid))
    save_project(p)
    return public(p)


@app.post("/api/projects/{pid}/undo")
def undo(pid: str):
    p = load_project(pid)
    if not p.get("history"):
        raise HTTPException(400, "Nada para desfazer.")
    p["timeline"] = p["history"].pop()
    save_project(p)
    return public(p)


def _do_render(pid: str, quality: str):
    d = PROJECTS / pid
    p = load_project(pid)
    music = p["timeline"]["music"]
    music_path = MUSIC / music["file"] if music.get("file") else None
    name = f"final-{int(time.time())}.mp4"
    try:
        render.render(d, d / p["source"], p["timeline"], p["info"], music_path, name, quality,
                      on_progress=lambda x: update_project(pid, render={"status": "renderizando", "progress": round(x, 3)}))
        update_project(pid, render={"status": "pronto", "progress": 1, "file": name})
    except Exception as exc:
        update_project(pid, render={"status": "erro", "error": str(exc)})


@app.post("/api/projects/{pid}/render")
def start_render(pid: str, body: RenderIn):
    p = load_project(pid)
    if (p.get("render") or {}).get("status") == "renderizando":
        raise HTTPException(409, "Já está renderizando.")
    update_project(pid, render={"status": "renderizando", "progress": 0})
    threading.Thread(target=_do_render, args=(pid, body.quality), daemon=True).start()
    return {"ok": True}


@app.get("/api/projects/{pid}/download/{name}")
def download(pid: str, name: str):
    d = project_dir(pid)
    f = d / name
    if f.parent != d or not f.exists() or not (name.startswith("final-") or name == "legendas.srt"):
        raise HTTPException(404, "Arquivo não encontrado.")
    p = load_project(pid)
    nice = f"{p['name']}-editado.mp4" if name.endswith(".mp4") else f"{p['name']}.srt"
    return FileResponse(f, filename=nice)


@app.get("/api/music")
def list_music():
    return sorted(f.name for f in MUSIC.iterdir() if f.suffix.lower() in AUDIO_EXT)


@app.post("/api/music")
async def upload_music(file: UploadFile = File(...)):
    name = Path(file.filename or "musica.mp3").name
    if Path(name).suffix.lower() not in AUDIO_EXT:
        raise HTTPException(400, "Use MP3, WAV, M4A, AAC ou OGG.")
    with open(MUSIC / name, "wb") as out:
        while chunk := await file.read(1 << 20):
            out.write(chunk)
    return list_music()


app.mount("/media/projects", StaticFiles(directory=PROJECTS), name="projects")
app.mount("/media/music", StaticFiles(directory=MUSIC), name="music")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
