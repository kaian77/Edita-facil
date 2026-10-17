/* Tour virtual em 3D (Three.js).
 * - 360°: a foto envolve a câmera numa esfera.
 * - Foto comum: vira uma parede curva em volta da câmera, com leve movimento de profundidade.
 * Portas (hotspots) levam de um cômodo a outro. */
import * as THREE from "./vendor/three.module.min.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const STATIC = !!window.TOUR_STATIC;
const params = new URLSearchParams(location.search);
const VISITOR = STATIC || params.get("view") === "1";
if (VISITOR) document.body.classList.add("visitor");

const T = { tour: null, room: null, lon: 0, lat: 0, fov: 70, adding: false, presenting: false, presentTimer: null, lastMove: 0 };

function toast(msg, ms = 3500) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), ms);
}

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

const photoUrl = (f) => (STATIC ? `photos/${f}` : `/media/tours/${T.tour.id}/photos/${f}`);

/* ---------------- cena 3D ---------------- */

const canvas = $("#canvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x07080b);
const camera = new THREE.PerspectiveCamera(70, 1, 0.1, 2000);
let mesh = null;
let limits = null; // para fotos comuns: até onde dá para olhar
const loader = new THREE.TextureLoader();
const texCache = new Map();

function resize() {
  const v = $("#view");
  renderer.setSize(v.clientWidth, v.clientHeight, false);
  camera.aspect = v.clientWidth / Math.max(1, v.clientHeight);
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);

function loadTexture(file) {
  if (texCache.has(file)) return Promise.resolve(texCache.get(file));
  return new Promise((ok, fail) => loader.load(photoUrl(file), (tex) => {
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    texCache.set(file, tex);
    ok(tex);
  }, undefined, fail));
}

async function buildRoom(room) {
  const tex = await loadTexture(room.photo);
  if (mesh) { scene.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose(); }
  if (room.kind === "360") {
    const geo = new THREE.SphereGeometry(500, 80, 48);
    geo.scale(-1, 1, 1);
    mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex }));
    limits = null;
  } else {
    // parede curva: a largura da foto vira um arco em volta de quem olha
    const ratio = room.ratio || tex.image.width / tex.image.height;
    const arc = THREE.MathUtils.degToRad(Math.min(160, Math.max(70, ratio * 68)));
    const r = 10;
    const h = (r * arc) / ratio;
    const geo = new THREE.CylinderGeometry(r, r, h, 96, 1, true, Math.PI - arc / 2, arc);
    geo.scale(-1, 1, 1);
    mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex, side: THREE.FrontSide }));
    const vHalf = THREE.MathUtils.radToDeg(Math.atan(h / 2 / r));
    limits = { lon: THREE.MathUtils.radToDeg(arc / 2), lat: vHalf };
  }
  scene.add(mesh);
}

function clampView() {
  if (!limits) { T.lat = Math.max(-85, Math.min(85, T.lat)); return; }
  const vfov = T.fov;
  const hfov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(vfov / 2)) * camera.aspect));
  const maxLon = Math.max(0, limits.lon - hfov / 2);
  const maxLat = Math.max(0, limits.lat - vfov / 2);
  T.lon = Math.max(-maxLon, Math.min(maxLon, T.lon));
  T.lat = Math.max(-maxLat, Math.min(maxLat, T.lat));
  // se a foto é menor que a tela, diminui o campo de visão para preencher
  const fit = Math.min(limits.lat * 2 * 0.86, THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(limits.lon * 0.9)) / camera.aspect)) * 0.9);
  if (T.fov > fit) T.fov = fit;
}

function dir(lon, lat) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(Math.sin(phi) * Math.sin(theta), Math.cos(phi), -Math.sin(phi) * Math.cos(theta));
}

