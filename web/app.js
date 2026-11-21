// Interlock — one screen. No framework, no build step.
"use strict";

const $ = (id) => document.getElementById(id);
const store = {
  get(k, session) { try { return (session ? sessionStorage : localStorage).getItem(k); } catch { return null; } },
  set(k, v, session) { try { (session ? sessionStorage : localStorage).setItem(k, v); } catch {} },
  del(k, session) { try { (session ? sessionStorage : localStorage).removeItem(k); } catch {} },
};

// ------------------------------------------------------------ access code + API
function accessCode() {
  let code = store.get("access_code", true);
  if (!code) {
    code = (prompt("Access code") || "").trim();
    if (code) store.set("access_code", code, true);
  }
  return code;
}

async function api(path, opts = {}, retried = false) {
  const headers = { "X-Access-Code": accessCode(), ...(opts.body ? { "Content-Type": "application/json" } : {}) };
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401 && !retried) {
    store.del("access_code", true);
    return api(path, opts, true);
  }
  if (!res.ok) throw new Error(`${res.status} ${(await res.json().catch(() => ({}))).detail || ""}`.trim());
  return res.json();
}

// ------------------------------------------------------------ plant
let plantId = store.get("plant_id");

async function loadPlants() {
  try {
    const plants = await api("/plants");
    $("plant-pick").innerHTML = `<option value="">Open a plant…</option>` + plants.map((p) =>
      `<option value="${p.plant_id}" ${p.plant_id === plantId ? "selected" : ""}>${
        String(p.name).replace(/[<>&"]/g, "")} — ${p.page_count} pages, ${p.files} files (${p.plant_id})</option>`).join("");
  } catch (e) { /* access code prompt handles 401 */ }
}

$("plant-pick").onchange = (e) => {
  if (!e.target.value) return;
  plantId = e.target.value;
  store.set("plant_id", plantId);
  $("result").hidden = true;
  showPlant();
  loadRegister();
};

async function showPlant() {
  if (!plantId) { $("plant-info").textContent = "No plant selected."; return null; }
  try {
    const p = await api(`/plants/${plantId}`);
    $("plant-info").textContent =
      `${p.name} — ${p.page_count} pages, ingest ${p.ingest_status}, ${p.files.length} files (id ${p.plant_id})`;
    const body = $("files").querySelector("tbody");
    body.innerHTML = "";
    p.files.forEach((f) => row(f.relative_path, `${f.status}${f.pages ? `, ${f.pages} pages` : ""}${f.error ? ` (${f.error})` : ""}`,
      f.status === "ingested" ? "accepted" : f.status === "failed" || f.status === "missing" ? "failed" : ""));
    return p;
  } catch (e) {
    $("plant-info").textContent = `Plant ${plantId}: ${e.message}`;
    return null;
  }
}

$("new-plant").onclick = async () => {
  const name = $("plant-name").value.trim() || "plant";
  const r = await api("/plants", { method: "POST", body: JSON.stringify({ name }) });
  plantId = r.plant_id;
  store.set("plant_id", plantId);
  $("files").querySelector("tbody").innerHTML = "";
  $("plant-name").value = "";
  await showPlant();
  loadPlants();
};

// ------------------------------------------------------------ collecting files
function readAll(reader) {
  return new Promise((resolve) => {
    const all = [];
    const next = () => reader.readEntries((batch) => {
      if (!batch.length) return resolve(all);
      all.push(...batch); next();
    }, () => resolve(all));
    next();
  });
}

async function walk(entry, out) {
  if (entry.isFile) {
    const file = await new Promise((res, rej) => entry.file(res, rej));
    out.push({ file, relative_path: entry.fullPath.replace(/^\/+/, "") });
  } else if (entry.isDirectory) {
    for (const child of await readAll(entry.createReader())) await walk(child, out);
  }
}

async function fromDrop(dt) {
  const out = [];
  const entries = [...dt.items].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (entries.length) { for (const e of entries) await walk(e, out); return out; }
  return [...dt.files].map((file) => ({ file, relative_path: file.name }));
}

const fromInput = (input) =>
  [...input.files].map((file) => ({ file, relative_path: file.webkitRelativePath || file.name }));

async function sha256(file) {
  const buf = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ------------------------------------------------------------ upload
function row(path, status, cls) {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td class="path"></td><td class="${cls}"></td><td></td>`;
  tr.children[0].textContent = path;
  tr.children[1].textContent = status;
  $("files").querySelector("tbody").appendChild(tr);
  return tr;
}

function put(url, file, bar) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", "application/pdf"); // must match the signature; no access code here
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) bar.value = e.loaded / e.total; };
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`HTTP ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("network error"));
    xhr.send(file);
  });
}

