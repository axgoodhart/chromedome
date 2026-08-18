"use strict";

const ACCEPTED = [".txt", ".rtf", ".html", ".css", ".js", ".tsx", ".jsx", ".py"];
const CUSTOM_SEED = [
  "#17233f", "#365486", "#7fc7d9", "#dcf2f1",
  "#f2efe7", "#d67b5b", "#d6a84b", "#6b8f71",
  "#77567a", "#b06f89", "#537188", "#c3acd0",
];

const state = {
  filename: null,
  source: null,           // "file" | "paste" | "sample"
  content: null,
  entries: [],
  excluded: new Set(),
  mapping: null,          // key -> toHex
  result: null,
  mode: "original",
  view: "cards",
  themeTable: null,       // the selected table as adjusted, for the strip
  adjust: {
    hue: 0, saturation: 100, brightness: 100, contrast: 100, sepia: 0,
  },
  simplify: { drift: 0, deviation: 0 },
  align: {
    colors: ["#2f6bdf", "#e2593a", "#58a66b", "#d6a33d"],
    enabled: [true, false, false, false],
    direction: "warmer",
    threshold: 40,
  },
  shuffle: { variant: "permute", seed: 1, drift: 0, deviation: 0 },
  theme: {
    id: "nord",
    customColors: CUSTOM_SEED.slice(0, 6),
    drift: 0,
    deviation: 0,
  },
};

const ADJUST_DEFAULTS = {
  hue: 0, saturation: 100, brightness: 100, contrast: 100, sepia: 0,
};
const ADJUST_UNITS = {
  hue: "°", saturation: "%", brightness: "%", contrast: "%", sepia: "%",
};

const $ = (id) => document.getElementById(id);

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/* ---- status + errors ---------------------------------------------------- */

function setStatus(text) {
  $("map-status").textContent = text;
}

function showError(message) {
  const banner = $("error-banner");
  banner.textContent = message;
  banner.hidden = false;
}

function clearError() {
  $("error-banner").hidden = true;
}