let t0 = performance.now();
function frame(now) {
  const dt = (now - t0) / 1000;
  t0 = now;
  if (T.room) {
    const idle = now - T.lastMove > 3500;
    if (T.presenting || (idle && VISITOR)) {
      if (limits) T.lon = Math.sin(now / 4000) * Math.max(0, limits.lon - 30);
      else T.lon += dt * 6;
    }
    clampView();
    camera.fov += (T.fov - camera.fov) * 0.15;
    camera.updateProjectionMatrix();
    // leve "respiração" da câmera: dá sensação de profundidade nas fotos comuns
    const breathe = limits ? Math.sin(now / 2600) * 0.35 : 0;
    camera.position.copy(dir(T.lon, 0).multiplyScalar(breathe));
    camera.lookAt(camera.position.clone().add(dir(T.lon, T.lat)));
    renderer.render(scene, camera);
    placeHotspots();
  }
  requestAnimationFrame(frame);
}

/* ---------------- controles ---------------- */

let drag = null;
canvas.addEventListener("pointerdown", (e) => {
  if (T.adding) return pickDoor(e);
  drag = { x: e.clientX, y: e.clientY, lon: T.lon, lat: T.lat };
  canvas.setPointerCapture(e.pointerId);
  canvas.style.cursor = "grabbing";
  stopPresent();
});
canvas.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const k = T.fov / canvas.clientHeight;
  T.lon = drag.lon - (e.clientX - drag.x) * k;
  T.lat = drag.lat + (e.clientY - drag.y) * k;
  T.lastMove = performance.now();
  $("#help").style.opacity = 0;
});
canvas.addEventListener("pointerup", () => { drag = null; canvas.style.cursor = ""; });
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  T.fov = Math.max(30, Math.min(limits ? 80 : 95, T.fov + e.deltaY * 0.04));
  T.lastMove = performance.now();
}, { passive: false });

/* ---------------- portas ---------------- */

function placeHotspots() {
  const box = $("#hotspots");
  const w = canvas.clientWidth, h = canvas.clientHeight;
  for (const el of box.children) {
    const v = dir(+el.dataset.yaw, +el.dataset.pitch).multiplyScalar(limits ? 9 : 400).project(camera);
    const visible = v.z < 1 && Math.abs(v.x) < 1.2 && Math.abs(v.y) < 1.2;
    el.style.display = visible ? "" : "none";
    if (visible) { el.style.left = `${(v.x + 1) / 2 * w}px`; el.style.top = `${(1 - v.y) / 2 * h}px`; }
  }
}

function renderHotspots() {
  const rooms = Object.fromEntries(T.tour.rooms.map((r) => [r.id, r]));
  $("#hotspots").innerHTML = T.room.links.map((l, i) => {
    const target = rooms[l.to];
    if (!target) return "";
    return `<div class="hs" data-to="${l.to}" data-yaw="${l.yaw}" data-pitch="${l.pitch}">
      <div class="ring">➜</div><div class="lbl">${esc(l.label || target.name)}</div>
      ${VISITOR ? "" : `<button class="x" data-rm="${i}" title="Remover porta">✕</button>`}
    </div>`;
  }).join("");
}

$("#hotspots").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-rm]");
  if (rm) {
    T.room.links.splice(+rm.dataset.rm, 1);
    saveRooms();
    renderHotspots();
    return;
  }
  const hs = e.target.closest(".hs");
  if (hs) goTo(hs.dataset.to);
});

function pickDoor(e) {
  const rect = canvas.getBoundingClientRect();
  const ndc = new THREE.Vector3(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1, 0.5);
  const d = ndc.unproject(camera).sub(camera.position).normalize();
  const yaw = THREE.MathUtils.radToDeg(Math.atan2(d.x, -d.z));
  const pitch = THREE.MathUtils.radToDeg(Math.asin(d.y));
  const others = T.tour.rooms.filter((r) => r.id !== T.room.id);
  if (!others.length) { toast("Envie mais fotos para ligar os cômodos."); return; }
  const pick = $("#doorPick");
  pick.hidden = false;
  pick.style.left = `${Math.min(e.clientX - rect.left, rect.width - 200)}px`;
  pick.style.top = `${Math.min(e.clientY - rect.top, rect.height - 40 * others.length - 40)}px`;
  pick.innerHTML = `<b>Essa porta leva para:</b>` + others.map((r) => `<button data-to="${r.id}">${esc(r.name)}</button>`).join("") + `<button data-cancel="1">Cancelar</button>`;
  pick.onclick = (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    pick.hidden = true;
    setAdding(false);
    if (b.dataset.cancel) return;
    T.room.links.push({ to: b.dataset.to, yaw: +yaw.toFixed(1), pitch: +pitch.toFixed(1), label: "" });
    // cria a porta de volta automaticamente, se ainda não existir
    const back = T.tour.rooms.find((r) => r.id === b.dataset.to);
    if (back && !back.links.some((l) => l.to === T.room.id)) back.links.push({ to: T.room.id, yaw: 180, pitch: -8, label: "" });
    saveRooms();
    renderHotspots();
    toast("Porta adicionada ✓");
  };
}

