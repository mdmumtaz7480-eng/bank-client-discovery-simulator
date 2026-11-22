const $ = id => document.getElementById(id);
let clients = [], products = [], client = null, history = [], clientIdx = 0;

const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");

// Tiny Markdown renderer: paragraphs, bullets, numbered lists, one level of nesting, **bold**
function md(text) {
  const out = []; let stack = []; // open lists
  const close = n => { while (stack.length > n) out.push(`</${stack.pop()}>`); };
  for (const raw of text.split("\n")) {
    if (!raw.trim()) continue;
    const m = raw.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
    if (m) {
      const depth = m[1].length >= 2 ? 2 : 1, tag = /\d/.test(m[2]) ? "ol" : "ul";
      close(depth); while (stack.length < depth) { out.push(`<${tag}>`); stack.push(tag); }
      out.push(`<li>${inline(m[3])}</li>`);
    } else { close(0); out.push(`<p>${inline(raw.trim())}</p>`); }
  }
  close(0); return out.join("");
}

function setStep(step, sectionId) {
  ["pick", "interview", "rec", "feedback"].forEach(s => $(s).classList.toggle("hidden", s !== sectionId));
  document.querySelectorAll("#stepper li").forEach(li => {
    const n = +li.dataset.step;
    li.classList.toggle("active", n === step);
    li.classList.toggle("done", n < step);
  });
  $("railClient").classList.toggle("hidden", !client || step === 1);
  window.scrollTo({ top: 0 });
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.add("hidden"), 4500); }
const avatar = (c, i, cls = "") => `<div class="avatar ${cls} av${i % 3}">${esc(c.avatar)}</div>`;

async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json(); if (!r.ok) throw new Error(j.error || r.statusText); return j;
}

async function init() {
  [clients, products] = await Promise.all([fetch("/api/clients").then(r => r.json()), fetch("/api/products").then(r => r.json())]);
  const cfg = await fetch("/api/config").then(r => r.json());
  $("model").textContent = cfg.model;
  $("cards").innerHTML = clients.map((c, i) => `
    <article class="card client">
      <div class="client-top">${avatar(c, i)}<div><h3>${esc(c.name)}</h3><div class="tag">${esc(c.tagline)}</div></div></div>
      <div class="meta"><span class="pill">${c.profile.age} yrs</span><span class="pill">${esc(c.profile.location.split(" (")[0])}</span><span class="pill">${esc(c.profile.occupation.split(" (")[0].split(" at ")[0])}</span></div>
      <p class="bio">${esc(c.profile.background)}</p>
      <p class="bio">${esc(c.profile.financial_situation)}</p>
      <button class="btn primary" data-id="${c.id}">Interview ${esc(c.name.split(" ")[0])} →</button>
    </article>`).join("");
  $("cards").querySelectorAll("button").forEach(b => b.onclick = () => start(b.dataset.id));
  $("tabProducts").innerHTML = products.map(p => `
    <div class="card prod">
      <h4>${esc(p.name)}<span class="badge ${p.sharia_compliant ? "sharia" : "conv"}">${p.sharia_compliant ? "Sharia-compliant" : "Conventional"}</span></h4>
      <p>${esc(p.summary)}</p>
      <h5>Features</h5><ul class="feat">${p.features.map(f => `<li>${esc(f)}</li>`).join("")}</ul>
      <h5>Limitations</h5><ul class="lim">${p.limitations.map(f => `<li>${esc(f)}</li>`).join("")}</ul>
    </div>`).join("");
  $("chips").innerHTML = products.map(p => `<button type="button" class="chip" data-name="${esc(p.name.split(" (")[0])}">+ ${esc(p.name.split(" (")[0])}</button>`).join("");
  $("chips").querySelectorAll(".chip").forEach(c => c.onclick = () => {
    const t = $("recs"); t.value += (t.value && !t.value.endsWith("\n") ? "\n" : "") + c.dataset.name + ": "; t.focus();
  });
  setStep(1, "pick");
}

