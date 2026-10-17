"use strict";
/* Edita Fácil — editor no navegador.
 * O preview é feito em tempo real sobre o vídeo original: o player pula os trechos
 * cortados e desenha legendas/textos por cima. Só a exportação usa o ffmpeg. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const S = {
  cfg: null, presets: [], music: [], project: null, peaks: [], brand: null,
  playing: false, outTime: 0, clipIdx: 0, sel: null, pps: 60,
  pollTimer: null, pending: null, aiBusy: false, capLines: [], ovKey: "",
};
const video = $("#video");
const musicAudio = new Audio();
musicAudio.loop = true;

/* ---------------- utilidades ---------------- */

async function api(path, opts = {}) {
  if (opts.json !== undefined) {
    opts.body = JSON.stringify(opts.json);
    opts.headers = { "Content-Type": "application/json" };
    delete opts.json;
  }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
  return data;
}

function toast(msg, ms = 3200) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), ms);
}

const pad = (n, l = 2) => String(Math.floor(n)).padStart(l, "0");
function tc(t) {
  t = Math.max(0, t || 0);
  return `${pad(t / 3600)}:${pad((t % 3600) / 60)}:${pad(t % 60)}:${pad((t % 1) * 30)}`;
}
function mmss(t) {
  t = Math.max(0, t || 0);
  return `${pad(t / 60)}:${pad(t % 60)}`;
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const uid = (p) => p + Math.random().toString(16).slice(2, 8);
const TL = () => S.project?.timeline;
const ready = () => S.project && S.project.status === "pronto" && TL();

function outputSize(fmt, info) {
  const sizes = { "9:16": [1080, 1920], "16:9": [1920, 1080], "1:1": [1080, 1080], "4:5": [1080, 1350] };
  if (sizes[fmt]) return sizes[fmt];
  const s = Math.min(1, 1920 / Math.max(info.width, info.height));
  return [Math.floor(info.width * s / 2) * 2, Math.floor(info.height * s / 2) * 2];
}

/* mesma regra do servidor (timeline.caption_lines) */
function captionLines(words, perLine) {
  const lines = [];
  let cur = [];
  for (const w of words) {
    if (cur.length && (cur.length >= perLine || w.s - cur[cur.length - 1].e > 0.6)) { lines.push(cur); cur = []; }
    cur.push(w);
    if (/[.!?]$/.test(w.w)) { lines.push(cur); cur = []; }
  }
  if (cur.length) lines.push(cur);
  return lines;
}

/* ---------------- inicialização ---------------- */

async function init() {
  // no celular, a tela simples é mais fácil (o editor completo continua em /?full=1)
  if (matchMedia("(max-width: 760px)").matches && !new URLSearchParams(location.search).get("full")) {
    location.replace("/celular.html" + location.search);
    return;
  }
  bindUI();
  [S.cfg, S.presets, S.music, S.brand] = await Promise.all([api("/api/config"), api("/api/presets"), api("/api/music"), api("/api/brand")]);
  applyBrand();
  renderConfig();
  renderPresets();
  renderMusicList();
  const projects = await loadProjects();
  const params = new URLSearchParams(location.search);
  const wanted = params.get("p");
  if (params.get("preset") && S.presets.some((x) => x.id === params.get("preset"))) {
    $("#presetSel").value = params.get("preset");
    toast("Estilo selecionado. Envie um vídeo ou clique em ✦ Editar com IA.");
  }
  if (wanted && projects.some((p) => p.id === wanted)) openProject(wanted);
  else if (projects.length) openProject(projects[0].id);
  else renderAll();
}

function applyBrand() {
  const c = S.brand.colors;
  const root = document.documentElement.style;
  root.setProperty("--brand-accent", c.accent);
  root.setProperty("--brand-primary", c.primary);
  if (S.brand.logo) $("#ovLogo").src = `/media/brand/logo.png?v=${Date.now()}`;
}

async function loadProjects() {
  const list = await api("/api/projects");
  const ul = $("#projList");
  ul.innerHTML = list.map((p) => `
    <li data-id="${p.id}" class="${S.project?.id === p.id ? "active" : ""}">
      <span>${esc(p.name)}</span>
      <small>${p.info ? mmss(p.info.duration) : "…"}</small>
      <button class="del" data-del="${p.id}" title="Apagar projeto">✕</button>
    </li>`).join("") || `<li class="hint">Nenhum projeto ainda.</li>`;
  return list;
}

async function openProject(id) {
  pause();
  S.sel = null;
  S.project = await api(`/api/projects/${id}`);
  setVideoSource();
  S.peaks = [];
  S.outTime = 0;
  S.clipIdx = 0;
  if (S.project.status === "pronto") S.peaks = await api(`/api/projects/${id}/peaks`);
  const preset = S.project.preset;
  if (preset && !new URLSearchParams(location.search).get("preset")) $("#presetSel").value = preset;
  renderAll();
  loadProjects();
  ensurePolling();
}

function setVideoSource() {
  const p = S.project;
  const want = `/media/projects/${p.id}/${p.preview || p.source}`;
  if (!video.src.endsWith(want)) {
    video.src = want;
    video.addEventListener("loadedmetadata", () => seek(S.outTime), { once: true });
  }
}

function setProject(p) {
  const prev = S.project;
  S.project = p;
  if (prev && prev.id === p.id && S.sel) {
    const t = p.timeline;
    const exists = S.sel.type === "clip" ? t.clips.some((c) => c.id === S.sel.id) : t.texts.some((x) => x.id === S.sel.id);
    if (!exists) S.sel = null;
  }
  renderAll();
  seek(Math.min(S.outTime, TL()?.duration || 0));
}

/* ---------------- polling (análise e exportação) ---------------- */

function ensurePolling() {
  clearInterval(S.pollTimer);
  const p = S.project;
  if (!p) return;
  const busy = p.status === "analisando" || p.render?.status === "renderizando";
  if (busy) S.pollTimer = setInterval(poll, 1000);
}

async function poll() {
  const p = S.project;
  if (!p) return;
  const fresh = await api(`/api/projects/${p.id}`).catch(() => null);
  if (!fresh || fresh.id !== S.project.id) return;
  const wasAnalyzing = p.status === "analisando";
  S.project = fresh;
  if (wasAnalyzing && fresh.status === "pronto") {
    S.peaks = await api(`/api/projects/${fresh.id}/peaks`);
    setVideoSource();
    renderAll();
    seek(0);
    loadProjects();
    (fresh.notes || []).forEach((n) => toast(n, 6000));
    if (S.pending && S.pending.pid === fresh.id && S.pending.auto) {
      const pend = S.pending;
      S.pending = pend.export ? { pid: pend.pid, exportAfterAI: true } : null;
      runAI(pend.extra, true, pend.preset);
    }
  } else if (fresh.status === "erro") {
    renderAll();
  } else {
    renderBusy();
    renderExport();
  }
  if (fresh.status !== "analisando" && fresh.render?.status !== "renderizando") clearInterval(S.pollTimer);
}

/* ---------------- envio de vídeo ---------------- */

let pickedFile = null;
function pickFile(file) {
  if (!file) return;
  if (!file.type.startsWith("video/") && !/\.(mp4|mov|m4v|mkv|webm|avi)$/i.test(file.name)) {
    toast("Escolha um arquivo de vídeo.");
    return;
  }
  pickedFile = file;
  $("#upName").textContent = `${file.name} — ${(file.size / 1e6).toFixed(1)} MB`;
  $("#upPreset").value = $("#presetSel").value || S.presets[0]?.id;
  updateUpPresetDesc();
  $("#uploadDlg").showModal();
}

function updateUpPresetDesc() {
  const p = S.presets.find((x) => x.id === $("#upPreset").value);
  $("#upPresetDesc").textContent = p ? p.description : "";
}

function uploadPicked() {
  const file = pickedFile;
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/projects");
  const pend = { auto: $("#upAuto").checked, export: $("#upExport").checked, preset: $("#upPreset").value, extra: $("#upExtra").value.trim() };
  $("#presetSel").value = pend.preset;
  showBusy("Enviando o vídeo… 0%", 0);
  xhr.upload.onprogress = (e) => e.lengthComputable && showBusy(`Enviando o vídeo… ${Math.round(e.loaded / e.total * 100)}%`, e.loaded / e.total);
  xhr.onload = async () => {
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status !== 200) { hideBusy(); toast(data.detail || "Falha no envio."); return; }
    S.pending = { ...pend, pid: data.id };
    await openProject(data.id);
  };
  xhr.onerror = () => { hideBusy(); toast("Falha no envio. O servidor está rodando?"); };
  xhr.send(fd);
}