function setAdding(on) {
  T.adding = on;
  canvas.classList.toggle("adding", on);
  $("#addDoor").classList.toggle("on", on);
  if (on) toast("Clique na imagem onde fica a passagem para o outro cômodo.");
}

/* ---------------- navegação ---------------- */

async function goTo(id, instant = false) {
  const room = T.tour.rooms.find((r) => r.id === id);
  if (!room) return;
  if (!instant) {
    T.fov = Math.max(30, T.fov - 25); // efeito de "andar" para dentro
    $("#fade").classList.add("on");
    await new Promise((r) => setTimeout(r, 330));
  }
  try { await buildRoom(room); } catch { toast("Não consegui carregar a foto."); }
  T.room = room;
  T.lon = room.yaw || 0;
  T.lat = 0;
  T.fov = 70;
  camera.fov = 85;
  renderHotspots();
  $("#infoTitle").textContent = room.name;
  $("#infoDesc").textContent = room.desc || "";
  document.querySelectorAll("[data-room]").forEach((el) => el.classList.toggle("active", el.dataset.room === id));
  $("#fade").classList.remove("on");
}

function present() {
  if (T.presenting) return stopPresent();
  T.presenting = true;
  $("#present").textContent = "❚❚ Parar";
  const next = () => {
    const rooms = T.tour.rooms;
    const i = rooms.findIndex((r) => r.id === T.room.id);
    goTo(rooms[(i + 1) % rooms.length].id);
  };
  T.presentTimer = setInterval(next, 7000);
}
function stopPresent() {
  if (!T.presenting) return;
  T.presenting = false;
  clearInterval(T.presentTimer);
  $("#present").textContent = "▶ Apresentação";
}

/* ---------------- painel de edição ---------------- */

function renderSide() {
  const t = T.tour;
  $("#tName").value = t.name;
  $("#roomCount").textContent = t.rooms.length ? `(${t.rooms.length})` : "";
  $("#rooms").innerHTML = t.rooms.map((r, i) => `
    <li data-room="${r.id}" class="${T.room?.id === r.id ? "active" : ""}">
      <img src="${photoUrl(r.thumb)}" alt="">
      <div><input type="text" value="${esc(r.name)}" data-name="${r.id}">
        <div class="meta">${r.kind === "360" ? "360°" : "Foto"} · ${r.links.length} porta(s) ${t.start === r.id ? "· início" : ""}</div></div>
      <div class="ops">
        <button data-up="${i}" title="Subir">▲</button>
        <button data-kind="${r.id}" title="Trocar tipo 360°/foto">⟳</button>
        <button data-del="${r.id}" title="Apagar">✕</button>
      </div>
    </li>`).join("");
  $("#lTitle").value = t.listing?.title || "";
  $("#lDesc").value = t.listing?.description || "";
  $("#lHigh").value = (t.listing?.highlights || []).join("\n");
  $("#strip").innerHTML = t.rooms.map((r) => `<button data-room="${r.id}" class="${T.room?.id === r.id ? "active" : ""}"><img src="${photoUrl(r.thumb)}" alt=""><span>${esc(r.name)}</span></button>`).join("");
  $("#empty").hidden = t.rooms.length > 0;
  $("#info").hidden = !t.rooms.length;
  $("#editBar").hidden = !t.rooms.length;
}

