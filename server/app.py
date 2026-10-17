"""Edita Fácil — servidor local. Rode com:  python -m server  (na pasta do projeto)."""
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, background, brand as brandkit, media, reference, render, studio, timeline as tl, transcribe, voices

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
MUSIC = ROOT / "music"
WEB = ROOT / "web"
PRESETS = Path(__file__).resolve().parent / "presets"
USER_PRESETS = reference.USER_PRESETS
DATA = ROOT / "data"
CONFIG = ROOT / "config.json"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}

PROJECTS.mkdir(exist_ok=True)
MUSIC.mkdir(exist_ok=True)
_lock = threading.Lock()

app = FastAPI(title="Edita Fácil")


# ---------- acesso pelo celular / pela nuvem ----------
# No próprio PC (127.0.0.1) abre direto. De outro aparelho (celular no Wi-Fi ou internet)
# pede o PIN que aparece no PC — ou a senha APP_PASSWORD, quando roda na nuvem.

def access_keys() -> tuple[str, str]:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    changed = False
    if not cfg.get("pin"):
        cfg["pin"] = f"{secrets.randbelow(10 ** 6):06d}"
        changed = True
    if not cfg.get("cookie_salt"):
        cfg["cookie_salt"] = secrets.token_hex(16)
        changed = True
    if changed:
        CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return os.environ.get("APP_PASSWORD") or cfg["pin"], cfg["cookie_salt"]


def _token(password: str, salt: str) -> str:
    return hmac.new(salt.encode(), password.encode(), hashlib.sha256).hexdigest()


def is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost") and "x-forwarded-for" not in request.headers \
        and not os.environ.get("APP_PASSWORD")


OPEN_PATHS = {"/entrar", "/api/login", "/favicon.ico"}
_fails: dict = {}


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if is_local(request) or path in OPEN_PATHS:
        return await call_next(request)
    password, salt = access_keys()
    if hmac.compare_digest(request.cookies.get("ef", ""), _token(password, salt)):
        return await call_next(request)
    if path.startswith("/api/") or path.startswith("/media/"):
        return JSONResponse({"detail": "Entre com o PIN primeiro."}, status_code=401)
    return RedirectResponse("/entrar")