async function uploadAll(items) {
  if (!plantId) { alert("Create a plant first."); return; }
  if (!items.length) return;
  $("upload-status").textContent = `Hashing ${items.length} files…`;
  const meta = [];
  for (const it of items) {
    const isPdf = /\.pdf$/i.test(it.relative_path) && it.file.size > 0;
    meta.push({ relative_path: it.relative_path, size: it.file.size,
                content_hash: isPdf ? await sha256(it.file) : `not-hashed:${it.relative_path}`,
                content_type: it.file.type || "" });
  }
  const r = await api(`/plants/${plantId}/files`, { method: "POST", body: JSON.stringify(meta) });
  r.skipped.forEach((s) => row(s.relative_path, `skipped: ${s.reason}`, "skipped"));
  r.duplicates.forEach((d) => row(d.relative_path, "duplicate (already in this plant)", "duplicate"));

  const byPath = Object.fromEntries(items.map((it) => [it.relative_path.replace(/\\/g, "/"), it.file]));
  const queue = r.accepted.map((a) => {
    const tr = row(a.relative_path, "uploading", "accepted");
    const bar = document.createElement("progress"); bar.max = 1; bar.value = 0;
    tr.children[2].appendChild(bar);
    return { ...a, tr, bar, file: byPath[a.relative_path] };
  });
  $("upload-status").textContent =
    `${r.accepted.length} accepted, ${r.skipped.length} skipped, ${r.duplicates.length} duplicates`;

  let failed = 0;
  async function worker() {
    while (queue.length) {
      const job = queue.shift();
      try {
        await put(job.upload_url, job.file, job.bar).catch(() => put(job.upload_url, job.file, job.bar));
        job.tr.children[1].textContent = "uploaded";
      } catch (e) {
        failed += 1;
        job.tr.children[1].textContent = `failed: ${e.message}`;
        job.tr.children[1].className = "failed";
      }
    }
  }
  await Promise.all([worker(), worker(), worker()]);
  if (r.accepted.length) await ingest(failed);
}

$("reingest").onclick = async () => {
  if (!plantId || !confirm("Rebuild this plant's pages from the files already uploaded?")) return;
  try { await ingest(0, "reingest"); } catch (e) { $("ingest-status").textContent = `Error: ${e.message}`; }
};

async function ingest(failed, route = "ingest") {
  const { job_id } = await api(`/plants/${plantId}/${route}`, { method: "POST" });
  $("ingest-status").textContent = `Ingest started${failed ? ` (${failed} uploads failed)` : ""}…`;
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    const j = await api(`/jobs/${job_id}`);
    const p = j.progress || {};
    $("ingest-status").textContent =
      `Ingest ${j.state}: files ${p.files_done ?? 0}/${p.files_total ?? 0}, pages ${p.pages_done ?? 0}`;
    if (j.state === "done" || j.state === "failed") {
      if (j.state === "failed") $("ingest-status").textContent += ` — ${j.error}`;
      const plant = await showPlant();
      loadPlants();
      if (plant && j.state === "done") $("ingest-status").textContent = `Ingest done: ${plant.page_count} pages in this plant.`;
      return;
    }
  }
}

// ------------------------------------------------------------ change check
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const cite = (o) => `${esc(o.file)} p.${esc(o.page)}`;

function table(el, head, rows) {
  $(el).innerHTML = `<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.join("") || `<tr><td colspan="${head.length}" class="muted">none</td></tr>`}</tbody>`;
}

function calcRows(results, label) {
  return results.map((r) => `<tr><td>${esc(label)}</td><td>${esc(r.rule_id)}</td>
    <td class="st-${esc(r.status)}">${esc(r.status)}</td>
    <td>${r.value == null ? "" : esc(Number(r.value).toFixed(2))} ${esc(r.unit)}</td>
    <td>${r.limit == null ? "" : esc(Number(r.limit).toFixed(2))}<div class="small">${esc(r.limit_source)}</div></td>
    <td><div>${esc(r.message)}</div><div class="small">${esc(r.formula)}</div>
      ${(r.assumptions || []).map((a) => `<div class="small">assumes: ${esc(a)}</div>`).join("")}
      ${(r.notes || []).map((n) => `<div class="small">note: ${esc(n)}</div>`).join("")}
      <div class="small">${Object.entries(r.inputs || {}).filter(([, v]) => v && v.value !== undefined).map(([k, v]) =>
        `${esc(k)}=${esc(v.value)} ${esc(v.unit || "")} [${esc(v.source)}${v.file ? " " + esc(v.file) + " p." + esc(v.page) : ""}]`).join(" · ")}</div></td></tr>`).join("");
}

