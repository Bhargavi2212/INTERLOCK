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

async function showPlant() {
  if (!plantId) { $("plant-info").textContent = "No plant selected."; return null; }
  try {
    const p = await api(`/plants/${plantId}`);
    $("plant-info").textContent =
      `${p.name} — ${p.page_count} pages, ingest ${p.ingest_status}, ${p.files.length} files (id ${p.plant_id})`;
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
  showPlant();
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

async function ingest(failed) {
  const { job_id } = await api(`/plants/${plantId}/ingest`, { method: "POST" });
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
      if (plant && j.state === "done") $("ingest-status").textContent = `Ingest done: ${plant.page_count} pages in this plant.`;
      return;
    }
  }
}

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
showPlant();