LOGIN_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Entrar · Edita Fácil</title>
<style>:root{color-scheme:dark}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0e0f13;color:#eee;
font:16px/1.4 system-ui,sans-serif;padding:16px;box-sizing:border-box}form{width:100%;max-width:340px;text-align:center}
.m{width:56px;height:56px;border-radius:14px;margin:0 auto 14px;background:linear-gradient(135deg,#ff6b3d,#9a6cff);display:grid;
place-items:center;font-weight:800;font-size:26px}input{width:100%;box-sizing:border-box;font-size:30px;letter-spacing:.3em;text-align:center;
padding:14px;border-radius:14px;border:1px solid #333;background:#15171d;color:#fff;margin:14px 0}button{width:100%;padding:15px;
border-radius:14px;border:0;background:#ff6b3d;color:#fff;font-size:17px;font-weight:700}p{color:#999;font-size:14px}#e{color:#ff8a8a}</style>
</head><body><form id="f"><div class="m">E</div><b>Edita Fácil</b>
<p>Digite o PIN que aparece no computador<br>(⚙ Configurações → Usar no celular)</p>
<input id="s" inputmode="numeric" autocomplete="one-time-code" placeholder="••••••" autofocus>
<button>Entrar</button><p id="e"></p></form>
<script>document.getElementById('f').onsubmit=async e=>{e.preventDefault();
const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({senha:document.getElementById('s').value})});
if(r.ok){location.href=matchMedia('(max-width: 860px)').matches?'/celular.html':'/';}else{document.getElementById('e').textContent=(await r.json()).detail||'PIN errado';}};</script>
</body></html>"""


@app.get("/entrar")
def login_page():
    return HTMLResponse(LOGIN_HTML)


@app.post("/api/login")
def login(request: Request, body: dict):
    ip = request.client.host if request.client else "?"
    fails, since = _fails.get(ip, (0, 0))
    if fails >= 8 and time.time() - since < 600:
        raise HTTPException(429, "Muitas tentativas. Espere 10 minutos.")
    password, salt = access_keys()
    if not hmac.compare_digest(str(body.get("senha", "")).strip(), password):
        _fails[ip] = (fails + 1, time.time())
        raise HTTPException(401, "PIN errado.")
    _fails.pop(ip, None)
    resp = JSONResponse({"ok": True})
    resp.set_cookie("ef", _token(password, salt), max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
    return resp


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))
            return sk.getsockname()[0]
    except OSError:
        return "127.0.0.1"


@app.get("/api/connect")
def connect_info(request: Request):
    if not is_local(request):
        raise HTTPException(403, "Só aparece no computador.")
    password, _ = access_keys()
    port = int(os.environ.get("PORT", "8000"))
    return {"url": f"http://{lan_ip()}:{port}/celular.html", "pin": password}


# ---------- armazenamento ----------

def load_config() -> dict:
    cfg = {"api_key": "", "model": ai.DEFAULT_MODEL, "effort": "medium", "language": "pt", "elevenlabs_key": ""}
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    if not cfg["api_key"]:
        cfg["api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    if not cfg["elevenlabs_key"]:
        cfg["elevenlabs_key"] = os.environ.get("ELEVENLABS_API_KEY", "")
    return cfg


def load_presets() -> dict:
    files = [*PRESETS.glob("*.json"), *USER_PRESETS.glob("*.json")]
    items = [json.loads(p.read_text(encoding="utf-8")) for p in files]
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

def analyze(pid: str, transcript: dict | None = None, plan_fn=None, proxy: bool = True):
    d = PROJECTS / pid
    p = load_project(pid)
    try:
        source = d / p["source"]
        update_project(pid, status="analisando", status_text="Lendo o vídeo…", progress=0.05)
        info = media.probe(source)
        update_project(pid, info=info, status_text="Gerando miniaturas…", progress=0.08)
        media.make_thumbnails(source, d / "thumbs")
        update_project(pid, status_text="Preparando o preview…", progress=0.12)
        if proxy and media.make_proxy(source, d / "preview.mp4"):
            update_project(pid, preview="preview.mp4")
        peaks = media.waveform_peaks(source) if info["has_audio"] else []
        (d / "peaks.json").write_text(json.dumps(peaks))
        update_project(pid, status_text="Transcrevendo a fala (local, sem gastar tokens)…", progress=0.2)

        def prog(x):
            update_project(pid, progress=round(0.2 + 0.75 * x, 3))

        if transcript is not None:
            tr = transcript
        elif info["has_audio"]:
            tr = transcribe.transcribe(source, info["duration"], load_config().get("language", "pt"), prog)
        else:
            tr = {"source": "silence", "segments": [{"id": 0, "start": 0, "end": info["duration"], "text": "", "words": []}]}
        (d / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False))

        presets = load_presets()
        preset = presets.get(p.get("preset")) or next(iter(presets.values()))
        plan = plan_fn(tr, preset) if plan_fn else tl.local_plan(tr, preset)
        first = tl.build(plan, tr, info, preset)
        first["summary"] = ""
        notes = []
        if tr["source"] not in ("whisper", "tts", "roteiro"):
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
    elevenlabs_key: str | None = None
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
        "has_elevenlabs": bool(cfg["elevenlabs_key"]),
        "elevenlabs_hint": f"…{cfg['elevenlabs_key'][-4:]}" if cfg["elevenlabs_key"] else "",
        "background": background.available(),
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
async def create_project(file: UploadFile = File(...), auto: bool = Form(False), preset: str = Form(""),
                         extra: str = Form(""), export: bool = Form(False)):
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
        "preset": preset if preset in load_presets() else next(iter(load_presets())),
        "chat": [], "history": [], "usage_total": 0.0,
    }
    if auto:
        p["auto"] = {"preset": p["preset"], "extra": extra.strip()[:500], "export": export}
        p["auto_stage"] = "analisando"
    save_project(p)

    def work():
        analyze(pid)
        run_auto(pid)
    threading.Thread(target=work, daemon=True).start()
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


def edit_project(pid: str, preset_id: str, request: str = "", fresh: bool = False) -> dict:
    """A IA edita o projeto (usado pelo editor, pelo celular e pelo modo automático)."""
    p = load_project(pid)
    if p["status"] != "pronto":
        raise ValueError("O vídeo ainda está sendo analisado.")
    preset = load_presets().get(preset_id)
    if not preset:
        raise ValueError("Modelo de edição não encontrado.")
    tr = load_transcript(pid)
    current = None if fresh or not p["chat"] else p["timeline"]
    user_msg = request.strip() or f"Editar com o modelo “{preset['name']}”"
    plan, usage = ai.request_plan(load_config(), tr, p["info"], preset, request, current)
    new_tl = tl.build(plan, tr, p["info"], preset, previous=p["timeline"])

    p = load_project(pid)  # recarrega: a análise/render pode ter mudado o arquivo
    p["history"] = (p.get("history") or [])[-19:] + [p["timeline"]]
    p["timeline"] = new_tl
    p["preset"] = preset["id"]
    p["usage_total"] = round(p.get("usage_total", 0) + usage["cost_usd"], 5)
    p["chat"].append({"role": "user", "text": user_msg})
    p["chat"].append({"role": "ai", "text": plan.get("summary", ""), "scenes": new_tl["scene_spans"],
                      "usage": usage, "duration": new_tl["duration"]})
    save_project(p)
    return p


@app.post("/api/projects/{pid}/edit")
async def ai_edit(pid: str, body: EditIn):
    try:
        p = await run_in_threadpool(edit_project, pid, body.preset, body.request, body.fresh)
    except ai.AIError as exc:
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(409 if "analisado" in str(exc) else 400, str(exc))
    except (KeyError, TypeError) as exc:
        raise HTTPException(500, f"Não consegui montar a edição: {exc}")
    return public(p)


def run_auto(pid: str):
    """Modo automático: depois da análise a IA edita e (se pedido) já exporta. Roda no servidor,
    então dá para fechar o celular e voltar depois."""
    p = load_project(pid)
    auto = p.get("auto") or {}
    if not auto or p["status"] != "pronto":
        return
    try:
        if load_config()["api_key"]:
            update_project(pid, auto_stage="editando")
            edit_project(pid, auto.get("preset") or p["preset"], auto.get("extra", ""), fresh=True)
        else:
            update_project(pid, auto_note="Sem chave da IA: só tirei os silêncios.")
        if auto.get("export"):
            update_project(pid, auto_stage="exportando", render={"status": "renderizando", "progress": 0})
            _do_render(pid, auto.get("quality", "media"))
        update_project(pid, auto_stage="pronto")
    except Exception as exc:
        update_project(pid, auto_stage="erro", auto_note=str(exc))


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


# ---------- modelos do usuário ----------

@app.delete("/api/presets/{preset_id}")
def delete_preset(preset_id: str):
    f = USER_PRESETS / f"{preset_id}.json"
    if not preset_id.replace("-", "").isalnum() or not f.exists():
        raise HTTPException(404, "Só dá para apagar modelos criados por você.")
    f.unlink()
    return get_presets()


# ---------- marca ----------

@app.get("/api/brand")
def get_brand():
    return brandkit.load()


@app.post("/api/brand")
def set_brand(body: dict):
    return brandkit.save(body)


@app.post("/api/brand/{kind}")
async def upload_brand_image(kind: str, file: UploadFile = File(...)):
    if kind not in ("logo", "avatar"):
        raise HTTPException(404)
    try:
        return await run_in_threadpool(brandkit.save_image, kind, await file.read())
    except Exception as exc:
        raise HTTPException(400, f"Não consegui abrir a imagem: {exc}")


@app.delete("/api/brand/{kind}")
def delete_brand_image(kind: str):
    if kind not in ("logo", "avatar"):
        raise HTTPException(404)
    for name in (f"{kind}.png", "avatar_round.png" if kind == "avatar" else ""):
        if name:
            (brandkit.BRAND_DIR / name).unlink(missing_ok=True)
    data = brandkit.load()
    data[kind] = None
    brandkit.BRAND_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


# ---------- vozes (ElevenLabs) ----------

def _el_key() -> str:
    return load_config()["elevenlabs_key"]


@app.get("/api/voices")
async def get_voices():
    try:
        return await run_in_threadpool(voices.list_voices, _el_key())
    except voices.VoiceError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/voices/clone")
async def clone_voice(name: str = Form(...), consent: bool = Form(False), files: list[UploadFile] = File(...)):
    if not consent:
        raise HTTPException(400, "Confirme que a voz é sua ou que a pessoa autorizou o uso.")
    samples = [(f.filename or "amostra.mp3", await f.read()) for f in files[:25]]
    if not samples or sum(len(b) for _, b in samples) < 50_000:
        raise HTTPException(400, "Envie pelo menos 30 segundos de áudio limpo (ideal: 1 a 3 minutos).")
    try:
        vid = await run_in_threadpool(voices.clone_voice, _el_key(), name.strip()[:60] or "Minha voz", samples)
    except voices.VoiceError as exc:
        raise HTTPException(400, str(exc))
    return {"id": vid}


@app.delete("/api/voices/{voice_id}")
async def remove_voice(voice_id: str):
    try:
        await run_in_threadpool(voices.delete_voice, _el_key(), voice_id)
    except voices.VoiceError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


class SpeakIn(BaseModel):
    voice_id: str
    text: str


@app.post("/api/voices/preview")
async def preview_voice(body: SpeakIn):
    try:
        audio, _ = await run_in_threadpool(voices.speak, _el_key(), body.voice_id, body.text[:300])
    except voices.VoiceError as exc:
        raise HTTPException(400, str(exc))
    return Response(audio, media_type="audio/mpeg")


# ---------- estúdio: vídeo só com o tema ----------

class StudioIn(BaseModel):
    theme: str
    seconds: int = 45
    format: str = "9:16"
    voice_id: str = ""
    preset: str = ""
    extra: str = ""
    music: str = ""
    auto_export: bool = False


def new_project(name: str, preset_id: str, **extra) -> dict:
    pid = uuid.uuid4().hex[:12]
    (PROJECTS / pid).mkdir()
    presets = load_presets()
    p = {
        "id": pid, "name": name[:60], "created": time.time(), "source": "source.mp4",
        "status": "analisando", "status_text": "Começando…", "progress": 0,
        "preset": preset_id if preset_id in presets else next(iter(presets)),
        "chat": [], "history": [], "usage_total": 0.0, **extra,
    }
    save_project(p)
    return p


def _run_studio(pid: str, body: StudioIn):
    d = PROJECTS / pid
    cfg = load_config()
    try:
        presets = load_presets()
        style = presets.get(body.preset)
        if style:
            style = dict(style, instructions=style.get("script_instructions") or style["instructions"])
        update_project(pid, status_text="O Claude está escrevendo o roteiro…", progress=0.05)
        script, usage = studio.write_script(cfg, body.theme, max(10, min(180, body.seconds)), style, body.extra,
                                            bool(brandkit.path("avatar")), bool(brandkit.path("logo")))
        update_project(pid, name=script["title"][:60] or body.theme[:60], status_text="Gravando a narração…", progress=0.2)
        scenes = studio.voice_scenes(script, d, cfg["elevenlabs_key"], body.voice_id,
                                     lambda x: update_project(pid, progress=round(0.2 + 0.25 * x, 3)))
        studio.save_script(d, script, scenes)
        update_project(pid, status_text="Animando as cenas (motion e 3D)…", progress=0.45)
        music = MUSIC / body.music if body.music and (MUSIC / body.music).exists() else None
        fmt = body.format if body.format in ai.FORMATS and body.format != "original" else "9:16"
        studio.render_motion(scenes, d, fmt, brandkit.load(), music,
                             on_progress=lambda x: update_project(pid, progress=round(0.45 + 0.4 * x, 3)))
        tr = studio.transcript_from_scenes(scenes)
        voiced = tr["source"] == "tts"

        def plan_fn(tr_, preset):
            return {"summary": "", "format": fmt, "captions": voiced, "music": False,
                    "clips": [{"start": s["start"], "end": s["end"], "zoom": 1.0, "label": s["title"]} for s in scenes],
                    "texts": [], "scenes": [{"title": s["title"], "desc": s["screen_text"]} for s in scenes]}

        analyze(pid, transcript=tr, plan_fn=plan_fn, proxy=False)
        p = load_project(pid)
        if p["status"] != "pronto":
            return
        t = p["timeline"]
        t["captions"].update(position="bottom", style="viral")
        t["logo"] = False  # a logo já está no vídeo animado
        p["timeline"] = tl.retime(t, tr)
        p["usage_total"] = usage["cost_usd"]
        tags = " ".join("#" + h.lstrip("#") for h in script.get("hashtags", []))
        p["chat"] = [
            {"role": "user", "text": f"Criar vídeo sobre: {body.theme}"},
            {"role": "ai", "text": f"Criei o roteiro, {'narrei com a sua voz, ' if voiced else ''}animei as cenas com a sua marca. "
                                   f"Legenda do post: {script.get('caption', '')} {tags}".strip(),
             "scenes": t["scene_spans"], "usage": usage, "duration": t["duration"]},
        ]
        save_project(p)
        if body.auto_export:
            update_project(pid, auto_stage="exportando", render={"status": "renderizando", "progress": 0})
            _do_render(pid, "media")
        update_project(pid, auto_stage="pronto")
    except (ai.AIError, voices.VoiceError) as exc:
        update_project(pid, status="erro", status_text=str(exc))
    except Exception as exc:
        update_project(pid, status="erro", status_text=f"Erro ao criar o vídeo: {exc}")


@app.post("/api/studio")
def create_from_theme(body: StudioIn):
    if not body.theme.strip():
        raise HTTPException(400, "Escreva o tema do vídeo.")
    cfg = load_config()
    if not cfg["api_key"]:
        raise HTTPException(400, "Coloque sua chave da API da Anthropic em ⚙️ Configurações.")
    if body.voice_id and not cfg["elevenlabs_key"]:
        raise HTTPException(400, "Para narrar, coloque sua chave da ElevenLabs em ⚙️ Configurações.")
    p = new_project(body.theme, body.preset, origin="estudio", auto_stage="criando")
    threading.Thread(target=_run_studio, args=(p["id"], body), daemon=True).start()
    return public(p)


# ---------- copiar estilo de um vídeo de referência ----------

JOBS: dict = {}


def _run_reference(job: str, path: Path, use_frames: bool):
    def say(text, prog):
        JOBS[job].update(status_text=text, progress=prog)
    try:
        style, usage = reference.analyze(path, load_config(), use_frames, say)
        preset = reference.save_as_preset(style)
        JOBS[job].update(status="pronto", progress=1, style=style, preset=preset, usage=usage)
    except Exception as exc:
        JOBS[job].update(status="erro", status_text=str(exc))
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/reference")
async def upload_reference(file: UploadFile = File(...), use_frames: bool = Form(True)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(400, "Envie um vídeo (MP4, MOV…).")
    if not load_config()["api_key"]:
        raise HTTPException(400, "Coloque sua chave da API da Anthropic em ⚙️ Configurações.")
    job = uuid.uuid4().hex[:10]
    tmp = DATA / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / f"ref_{job}{ext}"
    with open(path, "wb") as out:
        while chunk := await file.read(1 << 20):
            out.write(chunk)
    JOBS[job] = {"id": job, "status": "analisando", "status_text": "Enviado", "progress": 0}
    threading.Thread(target=_run_reference, args=(job, path, use_frames), daemon=True).start()
    return JOBS[job]


@app.get("/api/reference/{job}")
def reference_status(job: str):
    if job not in JOBS:
        raise HTTPException(404, "Análise não encontrada.")
    return JOBS[job]


# ---------- trocar o fundo ----------

class BackgroundIn(BaseModel):
    mode: str = "desfoque"
    color: str = "#111111"


def _run_background(pid: str, body: BackgroundIn):
    d = PROJECTS / pid
    p = load_project(pid)
    original = p.get("source_original") or p["source"]
    out_name = f"fundo-{int(time.time())}.mp4"
    try:
        update_project(pid, status="analisando", status_text="Trocando o fundo (o rosto e a voz não mudam)…", progress=0.01,
                       source_original=original)
        background.replace(d / original, d / out_name, p["info"], body.mode, body.color,
                           d / "fundo.png", brandkit.load()["colors"],
                           lambda x: update_project(pid, progress=round(x, 3)))
        old = p["source"] if p["source"] != original else None
        update_project(pid, status="pronto", status_text="Pronto", progress=1, source=out_name, preview=out_name)
        if old:
            (d / old).unlink(missing_ok=True)
    except Exception as exc:
        update_project(pid, status="pronto", status_text="Pronto", progress=1,
                       notes=[f"Não consegui trocar o fundo: {exc}"])


@app.post("/api/projects/{pid}/background")
def change_background(pid: str, body: BackgroundIn):
    p = load_project(pid)
    if p["status"] != "pronto":
        raise HTTPException(409, "Espere o projeto ficar pronto.")
    if not background.available():
        raise HTTPException(400, "Instale o recorte de fundo: pip install mediapipe opencv-python")
    if body.mode not in background.MODES:
        raise HTTPException(400, "Tipo de fundo inválido.")
    if body.mode == "imagem" and not (project_dir(pid) / "fundo.png").exists():
        raise HTTPException(400, "Envie a imagem do fundo primeiro.")
    threading.Thread(target=_run_background, args=(pid, body), daemon=True).start()
    return {"ok": True}


@app.post("/api/projects/{pid}/background-image")
async def background_image(pid: str, file: UploadFile = File(...)):
    from io import BytesIO

    from PIL import Image, ImageOps

    d = project_dir(pid)
    try:
        img = ImageOps.exif_transpose(Image.open(BytesIO(await file.read()))).convert("RGB")
    except Exception:
        raise HTTPException(400, "Não consegui abrir a imagem.")
    img.thumbnail((2400, 2400))
    img.save(d / "fundo.png")
    return {"ok": True}


@app.post("/api/projects/{pid}/asset")
async def upload_asset(pid: str, file: UploadFile = File(...)):
    """Imagem usada nos elementos (ex.: antes/depois do isso → nisso)."""
    from io import BytesIO

    from PIL import Image, ImageOps

    d = project_dir(pid) / "assets"
    d.mkdir(exist_ok=True)
    try:
        img = ImageOps.exif_transpose(Image.open(BytesIO(await file.read()))).convert("RGB")
    except Exception:
        raise HTTPException(400, "Não consegui abrir a imagem.")
    img.thumbnail((1200, 1200))
    name = f"img-{uuid.uuid4().hex[:8]}.jpg"
    img.save(d / name, quality=90)
    return {"file": name}


@app.post("/api/projects/{pid}/background/reset")
def reset_background(pid: str):
    p = load_project(pid)
    orig = p.get("source_original")
    if not orig:
        raise HTTPException(400, "O vídeo já está com o fundo original.")
    d = project_dir(pid)
    if p["source"] != orig:
        (d / p["source"]).unlink(missing_ok=True)
    preview = "preview.mp4" if (d / "preview.mp4").exists() else orig
    return public(update_project(pid, source=orig, preview=preview, source_original=None))


app.mount("/media/projects", StaticFiles(directory=PROJECTS), name="projects")
app.mount("/media/music", StaticFiles(directory=MUSIC), name="music")
app.mount("/media/brand", StaticFiles(directory=brandkit.BRAND_DIR), name="brand")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
