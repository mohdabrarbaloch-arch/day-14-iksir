/* Iksir front end. Plain DOM, no framework, no build step.
   The API is the product; this just makes it usable. */

const state = {
  token: localStorage.getItem("iksir_token") || null,
  user: null,
  targets: [],
  starter: [],
  selected: new Set(),
  authMode: "login",
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* ---------------- api ---------------- */

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;

  const res = await fetch(path, { ...options, headers });
  let body = null;
  const text = await res.text();
  if (text) {
    try { body = JSON.parse(text); } catch { body = { detail: text }; }
  }
  if (!res.ok) {
    const detail = body && body.detail;
    let message = "Request failed";
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) message = detail.map((d) => d.msg || String(d)).join("; ");
    else if (detail && detail.message) message = detail.message;
    throw new Error(message);
  }
  return body;
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = false;
}
function clearError(el) { el.hidden = true; el.textContent = ""; }

/* ---------------- auth ---------------- */

function renderAccount() {
  const who = $("#who");
  const btn = $("#authBtn");
  if (state.user) {
    who.textContent = state.user.display_name;
    btn.textContent = "Sign out";
  } else {
    who.textContent = "";
    btn.textContent = "Sign in";
  }
}

async function loadSession() {
  if (!state.token) return;
  try {
    state.user = await api("/api/auth/me");
  } catch {
    state.token = null;
    localStorage.removeItem("iksir_token");
    state.user = null;
  }
  renderAccount();
}

$("#authBtn").addEventListener("click", async () => {
  if (state.user) {
    state.token = null;
    state.user = null;
    localStorage.removeItem("iksir_token");
    renderAccount();
    $("#runsOut").innerHTML = '<p class="empty">Sign in to keep a history of your screening runs.</p>';
    return;
  }
  state.authMode = "login";
  renderAuthMode();
  $("#authModal").hidden = false;
  $("#authEmail").focus();
});

function renderAuthMode() {
  const isLogin = state.authMode === "login";
  $("#authTitle").textContent = isLogin ? "Sign in" : "Create an account";
  $("#authSubmit").textContent = isLogin ? "Sign in" : "Create account";
  $("#nameField").hidden = isLogin;
  $("#switchText").textContent = isLogin ? "No account yet?" : "Already have one?";
  $("#switchBtn").textContent = isLogin ? "Create one" : "Sign in";
  $("#authPassword").setAttribute("autocomplete", isLogin ? "current-password" : "new-password");
  clearError($("#authError"));
}

$("#switchBtn").addEventListener("click", () => {
  state.authMode = state.authMode === "login" ? "register" : "login";
  renderAuthMode();
});

$("#modalClose").addEventListener("click", () => { $("#authModal").hidden = true; });
$("#authModal").addEventListener("click", (e) => {
  if (e.target === $("#authModal")) $("#authModal").hidden = true;
});

$("#authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = $("#authError");
  clearError(errEl);
  const btn = $("#authSubmit");
  btn.disabled = true;

  try {
    const email = $("#authEmail").value.trim();
    const password = $("#authPassword").value;
    let body;

    if (state.authMode === "register") {
      const displayName = $("#authName").value.trim() || email.split("@")[0];
      body = await api("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, display_name: displayName, password }),
      });
    } else {
      body = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
    }

    state.token = body.access_token;
    state.user = body.user;
    localStorage.setItem("iksir_token", state.token);
    renderAccount();
    $("#authModal").hidden = true;
    $("#authPassword").value = "";
    loadRuns();
  } catch (err) {
    showError(errEl, err.message);
  } finally {
    btn.disabled = false;
  }
});

/* ---------------- tabs ---------------- */

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("is-active"));
    $$(".view").forEach((v) => v.classList.remove("is-active"));
    tab.classList.add("is-active");
    $(`#view-${tab.dataset.view}`).classList.add("is-active");
    if (tab.dataset.view === "runs") loadRuns();
  });
});

/* ---------------- data loading ---------------- */

async function loadTargets() {
  state.targets = await api("/api/targets");
  const select = $("#targetSelect");
  select.innerHTML = state.targets
    .map((t) => `<option value="${t.slug}">${t.name}</option>`)
    .join("");
  renderTargetSummary();
  select.addEventListener("change", renderTargetSummary);
}

