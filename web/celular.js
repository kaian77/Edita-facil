/* Edita Fácil no celular: escolher vídeo → estilo → "Editar sozinho". O servidor faz o resto. */
const M = { cfg: null, presets: [], file: null, preset: null, seconds: 45, current: null, timer: null };

async function init() {
  [M.cfg, M.presets] = await Promise.all([api("/api/config"), api("/api/presets")]);
  M.preset = M.presets.find((p) => p.id === "reels-viral")?.id || M.presets[0]?.id;
  renderStyles();
  $("#cStyle").innerHTML += M.presets.map((p) => `<option value="${p.id}">${p.icon} ${esc(p.name)}</option>`).join("");
  if (M.cfg.has_elevenlabs) {
    const brand = await api("/api/brand").catch(() => ({}));
    api("/api/voices").then((vs) => {
      $("#voice").innerHTML += vs.map((v) => `<option value="${v.id}" ${v.id === brand.voice_id ? "selected" : ""}>${esc(v.name)}${v.category === "cloned" ? " (sua voz)" : ""}</option>`).join("");
    }).catch(() => {});
  }
  bind();
  if (!M.cfg.has_key) toast("Toque em ⚙ e coloque a chave da IA para editar sozinho.", 5000);
  const p = new URLSearchParams(location.search).get("p");
  if (p) openDetail(p);
}

function go(view) {
  $$(".view").forEach((v) => (v.hidden = v.dataset.view !== view));
  $$(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.go === view || (view === "detalhe" && b.dataset.go === "videos")));
  if (view !== "detalhe") { clearInterval(M.timer); M.current = null; }
  if (view === "videos") loadList();
  window.scrollTo(0, 0);
}

function renderStyles() {
  $("#styles").innerHTML = M.presets.map((p) => `
    <button data-p="${p.id}" class="${p.id === M.preset ? "on" : ""}"><b>${p.icon} ${esc(p.name)}</b><span>${esc(p.description)}</span></button>`).join("");
}

function bind() {
  $$(".tabs button").forEach((b) => (b.onclick = () => go(b.dataset.go)));
  $("#styles").onclick = (e) => { const b = e.target.closest("[data-p]"); if (b) { M.preset = b.dataset.p; renderStyles(); } };
  $("#file").onchange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    M.file = f;
    const v = $("#pickPreview");
    v.src = URL.createObjectURL(f);
    v.hidden = false;
    v.play().catch(() => {});
    $("#pickEmpty").hidden = true;
    $("#pick").classList.add("has");
  };
  $("#goEdit").onclick = upload;
  $("#secs").onclick = (e) => {
    const b = e.target.closest("[data-s]");
    if (!b) return;
    M.seconds = +b.dataset.s;
    $$("#secs button").forEach((x) => x.classList.toggle("on", x === b));
  };
  $("#goCreate").onclick = create;
  $("#list").onclick = (e) => { const li = e.target.closest("[data-id]"); if (li) openDetail(li.dataset.id); };
  $("#back").onclick = () => go("videos");
  $("#quick").onclick = (e) => { if (e.target.tagName === "BUTTON") adjust(e.target.textContent); };
  $("#goAdj").onclick = () => adjust($("#adjText").value.trim());
  $("#exportNow").onclick = () => exportNow();
  $("#share").onclick = share;
  $("#cfgBtn").onclick = () => {
    $("#kA").value = "";
    $("#kE").value = "";
    $("#kHint").textContent = `${M.cfg.has_key ? "✓ Chave da IA salva." : "Falta a chave da IA (console.anthropic.com)."} ${M.cfg.has_elevenlabs ? "✓ ElevenLabs salva." : ""}`;
    $("#cfg").showModal();
  };
  $("#cfg").addEventListener("close", async () => {
    if ($("#cfg").returnValue !== "ok") return;
    const body = {};
    if ($("#kA").value.trim()) body.api_key = $("#kA").value.trim();
    if ($("#kE").value.trim()) body.elevenlabs_key = $("#kE").value.trim();
    if (Object.keys(body).length) { M.cfg = await api("/api/config", { method: "POST", json: body }); toast("Salvo ✓"); }
  });
}

function upload() {
  if (!M.file) return toast("Escolha um vídeo primeiro.");
  const fd = new FormData();
  fd.append("file", M.file);
  fd.append("auto", "true");
  fd.append("export", "true");
  fd.append("preset", M.preset);
  fd.append("extra", $("#extra").value);
  const btn = $("#goEdit");
  btn.disabled = true;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/projects");
  xhr.upload.onprogress = (e) => e.lengthComputable && (btn.textContent = `Enviando… ${Math.round((e.loaded / e.total) * 100)}%`);
  xhr.onload = () => {
    btn.disabled = false;
    btn.textContent = "✦ Editar sozinho";
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status !== 200) return toast(data.detail || "Falha no envio.");
    M.file = null;
    $("#pickPreview").hidden = true;
    $("#pickEmpty").hidden = false;
    $("#pick").classList.remove("has");
    $("#extra").value = "";
    openDetail(data.id);
  };
  xhr.onerror = () => { btn.disabled = false; btn.textContent = "✦ Editar sozinho"; toast("Sem conexão com o computador."); };
  xhr.send(fd);
}

async function create() {
  const theme = $("#theme").value.trim();
  if (!theme) return toast("Escreva o tema.");
  const btn = $("#goCreate");
  btn.disabled = true;
  try {
    const p = await api("/api/studio", { method: "POST", json: {
      theme, seconds: M.seconds, voice_id: $("#voice").value, preset: $("#cStyle").value, auto_export: true,
    } });
    $("#theme").value = "";
    openDetail(p.id);
  } catch (e) { toast(e.message, 5000); }
  btn.disabled = false;
}

