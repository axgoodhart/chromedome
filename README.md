# Chromap

A local color remapper. Point it at a text file, and every color literal in it
lands in a map you can remold four different ways, then download the rewritten
file. Python backend (Flask), HTML frontend — nothing leaves your machine.

## Run

```sh
cd chromap
python3 server.py
```

Then open <http://127.0.0.1:5177>.

Requires Python 3 and Flask (`pip install flask` if you don't have it).

## What it reads

`.txt` · `.rtf` · `.html` · `.css` · `.js` · `.tsx` · `.jsx` · `.py`

The scanner captures every color literal:

- hex — `#000`, `#0004`, `#000000`, `#00000080`
- functional — `rgb()`, `rgba()`, `hsl()`, `hsla()` (comma or space syntax)
- the 147 standard CSS color names — `tomato`, `rebeccapurple`, …
- RTF color tables — `\red255\green0\blue0`

Each literal is rewritten **in its own notation**: an `hsl()` stays an `hsl()`,
a named color becomes a name again when the new value has one (hex otherwise),
and alpha channels ride along untouched.

Every captured color has a *remap* toggle in the map — untick it to freeze that
color (useful for false positives like the word "tan" in prose, or `#abc` used
as an id selector).

## The four modes

1. **Simplify** — snap every color to the nearest of 60 plain values
   (12 hues × vivid/light/dark/soft, plus a 12-step neutral ramp).
2. **Align** — pick one to four anchor colors; every color takes its nearest
   anchor's hue and chroma **at its own lightness** (in Oklab, so darks stay
   dark and lights stay light), then drifts by an amount proportional to the
   original color's distance from the closest pure red, green, or blue. Drift
   direction is yours: warmer (toward red), cooler (toward blue), lighter (+),
   darker (−); the strength slider caps the drift. A color that starts on a
   pure primary holds its anchor exactly; white drifts the most.
3. **Shuffle** — reassign the existing palette among its own slots, or deal
   every color a random hue at its own lightness. Reshuffle deals again.
4. **Theme** — recast the palette into one of 24 prebuilt tables (Nord,
   Dracula, Solarized, Gruvbox, Catppuccin, …), now with twice the original
   shades, or build a custom table from 2–64 colors.

Nearest-value matching runs in Oklab with extra weight on lightness, so the
document's light/dark structure survives every mode. Simplify, Shuffle, and
Theme also expose hue-drift and tone-deviation percentages: drift retains the
source hue direction, while deviation retains its original lightness and
intensity.

## Adjust the result

Four sliders — **hue rotate** (±180°), **saturation** and **brightness**
(0–200%), **sepia** (0–100%) — sit under the mode settings and apply to all
four modes alike, because they land *last*: the engine maps colors the way
the mode says, then reshapes what came out.

That ordering is the point. Align rebuilds each color's lightness from the
source, so a brightness applied to its anchors would be thrown away; Theme
would re-snap every color to a different table entry mid-drag. Applied at the
end, one slider means one thing everywhere, and dragging recolors the palette
instead of reshuffling it.

The math is the same set of color matrices CSS filters are defined with
(`hue-rotate`, `saturate`, `sepia`, then a brightness gain), composed into a
single pass that clamps once at the end. But it runs here, on the values: the
file gets real hex and never a `filter()` for something downstream to
resolve. Colors you've unticked are frozen and skip the adjustment entirely.

In Theme mode the selected strip in the rail previews the adjusted table.

## Three ways to read the map

- **Cards** — one card per color, old chip beside new, with the *remap*
  toggle. The default, and the only view that can freeze a color.
- **Ordered** — both palettes sorted by hue family then lightness (neutrals
  trail the wheel) and linked literally. A level arrow means the color kept
  its rank; a raked one means the remap handed its slot to something else,
  and the `↑n` / `↓n` chip says how far it travelled. Hover a row to trace
  its link.
- **Sphere** — hue around the axis, lightness up it, chroma out from it, so
  the poles are black and white and the axis is grey. The cloud tweens from
  the current palette to the new one; scrub it by hand, replay it, or stop
  the spin. Dot size follows how often a color appears.

## Layout

```
server.py            Flask app — static frontend + JSON API
colorlib.py          scanner, color math, the four transforms, the adjust
                     pass, rewriter
palettes.py          the 60 simplify colors, 24 theme tables, CSS named colors
static/index.html    markup
static/css/          tokens.css, app.css
static/js/           colorspace.js (Oklab/OKLCH helpers, mirrors colorlib)
                     views.js      (the Ordered and Sphere renderers)
                     app.js        (state, wiring, the Cards view)
samples/             sample.css — one of everything the scanner reads
```

The consolidator analyzes stylesheet structure once in the browser and keeps
each parameter workbench independent. Hidden workbenches render only when
opened. Long imports yield between chunks so the page remains responsive.

Exports carry a `/* CC Status + Log */` comment — one dated line per exported
parameter recording its tiers, targets, theme knobs, and exempted selectors
(plus a line for color changes and frozen colors). Reopening an exported file
crawls that log and restores the decisions: tier names and targets preload,
exemptions re-apply, and a resume note summarizes what came back. Lines accrue
as history; the latest line per parameter is authoritative. Exemptions are
identified by (parameter, selector) — the value a declaration held when it was
exempted doesn't matter, and editing that value later keeps the exemption.
Re-exporting replaces the generated `ConsoliChrome shared scales` section in
place and appends to the log instead of duplicating either.

The color API caches up to four recent imported documents in local memory:

- `POST /api/documents {content}` → document ID + one color scan
- `POST /api/documents/{id}/map {mode, params, excluded}` → color mapping only
- `POST /api/documents/{id}/export {mapping}` → rewritten stylesheet
- `GET /api/meta` → palettes

Interactive controls never request a complete rewrite. The final stylesheet is
materialized only when its preview, Copy, or Download action needs it. The
original source still lives in the browser tab; the server cache disappears
when the local app stops.

The earlier `/api/scan` and `/api/transform` routes remain available for the
standalone Chromap interface.