/* ---------------- IA ---------------- */

async function runAI(request = "", fresh = false, presetId = null) {
  const p = S.project;
  if (!ready()) return toast("Envie um vídeo e espere a análise terminar.");
  if (!S.cfg.has_key) {
    toast("Coloque sua chave da API em Configurações.");
    openSettings();
    return;
  }
  if (S.aiBusy) return;
  S.aiBusy = true;
  const preset = presetId || $("#presetSel").value;
  const label = request || `Editar com o modelo “${S.presets.find((x) => x.id === preset)?.name}”`;
  renderChat({ role: "user", text: label, pending: true });
  setClaudeStatus("work", "editando…");
  try {
    const np = await api(`/api/projects/${p.id}/edit`, { method: "POST", json: { preset, request, fresh } });
    if (S.project.id === np.id) setProject(np);
    if (S.pending?.exportAfterAI && S.pending.pid === np.id) {
      S.pending = null;
      openExport();
      startRender();
    }
  } catch (e) {
    renderChat({ role: "user", text: label }, { role: "err", text: e.message });
  } finally {
    S.aiBusy = false;
    renderClaudeHead();
  }
}

/* ---------------- edição manual ---------------- */

let saveTimer = null;
async function saveTimeline(t = TL(), debounce = 0) {
  clearTimeout(saveTimer);
  const go = async () => {
    try {
      const np = await api(`/api/projects/${S.project.id}/timeline`, { method: "PUT", json: { timeline: t } });
      setProject(np);
    } catch (e) { toast(e.message); }
  };
  if (debounce) saveTimer = setTimeout(go, debounce);
  else await go();
}
const clone = (o) => JSON.parse(JSON.stringify(o));

function clipAt(t, clips = TL().clips) {
  let i = clips.findIndex((c) => t >= c.start && t < c.end);
  if (i < 0) i = t <= 0 ? 0 : clips.length - 1;
  return i;
}

function splitAtPlayhead() {
  if (!ready()) return;
  const t = clone(TL());
  const i = clipAt(S.outTime, t.clips);
  const c = t.clips[i];
  const cut = c.src_in + (S.outTime - c.start);
  if (cut - c.src_in < 0.15 || c.src_out - cut < 0.15) return toast("Mova a agulha para o meio de um clip.");
  const b = { ...c, id: uid("c"), src_in: +cut.toFixed(3) };
  c.src_out = +cut.toFixed(3);
  t.clips.splice(i + 1, 0, b);
  const splitOffset = cut - c.src_in;
  for (const x of t.texts) {
    if (x.clip_id === c.id && x.offset >= splitOffset) { x.clip_id = b.id; x.offset -= splitOffset; }
  }
  S.sel = { type: "clip", id: b.id };
  saveTimeline(t);
}

function deleteSelected() {
  if (!ready() || !S.sel) return toast("Selecione um clip ou texto na timeline.");
  const t = clone(TL());
  if (S.sel.type === "clip") {
    if (t.clips.length === 1) return toast("Não dá para apagar o último clip.");
    t.clips = t.clips.filter((c) => c.id !== S.sel.id);
  } else {
    t.texts = t.texts.filter((x) => x.id !== S.sel.id);
  }
  S.sel = null;
  saveTimeline(t);
}

function toggleZoom() {
  if (!ready()) return;
  const t = clone(TL());
  const id = S.sel?.type === "clip" ? S.sel.id : t.clips[clipAt(S.outTime, t.clips)].id;
  const c = t.clips.find((x) => x.id === id);
  c.zoom = c.zoom > 1.01 ? 1 : 1.15;
  S.sel = { type: "clip", id };
  saveTimeline(t);
}

function addText(style) {
  if (!ready()) return;
  const t = clone(TL());
  const c = t.clips[clipAt(S.outTime, t.clips)];
  const rich = RICH.includes(style);
  const x = { id: uid("t"), text: rich ? RICH_SAMPLES[style] : "Seu texto", clip_id: c.id, offset: Math.max(0, S.outTime - c.start),
    length: { isso_nisso: 6, produto: 4, rotina: 4, aviso: 8, pergunta: 3, final: 3 }[style] || 2.5, style };
  t.texts.push(x);
  S.sel = { type: "text", id: x.id };
  showPanel("inspetor");
  saveTimeline(t);
}

async function undo() {
  if (!S.project?.can_undo) return toast("Nada para desfazer.");
  try { setProject(await api(`/api/projects/${S.project.id}/undo`, { method: "POST" })); } catch (e) { toast(e.message); }
}

/* ---------------- player ---------------- */

