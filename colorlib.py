"""Chromap color engine.

Scans text for color literals (hex, rgb()/rgba(), hsl()/hsla(), CSS named
colors, RTF \\red\\green\\blue runs), builds the color map, and rewrites the
text under one of four transform modes: simplify, align, shuffle, theme.

Every literal keeps its original notation on the way back out — an hsl()
stays an hsl(), a named color becomes a name again when the new value has
one (hex otherwise), and alpha channels ride along untouched.
"""

import colorsys
import math
import random
import re
from functools import lru_cache

from palettes import NAMED_RGB, RGB_TO_NAME, SIMPLIFY_60, THEMES

# --- tokenizer -------------------------------------------------------------

_NAMED_ALT = "|".join(sorted(NAMED_RGB, key=len, reverse=True))

TOKEN_RE = re.compile(
    r"""
    (?P<hex>\#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3}))
        (?![0-9a-fA-F])
  | (?P<func>(?:rgba?|hsla?)\(\s*[^)]*?\))
  | (?P<rtf>\\red(?P<rr>\d{1,3})\\green(?P<rg>\d{1,3})\\blue(?P<rb>\d{1,3}))
  | (?<![\w#.&-])(?P<named>""" + _NAMED_ALT + r""")(?![\w-])
    """,
    re.VERBOSE | re.IGNORECASE,
)

_NUM = r"[-+]?\d*\.?\d+"
FUNC_BODY_RE = re.compile(
    r"(?P<fn>rgba?|hsla?)\(\s*"
    r"(?P<a>" + _NUM + r")(?P<au>%|deg)?\s*[,\s]\s*"
    r"(?P<b>" + _NUM + r")(?P<bu>%)?\s*[,\s]\s*"
    r"(?P<c>" + _NUM + r")(?P<cu>%)?"
    r"(?:\s*[,/]\s*(?P<alpha>" + _NUM + r")(?P<alphau>%)?)?\s*\)",
    re.IGNORECASE,
)


def _clamp(v, lo=0, hi=255):
    return max(lo, min(hi, v))


def _hex_to_rgba(token):
    s = token.lstrip("#")
    if len(s) in (3, 4):
        s = "".join(ch * 2 for ch in s)
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    a = int(s[6:8], 16) / 255.0 if len(s) == 8 else None
    return (r, g, b), a


def _func_to_rgba(token):
    m = FUNC_BODY_RE.fullmatch(token.strip())
    if not m:
        return None
    fn = m.group("fn").lower()
    a, b, c = float(m.group("a")), float(m.group("b")), float(m.group("c"))
    alpha = None
    if m.group("alpha") is not None:
        alpha = float(m.group("alpha"))
        if m.group("alphau") == "%":
            alpha /= 100.0
        alpha = max(0.0, min(1.0, alpha))
    if fn.startswith("rgb"):
        if m.group("au") == "%":
            a, b, c = a * 2.55, b * 2.55, c * 2.55
        rgb = tuple(_clamp(round(v)) for v in (a, b, c))
    else:
        h = (a % 360) / 360.0
        s = max(0.0, min(1.0, b / 100.0))
        l = max(0.0, min(1.0, c / 100.0))
        r, g, bl = colorsys.hls_to_rgb(h, l, s)
        rgb = (round(r * 255), round(g * 255), round(bl * 255))
    return rgb, alpha


def parse_token(match):
    """Return (rgb, alpha_or_None, format) for a TOKEN_RE match, or None."""
    if match.group("hex"):
        rgb, a = _hex_to_rgba(match.group("hex"))
        return rgb, a, "hex"
    if match.group("func"):
        parsed = _func_to_rgba(match.group("func"))
        if parsed is None:
            return None
        rgb, a = parsed
        fn = match.group("func").split("(")[0].lower()
        return rgb, a, fn
    if match.group("rtf"):
        vals = (match.group("rr"), match.group("rg"), match.group("rb"))
        if any(int(v) > 255 for v in vals):
            return None
        return tuple(int(v) for v in vals), None, "rtf"
    if match.group("named"):
        return NAMED_RGB[match.group("named").lower()], None, "named"
    return None


# --- the magical map --------------------------------------------------------