function renderTargetSummary() {
  const slug = $("#targetSelect").value;
  const t = state.targets.find((x) => x.slug === slug);
  if (!t) return;
  $("#targetSummary").innerHTML = `
    <strong>${t.gene}</strong> · ${t.family}<br>
    ${t.summary}
    <br><span style="color:var(--ink-faint)">Pocket wants: cLogP ≈ ${t.ideal_logp},
    ${t.hbd_required} donor(s), ${t.hba_required} acceptor(s),
    ${t.aromatic_rings_preferred} aromatic ring(s), MW ${t.mw_band[0]}–${t.mw_band[1]}.</span>`;
}

async function loadStarter() {
  state.starter = await api("/api/compounds/starter");
  const pick = $("#libraryPick");
  pick.innerHTML = state.starter
    .map((c) => `<button type="button" class="chip" data-slug="${c.slug}">${c.name}</button>`)
    .join("");
  pick.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const slug = chip.dataset.slug;
      if (state.selected.has(slug)) state.selected.delete(slug);
      else state.selected.add(slug);
      chip.classList.toggle("is-on");
    });
  });
  renderLibraryGrid();
}

function renderLibraryGrid() {
  $("#libraryGrid").innerHTML = state.starter
    .map(
      (c) => `
    <div class="lib-card">
      <h3>${c.name}</h3>
      <p class="lib-class">${c.therapeutic_class}</p>
      <div class="lib-smiles">${c.smiles}</div>
      <div class="lib-facts"><span>target <b>${c.known_target}</b></span></div>
    </div>`
    )
    .join("");
  // Descriptor facts are filled in lazily so the grid paints immediately.
  state.starter.forEach(async (c, i) => {
    try {
      const d = await api("/api/descriptors", {
        method: "POST",
        body: JSON.stringify({ smiles: c.smiles }),
      });
      const card = $("#libraryGrid").children[i];
      if (!card) return;
      const facts = card.querySelector(".lib-facts");
      facts.innerHTML = `
        <span>MW <b>${d.descriptors.molecular_weight}</b></span>
        <span>cLogP <b>${d.descriptors.clogp}</b></span>
        <span>TPSA <b>${d.descriptors.tpsa}</b></span>
        <span>${d.descriptors.molecular_formula}</span>`;
    } catch { /* leave the target line if descriptors fail */ }
  });
}

/* ---------------- screening ---------------- */