function stage(p) {
  const r = p.render || {};
  if (p.status === "erro") return { done: -1, err: p.status_text };
  if (p.auto_stage === "erro") return { done: -1, err: p.auto_note || "Algo deu errado." };
  if (p.status === "analisando") return { done: 1, text: p.status_text, prog: p.progress };
  if (r.status === "renderizando") return { done: 3, text: `Exportando… ${Math.round((r.progress || 0) * 100)}%`, prog: r.progress };
  if (p.auto_stage === "editando") return { done: 2, text: "A IA está editando…" };
  if (r.status === "pronto") return { done: 4 };
  if (r.status === "erro") return { done: -1, err: r.error };
  return { done: 4, notExported: true };
}

async function openDetail(id) {
  go("detalhe");
  M.current = id;
  history.replaceState(null, "", `/celular.html?p=${id}`);
  $("#openFull").href = `/?p=${id}&full=1`;
  await refresh();
  clearInterval(M.timer);
  M.timer = setInterval(refresh, 1500);
}

async function refresh() {
  const id = M.current;
  if (!id) return;
  const p = await api(`/api/projects/${id}`).catch(() => null);
  if (!p || M.current !== id) return;
  $("#dName").textContent = p.name;
  const s = stage(p);
  const studio = p.origin === "estudio";
  const labels = studio ? ["Pedido recebido", "Roteiro, voz e animações", "Ajustes", "Exportando", "Pronto"] : ["Vídeo enviado", "Ouvindo a fala", "A IA está editando", "Exportando", "Pronto"];
  $("#steps").innerHTML = labels.map((l, i) => {
    const cls = s.done < 0 ? "" : i < s.done ? "done" : i === s.done && s.done < 4 ? "now" : s.done === 4 && i === 4 ? "done" : "";
    const text = i === s.done && s.text ? s.text : l;
    return `<li class="${cls}"><i>${cls === "done" ? "✓" : ""}</i>${esc(text)}</li>`;
  }).join("");
  $("#dBarBox").hidden = !(s.prog > 0 && s.done < 4);
  $("#dBar").style.width = `${Math.round((s.prog || 0) * 100)}%`;
  $("#dErr").hidden = !s.err;
  $("#dErr").textContent = s.err ? `Erro: ${s.err}` : "";
  const finished = s.done === 4;
  $("#adjust").hidden = !finished && !s.err;
  $("#exportNow").hidden = !s.notExported;
  if (p.auto_note && !s.err) $("#dErr").hidden = false, ($("#dErr").textContent = p.auto_note);
  const file = p.render?.status === "pronto" ? p.render.file : null;
  $("#done").hidden = !file;
  if (file) {
    const src = `/media/projects/${p.id}/${file}`;
    if (!$("#final").src.endsWith(src)) $("#final").src = src;
    $("#download").href = `/api/projects/${p.id}/download/${file}`;
    M.shareSrc = src;
    M.shareName = `${p.name}.mp4`;
    const ai = [...(p.chat || [])].reverse().find((m) => m.role === "ai");
    $("#caption").hidden = !(studio && ai);
    if (studio && ai) $("#caption").textContent = ai.text;
  }
  if (finished || s.err) { clearInterval(M.timer); }
}

async function share() {
  try {
    const blob = await (await fetch(M.shareSrc)).blob();
    const file = new File([blob], M.shareName, { type: "video/mp4" });
    if (navigator.canShare && navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: M.shareName });
    else location.href = $("#download").href;
  } catch (e) {
    if (e.name !== "AbortError") location.href = $("#download").href;
  }
}

async function adjust(text) {
  if (!text) return toast("Escreva o que mudar.");
  const id = M.current;
  const p = await api(`/api/projects/${id}`);
  $("#goAdj").disabled = true;
  $("#adjust").hidden = true;
  $("#done").hidden = true;
  $("#steps").innerHTML = `<li class="now"><i></i>A IA está ajustando…</li>`;
  try {
    await api(`/api/projects/${id}/edit`, { method: "POST", json: { preset: p.preset, request: text, fresh: false } });
    $("#adjText").value = "";
    await exportNow();
  } catch (e) { toast(e.message, 5000); refresh(); }
  $("#goAdj").disabled = false;
}

async function exportNow() {
  const id = M.current;
  try {
    await api(`/api/projects/${id}/render`, { method: "POST", json: { quality: "media" } });
    clearInterval(M.timer);
    M.timer = setInterval(refresh, 1500);
    refresh();
  } catch (e) { toast(e.message); }
}

async function loadList() {
  const list = await api("/api/projects");
  const full = await Promise.all(list.slice(0, 30).map((p) => api(`/api/projects/${p.id}`).catch(() => null)));
  $("#list").innerHTML = full.filter(Boolean).map((p) => {
    const s = stage(p);
    const tag = s.err ? `<span class="tag err">erro</span>` : s.done === 4 ? (s.notExported ? `<span class="tag">pronto p/ exportar</span>` : `<span class="tag ok">pronto</span>`) : `<span class="tag work">fazendo…</span>`;
    const thumb = p.info ? `<img src="/media/projects/${p.id}/thumbs/t00001.jpg" alt="" loading="lazy">` : `<div class="ph"></div>`;
    const dur = p.timeline ? `${Math.round(p.timeline.duration)}s` : "";
    return `<li data-id="${p.id}">${thumb}<div><b>${esc(p.name)}</b><small>${dur}</small></div>${tag}</li>`;
  }).join("") || `<li class="note">Nenhum vídeo ainda.</li>`;
}

init().catch((e) => toast(`Sem conexão com o computador: ${e.message}`, 8000));
