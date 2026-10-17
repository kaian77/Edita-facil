/* Minha marca: dados, cores, logo, avatar e vozes. */
let BRAND = null;
const FIELDS = ["name", "handle", "niche", "audience", "tone", "cta", "avatar_desc"];
const COLORS = ["primary", "secondary", "accent", "text"];

async function init() {
  BRAND = await api("/api/brand");
  fill();
  for (const f of FIELDS) $(`#b_${f}`).oninput = preview;
  for (const c of COLORS) $(`#c_${c}`).oninput = preview;
  $("#save").onclick = save;
  $("#f_logo").onchange = (e) => upload("logo", e.target.files[0]);
  $("#f_avatar").onchange = (e) => upload("avatar", e.target.files[0]);
  $("#rmLogo").onclick = () => remove("logo");
  $("#rmAvatar").onclick = () => remove("avatar");
  $("#v_files").onchange = (e) => ($("#v_count").textContent = `${e.target.files.length} arquivo(s) escolhido(s)`);
  $("#v_clone").onclick = clone;
  const cfg = await api("/api/config");
  if (cfg.has_elevenlabs) loadVoices();
  else { $("#elWarn").hidden = false; $("#v_clone").disabled = true; }
}

function fill() {
  for (const f of FIELDS) $(`#b_${f}`).value = BRAND[f] || "";
  for (const c of COLORS) $(`#c_${c}`).value = BRAND.colors[c];
  $("#b_watermark").checked = BRAND.watermark;
  const v = Date.now();
  $("#pvLogo").style.backgroundImage = BRAND.logo ? `url(/media/brand/logo.png?v=${v})` : "";
  $("#pvAvatar").style.backgroundImage = BRAND.avatar ? `url(/media/brand/avatar_round.png?v=${v})` : "";
  $("#mkLogo").style.backgroundImage = BRAND.logo ? `url(/media/brand/logo.png?v=${v})` : "";
  $("#mkAv").style.backgroundImage = BRAND.avatar ? `url(/media/brand/avatar_round.png?v=${v})` : "";
  $("#mkAv").hidden = !BRAND.avatar;
  preview();
}

function preview() {
  const c = Object.fromEntries(COLORS.map((k) => [k, $(`#c_${k}`).value]));
  $("#mock").style.background = `linear-gradient(160deg, ${c.primary}cc, ${c.secondary}aa 55%, #0b0b10)`;
  $("#mock").style.color = c.text;
  $("#mkAcc").style.color = c.accent;
  $("#mkBox").style.background = c.accent;
  $("#mkBox").textContent = ($("#b_cta").value || "Agende agora").toUpperCase();
  $("#mkHandle").textContent = $("#b_handle").value || "@seuperfil";
}

async function save() {
  const body = Object.fromEntries(FIELDS.map((f) => [f, $(`#b_${f}`).value]));
  body.colors = Object.fromEntries(COLORS.map((k) => [k, $(`#c_${k}`).value]));
  body.watermark = $("#b_watermark").checked;
  BRAND = await api("/api/brand", { method: "POST", json: body });
  $("#saved").textContent = "✓ Marca salva. Vale para os próximos vídeos e exportações.";
  toast("Marca salva.");
}

async function upload(kind, file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try { BRAND = await api(`/api/brand/${kind}`, { method: "POST", body: fd }); fill(); toast(kind === "logo" ? "Logo salva." : "Avatar salvo."); }
  catch (e) { toast(e.message); }
}

async function remove(kind) {
  BRAND = await api(`/api/brand/${kind}`, { method: "DELETE" });
  fill();
}

async function loadVoices() {
  const ul = $("#voices");
  ul.innerHTML = `<li class="hint">Carregando vozes…</li>`;
  try {
    const vs = await api("/api/voices");
    vs.sort((a, b) => (b.category === "cloned") - (a.category === "cloned"));
    ul.innerHTML = vs.map((v) => `
      <li>
        <span class="grow">${v.id === BRAND.voice_id ? "⭐ " : ""}${esc(v.name)} <small>${v.category === "cloned" ? "sua voz clonada" : "ElevenLabs"}</small></span>
        <button data-test="${v.id}">▶ Testar</button>
        <button data-default="${v.id}" data-name="${esc(v.name)}">Usar como padrão</button>
        ${v.category === "cloned" ? `<button data-del="${v.id}">✕</button>` : ""}
      </li>`).join("") || `<li class="hint">Nenhuma voz.</li>`;
  } catch (e) {
    ul.innerHTML = `<li class="hint">${esc(e.message)}</li>`;
  }
  ul.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.test) testVoice(b.dataset.test, b);
    if (b.dataset.default) {
      BRAND = await api("/api/brand", { method: "POST", json: { voice_id: b.dataset.default, voice_name: b.dataset.name } });
      loadVoices();
    }
    if (b.dataset.del && confirm("Apagar esta voz clonada da sua conta ElevenLabs?")) {
      try { await api(`/api/voices/${b.dataset.del}`, { method: "DELETE" }); loadVoices(); } catch (err) { toast(err.message); }
    }
  };
}

async function testVoice(id, btn) {
  btn.disabled = true;
  try {
    const name = $("#b_name").value || "nossa marca";
    const r = await fetch("/api/voices/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice_id: id, text: `Oi! Esse é um teste da voz para os vídeos da ${name}.` }),
    });
    if (!r.ok) throw new Error((await r.json()).detail);
    new Audio(URL.createObjectURL(await r.blob())).play();
  } catch (e) { toast(e.message); }
  btn.disabled = false;
}

async function clone() {
  const files = $("#v_files").files;
  if (!files.length) return toast("Escolha os áudios da voz.");
  if (!$("#v_consent").checked) return toast("Marque a autorização para clonar a voz.");
  const fd = new FormData();
  fd.append("name", $("#v_name").value || "Minha voz");
  fd.append("consent", "true");
  for (const f of files) fd.append("files", f);
  const btn = $("#v_clone");
  btn.disabled = true;
  btn.textContent = "Clonando… (pode levar 1 minuto)";
  try {
    const { id } = await api("/api/voices/clone", { method: "POST", body: fd });
    BRAND = await api("/api/brand", { method: "POST", json: { voice_id: id, voice_name: $("#v_name").value || "Minha voz" } });
    toast("Voz clonada e definida como padrão! ⭐");
    loadVoices();
  } catch (e) { toast(e.message, 6000); }
  btn.disabled = false;
  btn.textContent = "Clonar voz";
}

init().catch((e) => toast(`Não consegui conectar ao servidor: ${e.message}`, 8000));