function seek(out) {
  if (!TL()) return;
  const t = TL();
  out = Math.max(0, Math.min(out, Math.max(0, t.duration - 0.001)));
  const i = clipAt(out);
  const c = t.clips[i];
  S.outTime = out;
  S.clipIdx = i;
  video.currentTime = c.src_in + (out - c.start);
  applyClip(c);
  syncMusic();
  drawFrame();
}

function applyClip(c) {
  video.style.transform = c.zoom > 1.001 ? `scale(${c.zoom})` : "";
}

function play() {
  if (!ready()) return;
  if (S.outTime >= TL().duration - 0.05) seek(0);
  S.playing = true;
  video.play().catch(() => {});
  syncMusic();
  $("#playBtn").textContent = "❚❚";
  requestAnimationFrame(loop);
}

function pause() {
  S.playing = false;
  video.pause();
  musicAudio.pause();
  $("#playBtn").textContent = "▶";
}

function loop() {
  if (!S.playing || !TL()) return;
  const clips = TL().clips;
  let c = clips[S.clipIdx];
  const ct = video.currentTime;
  if (ct >= c.src_out - 0.015 || video.ended) {
    if (S.clipIdx >= clips.length - 1) {
      pause();
      S.outTime = TL().duration;
      drawFrame();
      return;
    }
    S.clipIdx++;
    const n = clips[S.clipIdx];
    if (Math.abs(n.src_in - ct) > 0.04) video.currentTime = n.src_in;
    applyClip(n);
    c = n;
  }
  S.outTime = c.start + Math.max(0, Math.min(video.currentTime - c.src_in, c.src_out - c.src_in));
  drawFrame();
  requestAnimationFrame(loop);
}

function syncMusic() {
  const m = TL()?.music;
  if (!m || !m.enabled || !m.file) { musicAudio.pause(); return; }
  const src = `/media/music/${encodeURIComponent(m.file)}`;
  if (!musicAudio.src.endsWith(src)) musicAudio.src = src;
  musicAudio.volume = Math.min(1, m.volume * 2);
  if (musicAudio.duration) musicAudio.currentTime = S.outTime % musicAudio.duration;
  if (S.playing) musicAudio.play().catch(() => {});
  else musicAudio.pause();
}

/* desenha legenda, textos, agulha e timecode no tempo atual */
function drawFrame() {
  const t = TL();
  if (!t) return;
  const now = S.outTime;
  $("#tc").textContent = tc(now);
  $("#playhead").style.left = `${now * S.pps}px`;

  $("#ovLogo").hidden = !(t.logo && S.brand?.logo);
  const cap = $("#ovCaption");
  let capKey = "";
  if (t.captions.enabled) {
    const line = S.capLines.find((l) => now >= l[0].s && now <= l[l.length - 1].e + 0.15);
    if (line) {
      const cur = line.findIndex((w, i) => now >= w.s && (i === line.length - 1 || now < line[i + 1].s));
      capKey = `${line[0].s}|${t.captions.style === "viral" ? cur : ""}`;
      if (capKey !== cap._key) {
        const words = line.map((w, i) => (i === cur && t.captions.style === "viral" ? `<span class="on">${esc(w.w)}</span>` : esc(w.w)));
        cap.innerHTML = `<div class="cap ${t.captions.style}">${words.join(" ")}</div>`;
      }
    }
  }
  if (!capKey && cap._key) cap.innerHTML = "";
  cap._key = capKey;
  cap.className = `ov-caption ${t.captions.position || "bottom"} ${t.captions.style}`;

  const active = t.texts.filter((x) => now >= x.start && now < x.end);
  const rendered = active.map((x) => (RICH.includes(x.style) ? richHTML(x, now - x.start) : [x.id + x.text + x.style, plainHTML(x)]));
  const key = rendered.map((r) => r[0]).join("|");
  if (key !== S.ovKey) {
    S.ovKey = key;
    $("#ovTexts").innerHTML = rendered.map((r) => r[1]).join("");
  }

  const scroll = $("#tlScroll");
  const x = now * S.pps;
  if (S.playing && (x < scroll.scrollLeft || x > scroll.scrollLeft + scroll.clientWidth - 40)) scroll.scrollLeft = x - 60;
}

/* ---------- formato isso → nisso (mesmas regras de tempo do overlays.py) ---------- */
const RICH = ["aviso", "pergunta", "isso_nisso", "produto", "rotina", "final"];
const RICH_SAMPLES = {
  aviso: "Simulação com IA · não é consulta médica",
  pergunta: "Qual é a sua profissão?|Sou dentista. Edição com IA funciona pra mim?",
  isso_nisso: "isso|nisso",
  produto: "Nome do produto|manhã|noite",
  rotina: "Sua rotina|Passo 1|Passo 2|Passo 3",
  final: "|me chama no direct",
};
const RICH_NAMES = { aviso: "Aviso", pergunta: "Pergunta", isso_nisso: "Isso → Nisso", produto: "Use isso (produto)", rotina: "Checklist", final: "Tela final @" };
const parts = (t) => String(t || "").split("|").map((x) => x.trim());

function plainHTML(x) {
  const inner = ["destaque", "cta", "rodape"].includes(x.style) ? `<span>${esc(x.text)}</span>` : esc(x.text);
  return `<div class="ovt ${x.style}">${inner}</div>`;
}

