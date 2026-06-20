// ───────────────────────────────────────────────────────────────────────────
// HR / Admin Dashboard
// Self-contained module added alongside the existing chat app. It does NOT modify
// any chat / single-upload / conversation_id logic — it only adds the HR view and
// talks to the /admin/* endpoints. Auth reuses the same token the chat app stores
// in localStorage ("resumeai_token").
// ───────────────────────────────────────────────────────────────────────────
(function () {
  "use strict";

  // API_BASE is a global const declared in app.js (loaded before this file).
  const BASE = (typeof API_BASE !== "undefined") ? API_BASE : "http://localhost:8000";

  // --- Auth helpers (same token the chat flow already uses) ---
  function hrToken() { return localStorage.getItem("resumeai_token") || ""; }
  function hrAuthHeaders(extra = {}) {
    const t = hrToken();
    return t ? { ...extra, Authorization: `Bearer ${t}` } : extra;
  }
  function ensureAuth() {
    if (hrToken()) return true;
    alert("Please sign in first.");
    return false;
  }

  // --- Small utils ---
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function fmtSize(bytes) {
    if (!bytes && bytes !== 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  // --- Module state ---
  let hrRanked = [];
  let hrSort = { key: "rank", dir: "asc" };

  // DOM refs (assigned on DOMContentLoaded)
  let elWelcome, elChat, elHr, tabChat, tabHr;
  let fileInput, dropzone, fileListEl, uploadBtn, progressWrap, progressBar, uploadResult;
  let jobTitleEl, rankBtn, rankStatus, refreshBtn, exportBtn, tableBody;

  // ── View switching ─────────────────────────────────────────────────────────
  function showView(view) {
    if (view === "hr") {
      document.body.classList.add("hr-mode");
      elWelcome && elWelcome.classList.add("hidden");
      elChat && elChat.classList.add("hidden");
      elHr.classList.remove("hidden");
      tabHr.classList.add("active");
      tabChat.classList.remove("active");
      loadRanked();
    } else {
      document.body.classList.remove("hr-mode");
      elHr.classList.add("hidden");
      // Restore whichever chat sub-view was appropriate, mirroring app.js behaviour.
      const hasConvo = (typeof activeConversationId !== "undefined") && activeConversationId;
      if (hasConvo) {
        elWelcome && elWelcome.classList.add("hidden");
        elChat && elChat.classList.remove("hidden");
      } else {
        elChat && elChat.classList.add("hidden");
        elWelcome && elWelcome.classList.remove("hidden");
      }
      tabChat.classList.add("active");
      tabHr.classList.remove("active");
    }
  }

  // ── Role-based access ──────────────────────────────────────────────────────
  // Show the HR tab only for admin accounts. Runs on load and whenever auth state
  // changes, so refreshing the page never leaks the HR tab to a "user" account.
  async function applyRoleVisibility() {
    if (!tabHr) tabHr = document.getElementById("tabHr");
    if (!tabHr) return;
    const show = (visible) => tabHr.classList.toggle("hidden", !visible);
    if (!hrToken()) { show(false); return; }
    try {
      const res = await fetch(`${BASE}/auth/me`, { headers: hrAuthHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const me = await res.json();
      const isAdmin = me && me.role === "admin";
      show(isAdmin);
      // If a non-admin somehow has the HR view open, send them back to Chat.
      if (!isAdmin && document.body.classList.contains("hr-mode")) showView("chat");
    } catch (_) {
      show(false);
    }
  }

  // ── Bulk upload ──────────────────────────────────────────────────────────--
  function renderFileList() {
    const files = fileInput.files ? [...fileInput.files] : [];
    fileListEl.innerHTML = files.map(f =>
      `<li><i class="fas fa-file-lines"></i> ${escapeHtml(f.name)} <span class="fsize">${fmtSize(f.size)}</span></li>`
    ).join("");
    uploadBtn.disabled = files.length === 0;
  }

  function setProgress(pct) { progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`; }

  function renderUploadResult(data) {
    const created = (data && data.created) || [];
    const failed = (data && data.failed) || [];
    let html = `<span class="ok">✓ ${created.length} processed</span>`;
    if (failed.length) html += ` · <span class="fail">${failed.length} failed</span>`;
    if (created.length) {
      html += `<ul style="margin-top:8px;list-style:none;padding:0;">` +
        created.map(c => `<li><i class="fas fa-check" style="color:#15803d"></i> ${escapeHtml(c.file_name)}</li>`).join("") +
        `</ul>`;
    }
    if (failed.length) {
      html += `<ul style="margin-top:4px;list-style:none;padding:0;">` +
        failed.map(f => `<li class="fail"><i class="fas fa-xmark"></i> ${escapeHtml(f.file_name)} — ${escapeHtml(f.error || "error")}</li>`).join("") +
        `</ul>`;
    }
    uploadResult.className = "hr-result " + (failed.length && !created.length ? "error" : "ok");
    uploadResult.innerHTML = html;
  }

  function doBulkUpload() {
    const files = fileInput.files ? [...fileInput.files] : [];
    if (!files.length) return;
    if (!ensureAuth()) return;

    const formData = new FormData();
    files.forEach(f => formData.append("files", f)); // backend reads the "files" field

    progressWrap.classList.remove("hidden");
    setProgress(0);
    uploadBtn.disabled = true;
    uploadResult.className = "hr-result";
    uploadResult.textContent = "Uploading…";

    // XHR (not fetch) so we can show a real upload progress bar.
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/admin/upload/bulk`);
    xhr.setRequestHeader("Authorization", `Bearer ${hrToken()}`);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) setProgress((e.loaded / e.total) * 100); };
    xhr.onload = () => {
      setProgress(100);
      uploadBtn.disabled = false;
      if (xhr.status >= 200 && xhr.status < 300) {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (_) {}
        renderUploadResult(data);
        fileInput.value = "";
        renderFileList();
      } else {
        uploadResult.className = "hr-result error";
        uploadResult.textContent = `Upload failed (HTTP ${xhr.status}).`;
      }
      setTimeout(() => progressWrap.classList.add("hidden"), 600);
    };
    xhr.onerror = () => {
      uploadBtn.disabled = false;
      progressWrap.classList.add("hidden");
      uploadResult.className = "hr-result error";
      uploadResult.textContent = "Could not reach the server.";
    };
    xhr.send(formData);
  }

  // ── Rank ─────────────────────────────────────────────────────────────────--
  async function doRank() {
    if (!ensureAuth()) return;
    const jt = jobTitleEl.value.trim();
    const orig = rankBtn.innerHTML;
    rankBtn.disabled = true;
    rankBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ranking…';
    rankStatus.className = "hr-status";
    rankStatus.textContent = "Scoring candidates… this can take a few seconds.";
    try {
      const res = await fetch(`${BASE}/admin/rank-candidates?job_title=${encodeURIComponent(jt)}`, {
        method: "POST",
        headers: hrAuthHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      rankStatus.className = "hr-status ok";
      rankStatus.textContent = `Ranked ${data.total_candidates != null ? data.total_candidates : 0} candidate(s).`;
      await loadRanked();
    } catch (e) {
      rankStatus.className = "hr-status error";
      rankStatus.textContent = `Ranking failed: ${e.message}`;
    } finally {
      rankBtn.disabled = false;
      rankBtn.innerHTML = orig;
    }
  }

  // ── Ranked results table ───────────────────────────────────────────────────
  function scoreBadge(v) {
    const n = Number(v) || 0;
    const cls = n >= 70 ? "high" : n >= 40 ? "mid" : "low";
    return `<span class="score-badge ${cls}">${n.toFixed(1)}</span>`;
  }

  function compareRows(a, b, key, dir) {
    if (key === "file_name") {
      const va = (a[key] || "").toLowerCase();
      const vb = (b[key] || "").toLowerCase();
      const r = va < vb ? -1 : va > vb ? 1 : 0;
      return dir === "asc" ? r : -r;
    }
    const va = Number(a[key]) || 0;
    const vb = Number(b[key]) || 0;
    return dir === "asc" ? va - vb : vb - va;
  }

  function updateSortIndicators() {
    document.querySelectorAll("#hrTable thead th").forEach(th => {
      const existing = th.querySelector(".sort-ind");
      if (existing) existing.remove();
      if (th.dataset.sort === hrSort.key) {
        const span = document.createElement("span");
        span.className = "sort-ind";
        span.textContent = hrSort.dir === "asc" ? "▲" : "▼";
        th.appendChild(span);
      }
    });
  }

  function renderTable() {
    if (!hrRanked.length) {
      tableBody.innerHTML = `<tr><td colspan="6" class="hr-empty">No rankings yet — upload resumes and run “Rank candidates”.</td></tr>`;
      updateSortIndicators();
      return;
    }
    const rows = [...hrRanked].sort((a, b) => compareRows(a, b, hrSort.key, hrSort.dir));
    tableBody.innerHTML = rows.map(r => `
      <tr>
        <td class="hr-rankcell">#${r.rank != null ? r.rank : "—"}</td>
        <td class="hr-fname">${escapeHtml(r.file_name || "")}</td>
        <td>${scoreBadge(r.skills_score)}</td>
        <td>${scoreBadge(r.experience_score)}</td>
        <td>${scoreBadge(r.education_score)}</td>
        <td>${scoreBadge(r.overall_score)}</td>
      </tr>`).join("");
    updateSortIndicators();
  }

  async function loadRanked() {
    if (!hrToken()) return;
    try {
      const res = await fetch(`${BASE}/admin/candidates/ranked`, { headers: hrAuthHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      hrRanked = await res.json();
      renderTable();
    } catch (e) {
      tableBody.innerHTML = `<tr><td colspan="6" class="hr-empty">Could not load rankings (${escapeHtml(e.message)}).</td></tr>`;
    }
  }

  // ── Export CSV ─────────────────────────────────────────────────────────────
  async function doExport() {
    if (!ensureAuth()) return;
    try {
      const res = await fetch(`${BASE}/admin/candidates/export`, { headers: hrAuthHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "candidate_rankings.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (e) {
      alert("Export failed: " + e.message);
    }
  }

  // ── Wire up ────────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", () => {
    elWelcome = document.getElementById("welcome-screen");
    elChat = document.getElementById("chat-area");
    elHr = document.getElementById("hr-dashboard");
    tabChat = document.getElementById("tabChat");
    tabHr = document.getElementById("tabHr");

    fileInput = document.getElementById("hrFileInput");
    dropzone = document.getElementById("hrDropzone");
    fileListEl = document.getElementById("hrFileList");
    uploadBtn = document.getElementById("hrUploadBtn");
    progressWrap = document.getElementById("hrProgressWrap");
    progressBar = document.getElementById("hrProgressBar");
    uploadResult = document.getElementById("hrUploadResult");

    jobTitleEl = document.getElementById("hrJobTitle");
    rankBtn = document.getElementById("hrRankBtn");
    rankStatus = document.getElementById("hrRankStatus");
    refreshBtn = document.getElementById("hrRefreshBtn");
    exportBtn = document.getElementById("hrExportBtn");
    tableBody = document.getElementById("hrTableBody");

    if (!elHr || !tabHr) return; // markup missing — nothing to wire

    // Tabs
    tabHr.addEventListener("click", () => { if (ensureAuth()) showView("hr"); });
    tabChat.addEventListener("click", () => showView("chat"));
    // When the chat app logs out, fall back to the chat view (its handler also runs).
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", () => { showView("chat"); applyRoleVisibility(); });

    // Gate the HR tab by role: on initial load, and again whenever auth state
    // changes. app.js toggles the "hidden" class on #authState on login/logout,
    // so observing it re-runs the role check after every login.
    applyRoleVisibility();
    const authState = document.getElementById("authState");
    if (authState) {
      new MutationObserver(() => applyRoleVisibility())
        .observe(authState, { attributes: true, attributeFilter: ["class"] });
    }

    // Bulk upload
    fileInput.addEventListener("change", renderFileList);
    uploadBtn.addEventListener("click", doBulkUpload);

    // Drag & drop onto the dropzone
    ["dragenter", "dragover"].forEach(ev =>
      dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); }));
    ["dragleave", "dragend"].forEach(ev =>
      dropzone.addEventListener(ev, () => dropzone.classList.remove("dragover")));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        renderFileList();
      }
    });

    // Rank + results
    rankBtn.addEventListener("click", doRank);
    if (refreshBtn) refreshBtn.addEventListener("click", loadRanked);
    if (exportBtn) exportBtn.addEventListener("click", doExport);

    // Sortable headers
    document.querySelectorAll("#hrTable thead th").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (!key) return;
        if (hrSort.key === key) {
          hrSort.dir = hrSort.dir === "asc" ? "desc" : "asc";
        } else {
          hrSort.key = key;
          // numbers default high→low, names default A→Z, rank default 1→N
          hrSort.dir = (key === "file_name" || key === "rank") ? "asc" : "desc";
        }
        renderTable();
      });
    });
  });
})();