let saveT = null;
function saveRooms(extra = {}) {
  if (STATIC) return;
  clearTimeout(saveT);
  saveT = setTimeout(async () => {
    try {
      const fresh = await api(`/api/tours/${T.tour.id}`, { method: "PUT", json: { rooms: T.tour.rooms, ...extra } });
      T.tour.start = fresh.start;
      T.tour.rooms = fresh.rooms;
      T.room = fresh.rooms.find((r) => r.id === T.room?.id) || T.room;
      renderSide();
    } catch (e) { toast(e.message); }
  }, 350);
}

function bindSide() {
  $("#rooms").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    const rooms = T.tour.rooms;
    if (b?.dataset.up) {
      const i = +b.dataset.up;
      if (i > 0) { [rooms[i - 1], rooms[i]] = [rooms[i], rooms[i - 1]]; saveRooms({ start: rooms[0].id }); renderSide(); }
      return;
    }
    if (b?.dataset.kind) {
      const r = rooms.find((x) => x.id === b.dataset.kind);
      r.kind = r.kind === "360" ? "foto" : "360";
      saveRooms();
      if (T.room?.id === r.id) goTo(r.id, true);
      renderSide();
      return;
    }
    if (b?.dataset.del) {
      if (!confirm("Apagar este cômodo?")) return;
      T.tour.rooms = rooms.filter((r) => r.id !== b.dataset.del);
      saveRooms();
      if (T.room?.id === b.dataset.del) T.tour.rooms[0] ? goTo(T.tour.rooms[0].id, true) : (T.room = null);
      renderSide();
      return;
    }
    const li = e.target.closest("li[data-room]");
    if (li && e.target.tagName !== "INPUT") goTo(li.dataset.room);
  });
  $("#rooms").addEventListener("input", (e) => {
    const id = e.target.dataset.name;
    if (!id) return;
    const r = T.tour.rooms.find((x) => x.id === id);
    r.name = e.target.value;
    if (T.room?.id === id) $("#infoTitle").textContent = r.name;
    saveRooms();
  });
  $("#strip").addEventListener("click", (e) => { const b = e.target.closest("[data-room]"); if (b) { stopPresent(); goTo(b.dataset.room); } });
  $("#tName").oninput = () => { T.tour.name = $("#tName").value; saveRooms({ name: T.tour.name }); };
  for (const id of ["#lTitle", "#lDesc", "#lHigh"]) $(id).oninput = () => saveRooms({ listing: {
    title: $("#lTitle").value, description: $("#lDesc").value, highlights: $("#lHigh").value.split("\n").filter(Boolean) } });
  $("#copyListing").onclick = () => {
    const txt = `${$("#lTitle").value}\n\n${$("#lDesc").value}\n\n${$("#lHigh").value.split("\n").filter(Boolean).map((x) => "• " + x).join("\n")}`;
    navigator.clipboard.writeText(txt).then(() => toast("Texto copiado!"));
  };

  $("#photoInput").onchange = (e) => { uploadPhotos(e.target.files); e.target.value = ""; };
  const drop = $("#photoDrop");
  for (const target of [drop, $("#view")]) {
    target.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    target.addEventListener("dragleave", () => drop.classList.remove("over"));
    target.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); uploadPhotos(e.dataTransfer.files); });
  }
  $("#addDoor").onclick = () => setAdding(!T.adding);
  $("#setStartView").onclick = () => { T.room.yaw = +T.lon.toFixed(1); saveRooms(); toast("Vista inicial salva ✓"); };
  $("#present").onclick = present;
  $("#aiDescribe").onclick = describe;
  $("#makeVideo").onclick = async () => {
    try { const p = await api(`/api/tours/${T.tour.id}/video`, { method: "POST", json: {} }); location.href = `/?p=${p.id}`; }
    catch (e) { toast(e.message); }
  };
  $("#shareView").onclick = () => window.open(`/tour.html?id=${T.tour.id}&view=1`, "_blank");
  $("#downloadZip").onclick = () => (location.href = `/api/tours/${T.tour.id}/zip`);
  $("#newTour").onclick = async () => {
    const name = prompt("Nome do imóvel:", "Meu Airbnb");
    if (name === null) return;
    const t = await api("/api/tours", { method: "POST", json: { name } });
    await loadList(t.id);
  };
  $("#tourSel").onchange = () => openTour($("#tourSel").value);
}