function richHTML(x, p) {
  const d = x.end - x.start;
  const P = parts(x.text);
  const asset = (f) => `/media/projects/${S.project.id}/assets/${encodeURIComponent(f)}`;
  if (x.style === "aviso") return [x.id + "a", `<div class="rx rx-aviso">ⓘ ${esc(P[0])}</div>`];
  if (x.style === "pergunta") {
    const h = S.brand?.handle ? `<div class="rx rx-handle" style="right:14cqw;top:27cqh">${esc(S.brand.handle.toUpperCase())}</div>` : "";
    return [x.id + "p", `<div class="rx rx-perg"><div class="h">${esc(P[0])}</div><div class="b">${esc(P[1] || "")}</div></div>${h}`];
  }
  if (x.style === "isso_nisso") {
    const ta = Math.max(0.35, d * 0.2), tb = Math.max(ta + 0.5, d * 0.45);
    const showA = x.img_a && p >= ta, showB = x.img_b && p >= tb, arrow = p >= tb + 0.35;
    const frame = (cls, img, show, label, scan) => `<div class="rx glass rx-frame ${cls} ${show ? "lit" : ""}">
      ${show ? `<img src="${asset(img)}" alt="">${scan ? '<i class="scan"></i>' : ""}` : esc(label)}</div>`;
    return [`${x.id}n${+!!showA}${+!!showB}${+arrow}`,
      frame("a", x.img_a, showA, P[0] || "isso", false) + frame("b", x.img_b, showB, P[1] || "nisso", true) + (arrow ? `<div class="rx rx-arrow"></div>` : "")];
  }
  if (x.style === "produto") {
    const card = Math.min(0.8, d * 0.3);
    if (p < card) return [x.id + "ph", `<div class="rx glass rx-prod ph">use isso</div>`];
    const chips = P.slice(1).filter(Boolean).slice(0, 4);
    const n = chips.filter((_, i) => p >= card + 0.35 + 0.3 * i).length;
    return [`${x.id}c${n}`, `<div class="rx rx-prod card"><span>${esc(P[0])}</span></div>
      <div class="rx rx-chips">${chips.slice(0, n).map((c) => `<span>• ${esc(c)}</span>`).join("")}</div>`];
  }
  if (x.style === "rotina") {
    const items = P.slice(1).filter(Boolean).slice(0, 5);
    const nIt = Math.max(1, items.length);
    const shown = items.filter((_, i) => p >= 0.15 + 0.2 * i).length;
    const checked = items.filter((_, i) => p >= d * 0.35 + (d * 0.45 * i) / Math.max(1, nIt - 1)).length;
    return [`${x.id}r${shown}${checked}`, `<div class="rx rx-rot"><div class="t">${esc(P[0] || "Sua rotina")}</div>
      ${items.slice(0, shown).map((it, i) => `<div class="i ${i < checked ? "ok" : ""}"><i>${i < checked ? "✓" : ""}</i>${esc(it)}</div>`).join("")}</div>`];
  }
  if (x.style === "final") {
    const handle = P[0] || S.brand?.handle || "";
    return [x.id + "f", `<div class="rx rx-final"><div class="ig"></div>${handle ? `<b>${esc(handle)}</b>` : ""}${P[1] ? `<span>${esc(P[1])}</span>` : ""}</div>`];
  }
  return [x.id, ""];
}