async function fetchPng(path) {
  const r = await fetch(path, { headers: { "X-Access-Code": accessCode() } });
  if (!r.ok) throw new Error(`${r.status}`);
  return URL.createObjectURL(await r.blob());
}

async function showDrawing(res) {
  const d = res.drawing || {};
  const el = $("drawing");
  if (!d.image && !d.readings?.length) {
    el.innerHTML = `<p class="muted">No drawing: ${esc(d.reason || d.check || "not found")}</p>`;
    return;
  }
  const rows = (d.readings || []).map((r) => `<tr><td>${esc(r.input)}</td><td>${esc(r.value)} ${esc(r.unit || "")}</td>
    <td>"${esc(r.quote)}"</td><td>${r.evidence_ok ? '<span class="ok-mark">verified ✓</span>'
      : `<span class="bad-mark">not verified</span> <span class="small">${esc(r.evidence_reason)}</span>`}</td></tr>`).join("");
  el.innerHTML = `<p>${d.found ? "Item found and verified on" : "Item not verified on"} ${cite(d)} (drawing)
      · anchor: ${esc(d.anchor_text || d.anchor || "none")}
      · <a href="#" id="whole-sheet">view whole sheet</a></p>
    <p class="small">${esc(d.check || "")} ${d.why ? "· model: " + esc(d.why) : ""}</p>
    <div id="drawing-img" class="muted">loading drawing…</div>
    <table><thead><tr><th>Reading</th><th>Value</th><th>Label as printed</th><th>Check</th></tr></thead><tbody>${rows ||
      "<tr><td colspan=4 class='muted'>no readings</td></tr>"}</tbody></table>`;
  $("whole-sheet").onclick = async (e) => {
    e.preventDefault();
    try { window.open(await fetchPng(`/changes/${res.change_id}/drawing.png?full=1`), "_blank"); } catch (err) { alert(err.message); }
  };
  try {
    const url = await fetchPng(`/changes/${res.change_id}/drawing.png`);
    $("drawing-img").innerHTML = `<img alt="P&ID crop with the item boxed" src="${url}">`;
  } catch (err) {
    $("drawing-img").textContent = `drawing image not available (${err.message})`;
  }
}

async function loadRegister() {
  if (!plantId) return;
  try {
    const entries = await api(`/plants/${plantId}/register`);
    $("register").innerHTML = entries.length ? "<b>Register</b> (approved changes): " + entries.map((e) =>
      `${esc(e.item)} · ${esc(e.attribute)} = ${esc(e.value)} ${esc(e.unit || "")} (${esc(e.approved_at)})`).join("; ")
      : "Register: no approved changes.";
  } catch (e) { $("register").textContent = ""; }
}