async function api(path, body) {
  let res;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("The local server didn’t answer. It may have stopped — restart it with python3 server.py, then retry.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "The server refused the request.");
  return data;
}

/* ---- meta (strip of 60, theme tables) ------------------------------------ */

const themeStrips = new Map();   // id -> strip element
const themeBase = new Map();     // id -> unadjusted colors

async function loadMeta() {
  let meta;
  try {
    const res = await fetch("/api/meta");
    meta = await res.json();
  } catch {
    showError("The local server didn’t answer while loading palettes. Restart it with python3 server.py, then reload this page.");
    return;
  }

  const strip = $("strip60");
  for (const hex of meta.simplify) {
    const cell = document.createElement("span");
    cell.style.setProperty("--c", hex);
    strip.appendChild(cell);
  }

  const list = $("theme-list");

  function addThemeOption(theme, checked = false) {
    const label = document.createElement("label");
    label.className = "theme";

    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "theme-table";
    radio.value = theme.id;
    radio.checked = checked;

    const name = document.createElement("span");
    name.className = "theme__name";
    name.textContent = theme.label;

    const stripEl = document.createElement("span");
    stripEl.className = "theme__strip";
    themeStrips.set(theme.id, stripEl);
    if (theme.id !== "custom") themeBase.set(theme.id, theme.colors);
    paintStrip(stripEl, theme.colors);

    label.append(radio, name, stripEl);
    list.appendChild(label);
  }

  addThemeOption({
    id: "custom",
    label: "Custom",
    colors: state.theme.customColors,
  });
  meta.themes.forEach((theme, i) => addThemeOption(theme, i === 0));
  renderCustomColors();

  list.addEventListener("change", (e) => {
    if (e.target.name === "theme-table") {
      state.theme.id = e.target.value;
      $("custom-theme-editor").hidden = state.theme.id !== "custom";
      state.themeTable = null;
      refreshThemeStrips();
      requestTransform();
    }
  });
}

function paintStrip(el, colors) {
  el.replaceChildren();
  for (const hex of colors) {
    const cell = document.createElement("span");
    cell.style.setProperty("--c", hex);
    el.appendChild(cell);
  }
}

/* Every strip shows its own table; the selected one shows it adjusted. */
function refreshThemeStrips() {
  for (const [id, el] of themeStrips) {
    const base = id === "custom" ? state.theme.customColors : themeBase.get(id);
    const adjusted = state.mode === "theme"
      && id === state.theme.id
      && state.themeTable;
    paintStrip(el, adjusted || base || []);
  }
}

function renderCustomColors() {
  const container = $("custom-colors");
  container.replaceChildren();

  state.theme.customColors.forEach((hex, index) => {
    const row = document.createElement("div");
    row.className = "custom-color";

    const input = document.createElement("input");
    input.type = "color";
    input.value = hex;
    input.setAttribute("aria-label", `Custom color ${index + 1}`);
    input.addEventListener("input", () => {
      state.theme.customColors[index] = input.value;
      code.textContent = input.value;
      state.themeTable = null;
      refreshThemeStrips();
      if (state.theme.id === "custom") requestTransform();
    });

    const code = document.createElement("code");
    code.textContent = hex;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "custom-color__remove";
    remove.textContent = "−";
    remove.setAttribute("aria-label", `Remove custom color ${index + 1}`);
    remove.disabled = state.theme.customColors.length <= 2;
    remove.addEventListener("click", () => {
      state.theme.customColors.splice(index, 1);
      renderCustomColors();
      if (state.theme.id === "custom") requestTransform();
    });

    row.append(input, code, remove);
    container.appendChild(row);
  });

  $("custom-add").disabled = state.theme.customColors.length >= 64;
  refreshThemeStrips();
}

/* ---- file handling -------------------------------------------------------- */

function extensionOf(name) {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

async function openFile(file) {
  clearError();
  const ext = extensionOf(file.name);
  if (!ACCEPTED.includes(ext)) {
    showError(`Chromap can’t read ${file.name} — it only scans text formats (${ACCEPTED.join(", ")}). Pick one of those.`);
    return;
  }
  const content = await file.text();
  await scanContent(file.name, content, file.size);
}

function renderFileChip(name, size, source) {
  const info = $("file-info");
  info.textContent = "";
  const chip = document.createElement("div");
  chip.className = "filechip";
  const nameEl = document.createElement("span");
  nameEl.className = "filechip__name";
  nameEl.textContent = name;
  const sizeEl = document.createElement("span");
  sizeEl.className = "filechip__size";
  sizeEl.textContent = size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`;
  chip.append(nameEl, sizeEl);
  info.appendChild(chip);

  if (source !== "paste") return;

  const more = document.createElement("div");
  more.className = "filechip__more";
  const tag = document.createElement("span");
  tag.className = "chip-mono";
  tag.textContent = "PASTED";
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "btn btn--ghost btn--compact";
  edit.textContent = "Edit text";
  edit.addEventListener("click", openPaste);
  more.append(tag, edit);
  info.appendChild(more);
}

async function scanContent(name, content, size, source = "file") {
  setStatus("SCANNING…");
  state.filename = name;
  state.source = source;
  state.content = content;
  state.excluded.clear();
  state.mapping = null;
  state.result = null;

  /* Do not make the browser keep laying out an obsolete long preview while
   * the new map is being built. The replacement is inserted after transform. */
  $("preview").hidden = true;
  $("preview-code").replaceChildren();
  $("preview-note").hidden = true;

  renderFileChip(name, size ?? content.length, source);

  let data;
  try {
    data = await api("/api/scan", { content });
  } catch (err) {
    setStatus("SCAN FAILED");
    showError(err.message);
    return;
  }

  state.entries = data.entries;

  if (state.entries.length === 0) {
    setStatus("0 COLORS");
    $("map-empty").hidden = false;
    $("preview").hidden = true;
    $("btn-download").disabled = true;
    invalidateViews();
    showError(`No colors found in ${name}. The scanner looks for hex, rgb()/rgba(), hsl()/hsla(), CSS color names, and RTF color tables — try another file, or scan the sample.`);
    return;
  }

  $("map-empty").hidden = true;
  invalidateViews();
  requestTransformNow();
}

/* ---- views ------------------------------------------------------------------ */

let orderedView = null;
let sphereView = null;

/* One row shape, three readings of it. */
function viewRows() {
  return state.entries.map((entry) => {
    const frozen = state.excluded.has(entry.key);
    const toHex = !frozen && state.mapping ? state.mapping[entry.key] : null;
    return {
      key: entry.key,
      fromHex: entry.hex,
      toHex: toHex || entry.hex,
      count: entry.count,
      label: entry.literals[0].text,
      excluded: frozen || !toHex,
    };
  });
}

const viewPanels = {
  cards: { id: "map-grid", dirty: true, render: () => renderMap() },
  ordered: {
    id: "view-ordered",
    dirty: true,
    render: () => orderedView && orderedView.render(viewRows()),
  },
  sphere: {
    id: "view-sphere",
    dirty: true,
    render: () => sphereView && sphereView.update(viewRows()),
  },
};

function invalidateViews() {
  for (const panel of Object.values(viewPanels)) panel.dirty = true;
  syncViews();
}

/* Only the visible view renders; the others wait until they are asked for. */
function syncViews() {
  const hasData = state.entries.length > 0;
  $("view-switch").hidden = !hasData;

  for (const [name, panel] of Object.entries(viewPanels)) {
    const on = hasData && state.view === name;
    $(panel.id).hidden = !on;
    if (on && panel.dirty) {
      panel.render();
      panel.dirty = false;
    }
  }

  if (sphereView) sphereView.setActive(hasData && state.view === "sphere");
}

/* ---- the magical map -------------------------------------------------------- */

function formatTag(entry) {
  const formats = [...new Set(entry.literals.map((l) => l.format.toUpperCase()))];
  const shown = formats.slice(0, 2).join("+");
  return formats.length > 2 ? `${shown}+` : shown;
}

function renderMap() {
  const grid = $("map-grid");
  grid.textContent = "";

  for (const entry of state.entries) {
    const excluded = state.excluded.has(entry.key);
    const toHex = !excluded && state.mapping ? state.mapping[entry.key] : null;

    const card = document.createElement("article");
    card.className = "sw" + (excluded ? " sw--off" : "");

    const chips = document.createElement("div");
    chips.className = "sw__chips";
    const oldChip = document.createElement("span");
    oldChip.className = "sw__old";
    oldChip.style.setProperty("--c", entry.hex);
    chips.appendChild(oldChip);
    if (toHex && toHex !== entry.hex) {
      const newChip = document.createElement("span");
      newChip.className = "sw__new";
      newChip.style.setProperty("--c", toHex);
      chips.appendChild(newChip);
    }

    const body = document.createElement("div");
    body.className = "sw__body";

    const lits = document.createElement("div");
    lits.className = "sw__lits";
    const from = document.createElement("code");
    from.textContent = entry.literals[0].text;
    from.title = entry.literals.map((l) => `${l.text} ×${l.count}`).join("\n");
    lits.appendChild(from);
    if (toHex) {
      const arrow = document.createElement("span");
      arrow.className = "sw__arrow";
      arrow.textContent = "→";
      const to = document.createElement("code");
      to.className = "sw__to";
      to.textContent = toHex;
      lits.append(arrow, to);
    }

    const row = document.createElement("div");
    row.className = "sw__row";
    const meta = document.createElement("span");
    meta.className = "sw__meta";
    meta.textContent = `×${entry.count} · ${formatTag(entry)}`;
    const keep = document.createElement("label");
    keep.className = "sw__keep";
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = !excluded;
    check.setAttribute("aria-label", `Remap ${entry.hex}`);
    check.addEventListener("change", () => {
      if (check.checked) state.excluded.delete(entry.key);
      else state.excluded.add(entry.key);
      card.classList.toggle("sw--off", !check.checked);
      requestTransform();
    });
    keep.append(check, document.createTextNode("remap"));
    row.append(meta, keep);

    body.append(lits, row);
    card.append(chips, body);
    grid.appendChild(card);
  }
}

/* ---- transform ----------------------------------------------------------------- */

/* The adjust sliders ride on every mode — the engine applies them as a final
 * pass over whatever the mode mapped. */
function buildParams() {
  const params = paramsForMode();
  params.adjust = { ...state.adjust };
  return params;
}

function paramsForMode() {
  switch (state.mode) {
    case "original":
      return {};
    case "simplify":
      return {
        drift: state.simplify.drift,
        deviation: state.simplify.deviation,
      };
    case "align": {
      return {
        colors: state.align.colors.filter((_, i) => state.align.enabled[i]),
        direction: state.align.direction,
        threshold: state.align.threshold,
      };
    }
    case "shuffle":
      return {
        variant: state.shuffle.variant,
        seed: state.shuffle.seed,
        drift: state.shuffle.drift,
        deviation: state.shuffle.deviation,
      };
    case "theme": {
      const params = {
        theme: state.theme.id,
        drift: state.theme.drift,
        deviation: state.theme.deviation,
      };
      if (state.theme.id === "custom") {
        params.colors = state.theme.customColors;
      }
      return params;
    }
    default:
      return {};
  }
}

let transformSeq = 0;

async function runTransform() {
  if (!state.content || state.entries.length === 0) return;
  clearError();
  setStatus(`${state.entries.length} COLORS · REMAPPING…`);

  const seq = ++transformSeq;
  let data;
  try {
    data = await api("/api/transform", {
      content: state.content,
      mode: state.mode,
      params: buildParams(),
      excluded: [...state.excluded],
    });
  } catch (err) {
    if (seq !== transformSeq) return;
    setStatus(`${state.entries.length} COLORS`);
    showError(err.message);
    return;
  }

  /* Dragging a slider keeps several requests in flight; only the newest
   * one is allowed to land. */
  if (seq !== transformSeq) return;

  state.result = data.result;
  state.mapping = Object.fromEntries(data.mapping.map((r) => [r.key, r.toHex]));
  state.themeTable = data.themeTable || null;

  refreshThemeStrips();
  invalidateViews();

  const changed = data.mapping.filter((r) => r.fromHex !== r.toHex).length;
  setStatus(`${state.entries.length} COLORS · ${changed} CHANGED`);

  $("preview").hidden = false;
  $("preview-name").textContent = downloadName();
  $("preview-code").innerHTML = data.previewHtml;
  $("preview-note").hidden = !data.previewTruncated;
  $("btn-download").disabled = false;
}

const requestTransform = debounce(runTransform, 250);
const requestTransformNow = () => runTransform();

/* ---- download + copy -------------------------------------------------------------- */

function downloadName() {
  const name = state.filename || "file.txt";
  const dot = name.lastIndexOf(".");
  return dot === -1 ? `${name}.recolored` : `${name.slice(0, dot)}.recolored${name.slice(dot)}`;
}

function download() {
  if (state.result == null) return;
  const blob = new Blob([state.result], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = downloadName();
  a.click();
  URL.revokeObjectURL(url);
}

async function copyResult() {
  if (state.result == null) return;
  const btn = $("btn-copy");
  try {
    await navigator.clipboard.writeText(state.result);
  } catch {
    showError("The clipboard refused the write — the browser may need a user gesture or permission. Use Download instead.");
    return;
  }
  btn.dataset.state = "copied";
  btn.textContent = "Copied ✓";
  setTimeout(() => {
    delete btn.dataset.state;
    btn.textContent = "Copy result";
  }, 2500);
}

/* ---- paste or type ------------------------------------------------------------------ */

function sanitizeName(raw) {
  const cleaned = raw.replace(/[\\/]+/g, "-").replace(/^[.\-\s]+/, "").trim();
  return cleaned || "pasted.txt";
}

function updatePasteCount() {
  const n = $("paste-text").value.length;
  $("paste-count").textContent = `${n.toLocaleString()} character${n === 1 ? "" : "s"}`;
}

function showPasteError(message) {
  const banner = $("paste-error");
  banner.textContent = message;
  banner.hidden = false;
}

function openPaste() {
  clearError();
  $("paste-error").hidden = true;
  if (state.source === "paste") {
    $("paste-text").value = state.content ?? "";
    $("paste-name").value = state.filename ?? "pasted.css";
  }
  updatePasteCount();
  $("paste-dialog").showModal();
  const area = $("paste-text");
  area.focus();
  area.setSelectionRange(area.value.length, area.value.length);
}

async function submitPaste(event) {
  event.preventDefault();
  const text = $("paste-text").value;
  if (text.trim() === "") {
    showPasteError("There’s nothing to scan yet — paste or type some text first.");
    $("paste-text").focus();
    return;
  }
  const name = sanitizeName($("paste-name").value);
  $("paste-name").value = name;
  $("paste-dialog").close();
  await scanContent(name, text, text.length, "paste");
}

/* ---- sample ------------------------------------------------------------------------ */

async function loadSample() {
  clearError();
  let text;
  try {
    const res = await fetch("/samples/sample.css");
    if (!res.ok) throw new Error();
    text = await res.text();
  } catch {
    showError("The sample didn’t load. The server may have stopped — restart it with python3 server.py, then retry.");
    return;
  }
  await scanContent("sample.css", text, text.length, "sample");
}

/* ---- wiring ------------------------------------------------------------------------- */

function showParamsFor(mode) {
  document.querySelectorAll(".param-group").forEach((el) => {
    el.hidden = el.dataset.mode !== mode;
  });
}

function init() {
  loadMeta();

  /* Keep the settings panels honest about state.mode rather than trusting
   * whichever radio the markup happens to mark as checked. */
  const checked = document.querySelector('input[name="mode"]:checked');
  if (checked) checked.checked = false;
  const own = document.querySelector(`input[name="mode"][value="${state.mode}"]`);
  if (own) own.checked = true;
  showParamsFor(state.mode);

  orderedView = createOrderedView({
    body: $("ord-body"),
    fromCol: $("ord-from"),
    toCol: $("ord-to"),
    svg: $("ord-links"),
  });

  sphereView = createSphereView({
    canvas: $("orb-canvas"),
    scrub: $("orb-t"),
    scrubOut: $("orb-t-out"),
    replay: $("orb-replay"),
    spinToggle: $("orb-spin"),
  });

  document.querySelectorAll('input[name="view"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      state.view = radio.value;
      syncViews();
    });
  });

  $("file-input").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) openFile(file);
    e.target.value = "";
  });

  $("btn-open-2").addEventListener("click", () => $("file-input").click());
  $("btn-sample").addEventListener("click", loadSample);
  $("btn-sample-2").addEventListener("click", loadSample);
  $("btn-paste").addEventListener("click", openPaste);
  $("btn-paste-2").addEventListener("click", openPaste);
  $("paste-cancel").addEventListener("click", () => $("paste-dialog").close());
  $("paste-form").addEventListener("submit", submitPaste);
  $("paste-text").addEventListener("input", () => {
    updatePasteCount();
    $("paste-error").hidden = true;
  });
  $("paste-text").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      $("paste-form").requestSubmit();
    }
  });
  $("btn-download").addEventListener("click", download);
  $("btn-copy").addEventListener("click", copyResult);

  document.querySelectorAll('input[name="mode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      state.mode = radio.value;
      showParamsFor(radio.value);
      state.themeTable = null;
      refreshThemeStrips();
      requestTransform();
    });
  });

  state.align.colors.forEach((_, index) => {
    const number = index + 1;
    const input = $(`align-c${number}`);
    input.addEventListener("input", () => {
      state.align.colors[index] = input.value;
      $(`align-c${number}-hex`).textContent = input.value;
      requestTransform();
    });

    if (index > 0) {
      $(`align-c${number}-on`).addEventListener("change", (e) => {
        state.align.enabled[index] = e.target.checked;
        $(`align-c${number}-wrap`).hidden = !e.target.checked;
        requestTransform();
      });
    }
  });

  $("align-dir").addEventListener("change", (e) => {
    state.align.direction = e.target.value;
    requestTransform();
  });

  const threshold = $("align-threshold");
  threshold.addEventListener("input", () => {
    state.align.threshold = Number(threshold.value);
    $("align-threshold-out").textContent = `${threshold.value}%`;
    requestTransform();
  });

  function wireDiversity(mode, values) {
    for (const field of ["drift", "deviation"]) {
      const input = $(`${mode}-${field}`);
      input.addEventListener("input", () => {
        values[field] = Number(input.value);
        $(`${mode}-${field}-out`).textContent = `${input.value}%`;
        requestTransform();
      });
    }
  }

  wireDiversity("simplify", state.simplify);
  wireDiversity("shuffle", state.shuffle);
  wireDiversity("theme", state.theme);

  function showAdjust(field) {
    const value = state.adjust[field];
    $(`adjust-${field}`).value = String(value);
    $(`adjust-${field}-out`).textContent = `${value}${ADJUST_UNITS[field]}`;
  }

  for (const field of Object.keys(ADJUST_DEFAULTS)) {
    $(`adjust-${field}`).addEventListener("input", (e) => {
      state.adjust[field] = Number(e.target.value);
      showAdjust(field);
      requestTransform();
    });
  }

  $("adjust-reset").addEventListener("click", () => {
    state.adjust = { ...ADJUST_DEFAULTS };
    Object.keys(ADJUST_DEFAULTS).forEach(showAdjust);
    requestTransform();
  });

  document.querySelectorAll('input[name="shuffle-variant"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      state.shuffle.variant = radio.value;
      requestTransform();
    });
  });

  $("btn-reshuffle").addEventListener("click", () => {
    state.shuffle.seed = Math.floor(Math.random() * 1e9);
    requestTransform();
  });

  $("custom-add").addEventListener("click", () => {
    if (state.theme.customColors.length >= 64) return;
    const next = CUSTOM_SEED[
      state.theme.customColors.length % CUSTOM_SEED.length];
    state.theme.customColors.push(next);
    renderCustomColors();
    if (state.theme.id === "custom") requestTransform();
  });

  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) openFile(file);
  });
}

init();
