"use strict";

/* Two alternate readings of the same mapping.
 *
 *   Ordered — both palettes sorted by hue family then lightness, linked
 *             literally: a level line means the color kept its rank, a raked
 *             line means the remap handed its slot to something else.
 *   Sphere  — hue around the axis, lightness up it, chroma out from it; the
 *             whole cloud tweens from the current palette to the new one.
 *
 * Both take the same row shape:
 *   {key, fromHex, toHex, count, label, excluded}
 */

/* ---- ordered ------------------------------------------------------------ */

function createOrderedView({ body, fromCol, toCol, svg }) {
  const SVG_NS = "http://www.w3.org/2000/svg";
  let rows = [];
  let links = [];   // {path, head, fromEl, toEl}
  let pairs = [];   // last laid-out pairing, so a resize only redraws links
  let drawFrame = null;
  let lastLayoutKey = "";

  /* Group by hue family (12 x 30deg, red-centered), lightest first inside a
   * family; neutrals fall out of the wheel and ride at the end by lightness. */
  function sortKey(hex) {
    const [L, C, H] = CS.hexToOklch(hex);
    if (C < 0.025) return [1, 0, -L, 0];
    let deg = (H * 180) / Math.PI;
    deg = ((deg % 360) + 360) % 360;
    return [0, Math.floor(((deg + 15) % 360) / 30), -L, deg];
  }

  function byKey(a, b) {
    for (let i = 0; i < 4; i += 1) {
      const d = a.sort[i] - b.sort[i];
      if (d) return d;
    }
    return 0;
  }

  function rowEl(hex, meta, side, extra) {
    const el = document.createElement("div");
    el.className = "ord__row";

    const chip = document.createElement("span");
    chip.className = "ord__chip";
    chip.style.setProperty("--c", hex);

    const text = document.createElement("span");
    text.className = "ord__text";
    const code = document.createElement("code");
    code.textContent = hex;
    const sub = document.createElement("span");
    sub.className = "ord__meta";
    sub.textContent = meta;
    text.append(code, sub);

    if (side === "to") el.append(text, chip);
    else el.append(chip, text);
    if (extra) el.appendChild(extra);
    return el;
  }

  function deltaEl(delta) {
    const el = document.createElement("span");
    el.className = "ord__delta";
    if (delta === 0) {
      el.dataset.dir = "same";
      el.textContent = "=";
      el.title = "Kept its rank in the palette";
    } else {
      el.dataset.dir = delta < 0 ? "up" : "down";
      el.textContent = (delta < 0 ? "↑" : "↓") + Math.abs(delta);
      el.title = `Moved ${Math.abs(delta)} place${
        Math.abs(delta) === 1 ? "" : "s"} ${delta < 0 ? "up" : "down"} the order`;
    }
    return el;
  }

  function highlight(index) {
    links.forEach((link, i) => {
      const on = index === null || i === index;
      link.path.classList.toggle("is-dim", !on);
      if (link.head) link.head.classList.toggle("is-dim", !on);
      link.fromEl.classList.toggle("is-lit", index === i);
      link.toEl.classList.toggle("is-lit", index === i);
    });
  }

  function render(nextRows) {
    if (nextRows) rows = nextRows;

    const items = rows.map((r, i) => ({
      ...r,
      source: i,
      sort: sortKey(r.fromHex),
      toSort: sortKey(r.toHex),
    }));

    const fromOrder = [...items].sort(byKey);
    const toOrder = [...items].sort((a, b) => {
      for (let i = 0; i < 4; i += 1) {
        const d = a.toSort[i] - b.toSort[i];
        if (d) return d;
      }
      return 0;
    });

    const toRank = new Map(toOrder.map((it, i) => [it.source, i]));

    fromCol.replaceChildren();
    toCol.replaceChildren();
    links = [];

    const fromEls = fromOrder.map((it, i) => {
      const delta = toRank.get(it.source) - i;
      const el = rowEl(it.fromHex, `×${it.count}`, "from",
        it.excluded ? null : deltaEl(delta));
      if (it.excluded) el.classList.add("ord__row--frozen");
      fromCol.appendChild(el);
      return el;
    });

    const toEls = toOrder.map((it) => {
      const el = rowEl(it.toHex, it.excluded ? "frozen" : `×${it.count}`, "to");
      if (it.excluded) el.classList.add("ord__row--frozen");
      toCol.appendChild(el);
      return el;
    });

    pairs = fromOrder.map((it, i) => ({
      excluded: it.excluded,
      hex: it.fromHex,
      fromEl: fromEls[i],
      toEl: toEls[toRank.get(it.source)],
    }));

    fromEls.forEach((el, i) => {
      el.addEventListener("pointerenter", () => highlight(i));
      el.addEventListener("pointerleave", () => highlight(null));
    });

    draw(true);
  }

  function draw(force = false) {
    if (!pairs.length) return;
    const width = svg.clientWidth || body.clientWidth * 0.15 || 80;
    const height = Math.max(fromCol.offsetHeight, toCol.offsetHeight);
    if (!height) return;

    const layoutKey = `${width}:${height}:${pairs.length}`;
    if (!force && layoutKey === lastLayoutKey) return;

    /* Read every row position before changing the SVG. Interleaving these
     * offset reads with appendChild() forced Chrome to lay out the entire
     * page once per color — especially expensive beside a long preview. */
    const geometry = pairs.map((pair) => ({
      pair,
      y1: pair.fromEl.offsetTop + pair.fromEl.offsetHeight / 2,
      y2: pair.toEl.offsetTop + pair.toEl.offsetHeight / 2,
    }));

    const fragment = document.createDocumentFragment();
    const nextLinks = [];
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.style.height = `${height}px`;

    const end = Math.max(width - 9, 1);

    for (const { pair, y1, y2 } of geometry) {
      const level = Math.abs(y1 - y2) < 1;

      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d",
        `M0 ${y1} C ${end * 0.45} ${y1}, ${end * 0.55} ${y2}, ${end} ${y2}`);
      path.setAttribute("class", "ord__link "
        + (pair.excluded ? "ord__link--frozen"
          : level ? "ord__link--direct" : "ord__link--moved"));
      path.style.setProperty("--c", pair.hex);
      fragment.appendChild(path);

      let head = null;
      if (!pair.excluded) {
        head = document.createElementNS(SVG_NS, "path");
        head.setAttribute("d",
          `M${width} ${y2} L${end} ${y2 - 3.6} L${end} ${y2 + 3.6} Z`);
        head.setAttribute("class", "ord__head-mark "
          + (level ? "ord__link--direct" : "ord__link--moved"));
        fragment.appendChild(head);
      }

      nextLinks.push({ path, head, fromEl: pair.fromEl, toEl: pair.toEl });
    }

    svg.replaceChildren(fragment);
    links = nextLinks;
    lastLayoutKey = layoutKey;
  }

  /* Only the links depend on geometry, so a resize redraws them alone —
   * rebuilding the rows here would feed the observer its own output. Collapse
   * resize bursts into one frame, and skip redraws whose geometry is stable. */
  new ResizeObserver(() => {
    if (body.offsetParent === null || drawFrame !== null) return;
    drawFrame = requestAnimationFrame(() => {
      drawFrame = null;
      if (body.offsetParent !== null) draw();
    });
  }).observe(body);

  return { render };
}