function renderFix(res) {
  const el = $("fix");
  const v = (res.verdict || {}).verdict;
  if (v !== "BLOCK" && v !== "REVIEW") { el.innerHTML = ""; return; }
  const f = res.fix;
  let html = `<h3>Fix</h3><button id="find-fix">Find a fix</button> <span id="fix-status" class="muted"></span>`;
  if (f) {
    const tries = (f.tries || []).map((t) => `<tr><td>${esc(t.n)}</td><td>${esc(t.candidate)}</td>
      <td>${esc((t.flagged || []).join(", ") || "-")}</td><td>${esc((t.newly_held || []).join(", ") || "-")}</td></tr>`).join("");
    const proven = f.recheck && f.recheck.proven;
    const stamp = proven ? `<div class="stamp proven">Proven by the server</div>`
      : f.outcome === "proposed" ? `<div class="stamp not">Agent's fix not proven by the server</div>`
      : `<div class="stamp not">Agent refused</div>`;
    const reasons = [...(f.reasons || []), ...((f.recheck || {}).reasons || [])];
    const dis = res.disagreements || [];
    html += `<p class="small">Sandbox: ${esc(f.environment_id || "none")} · ${f.reused_sandbox ? "this plant's sandbox, reused" : "new sandbox"}
      ${f.sandbox_note ? " · " + esc(f.sandbox_note) : ""} ${f.persistent === false ? " · fresh sandbox per fix" : ""}
      ${f.runs_listing ? " · earlier runs: " + esc(f.runs_listing) : ""} · ${esc(f.seconds)} s</p>
      ${f.bundle_note ? `<p class="small">${esc(f.bundle_note)}${f.bundle_sha256_reported ? " (" + esc(f.bundle_sha256_reported.slice(0, 12)) + "…)" : ""}</p>` : ""}
      <p class="small">Agent's tries (reported by the agent from its sandbox):</p>
      <table><thead><tr><th>#</th><th>Candidate</th><th>Flagged</th><th>Newly held</th></tr></thead><tbody>${tries ||
        "<tr><td colspan=4 class='muted'>none reported</td></tr>"}</tbody></table>
      ${(f.fix || []).length ? "<p><b>Proposed fix:</b> " + f.fix.map((x) => `${esc(x.input)} ${esc(x.from || "")} → ${esc(x.to)} ${esc(x.unit || "")} (${esc(x.why || "")})`).join("; ") + "</p>" : ""}
      ${stamp}${reasons.length ? "<ul>" + reasons.map((r) => `<li>${esc(r)}</li>`).join("") + "</ul>" : ""}`;
    if (proven && !res.approved) {
      html += dis.length ? `<p class="small">Still to resolve by the engineer: documents disagree. Tick each once resolved:</p>` +
        dis.map((d, i) => `<label class="small"><input type="checkbox" class="resolve" value="${esc(d.attribute)}">
          I have resolved the document disagreement: ${esc(d.attribute)} (${d.values.map((x) => `${cite(x)} = ${esc(x.value)}`).join("; ")})</label><br>`).join("") : "";
      html += `<button id="approve">Approve</button> <span id="approve-status" class="small"></span>`;
    }
    if (res.approved) html += `<p class="ok-mark">Added to the plant's register: ${esc(res.approved.entry_ids.join(", "))}</p>`;
  }
  el.innerHTML = html;
  $("find-fix").onclick = () => findFix(res.change_id);
  const ap = $("approve");
  if (ap) {
    const boxes = [...document.querySelectorAll(".resolve")];
    const sync = () => { ap.disabled = !boxes.every((b) => b.checked); };
    boxes.forEach((b) => (b.onchange = sync));
    sync();
    ap.onclick = async () => {
      try {
        const r = await api(`/changes/${res.change_id}/approve`, { method: "POST",
          body: JSON.stringify({ resolved: boxes.map((b) => b.value) }) });
        $("approve-status").textContent = `Added to the register: ${r.entries.map((e) => e.entry_id).join(", ")}`;
        ap.disabled = true;
        loadRegister();
      } catch (e) { $("approve-status").textContent = `Not approved: ${e.message}`; }
    };
  }
}

async function findFix(changeId) {
  $("find-fix").disabled = true;
  const started = Date.now();
  try {
    const { job_id } = await api(`/changes/${changeId}/fix`, { method: "POST" });
    for (;;) {
      await new Promise((r) => setTimeout(r, 3000));
      const j = await api(`/jobs/${job_id}`);
      $("fix-status").textContent = `${j.step === "agent" ? "Agent working in the plant's sandbox…" : esc(j.step)} ${Math.round((Date.now() - started) / 1000)} s`;
      if (j.state === "done" || j.state === "failed") {
        const res = await api(`/changes/${changeId}`);
        renderFix(res);
        if (j.state === "failed") $("fix-status").textContent = `Fix job failed: ${j.error}`;
        return;
      }
    }
  } catch (e) {
    $("fix-status").textContent = `Error: ${e.message}`;
    $("find-fix").disabled = false;
  }
}