async function uploadPhotos(files) {
  const list = [...files].filter((f) => f.type.startsWith("image/"));
  if (!list.length) return;
  if (!T.tour) await loadList((await api("/api/tours", { method: "POST", json: { name: "Meu Airbnb" } })).id);
  $("#upProg").hidden = false;
  for (let i = 0; i < list.length; i++) {
    const fd = new FormData();
    fd.append("files", list[i]);
    $("#upBar").style.width = `${Math.round((i / list.length) * 100)}%`;
    try { T.tour = await api(`/api/tours/${T.tour.id}/photos`, { method: "POST", body: fd }); }
    catch (e) { toast(e.message); }
  }
  $("#upProg").hidden = true;
  renderSide();
  if (!T.room && T.tour.rooms.length) goTo(T.tour.start, true);
  const n360 = T.tour.rooms.filter((r) => r.kind === "360").length;
  toast(`${list.length} foto(s) adicionada(s)${n360 ? ` · ${n360} panorâmica(s) 360°` : ""}. Agora clique em ✦ Descrever com IA.`, 5000);
}

async function describe() {
  const b = $("#aiDescribe");
  b.disabled = true;
  b.textContent = "A IA está olhando as fotos…";
  try {
    const { tour, usage } = await api(`/api/tours/${T.tour.id}/describe`, { method: "POST" });
    T.tour = tour;
    renderSide();
    goTo(tour.start, true);
    $("#listingBox").open = true;
    toast(`Pronto! Cômodos, portas e anúncio criados · US$ ${usage.cost_usd.toFixed(3)}`, 5000);
  } catch (e) { toast(e.message, 6000); }
  b.disabled = false;
  b.textContent = "✦ Descrever com IA";
}

/* ---------------- abrir ---------------- */

async function openTour(id) {
  stopPresent();
  T.tour = STATIC ? await (await fetch("tour.json")).json() : await api(`/api/tours/${id}`);
  T.room = null;
  if (mesh) { scene.remove(mesh); mesh = null; }
  $("#hotspots").innerHTML = "";
  if (!VISITOR) {
    renderSide();
    history.replaceState(null, "", `/tour.html?id=${T.tour.id}`);
  } else {
    $("#strip").innerHTML = T.tour.rooms.map((r) => `<button data-room="${r.id}"><img src="${photoUrl(r.thumb)}" alt=""><span>${esc(r.name)}</span></button>`).join("");
    $("#strip").onclick = (e) => { const b = e.target.closest("[data-room]"); if (b) goTo(b.dataset.room); };
    $("#present").onclick = present;
    document.title = T.tour.listing?.title || T.tour.name;
  }
  $("#empty").hidden = T.tour.rooms.length > 0;
  if (T.tour.rooms.length) await goTo(T.tour.start || T.tour.rooms[0].id, true);
}

async function loadList(selectId) {
  const list = await api("/api/tours");
  $("#tourSel").innerHTML = list.map((t) => `<option value="${t.id}">${esc(t.name)} (${t.rooms})</option>`).join("") || `<option value="">Nenhum tour</option>`;
  const id = selectId || params.get("id") || list[0]?.id;
  if (id) { $("#tourSel").value = id; await openTour(id); }
  else { $("#empty").hidden = false; $("#info").hidden = true; $("#editBar").hidden = true; }
}

resize();
requestAnimationFrame(frame);
if (STATIC) openTour();
else if (VISITOR) openTour(params.get("id")).catch((e) => toast(e.message));
else { bindSide(); loadList().catch((e) => toast(`Não consegui conectar ao servidor: ${e.message}`, 8000)); }