function fitFrame() {
  const p = S.project;
  const frame = $("#frame");
  const stage = $("#stage");
  if (!p?.info) return;
  const fmt = TL()?.format || "9:16";
  const ratios = { "9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1, "4:5": 4 / 5 };
  const r = ratios[fmt] || p.info.width / p.info.height;
  const W = stage.clientWidth - 16, H = stage.clientHeight - 16;
  let w = H * r, h = H;
  if (w > W) { w = W; h = W / r; }
  frame.style.width = `${w}px`;
  frame.style.height = `${h}px`;
  frame.style.aspectRatio = "auto";
  frame.classList.toggle("contain", fmt === "original");
}

/* ---------------- renderização da interface ---------------- */

function renderAll() {
  const p = S.project;
  const t = TL();
  $("#emptyState").hidden = !!p;
  $("#frame").style.visibility = p ? "visible" : "hidden";
  $("#projName").textContent = p ? p.name : "Nenhum projeto";
  const edited = p?.chat?.some((m) => m.role === "ai");
  $("#projSub").textContent = !p ? "Envie um vídeo cru para começar" : p.status !== "pronto" ? p.status_text : edited ? "Editado pelo Claude" : "Pronto para editar";
  if (p?.info && t) {
    const [w, h] = outputSize(t.format, p.info);
    $("#spec").textContent = `${w} × ${h} · 30 fps`;
    $("#dur").textContent = `duração ${mmss(t.duration)} (original ${mmss(p.info.duration)})`;
    $("#formatSel").value = t.format;
    S.capLines = captionLines(t.caption_words || [], t.captions.words || 3);
  } else {
    $("#spec").textContent = "—";
    $("#dur").textContent = "";
    S.capLines = [];
  }
  S.ovKey = "";
  fitFrame();
  renderBusy();
  renderTimeline();
  renderChat();
  renderClaudeHead();
  renderSidePanels();
  renderInspector();
  drawFrame();
}

function showBusy(text, frac) {
  $("#busy").hidden = false;
  $("#busyText").textContent = text;
  $("#busyBar").style.width = `${Math.round((frac || 0) * 100)}%`;
}
function hideBusy() { $("#busy").hidden = true; }
function renderBusy() {
  const p = S.project;
  if (!p) return hideBusy();
  if (p.status === "analisando") showBusy(p.status_text, p.progress);
  else if (p.status === "erro") showBusy(p.status_text, 0);
  else hideBusy();
}

function renderConfig() {
  const c = S.cfg;
  const name = c.models.find((m) => m.id === c.model)?.name.split(" —")[0] || c.model;
  const conn = $("#conn");
  conn.classList.toggle("on", c.has_key);
  conn.lastElementChild.textContent = c.has_key ? `${name} — conectado` : "Claude — sem chave";
  $("#clModel").textContent = name.replace("Claude ", "");
  renderClaudeHead();
}

function setClaudeStatus(cls, text) {
  const el = $("#clStatus");
  el.className = `cl-status ${cls}`;
  el.innerHTML = `<i class="dot"></i>${esc(text)}`;
}

function renderClaudeHead() {
  const p = S.project;
  if (S.aiBusy) return;
  if (!S.cfg?.has_key) setClaudeStatus("", "sem chave da API");
  else if (!p) setClaudeStatus("on", "aguardando vídeo");
  else if (p.status !== "pronto") setClaudeStatus("work", "analisando o vídeo…");
  else setClaudeStatus("on", p.chat.some((m) => m.role === "ai") ? "edição pronta" : "pronto para editar");
  $("#clCost").innerHTML = p?.usage_total ? `gasto com IA<br><b>US$ ${p.usage_total.toFixed(3)}</b>` : "";
}

function renderPresets() {
  const opts = S.presets.map((p) => `<option value="${p.id}">${p.icon} ${esc(p.name)}</option>`).join("");
  $("#presetSel").innerHTML = opts;
  $("#upPreset").innerHTML = opts;
  $("#presetList").innerHTML = S.presets.map((p) => `
    <button class="preset" data-preset="${p.id}">
      <b>${p.icon} ${esc(p.name)}</b><span>${esc(p.description)}</span>
    </button>`).join("");
  const styles = [["gancho", "Gancho"], ["titulo", "Título"], ["destaque", "Destaque"], ["rodape", "Rodapé"], ["cta", "Chamada (CTA)"]];
  $("#textStyles").innerHTML = styles.map(([id, n]) => `<button data-addtext="${id}">${n}</button>`).join("");
  $("#richStyles").innerHTML = RICH.map((id) => `<button data-addtext="${id}">${RICH_NAMES[id]}</button>`).join("");
}

function renderSidePanels() {
  const t = TL();
  const sel = $("#presetSel").value;
  $$(".preset").forEach((b) => b.classList.toggle("active", b.dataset.preset === sel));
  if (!t) return;
  $("#capEnabled").checked = t.captions.enabled;
  $("#capStyle").value = t.captions.style;
  $("#capPos").value = t.captions.position || "bottom";
  $("#capWords").value = t.captions.words || 3;
  $("#capWordsOut").textContent = t.captions.words || 3;
  $("#logoEnabled").checked = !!t.logo;
  $("#logoEnabled").disabled = !S.brand?.logo;
  $("#musicEnabled").checked = !!t.music.enabled;
  $("#musicDuck").checked = t.music.duck !== false;
  $("#musicVol").value = t.music.volume ?? 0.12;
  $("#musicVolOut").textContent = `${Math.round((t.music.volume ?? 0.12) * 100)}%`;
  renderMusicList();
}

function renderMusicList() {
  const cur = TL()?.music?.file;
  $("#musicList").innerHTML = S.music.map((m) => `<li data-music="${esc(m)}" class="${m === cur ? "active" : ""}">♫ ${esc(m)}</li>`).join("")
    || `<li class="hint">Nenhuma música. Envie um MP3 (use músicas livres de direitos).</li>`;
}

function renderChat(...extra) {
  const p = S.project;
  const box = $("#chat");
  const msgs = [...(p?.chat || []), ...extra];
  let html = "";
  if (!p) {
    html = `<div class="msg ai"><div class="who">Claude</div>Oi! Mande seu vídeo cru (arraste no centro da tela). Eu corto as pausas, monto as cenas, coloco legenda, zoom e textos, tudo sozinho. Depois é só pedir ajustes aqui.</div>`;
  } else if (p.status === "pronto" && !msgs.length) {
    const src = p.transcript_source === "whisper" ? "Transcrevi a fala" : "Separei os trechos com fala";
    html = `<div class="msg ai"><div class="who">Claude</div>${src} e já tirei os silêncios. Escolha um modelo abaixo e clique em <b>✦ Editar com IA</b>, ou me diga o que quer.</div>`;
  }
  for (const m of msgs) {
    if (m.role === "user") html += `<div class="msg user"><small>Você</small>${esc(m.text)}</div>`;
    else if (m.role === "err") html += `<div class="msg err">${esc(m.text)}</div>`;
    else {
      const scenes = (m.scenes || []).map((s) => `
        <div class="scene" data-seek="${s.start}">
          <div class="sh"><span>${s.code} ${esc(s.label)}</span><em>${mmss(s.start)}</em></div>
          ${s.desc ? `<p>${esc(s.desc)}</p>` : ""}
        </div>`).join("");
      const u = m.usage;
      const usage = u ? `<div class="usage">${(u.input_tokens / 1000).toFixed(1)}k tokens lidos${u.cached_tokens ? ` (${(u.cached_tokens / 1000).toFixed(1)}k do cache)` : ""} · ${(u.output_tokens / 1000).toFixed(1)}k escritos · US$ ${u.cost_usd.toFixed(4)}</div>` : "";
      html += `<div class="msg ai"><div class="who">Claude · ${m.duration ? `vídeo final ${mmss(m.duration)}` : "edição"}</div>${esc(m.text)}<div class="scenes">${scenes}</div>${usage}</div>`;
    }
  }
  if (extra.some((m) => m.pending)) html += `<div class="msg sys">Claude está editando… (leva de 10 a 60 segundos)</div>`;
  box.innerHTML = html;
  box.scrollTop = box.scrollHeight;
}

/* ---------------- timeline ---------------- */

function renderTimeline() {
  const t = TL();
  const p = S.project;
  const ids = ["#ruler", "#trScenes", "#trTexts", "#trCaps", "#trVideo", "#trAudio", "#trMusic"];
  if (!t || p.status !== "pronto") {
    ids.forEach((s) => ($(s).innerHTML = ""));
    $("#tlInfo").textContent = "";
    return;
  }
  const pps = S.pps;
  const width = t.duration * pps + 240;
  $("#tlContent").style.width = `${width}px`;
  const edited = p.chat.some((m) => m.role === "ai");
  $("#tlInfo").textContent = `${t.clips.length} clipes · ${t.texts.length} textos · ${S.capLines.length} legendas · ${mmss(t.duration)}${edited ? " · editado pelo Claude" : ""}`;

  // régua
  const step = [0.5, 1, 2, 5, 10, 15, 30, 60, 120].find((s) => s * pps >= 70) || 300;
  let ruler = "";
  for (let s = 0; s <= t.duration + step; s += step) {
    ruler += `<div class="tick" style="left:${s * pps}px">${mmss(s)}</div>`;
    for (let k = 1; k < 4; k++) ruler += `<div class="tick minor" style="left:${(s + (step * k) / 4) * pps}px"></div>`;
  }
  $("#ruler").innerHTML = ruler;

  const box = (x0, x1) => `left:${x0 * pps}px;width:${Math.max(2, (x1 - x0) * pps - 1)}px`;
  const isSel = (type, id) => (S.sel && S.sel.type === type && S.sel.id === id ? " sel" : "");

  $("#trScenes").innerHTML = (t.scene_spans || []).map((s) =>
    `<div class="blk scene" data-seek="${s.start}" style="${box(s.start, s.end)}" title="${esc(s.desc)}">${s.code} · ${esc(s.label)}</div>`).join("");

  $("#trTexts").innerHTML = t.texts.map((x) =>
    `<div class="blk text${isSel("text", x.id)}" data-text="${x.id}" style="${box(x.start, x.end)}" title="${esc(x.text)}">${esc(x.text)}<i class="h r" data-h="r"></i></div>`).join("");

  $("#trCaps").innerHTML = t.captions.enabled ? S.capLines.map((l) => {
    const a = l[0].s, b = l[l.length - 1].e;
    return `<div class="blk cap" data-seek="${a}" style="${box(a, b)}">${esc(l.map((w) => w.w).join(" "))}</div>`;
  }).join("") : "";

  const info = p.info;
  const tw = Math.round(60 * (info.width / info.height));
  const maxThumb = Math.max(1, Math.floor(info.duration));
  $("#trVideo").innerHTML = t.clips.map((c, i) => {
    const w = (c.end - c.start) * pps;
    const n = Math.min(40, Math.ceil(w / tw));
    let thumbs = "";
    for (let k = 0; k < n; k++) {
      const st = c.src_in + (k * tw) / pps;
      const idx = Math.min(maxThumb, Math.floor(st) + 1);
      thumbs += `<img src="/media/projects/${p.id}/thumbs/t${pad(idx, 5)}.jpg" loading="lazy" alt="">`;
    }
    return `<div class="blk clip${isSel("clip", c.id)}" data-clip="${c.id}" style="${box(c.start, c.end)}">
      <div class="thumbs">${thumbs}</div>
      <span class="lbl">${i + 1} · ${esc(c.label)}</span>${c.zoom > 1.001 ? `<span class="zm">${c.zoom.toFixed(2)}x</span>` : ""}
      <i class="h l" data-h="l"></i><i class="h r" data-h="r"></i></div>`;
  }).join("");

  $("#trAudio").innerHTML = info.has_audio ? t.clips.map((c) => `<div class="blk audio" style="${box(c.start, c.end)}"><canvas data-wave="${c.id}"></canvas></div>`).join("") : "";
  drawWaves();

  $("#trMusic").innerHTML = t.music.enabled && t.music.file
    ? `<div class="blk music" style="${box(0, t.duration)}">♫ ${esc(t.music.file)} · ${Math.round(t.music.volume * 100)}%${t.music.duck ? " · abaixa na fala" : ""}</div>` : "";
}

function drawWaves() {
  const t = TL();
  const per = 20;
  for (const cv of $$("canvas[data-wave]")) {
    const c = t.clips.find((x) => x.id === cv.dataset.wave);
    const w = Math.min(8000, Math.max(2, Math.round(cv.parentElement.clientWidth)));
    const h = 24;
    cv.width = w;
    cv.height = h;
    const g = cv.getContext("2d");
    g.fillStyle = "#4b93ff";
    const a = c.src_in * per, b = c.src_out * per;
    for (let x = 0; x < w; x++) {
      const i = Math.floor(a + ((b - a) * x) / w);
      const v = S.peaks[i] || 0;
      const bh = Math.max(1, v * (h - 2));
      g.fillRect(x, (h - bh) / 2, 1, bh);
    }
  }
}

function tlTimeFromEvent(e) {
  const rect = $("#tlContent").getBoundingClientRect();
  return (e.clientX - rect.left) / S.pps;
}

/* arrastar bordas de clip e mover textos */
function startDrag(e, kind, id, handle) {
  e.preventDefault();
  e.stopPropagation();
  const t = clone(TL());
  const el = e.target.closest(".blk");
  const x0 = e.clientX;
  const left0 = parseFloat(el.style.left), w0 = parseFloat(el.style.width);
  let moved = false;
  const dur = S.project.info.duration;
  const item = kind === "clip" ? t.clips.find((c) => c.id === id) : t.texts.find((x) => x.id === id);
  const orig = { ...item };
  const onMove = (ev) => {
    const d = (ev.clientX - x0) / S.pps;
    if (Math.abs(ev.clientX - x0) > 2) moved = true;
    if (kind === "clip") {
      if (handle === "l") {
        item.src_in = Math.max(0, Math.min(orig.src_out - 0.2, orig.src_in + d));
        const dd = (item.src_in - orig.src_in) * S.pps;
        el.style.left = `${left0 + dd}px`;
        el.style.width = `${w0 - dd}px`;
      } else {
        item.src_out = Math.min(dur, Math.max(orig.src_in + 0.2, orig.src_out + d));
        el.style.width = `${w0 + (item.src_out - orig.src_out) * S.pps}px`;
      }
    } else if (handle === "r") {
      item.length = Math.max(0.5, Math.min(10, orig.length + d));
      el.style.width = `${w0 + (item.length - orig.length) * S.pps}px`;
    } else {
      const ns = Math.max(0, Math.min(TL().duration - 0.3, orig.start + d));
      el.style.left = `${ns * S.pps}px`;
      item._start = ns;
    }
  };
  const onUp = () => {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    S.sel = { type: kind, id };
    if (!moved) { renderTimeline(); renderInspector(); return; }
    if (kind === "text" && item._start !== undefined) {
      const c = TL().clips[clipAt(item._start)];
      item.clip_id = c.id;
      item.offset = item._start - c.start;
      delete item._start;
    }
    saveTimeline(t);
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

/* ---------------- inspetor ---------------- */

function renderInspector() {
  const box = $("#inspector");
  const t = TL();
  if (!t || !S.sel) { box.innerHTML = `<p class="hint">Clique num clip ou texto da timeline.</p>`; return; }
  if (S.sel.type === "clip") {
    const c = t.clips.find((x) => x.id === S.sel.id);
    if (!c) return;
    box.innerHTML = `
      <p class="hint">Clip ${t.clips.indexOf(c) + 1} · do original ${mmss(c.src_in)}–${mmss(c.src_out)} (${(c.src_out - c.src_in).toFixed(1)}s)</p>
      <label class="field">Nome da cena <input type="text" id="inLabel" value="${esc(c.label)}"></label>
      <label class="field">Zoom <input type="range" id="inZoom" min="1" max="1.4" step="0.01" value="${c.zoom}"><output>${c.zoom.toFixed(2)}x</output></label>
      <button id="inDel">🗑 Apagar clip</button>`;
    const upd = (f) => { const nt = clone(TL()); f(nt.clips.find((x) => x.id === c.id)); saveTimeline(nt, 400); };
    $("#inLabel").oninput = (e) => upd((x) => (x.label = e.target.value || "Cena"));
    $("#inZoom").oninput = (e) => {
      e.target.nextElementSibling.textContent = `${(+e.target.value).toFixed(2)}x`;
      video.style.transform = `scale(${e.target.value})`;
      upd((x) => (x.zoom = +e.target.value));
    };
    $("#inDel").onclick = deleteSelected;
  } else {
    const x = t.texts.find((y) => y.id === S.sel.id);
    if (!x) return;
    box.innerHTML = `
      <label class="field">Texto <textarea id="inText" rows="2">${esc(x.text)}</textarea></label>
      <label class="field">Estilo
        <select id="inStyle">${["gancho", "titulo", "destaque", "rodape", "cta", ...RICH].map((s) => `<option value="${s}" ${s === x.style ? "selected" : ""}>${RICH_NAMES[s] || s}</option>`).join("")}</select>
      </label>
      ${RICH.includes(x.style) ? `<p class="hint">Separe as partes com <b>|</b>. Ex.: ${esc(RICH_SAMPLES[x.style])}</p>` : ""}
      ${x.style === "isso_nisso" ? `<div class="row-btns">
        <label class="drop"><input type="file" accept="image/*" hidden data-img="img_a"><b>Imagem do “isso”</b><span>${x.img_a ? "✓ escolhida" : "antes"}</span></label>
        <label class="drop"><input type="file" accept="image/*" hidden data-img="img_b"><b>Imagem do “nisso”</b><span>${x.img_b ? "✓ escolhida" : "depois"}</span></label>
      </div>` : ""}
      <label class="field">Duração <input type="range" id="inLen" min="0.5" max="10" step="0.1" value="${x.length}"><output>${x.length.toFixed(1)}s</output></label>
      <button id="inDel">🗑 Apagar texto</button>`;
    const upd = (f) => { const nt = clone(TL()); f(nt.texts.find((y) => y.id === x.id)); saveTimeline(nt, 500); };
    $("#inText").oninput = (e) => upd((y) => (y.text = e.target.value));
    $("#inStyle").onchange = (e) => {
      const st = e.target.value;
      upd((y) => { y.style = st; if (RICH.includes(st) && !y.text.includes("|") && st !== "aviso") y.text = RICH_SAMPLES[st]; });
    };
    for (const inp of $$("input[data-img]", box)) inp.onchange = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      const fd = new FormData();
      fd.append("file", f);
      try {
        const { file } = await api(`/api/projects/${S.project.id}/asset`, { method: "POST", body: fd });
        upd((y) => (y[inp.dataset.img] = file));
        toast("Imagem adicionada ✓");
      } catch (err) { toast(err.message); }
    };
    $("#inLen").oninput = (e) => { e.target.nextElementSibling.textContent = `${(+e.target.value).toFixed(1)}s`; upd((y) => (y.length = +e.target.value)); };
    $("#inDel").onclick = deleteSelected;
  }
}

/* ---------------- painéis, diálogos ---------------- */

function showPanel(name) {
  $$(".rail-btn").forEach((b) => b.classList.toggle("active", b.dataset.panel === name));
  $$(".panel section").forEach((s) => s.classList.toggle("active", s.dataset.panel === name));
}

function openSettings() {
  const c = S.cfg;
  $("#cfgKey").value = "";
  $("#cfgKey").placeholder = c.has_key ? `chave salva (${c.key_hint}) — deixe vazio para manter` : "sk-ant-…";
  $("#cfgEl").value = "";
  $("#cfgEl").placeholder = c.has_elevenlabs ? `chave salva (${c.elevenlabs_hint}) — deixe vazio para manter` : "sk_…";
  $("#cfgModel").innerHTML = c.models.map((m) => `<option value="${m.id}" ${m.id === c.model ? "selected" : ""}>${esc(m.name)}</option>`).join("");
  $("#cfgEffort").value = c.effort;
  $("#cfgLang").value = c.language;
  $("#cfgWhisper").innerHTML = c.whisper
    ? "✅ Transcrição local ativa (faster-whisper): legendas e cortes por palavra, sem gastar tokens."
    : "⚠️ Transcrição local não instalada. Rode <b>pip install faster-whisper</b> para legendas e cortes inteligentes.";
  $("#settingsDlg").showModal();
}

async function saveSettings() {
  const body = { model: $("#cfgModel").value, effort: $("#cfgEffort").value, language: $("#cfgLang").value };
  const key = $("#cfgKey").value.trim();
  if (key) body.api_key = key;
  const el = $("#cfgEl").value.trim();
  if (el) body.elevenlabs_key = el;
  S.cfg = await api("/api/config", { method: "POST", json: body });
  renderConfig();
  toast("Configurações salvas.");
}

async function openPhone() {
  try {
    const { url, pin } = await api("/api/connect");
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    $("#qr").innerHTML = qr.createSvgTag({ cellSize: 6, margin: 0, scalable: true });
    $("#phoneUrl").textContent = url;
    $("#phonePin").textContent = pin;
    $("#phoneDlg").showModal();
  } catch (e) { toast(e.message); }
}

function openExport() {
  if (!ready()) return toast("Abra um projeto primeiro.");
  const t = TL();
  const [w, h] = outputSize(t.format, S.project.info);
  $("#expInfo").textContent = `${w}×${h} · ${mmss(t.duration)} · ${t.clips.length} cortes${t.captions.enabled ? " · legendas" : ""}${t.music.enabled ? " · música" : ""}`;
  renderExport();
  if (!$("#exportDlg").open) $("#exportDlg").showModal();
}

function renderExport() {
  const r = S.project?.render;
  const bar = $("#expBar");
  const st = $("#expStatus");
  const links = $("#expLinks");
  $("#expGo").disabled = r?.status === "renderizando";
  if (!r) { bar.style.width = "0"; st.textContent = ""; links.innerHTML = ""; return; }
  bar.style.width = `${Math.round((r.progress || 0) * 100)}%`;
  if (r.status === "renderizando") { st.textContent = `Renderizando… ${Math.round((r.progress || 0) * 100)}%`; links.innerHTML = ""; }
  else if (r.status === "erro") { st.textContent = `Erro: ${r.error}`; links.innerHTML = ""; }
  else if (r.status === "pronto") {
    st.textContent = "Pronto! 🎉";
    const base = `/api/projects/${S.project.id}/download`;
    links.innerHTML = `<a href="${base}/${r.file}">⬇ Baixar vídeo MP4</a><a class="sec" href="${base}/legendas.srt">Legendas .srt</a>`;
  }
}

async function startRender() {
  try {
    await api(`/api/projects/${S.project.id}/render`, { method: "POST", json: { quality: $("#expQuality").value } });
    S.project.render = { status: "renderizando", progress: 0 };
    renderExport();
    ensurePolling();
  } catch (e) { toast(e.message); }
}

/* ---------------- eventos ---------------- */

function bindUI() {
  const actions = {
    new: () => $("#fileInput").click(), undo, export: openExport, settings: openSettings, phone: openPhone,
    play: () => (S.playing ? pause() : play()), start: () => seek(0), end: () => seek(TL()?.duration || 0),
    back: () => seek(S.outTime - 1), fwd: () => seek(S.outTime + 1),
    split: splitAtPlayhead, delete: deleteSelected, zoomclip: toggleZoom,
  };
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-action]");
    if (a && actions[a.dataset.action]) return actions[a.dataset.action]();
    const sk = e.target.closest("[data-seek]");
    if (sk) { pause(); seek(+sk.dataset.seek); }
  });

  $$(".rail-btn").forEach((b) => (b.onclick = () => showPanel(b.dataset.panel)));
  $$(".pages button").forEach((b) => (b.onclick = () => {
    const pg = b.dataset.page;
    if (pg === "exportar") return openExport();
    $$(".pages button").forEach((x) => x.classList.toggle("active", x === b));
    showPanel({ midia: "midia", modelos: "modelos", edicao: "inspetor", audio: "audio" }[pg]);
  }));

  // envio por clique e arrastar
  for (const inp of $$('input[type=file][accept="video/*"]')) inp.onchange = (e) => { pickFile(e.target.files[0]); e.target.value = ""; };
  for (const target of [$("#stage"), $("#dropSmall")]) {
    target.addEventListener("dragover", (e) => { e.preventDefault(); target.classList.add("over"); });
    target.addEventListener("dragleave", () => target.classList.remove("over"));
    target.addEventListener("drop", (e) => { e.preventDefault(); target.classList.remove("over"); pickFile(e.dataTransfer.files[0]); });
  }
  $("#upPreset").onchange = updateUpPresetDesc;
  $("#uploadDlg").addEventListener("close", () => { if ($("#uploadDlg").returnValue === "ok") uploadPicked(); });
  $("#settingsDlg").addEventListener("close", () => { if ($("#settingsDlg").returnValue === "ok") saveSettings(); });
  $("#expGo").onclick = startRender;

  $("#projList").onclick = async (e) => {
    const del = e.target.closest("[data-del]");
    if (del) {
      e.stopPropagation();
      if (!confirm("Apagar este projeto e seus arquivos?")) return;
      await api(`/api/projects/${del.dataset.del}`, { method: "DELETE" });
      if (S.project?.id === del.dataset.del) { S.project = null; video.removeAttribute("src"); renderAll(); }
      const list = await loadProjects();
      if (!S.project && list.length) openProject(list[0].id);
      return;
    }
    const li = e.target.closest("li[data-id]");
    if (li) openProject(li.dataset.id);
  };

  $("#presetList").onclick = (e) => {
    const b = e.target.closest("[data-preset]");
    if (!b) return;
    $("#presetSel").value = b.dataset.preset;
    renderSidePanels();
    if (ready()) runAI("", true);
  };
  $("#presetSel").onchange = renderSidePanels;
  $("#autoBtn").onclick = () => runAI("", true);
  $("#textStyles").onclick = $("#richStyles").onclick = (e) => { const b = e.target.closest("[data-addtext]"); if (b) addText(b.dataset.addtext); };

  $("#chatForm").onsubmit = (e) => {
    e.preventDefault();
    const text = $("#chatText").value.trim();
    if (!text) return;
    $("#chatText").value = "";
    runAI(text, false);
  };
  $("#chatText").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chatForm").requestSubmit(); }
  });
  $("#chips").onclick = (e) => { if (e.target.tagName === "BUTTON") runAI(e.target.textContent, false); };

  // legendas, formato, música
  const editTl = (f, debounce = 0) => { if (!ready()) return; const t = clone(TL()); f(t); saveTimeline(t, debounce); };
  $("#capEnabled").onchange = (e) => editTl((t) => (t.captions.enabled = e.target.checked));
  $("#capStyle").onchange = (e) => editTl((t) => (t.captions.style = e.target.value));
  $("#capPos").onchange = (e) => editTl((t) => (t.captions.position = e.target.value));
  $("#capWords").oninput = (e) => { $("#capWordsOut").textContent = e.target.value; editTl((t) => (t.captions.words = +e.target.value), 300); };
  $("#formatSel").onchange = (e) => editTl((t) => (t.format = e.target.value));
  $("#musicEnabled").onchange = (e) => {
    if (e.target.checked && !TL()?.music.file) { e.target.checked = false; return toast("Escolha uma música na lista primeiro."); }
    editTl((t) => (t.music.enabled = e.target.checked));
  };
  $("#musicDuck").onchange = (e) => editTl((t) => (t.music.duck = e.target.checked));
  $("#musicVol").oninput = (e) => { $("#musicVolOut").textContent = `${Math.round(e.target.value * 100)}%`; editTl((t) => (t.music.volume = +e.target.value), 300); };
  $("#musicList").onclick = (e) => {
    const li = e.target.closest("[data-music]");
    if (li) editTl((t) => { t.music.file = li.dataset.music; t.music.enabled = true; });
  };
  $("#musicInput").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try { S.music = await api("/api/music", { method: "POST", body: fd }); renderMusicList(); toast("Música enviada."); }
    catch (err) { toast(err.message); }
    e.target.value = "";
  };

  $("#logoEnabled").onchange = (e) => editTl((t) => (t.logo = e.target.checked));

  // fundo
  const bgRows = () => {
    const m = $("#bgMode").value;
    $("#bgColorRow").hidden = m !== "cor";
    $("#bgImageRow").hidden = m !== "imagem";
  };
  $("#bgMode").onchange = bgRows;
  bgRows();
  $("#bgImage").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f || !S.project) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      await api(`/api/projects/${S.project.id}/background-image`, { method: "POST", body: fd });
      $("#bgImageName").textContent = f.name;
    } catch (err) { toast(err.message); }
  };
  $("#bgApply").onclick = async () => {
    if (!ready()) return toast("Abra um projeto pronto primeiro.");
    try {
      await api(`/api/projects/${S.project.id}/background`, { method: "POST", json: { mode: $("#bgMode").value, color: $("#bgColor").value } });
      pause();
      S.project.status = "analisando";
      S.project.status_text = "Trocando o fundo…";
      S.project.progress = 0;
      renderBusy();
      ensurePolling();
    } catch (err) { toast(err.message); }
  };
  $("#bgReset").onclick = async () => {
    if (!S.project) return;
    try { setProject(await api(`/api/projects/${S.project.id}/background/reset`, { method: "POST" })); setVideoSource(); toast("Fundo original de volta."); }
    catch (err) { toast(err.message); }
  };

  // timeline
  $("#tlZoom").oninput = (e) => { S.pps = +e.target.value; renderTimeline(); drawFrame(); };
  $("#tlContent").addEventListener("mousedown", (e) => {
    const clip = e.target.closest("[data-clip]");
    const text = e.target.closest("[data-text]");
    const handle = e.target.dataset.h;
    if (clip && handle) return startDrag(e, "clip", clip.dataset.clip, handle);
    if (text) return startDrag(e, "text", text.dataset.text, handle);
    if (clip) { S.sel = { type: "clip", id: clip.dataset.clip }; showPanel("inspetor"); renderTimeline(); renderInspector(); }
    if (!e.target.closest("[data-seek]")) { pause(); seek(tlTimeFromEvent(e)); }
  });

  video.addEventListener("click", () => (S.playing ? pause() : play()));
  window.addEventListener("resize", () => { fitFrame(); drawWaves(); });

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select") || $("dialog[open]")) return;
    if (e.code === "Space") { e.preventDefault(); S.playing ? pause() : play(); }
    else if (e.key === "s" || e.key === "S") splitAtPlayhead();
    else if (e.key === "Delete" || e.key === "Backspace") deleteSelected();
    else if (e.key === "z" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); undo(); }
    else if (e.key === "z") toggleZoom();
    else if (e.key === "ArrowLeft") seek(S.outTime - (e.shiftKey ? 1 : 1 / 30));
    else if (e.key === "ArrowRight") seek(S.outTime + (e.shiftKey ? 1 : 1 / 30));
    else if (e.key === "Home") seek(0);
  });
}

init().catch((e) => toast(`Não consegui conectar ao servidor: ${e.message}`, 8000));