function start(id) {
  clientIdx = clients.findIndex(c => c.id === id); client = clients[clientIdx]; history = [];
  $("chatAvatar").className = `avatar lg av${clientIdx % 3}`; $("chatAvatar").textContent = client.avatar;
  $("cname").textContent = client.name;
  $("chat").innerHTML = `<div class="empty"><b>Start the conversation</b>${esc(client.profile.stated_need_at_start)}<br><br>Greet ${esc(client.name.split(" ")[0])} and ask open questions. Private needs only come out when you ask about them.</div>`;
  const p = client.profile;
  $("tabBrief").innerHTML = `<div class="card brief"><dl>
    <div><dt>Occupation</dt><dd>${esc(p.occupation)}</dd></div>
    <div><dt>Location</dt><dd>${esc(p.location)}</dd></div>
    <div><dt>Situation</dt><dd>${esc(p.financial_situation)}</dd></div>
    <div><dt>First impression</dt><dd>${esc(p.stated_need_at_start)}</dd></div></dl></div>
    <div class="tip"><b>Tip:</b> the product catalogue is in the “Products” tab. Discuss products with the client once you understand their needs.</div>`;
  $("railClient").innerHTML = `${avatar(client, clientIdx)}<div><b>${esc(client.name)}</b><small>${esc(client.profile.occupation.split(" at ")[0].split(" (")[0])}</small></div>`;
  $("summary").value = ""; $("recs").value = "";
  switchTab("brief"); setStep(2, "interview"); $("msg").focus();
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.dataset.tab === name));
  $("tabBrief").classList.toggle("hidden", name !== "brief"); $("tabProducts").classList.toggle("hidden", name !== "products");
}
document.querySelectorAll(".tab").forEach(t => t.onclick = () => switchTab(t.dataset.tab));

function bubble(role, html) {
  const e = $("chat").querySelector(".empty"); if (e) e.remove();
  const d = document.createElement("div"); d.className = "msg " + role; d.innerHTML = html;
  $("chat").appendChild(d); $("chat").scrollTop = $("chat").scrollHeight; return d;
}
$("composer").onsubmit = async e => {
  e.preventDefault();
  const t = $("msg").value.trim(); if (!t || $("send").disabled) return;
  $("msg").value = ""; bubble("student", esc(t)); history.push({ role: "student", content: t });
  $("send").disabled = true;
  const wait = bubble("client", '<span class="typing"><i></i><i></i><i></i></span>');
  try {
    const { reply } = await api("/api/chat", { client_id: client.id, messages: history });
    wait.textContent = reply; history.push({ role: "client", content: reply });
  } catch (err) { wait.textContent = "Error: " + err.message; wait.classList.add("err"); history.pop(); }
  $("chat").scrollTop = $("chat").scrollHeight; $("send").disabled = false; $("msg").focus();
};

$("toRec").onclick = () => {
  if (history.filter(m => m.role === "client").length < 1) return toast("Ask the client at least one question first.");
  setStep(3, "rec");
};
$("backInt").onclick = () => setStep(2, "interview");
$("back").onclick = () => { client = null; setStep(1, "pick"); };
$("again").onclick = () => { client = null; setStep(1, "pick"); };
$("reviewRec").onclick = () => setStep(3, "rec");

function renderFeedback(text) {
  const sections = text.split(/^## /m).filter(s => s.trim());
  const meta = [["good", "✓", /well/i], ["miss", "!", /miss/i], ["improve", "↗", /improve/i]];
  return '<div class="fb-grid">' + sections.map(s => {
    const [title, ...rest] = s.split("\n");
    const m = meta.find(x => x[2].test(title)) || ["improve", "•"];
    return `<section class="card fb ${m[0]}"><h2><span class="ico">${m[1]}</span>${esc(title.trim())}</h2>${md(rest.join("\n"))}</section>`;
  }).join("") + "</div>";
}

$("getFb").onclick = async () => {
  $("fbErr").textContent = "";
  if (history.length < 2) { $("fbErr").textContent = "Interview the client first."; return; }
  $("getFb").disabled = true; $("getFb").textContent = "Coach is reviewing…";
  $("fbBody").innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  setStep(4, "feedback");
  try {
    const { feedback } = await api("/api/feedback", { client_id: client.id, messages: history, summary: $("summary").value, recommendations: $("recs").value });
    $("fbBody").innerHTML = renderFeedback(feedback);
  } catch (err) { setStep(3, "rec"); $("fbErr").textContent = err.message; }
  $("getFb").disabled = false; $("getFb").textContent = "Get coaching feedback";
};

init().catch(e => toast("Could not load the app: " + e.message));