$("#screenBtn").addEventListener("click", async () => {
  const errEl = $("#screenError");
  clearError(errEl);

  const target = $("#targetSelect").value;
  const compounds = state.starter
    .filter((c) => state.selected.has(c.slug))
    .map((c) => ({ name: c.name, smiles: c.smiles }));

  const own = $("#smilesInput").value.trim();
  if (own) compounds.push({ name: "Your compound", smiles: own });

  if (!compounds.length) {
    showError(errEl, "Pick at least one compound from the library, or paste a SMILES.");
    return;
  }

  const btn = $("#screenBtn");
  btn.disabled = true;
  btn.textContent = "Screening…";

  try {
    const result = await api("/api/screen", {
      method: "POST",
      body: JSON.stringify({ target, compounds }),
    });
    renderResults(result);
  } catch (err) {
    showError(errEl, err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run screen";
  }
});

function renderResults(payload) {
  const badge = $("#hitBadge");
  badge.hidden = false;
  badge.textContent = `${payload.hit_count} of ${payload.compound_count} hit`;

  const html = payload.results
    .map((r, i) => {
      const bars = r.terms
        .map(
          (t) => `
        <div class="bar-row">
          <span class="bar-label">${t.name.replace(/_/g, " ")}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${(t.value * 100).toFixed(0)}%"></span></span>
          <span class="bar-val">${t.points.toFixed(1)}</span>
        </div>`
        )
        .join("");

      const penalties = r.penalties.length
        ? `<div class="penalty">−${r.penalties.map((p) => p.points).reduce((a, b) => a + b, 0).toFixed(1)} from ${r.penalties
            .map((p) => p.reason)
            .join(", ")}</div>`
        : "";

      return `
      <div class="result">
        <div class="result-top">
          <span class="result-rank">${i + 1}</span>
          <span class="result-name">${r.compound_name}</span>
          <span class="verdict ${r.verdict}">${r.verdict}</span>
          <span class="result-score">${r.final_score.toFixed(1)}</span>
        </div>
        <p class="result-smiles">${r.smiles}</p>
        <div class="result-facts">
          <span>MW <b>${r.descriptors.molecular_weight}</b></span>
          <span>cLogP <b>${r.descriptors.clogp}</b></span>
          <span>TPSA <b>${r.descriptors.tpsa}</b></span>
          <span>HBD <b>${r.descriptors.h_bond_donors}</b></span>
          <span>HBA <b>${r.descriptors.h_bond_acceptors}</b></span>
          <span>rings <b>${r.descriptors.ring_count}</b></span>
          <span>rot <b>${r.descriptors.rotatable_bonds}</b></span>
        </div>
        <div class="bars">${bars}</div>
        ${penalties}
      </div>`;
    })
    .join("");

  $("#results").innerHTML = html;
}

/* ---------------- descriptors ---------------- */

$("#descBtn").addEventListener("click", async () => {
  const errEl = $("#descError");
  clearError(errEl);
  const smiles = $("#descInput").value.trim();
  if (!smiles) { showError(errEl, "Paste a SMILES string first."); return; }

  const btn = $("#descBtn");
  btn.disabled = true;
  try {
    const d = await api("/api/descriptors", {
      method: "POST",
      body: JSON.stringify({ smiles }),
    });
    renderDescriptors(d);
  } catch (err) {
    showError(errEl, err.message);
  } finally {
    btn.disabled = false;
  }
});

function renderDescriptors(d) {
  const meta = d.descriptors;
  const cells = [
    ["Formula", meta.molecular_formula],
    ["Molecular weight", meta.molecular_weight],
    ["Exact mass", meta.exact_mass],
    ["cLogP", meta.clogp],
    ["TPSA", meta.tpsa],
    ["H-bond donors", meta.h_bond_donors],
    ["H-bond acceptors", meta.h_bond_acceptors],
    ["Rings", meta.ring_count],
    ["Aromatic rings", meta.aromatic_ring_count],
    ["Rotatable bonds", meta.rotatable_bonds],
    ["Heavy atoms", meta.heavy_atoms],
    ["Fraction sp3", meta.fraction_csp3],
  ];

  const grid = cells
    .map(
      ([k, v]) => `<div class="desc-cell"><div class="desc-key">${k}</div><div class="desc-val">${v}</div></div>`
    )
    .join("");

  const checks = d.rule_checks
    .map(
      (c) => `
    <div class="check">
      <span class="check-dot ${c.passed ? "ok" : "no"}"></span>
      <span class="check-name">${c.name}</span>
      <span class="check-vals">${c.value} / ${c.threshold}</span>
    </div>`
    )
    .join("");

  $("#descOut").innerHTML = `
    <div class="desc-grid">${grid}</div>
    <div class="checks">${checks}</div>`;
}

/* ---------------- runs ---------------- */

async function loadRuns() {
  const out = $("#runsOut");
  if (!state.user) {
    out.innerHTML = '<p class="empty">Sign in to keep a history of your screening runs.</p>';
    return;
  }
  try {
    const runs = await api("/api/screen/runs");
    if (!runs.length) {
      out.innerHTML = '<p class="empty">No saved runs yet. Screening runs are saved when you are signed in.</p>';
      return;
    }
    out.innerHTML = runs
      .map(
        (r) => `
      <div class="result">
        <div class="result-top">
          <span class="result-name">${r.target_name}</span>
          <span class="result-score">${r.hit_count}/${r.compound_count}</span>
        </div>
        <div class="result-facts">
          <span>${new Date(r.created_at).toLocaleString()}</span>
        </div>
      </div>`
      )
      .join("");
  } catch (err) {
    out.innerHTML = `<p class="empty">${err.message}</p>`;
  }
}

/* ---------------- boot ---------------- */

(async function boot() {
  try {
    await Promise.all([loadTargets(), loadStarter(), loadSession()]);
  } catch (err) {
    console.error("boot failed", err);
  }
})();
