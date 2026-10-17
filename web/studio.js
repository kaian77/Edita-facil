/* Criar com IA: vídeo só com o tema e cópia de estilo de um vídeo de referência. */
let CFG = null;

async function init() {
  bindTabs();
  const [cfg, presets, music, brand] = await Promise.all([
    api("/api/config"), api("/api/presets"), api("/api/music"), api("/api/brand"),
  ]);
  CFG = cfg;
  fillStyles(presets);
  $("#music").innerHTML += music.map((m) => `<option>${esc(m)}</option>`).join("");
  const has = [brand.name && "nome", brand.logo && "logo", brand.avatar && "avatar", "cores"].filter(Boolean);
  $("#brandHint").innerHTML = `Sua marca: ${has.join(", ")}. <a href="/marca.html">Editar marca</a>`;

  const warn = [];
  if (!cfg.has_key) warn.push("Falta a chave da Anthropic (⚙ no Editor).");
  if (!cfg.has_elevenlabs) warn.push("Sem chave da ElevenLabs: o vídeo sai sem narração. Coloque em ⚙ no Editor para usar sua voz.");
  if (warn.length) { $("#themeWarn").hidden = false; $("#themeWarn").innerHTML = warn.map(esc).join("<br>"); }

  if (cfg.has_elevenlabs) {
    api("/api/voices").then((vs) => {
      const mine = vs.filter((v) => v.category === "cloned");
      const other = vs.filter((v) => v.category !== "cloned");
      const opt = (v) => `<option value="${v.id}" ${v.id === brand.voice_id ? "selected" : ""}>${esc(v.name)}</option>`;
      $("#voice").innerHTML += (mine.length ? `<optgroup label="Suas vozes">${mine.map(opt).join("")}</optgroup>` : "")
        + `<optgroup label="Vozes da ElevenLabs">${other.map(opt).join("")}</optgroup>`;
    }).catch((e) => toast(e.message));
  }

  $("#create").onclick = create;
  $("#refFile").onchange = (e) => { if (e.target.files[0]) analyzeRef(e.target.files[0]); e.target.value = ""; };
  const drop = $("#refDrop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) analyzeRef(e.dataTransfer.files[0]); });
  const params = new URLSearchParams(location.search);
  if (params.get("tab")) showTab(params.get("tab"));
}

function fillStyles(presets) {
  const sel = $("#style");
  const keep = sel.value;
  sel.innerHTML = `<option value="">Automático</option>` + presets.map((p) => `<option value="${p.id}">${p.icon} ${esc(p.name)}</option>`).join("");
  sel.value = keep;
  const mine = presets.filter((p) => p.user);
  $("#styles").innerHTML = mine.map((p) => `
    <li><span class="grow">${p.icon} ${esc(p.name)}<br><small>${esc(p.description)}</small></span>
      <button data-use="${p.id}">Criar</button><button data-edit="${p.id}" title="Usar para editar meus vídeos">Editar</button><button data-del="${p.id}">✕</button></li>`).join("")
    || `<li class="hint">Nenhum ainda. Envie um vídeo de referência.</li>`;
  $("#styles").onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.use) { $("#style").value = b.dataset.use; showTab("tema"); $("#theme").focus(); }
    if (b.dataset.edit) location.href = `/?preset=${b.dataset.edit}`;
    if (b.dataset.del && confirm("Apagar este estilo?")) fillStyles(await api(`/api/presets/${b.dataset.del}`, { method: "DELETE" }));
  };
}

async function create() {
  const theme = $("#theme").value.trim();
  if (!theme) return toast("Escreva o tema do vídeo.");
  const btn = $("#create");
  btn.disabled = true;
  btn.textContent = "Começando…";
  try {
    const p = await api("/api/studio", { method: "POST", json: {
      theme, seconds: +$("#seconds").value, format: $("#format").value, voice_id: $("#voice").value,
      preset: $("#style").value, extra: $("#extra").value, music: $("#music").value,
    } });
    location.href = `/?p=${p.id}`;  // o editor mostra o progresso
  } catch (e) {
    toast(e.message, 6000);
    btn.disabled = false;
    btn.textContent = "✦ Criar vídeo";
  }
}

async function analyzeRef(file) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("use_frames", $("#refFrames").checked);
  $("#refProgress").hidden = false;
  $("#recipe").hidden = true;
  const status = (t, p) => { $("#refStatus").textContent = t; $("#refBar").style.width = `${Math.round(p * 100)}%`; };
  status("Enviando…", 0.02);
  try {
    let job = await api("/api/reference", { method: "POST", body: fd });
    while (job.status === "analisando") {
      status(job.status_text, job.progress);
      await new Promise((r) => setTimeout(r, 1200));
      job = await api(`/api/reference/${job.id}`);
    }
    if (job.status === "erro") throw new Error(job.status_text);
    status(`Pronto! Gasto: US$ ${job.usage.cost_usd.toFixed(4)}`, 1);
    showRecipe(job.style, job.preset);
    fillStyles(await api("/api/presets"));
  } catch (e) {
    status(`Erro: ${e.message}`, 0);
  }
}

function showRecipe(st, preset) {
  const box = $("#recipe");
  box.hidden = false;
  const s = st.stats;
  box.innerHTML = `
    <h2>🎯 ${esc(st.name)}</h2>
    <p class="hint">${esc(st.summary)}</p>
    <div><span class="pill">${s.duracao_s}s</span><span class="pill">${s.cortes} cortes</span><span class="pill">${s.tempo_medio_por_plano_s}s por plano</span><span class="pill">${s.palavras_por_minuto} palavras/min</span></div>
    <dl>
      <dt>Estrutura</dt><dd><ol>${st.structure.map((x) => `<li>${esc(x)}</li>`).join("")}</ol></dd>
      <dt>Gancho</dt><dd>${esc(st.hook)}</dd>
      <dt>Ritmo</dt><dd>${esc(st.pacing)}</dd>
      <dt>Textos</dt><dd>${esc(st.text_style)}</dd>
      <dt>Música</dt><dd>${esc(st.music_mood)}</dd>
    </dl>
    <div class="row-btns">
      <button class="primary" id="useNow">✦ Criar com meu tema nesse estilo</button>
      <a href="/?preset=${preset.id}"><button>Usar para editar meus vídeos</button></a>
    </div>`;
  $("#useNow").onclick = () => { $("#style").value = preset.id; showTab("tema"); $("#theme").focus(); };
}

init().catch((e) => toast(`Não consegui conectar ao servidor: ${e.message}`, 8000));