def scan(content):
    """Build the color map: one entry per distinct RGB value found.

    Returns a list of dicts sorted by count desc:
      {key, hex, count, literals: [{text, format, count}]}
    """
    entries = {}
    for m in TOKEN_RE.finditer(content):
        parsed = parse_token(m)
        if parsed is None:
            continue
        rgb, _alpha, fmt = parsed
        key = "%d,%d,%d" % rgb
        entry = entries.setdefault(
            key, {"key": key, "hex": rgb_to_hex(rgb), "count": 0,
                  "literals": {}})
        entry["count"] += 1
        lit = entry["literals"].setdefault(
            m.group(0), {"text": m.group(0), "format": fmt, "count": 0})
        lit["count"] += 1
    result = []
    for entry in entries.values():
        entry["literals"] = sorted(entry["literals"].values(),
                                   key=lambda l: -l["count"])
        result.append(entry)
    result.sort(key=lambda e: -e["count"])
    return result


# --- color math -------------------------------------------------------------

def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def is_six_digit_hex(value):
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value))


def _srgb_to_linear(v):
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _linear_to_srgb_byte(v):
    v = max(0.0, min(1.0, v))
    v = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return _clamp(round(v * 255))


@lru_cache(maxsize=8192)
def rgb_to_oklab(rgb):
    r, g, b = (_srgb_to_linear(v) for v in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _oklab_to_linear(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _in_gamut(lin):
    return all(-1e-6 <= v <= 1 + 1e-6 for v in lin)


def oklch_to_rgb(L, C, H):
    """OKLCH -> sRGB. Out-of-gamut colors keep L and H; C shrinks to fit."""
    L = max(0.0, min(1.0, L))
    lin = _oklab_to_linear(L, C * math.cos(H), C * math.sin(H))
    if not _in_gamut(lin):
        lo, hi = 0.0, C
        for _ in range(22):
            mid = (lo + hi) / 2
            mid_lin = _oklab_to_linear(L, mid * math.cos(H),
                                       mid * math.sin(H))
            if _in_gamut(mid_lin):
                lo = mid
            else:
                hi = mid
        lin = _oklab_to_linear(L, lo * math.cos(H), lo * math.sin(H))
    return tuple(_linear_to_srgb_byte(v) for v in lin)


def nearest(rgb, table, l_weight=1.8):
    """Perceptual nearest match in Oklab. Lightness is weighted extra so a
    document's light/dark structure survives the remap."""
    o = rgb_to_oklab(tuple(rgb))

    def dist(t):
        tl = rgb_to_oklab(tuple(t))
        return ((l_weight * (o[0] - tl[0])) ** 2
                + (o[1] - tl[1]) ** 2 + (o[2] - tl[2]) ** 2)

    return min(table, key=dist)


_PRIMARIES = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
# The farthest any color sits from its nearest pure primary (white).
_MAX_PRIMARY_DIST = math.sqrt(2) * 255


def primary_distance(rgb):
    """0.0 at a pure primary, 1.0 at white — plain Euclidean on purpose."""
    d = min(math.dist(rgb, p) for p in _PRIMARIES)
    return d / _MAX_PRIMARY_DIST


# Drift poles in OKLCH hue: warm ~ red-orange, cool ~ cobalt blue.
_WARM_POLE = math.radians(40.0)
_COOL_POLE = math.radians(262.0)


def _rotate_toward(h, pole, max_step):
    delta = (pole - h + math.pi) % (2 * math.pi) - math.pi
    return h + max(-max_step, min(max_step, delta))


def _percent(params, field, default=0):
    try:
        value = float(params.get(field, default))
    except (TypeError, ValueError):
        raise ValueError("%s must be a percentage from 0 to 100" % field)
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("%s must be a percentage from 0 to 100" % field)
    return value / 100.0


# --- table adjustment -------------------------------------------------------
#
# Hue / saturation / brightness / sepia use the same color matrices CSS
# filters are defined with, but they run here and land in the file as real
# values -- nothing downstream ever sees a filter() to resolve.

_LUMA = (0.213, 0.715, 0.072)
_IDENTITY_M = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
_SEPIA_M = ((0.393, 0.769, 0.189),
            (0.349, 0.686, 0.168),
            (0.272, 0.534, 0.131))

ADJUST_FIELDS = {           # field: (default, low, high)
    "hue": (0.0, -180.0, 180.0),
    "saturation": (100.0, 0.0, 200.0),
    "brightness": (100.0, 0.0, 200.0),
    "contrast": (100.0, 0.0, 200.0),
    "sepia": (0.0, 0.0, 100.0),
}

_MID = 127.5                # contrast pivot, per the filter spec's 0.5


def _mat_mul(a, b):
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _saturate_matrix(s):
    return tuple(
        tuple(_LUMA[j] + s * ((1.0 if i == j else 0.0) - _LUMA[j])
              for j in range(3))
        for i in range(3)
    )


def _hue_rotate_matrix(degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return (
        (0.213 + c * 0.787 - s * 0.213,
         0.715 - c * 0.715 - s * 0.715,
         0.072 - c * 0.072 + s * 0.928),
        (0.213 - c * 0.213 + s * 0.143,
         0.715 + c * 0.285 + s * 0.140,
         0.072 - c * 0.072 - s * 0.283),
        (0.213 - c * 0.213 - s * 0.787,
         0.715 - c * 0.715 + s * 0.715,
         0.072 + c * 0.928 + s * 0.072),
    )


def _sepia_matrix(amount):
    return tuple(
        tuple(_IDENTITY_M[i][j]
              + (_SEPIA_M[i][j] - _IDENTITY_M[i][j]) * amount
              for j in range(3))
        for i in range(3)
    )


def adjust_params(params):
    """Read and range-check the four table sliders."""
    raw = params.get("adjust") or {}
    if not isinstance(raw, dict):
        raise ValueError("adjust must be an object of slider values")
    out = {}
    for field, (default, lo, hi) in ADJUST_FIELDS.items():
        try:
            value = float(raw.get(field, default))
        except (TypeError, ValueError):
            raise ValueError("%s must be a number from %g to %g"
                             % (field, lo, hi))
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError("%s must be a number from %g to %g"
                             % (field, lo, hi))
        out[field] = value
    return out


def is_neutral_adjust(adjust):
    return all(adjust[f] == default
               for f, (default, _lo, _hi) in ADJUST_FIELDS.items())


def adjust_table(table, adjust):
    """Bake the sliders into a run of RGB values.

    Order is hue-rotate, saturate, sepia, then brightness and contrast --
    sepia late so it reads as a single tone knob, and the two tonal knobs
    last so they always bite. The three matrices compose into one pass and
    nothing clamps until the very end, so a channel that overshoots
    mid-chain can still come back instead of clipping early.
    """
    if is_neutral_adjust(adjust):
        return list(table)

    m = _hue_rotate_matrix(adjust["hue"])
    m = _mat_mul(_saturate_matrix(adjust["saturation"] / 100.0), m)
    m = _mat_mul(_sepia_matrix(adjust["sepia"] / 100.0), m)
    gain = adjust["brightness"] / 100.0
    slope = adjust["contrast"] / 100.0

    out = []
    for rgb in table:
        channels = []
        for i in range(3):
            v = (m[i][0] * rgb[0] + m[i][1] * rgb[1] + m[i][2] * rgb[2]) * gain
            channels.append(_clamp(round((v - _MID) * slope + _MID)))
        out.append(tuple(channels))
    return out


def resolve_theme_table(params):
    """The theme's table, resolved but not yet adjusted.

    Matching runs against this, unadjusted, so dragging a slider recolors the
    palette instead of reshuffling which entry each source snaps to.
    """
    theme = params.get("theme", "")
    if theme == "custom":
        colors = params.get("colors")
        if not isinstance(colors, list) or not 2 <= len(colors) <= 64:
            raise ValueError("A custom theme needs 2 to 64 colors")
        table = []
        for value in colors:
            if (not isinstance(value, str)
                    or not re.fullmatch(r"#[0-9a-fA-F]{6}", value)):
                raise ValueError(
                    "Custom theme colors must use six-digit hex values")
            table.append(_hex_to_rgba(value)[0])
    else:
        table = THEMES.get(theme)
    if not table:
        raise ValueError("Unknown theme %r" % theme)
    return table


def theme_preview_table(params):
    """The theme table as the rail strip should show it: resolved + adjusted."""
    return adjust_table(resolve_theme_table(params), adjust_params(params))


def _diversify(original, target, drift, deviation):
    """Retain source hue and tone differences around a mapped target."""
    if drift == 0 and deviation == 0:
        return target

    source_L, source_a, source_b = rgb_to_oklab(tuple(original))
    target_L, target_a, target_b = rgb_to_oklab(tuple(target))
    source_C = math.hypot(source_a, source_b)
    target_C = math.hypot(target_a, target_b)
    source_H = math.atan2(source_b, source_a)
    target_H = math.atan2(target_b, target_a)

    if source_C < 0.0001:
        source_H = target_H
    elif target_C < 0.0001:
        target_H = source_H

    hue_delta = (source_H - target_H + math.pi) % (2 * math.pi) - math.pi
    H = target_H + hue_delta * drift
    L = target_L + (source_L - target_L) * deviation
    C = target_C + (source_C - target_C) * deviation
    return oklch_to_rgb(L, C, H)


def _diversity_params(params):
    return (_percent(params, "drift"), _percent(params, "deviation"))


def _align_one(rgb, targets, threshold, direction):
    """Take the nearest anchor's hue and chroma, keep the original color's
    lightness, then drift by primary-distance x threshold. Anchors are
    picked hue-first (lightness barely counts) since L is preserved anyway."""
    target = nearest(rgb, targets, l_weight=0.3)
    L = rgb_to_oklab(tuple(rgb))[0]
    _tL, ta, tb = rgb_to_oklab(tuple(target))
    C = math.hypot(ta, tb)
    H = math.atan2(tb, ta)
    dev = primary_distance(rgb) * (float(threshold) / 100.0)
    if direction == "warmer":
        H = _rotate_toward(H, _WARM_POLE, dev * math.radians(90))
    elif direction == "cooler":
        H = _rotate_toward(H, _COOL_POLE, dev * math.radians(90))
    elif direction == "lighter":
        L = min(1.0, L + dev * 0.35)
    else:  # darker
        L = max(0.0, L - dev * 0.35)
    return oklch_to_rgb(L, C, H)


def _random_color(rng, base_rgb):
    """Random hue and chroma at the base color's own lightness."""
    L = rgb_to_oklab(tuple(base_rgb))[0]
    H = rng.uniform(0.0, 2 * math.pi)
    C = rng.uniform(0.05, 0.24)
    return oklch_to_rgb(L, C, H)


def build_mapping(entries, mode, params, excluded=()):
    """Map each entry key -> new (r, g, b). Excluded keys map to themselves."""
    excluded = set(excluded)
    keys = [e["key"] for e in entries if e["key"] not in excluded]
    rgbs = {k: tuple(int(v) for v in k.split(",")) for k in keys}
    mapping = {}

    if mode == "original":
        # No remap at all -- every color maps to itself, leaving the adjust
        # pass below as the only thing acting on the palette.
        for k in keys:
            mapping[k] = rgbs[k]

    elif mode == "simplify":
        drift, deviation = _diversity_params(params)
        for k in keys:
            target = nearest(rgbs[k], SIMPLIFY_60)
            mapping[k] = _diversify(
                rgbs[k], target, drift, deviation)

    elif mode == "theme":
        table = resolve_theme_table(params)
        drift, deviation = _diversity_params(params)
        for k in keys:
            target = nearest(rgbs[k], table)
            mapping[k] = _diversify(
                rgbs[k], target, drift, deviation)

    elif mode == "align":
        targets = []
        colors = params.get("colors")
        if colors is None:
            colors = [params.get(field)
                      for field in ("color1", "color2", "color3", "color4")]
        if not isinstance(colors, list) or len(colors) > 4:
            raise ValueError("Align accepts up to four anchor colors")
        for v in colors:
            if v:
                if (not isinstance(v, str)
                        or not re.fullmatch(r"#[0-9a-fA-F]{6}", v)):
                    raise ValueError(
                        "Anchor colors must use six-digit hex values")
                (rgb, _a) = _hex_to_rgba(v)
                targets.append(rgb)
        if not targets:
            raise ValueError("Align needs at least one target color")
        threshold = _percent(params, "threshold", 40) * 100
        direction = params.get("direction", "warmer")
        if direction not in ("warmer", "cooler", "lighter", "darker"):
            raise ValueError("Unknown direction %r" % direction)
        for k in keys:
            mapping[k] = _align_one(rgbs[k], targets, threshold, direction)

    elif mode == "shuffle":
        rng = random.Random(params.get("seed", 0))
        drift, deviation = _diversity_params(params)
        if params.get("variant", "permute") == "permute":
            shuffled = list(keys)
            rng.shuffle(shuffled)
            for k, other in zip(keys, shuffled):
                mapping[k] = _diversify(
                    rgbs[k], rgbs[other], drift, deviation)
        else:
            for k in keys:
                target = _random_color(rng, rgbs[k])
                mapping[k] = _diversify(
                    rgbs[k], target, drift, deviation)

    else:
        raise ValueError("Unknown mode %r" % mode)

    # The sliders land last, on whatever the mode produced. Doing it here
    # rather than on each mode's target table is what makes them mean the
    # same thing everywhere -- Align in particular rebuilds lightness from
    # the source color, so a brightness applied to its anchors would vanish.
    # Excluded keys never enter `mapping`, so frozen colors stay untouched.
    keys_out = list(mapping)
    adjusted = adjust_table([mapping[k] for k in keys_out], adjust_params(params))
    return dict(zip(keys_out, adjusted))


# --- rewriting --------------------------------------------------------------

def _fmt_hsl(fn, rgb, alpha):
    h, l, s = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    h, s, l = round(h * 360), round(s * 100), round(l * 100)
    if alpha is not None:
        return "%s(%d, %d%%, %d%%, %s)" % (fn if fn.endswith("a") else fn + "a",
                                           h, s, l, _fmt_alpha(alpha))
    return "%s(%d, %d%%, %d%%)" % ("hsl", h, s, l)


def _fmt_alpha(alpha):
    s = ("%.3f" % alpha).rstrip("0").rstrip(".")
    return s or "0"


def format_like(original_fmt, rgb, alpha):
    """Render rgb in the same notation the original literal used."""
    if original_fmt == "hex":
        if alpha is not None:
            return rgb_to_hex(rgb) + "%02x" % round(alpha * 255)
        return rgb_to_hex(rgb)
    if original_fmt in ("rgb", "rgba"):
        if alpha is not None:
            return "rgba(%d, %d, %d, %s)" % (*rgb, _fmt_alpha(alpha))
        return "rgb(%d, %d, %d)" % rgb
    if original_fmt in ("hsl", "hsla"):
        return _fmt_hsl(original_fmt, rgb, alpha)
    if original_fmt == "rtf":
        return "\\red%d\\green%d\\blue%d" % rgb
    if original_fmt == "named":
        return RGB_TO_NAME.get(rgb, rgb_to_hex(rgb))
    return rgb_to_hex(rgb)


def rewrite(content, mapping):
    """Replace every mapped literal, preserving notation and alpha.

    A literal whose color did not actually move is left byte-for-byte alone
    rather than re-emitted, so `#fff` stays `#fff` and a no-op remap returns
    the file untouched.
    """
    def _sub(m):
        parsed = parse_token(m)
        if parsed is None:
            return m.group(0)
        rgb, alpha, fmt = parsed
        key = "%d,%d,%d" % rgb
        if key not in mapping or tuple(mapping[key]) == tuple(rgb):
            return m.group(0)
        return format_like(fmt, mapping[key], alpha)

    return TOKEN_RE.sub(_sub, content)


def rewrite_annotated(content, mapping, limit=200_000):
    """Like rewrite(), but returns HTML: escaped text with each rewritten
    literal wrapped in <mark> carrying its new color. Truncates at `limit`
    source characters; returns (html, truncated)."""
    import html as _html

    truncated = len(content) > limit
    src = content[:limit]
    parts = []
    pos = 0
    for m in TOKEN_RE.finditer(src):
        parsed = parse_token(m)
        if parsed is None:
            continue
        rgb, alpha, fmt = parsed
        key = "%d,%d,%d" % rgb
        if key not in mapping or tuple(mapping[key]) == tuple(rgb):
            continue          # unchanged literals are not highlights
        new_rgb = mapping[key]
        parts.append(_html.escape(src[pos:m.start()]))
        parts.append('<mark style="--c:%s">%s</mark>' % (
            rgb_to_hex(new_rgb),
            _html.escape(format_like(fmt, new_rgb, alpha))))
        pos = m.end()
    parts.append(_html.escape(src[pos:]))
    return "".join(parts), truncated


def transform(content, mode, params, excluded=()):
    """Scan + map + rewrite. Returns (mapping_rows, new_content, info)."""
    entries = scan(content)
    mapping = build_mapping(entries, mode, params, excluded)
    rows = []
    for e in entries:
        if e["key"] not in mapping:
            continue
        new_rgb = mapping[e["key"]]
        rows.append({
            "key": e["key"],
            "fromHex": e["hex"],
            "toHex": rgb_to_hex(new_rgb),
            "count": e["count"],
        })
    info = {}
    if mode == "theme":
        info["themeTable"] = [rgb_to_hex(c)
                              for c in theme_preview_table(params)]
    return rows, rewrite(content, mapping), info