function showResult(res) {
  $("result").hidden = false;
  const v = res.verdict || {};
  $("verdict").className = `verdict ${esc(v.verdict)}`;
  $("verdict").innerHTML = `${esc(v.label)}<div class="verdict reasons">${(v.reasons || []).map(esc).join("<br>")}</div>`;
  $("headlines").innerHTML = (res.headlines || []).map((h) => `<li>${esc(typeof h === "string" ? h : JSON.stringify(h))}</li>`).join("") || "<li class='muted'>none</li>";
  table("pages", ["Page", "Found by", "Same item (P)", "Why"], (res.pages || []).map((p) =>
    `<tr><td>${cite(p)}</td><td>${esc(p.found_by)}</td><td>${p.same_item_p == null ? "" : Number(p.same_item_p).toFixed(2)}${p.uncertain ? " uncertain" : ""}</td><td>${esc(p.why)}</td></tr>`));
  table("values", ["Input", "Value", "Source", "Quote"], [...(res.values || []), ...(res.limits || []).map((l) => ({
    input: `limit ${l.applies_to || ""}`, value: `${l.low ?? ""}-${l.high ?? ""}`, unit: l.unit, file: l.file, page: l.page,
    quote: l.quote, evidence_ok: l.evidence_ok, evidence_reason: l.evidence_reason }))].map((x) =>
    `<tr class="${x.evidence_ok ? "" : "struck"}"><td>${esc(x.input)}</td><td>${esc(x.value)} ${esc(x.unit)}</td><td>${cite(x)}</td>
     <td>"${esc(x.quote)}"${x.evidence_ok ? "" : `<div class="small">evidence failed: ${esc(x.evidence_reason)}</div>`}</td></tr>`));
  const expl = res.explanations || [];
  $("disagreements").innerHTML = (res.disagreements || []).map((d) => `<p><b>${esc(d.attribute)}</b>: ${
    d.values.map((x) => `${cite(x)} = ${esc(x.value)}`).join("; ")}</p>`).join("") +
    expl.map((e) => `<p class="small">${esc(e.note || `${e.attribute}: likely right ${e.likely_right_file || "?"} p.${e.likely_right_page || "?"} — ${e.why} Consequence: ${e.consequence}`)}</p>`).join("") ||
    "<p class='muted'>none</p>";
  $("calc").innerHTML = `<table><thead><tr><th></th><th>Rule</th><th>Status</th><th>Value</th><th>Limit</th><th>Detail</th></tr></thead>
    <tbody>${calcRows(res.results_after || [], "after change")}${calcRows(res.results_issued || [], "as issued")}</tbody></table>`;
  $("clashes").innerHTML = (res.clashes || []).map((c) => `<p>${esc(c.entry_id)}: ${esc(c.attribute)} approved ${esc(c.approved)}, proposed ${esc(c.proposed)}</p>`).join("") || "<p class='muted'>none (register checked)</p>";
  showDrawing(res);
  renderFix(res);
  $("timing").textContent = `${res.seconds_total} s: ` + (res.steps || []).map((s) => `${s.name} ${s.seconds}s`).join(", ") +
    ` · long read ${res.long_read} · same-item ${res.same_item_mode} ${res.same_item_note || ""}`;
}

$("check").onclick = async () => {
  const text = $("change-text").value.trim();
  if (!plantId) { alert("Create or pick a plant first."); return; }
  if (!text) { $("check-status").textContent = "Type the change first (the grey text is only an example)."; return; }
  $("check-status").textContent = "starting…";
  $("result").hidden = true;
  $("check").disabled = true;
  const started = Date.now();
  try {
    const { job_id, change_id } = await api(`/plants/${plantId}/changes`, { method: "POST", body: JSON.stringify({ text }) });
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      const j = await api(`/jobs/${job_id}`);
      $("steps").innerHTML = (j.steps || []).map((s) => `<li>${esc(s.name)} — ${esc(s.state)} (${esc(s.seconds)} s)</li>`).join("") +
        (j.state === "running" ? `<li>${esc(j.step)}…</li>` : "");
      $("check-status").textContent = `${j.state} · ${Math.round((Date.now() - started) / 1000)} s`;
      if (j.state === "done") { showResult(await api(`/changes/${change_id}`)); break; }
      if (j.state === "failed") { $("check-status").textContent = `failed: ${j.error}`; break; }
    }
  } catch (e) {
    $("check-status").textContent = `Error: ${e.message}`;
  } finally {
    $("check").disabled = false;
  }
};

// ------------------------------------------------------------ wiring
$("pick-folder").onchange = (e) => uploadAll(fromInput(e.target)).catch(showError);
$("pick-files").onchange = (e) => uploadAll(fromInput(e.target)).catch(showError);
const drop = $("drop");
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); fromDrop(e.dataTransfer).then(uploadAll).catch(showError); };

function showError(e) { $("upload-status").textContent = `Error: ${e.message}`; }

fetch("/health").then((r) => r.json()).then((d) => { $("version").textContent = d.version; })
  .catch(() => { $("version").textContent = "unavailable"; });
showPlant().then(loadPlants).then(loadRegister);