/* ---- sphere -------------------------------------------------------------- */

function createSphereView({ canvas, scrub, scrubOut, replay, spinToggle }) {
  const ctx = canvas.getContext("2d");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");

  const TILT = (17 * Math.PI) / 180;
  const CHROMA_EDGE = 0.33;   // Oklab chroma that reaches the surface
  const MORPH_DURATION = 1100;
  const MORPH_GAP = 5000;

  let points = [];
  let spin = 0;
  let spinning = true;
  let t = 1;
  let morph = null;           // {from, to, elapsed, dur}
  let gapTimer = null;
  let frame = null;
  let last = 0;
  let active = false;

  /* hue -> angle around the axis, lightness -> height, chroma -> radius. */
  function place(hex) {
    const [L, C, H] = CS.hexToOklch(hex);
    const phi = (CS.clamp(L, 0, 1) - 0.5) * Math.PI;
    const ring = Math.cos(phi) * Math.min(1, C / CHROMA_EDGE);
    return [ring * Math.cos(H), Math.sin(phi), ring * Math.sin(H)];
  }

  function project(p, cx, cy, R) {
    const cos = Math.cos(spin);
    const sin = Math.sin(spin);
    const x = p[0] * cos + p[2] * sin;
    const z = -p[0] * sin + p[2] * cos;
    const y = p[1] * Math.cos(TILT) - z * Math.sin(TILT);
    const depth = p[1] * Math.sin(TILT) + z * Math.cos(TILT);
    return [cx + x * R, cy - y * R, depth];
  }

  function update(rows) {
    points = rows.map((r) => ({
      a: place(r.fromHex),
      b: place(r.toHex),
      labA: CS.hexToOklab(r.fromHex),
      labB: CS.hexToOklab(r.toHex),
      excluded: r.excluded,
      count: r.count,
    }));
    if (active) draw();
  }

  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);

  function wire(cx, cy, R) {
    ctx.lineWidth = 1;
    for (const L of [0.15, 0.35, 0.5, 0.65, 0.85]) {
      const phi = (L - 0.5) * Math.PI;
      const ring = Math.cos(phi);
      const y = Math.sin(phi);
      ctx.beginPath();
      for (let i = 0; i <= 64; i += 1) {
        const th = (i / 64) * Math.PI * 2;
        const [px, py] = project([ring * Math.cos(th), y, ring * Math.sin(th)],
          cx, cy, R);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = L === 0.5
        ? "rgba(150, 175, 215, 0.30)" : "rgba(150, 175, 215, 0.13)";
      ctx.stroke();
    }

    const [tx, ty] = project([0, 1, 0], cx, cy, R);
    const [bx, by] = project([0, -1, 0], cx, cy, R);
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(bx, by);
    ctx.strokeStyle = "rgba(150, 175, 215, 0.18)";
    ctx.stroke();
  }

  function draw() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (canvas.width !== Math.round(w * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    const R = Math.min(w, h) * 0.4;

    wire(cx, cy, R);

    const k = ease(CS.clamp(t, 0, 1));
    const drawn = points.map((pt) => {
      const pos = [
        pt.a[0] + (pt.b[0] - pt.a[0]) * k,
        pt.a[1] + (pt.b[1] - pt.a[1]) * k,
        pt.a[2] + (pt.b[2] - pt.a[2]) * k,
      ];
      const [px, py, depth] = project(pos, cx, cy, R);
      const rgb = CS.oklabToRgb(CS.mixOklab(pt.labA, pt.labB, k));
      return {
        px, py, depth, rgb, pt,
        from: project(pt.a, cx, cy, R),
        to: project(pt.b, cx, cy, R),
      };
    });

    drawn.sort((p, q) => p.depth - q.depth);

    /* trails: where each color came from, and where it is headed */
    for (const d of drawn) {
      if (d.pt.excluded) continue;
      if (Math.hypot(d.to[0] - d.from[0], d.to[1] - d.from[1]) < 2) continue;
      ctx.beginPath();
      ctx.moveTo(d.from[0], d.from[1]);
      ctx.lineTo(d.to[0], d.to[1]);
      ctx.strokeStyle = `rgba(${d.rgb.join(",")},0.16)`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    const base = CS.clamp(Math.min(w, h) / 46, 3.5, 8);
    for (const d of drawn) {
      const near = (d.depth + 1) / 2;
      const r = base * (0.66 + 0.34 * near)
        * (1 + Math.min(0.5, Math.log10(d.pt.count + 1) * 0.28));
      ctx.beginPath();
      ctx.arc(d.px, d.py, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${d.rgb.join(",")},${(0.45 + 0.55 * near).toFixed(3)})`;
      ctx.fill();
      ctx.lineWidth = d.pt.excluded ? 1.4 : 1;
      ctx.strokeStyle = d.pt.excluded
        ? `rgba(235, 245, 255,${(0.25 + 0.35 * near).toFixed(3)})`
        : `rgba(8, 12, 22,${(0.25 + 0.3 * near).toFixed(3)})`;
      if (d.pt.excluded) ctx.setLineDash([2.5, 2.5]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  function setT(value, silent) {
    t = CS.clamp(value, 0, 1);
    if (!silent) {
      scrub.value = String(Math.round(t * 100));
      scrubOut.textContent = `${Math.round(t * 100)}%`;
    }
    if (active && !frame) draw();
  }

  function schedule() {
    if (frame || !active) return;
    if (!morph && (!spinning || reduced.matches)) return;
    frame = requestAnimationFrame(tick);
  }

  function clearGap() {
    if (gapTimer !== null) clearTimeout(gapTimer);
    gapTimer = null;
  }

  function startMorph(to, from = t) {
    clearGap();
    if (!active || !points.length) return;
    if (reduced.matches) {
      morph = null;
      setT(to);
      draw();
      return;
    }
    setT(from);
    morph = { from, to, elapsed: 0, dur: MORPH_DURATION };
    last = 0;
    schedule();
  }

  function queueReverse() {
    clearGap();
    if (!active || reduced.matches || !points.length) return;
    gapTimer = setTimeout(() => {
      gapTimer = null;
      startMorph(t >= 0.5 ? 0 : 1);
    }, MORPH_GAP);
  }

  function tick(now) {
    frame = null;
    const dt = last ? Math.min(64, now - last) : 16;
    last = now;

    if (spinning && !reduced.matches) spin += (dt / 1000) * 0.34;

    if (morph) {
      /* accumulate frames rather than read the wall clock: a tab that was
       * backgrounded mid-morph resumes the tween instead of skipping it. */
      morph.elapsed += dt;
      const p = CS.clamp(morph.elapsed / morph.dur, 0, 1);
      setT(morph.from + (morph.to - morph.from) * p);
      if (p >= 1) {
        morph = null;
        queueReverse();
      }
    }

    draw();
    schedule();
  }

  function play() {
    if (!points.length) return;
    startMorph(1, 0);
  }

  function setActive(on) {
    if (on === active) return;
    active = on;
    if (!on) {
      clearGap();
      morph = null;
      if (frame) cancelAnimationFrame(frame);
      frame = null;
      last = 0;
      return;
    }
    draw();
    play();
  }

  scrub.addEventListener("input", () => {
    clearGap();
    morph = null;
    setT(Number(scrub.value) / 100);
    if (!frame) draw();
    queueReverse();
  });

  replay.addEventListener("click", play);

  spinToggle.addEventListener("change", () => {
    spinning = spinToggle.checked;
    last = 0;
    if (spinning) schedule();
    else if (frame) { cancelAnimationFrame(frame); frame = null; draw(); }
  });

  new ResizeObserver(() => { if (active) draw(); }).observe(canvas);

  return { update, setActive, play };
}
