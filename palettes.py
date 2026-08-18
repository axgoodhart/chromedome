"""Color data for Chromap: the 60-color simplify set and the 24 theme tables.

All colors are (r, g, b) tuples, 0-255.
"""

import colorsys


def _hx(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
    return (round(r * 255), round(g * 255), round(b * 255))


def _companion_hex(value):
    """Create a coordinated lighter/darker partner for a theme color."""
    r, g, b = _hx(value)
    h, lightness, saturation = colorsys.rgb_to_hls(
        r / 255.0, g / 255.0, b / 255.0)
    lightness += 0.11 if lightness < 0.58 else -0.11
    lightness = max(0.08, min(0.92, lightness))
    if saturation > 0.02:
        saturation = min(1.0, saturation * 0.92 + 0.02)
    rr, gg, bb = colorsys.hls_to_rgb(h, lightness, saturation)
    return "#%02x%02x%02x" % (
        round(rr * 255), round(gg * 255), round(bb * 255))


def _double_theme(values):
    doubled = []
    for value in values:
        doubled.extend((value, _companion_hex(value)))
    return doubled


# ---------------------------------------------------------------------------
# Simplify: 60 colors. 12 hues x 4 variants (vivid / light / dark / soft)
# plus a 12-step neutral ramp.
# ---------------------------------------------------------------------------

_HUES = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]

SIMPLIFY_60 = []
for _h in _HUES:
    SIMPLIFY_60.append(_hsl(_h, 90, 50))   # vivid
    SIMPLIFY_60.append(_hsl(_h, 85, 75))   # light
    SIMPLIFY_60.append(_hsl(_h, 80, 30))   # dark
    SIMPLIFY_60.append(_hsl(_h, 30, 55))   # soft
for _i in range(12):                        # neutrals, black -> white
    _v = round(_i * 255 / 11)
    SIMPLIFY_60.append((_v, _v, _v))

assert len(SIMPLIFY_60) == 60


# ---------------------------------------------------------------------------
# 24 theme tables.
# ---------------------------------------------------------------------------

THEMES = {
    "nord": ["#2e3440", "#3b4252", "#434c5e", "#4c566a", "#d8dee9", "#e5e9f0",
             "#eceff4", "#8fbcbb", "#88c0d0", "#81a1c1", "#5e81ac", "#bf616a",
             "#d08770", "#ebcb8b", "#a3be8c", "#b48ead"],
    "dracula": ["#282a36", "#44475a", "#f8f8f2", "#6272a4", "#8be9fd",
                "#50fa7b", "#ffb86c", "#ff79c6", "#bd93f9", "#ff5555",
                "#f1fa8c"],
    "solarized-light": ["#fdf6e3", "#eee8d5", "#93a1a1", "#839496", "#657b83",
                        "#586e75", "#b58900", "#cb4b16", "#dc322f", "#d33682",
                        "#6c71c4", "#268bd2", "#2aa198", "#859900"],
    "solarized-dark": ["#002b36", "#073642", "#586e75", "#657b83", "#839496",
                       "#93a1a1", "#b58900", "#cb4b16", "#dc322f", "#d33682",
                       "#6c71c4", "#268bd2", "#2aa198", "#859900"],
    "gruvbox": ["#282828", "#cc241d", "#98971a", "#d79921", "#458588",
                "#b16286", "#689d6a", "#a89984", "#ebdbb2", "#fb4934",
                "#b8bb26", "#fabd2f", "#83a598", "#d3869b", "#8ec07c",
                "#fbf1c7"],
    "monokai": ["#272822", "#f92672", "#a6e22e", "#f4bf75", "#66d9ef",
                "#ae81ff", "#a1efe4", "#f8f8f2", "#75715e", "#fd971f"],
    "catppuccin": ["#1e1e2e", "#cdd6f4", "#f5e0dc", "#f5c2e7", "#cba6f7",
                   "#f38ba8", "#fab387", "#f9e2af", "#a6e3a1", "#94e2d5",
                   "#89dceb", "#89b4fa", "#b4befe"],
    "tokyo-night": ["#1a1b26", "#c0caf5", "#7aa2f7", "#bb9af7", "#7dcfff",
                    "#2ac3de", "#b4f9f8", "#9ece6a", "#e0af68", "#f7768e",
                    "#414868"],
    "one-dark": ["#282c34", "#abb2bf", "#e06c75", "#98c379", "#e5c07b",
                 "#61afef", "#c678dd", "#56b6c2", "#5c6370"],
    "rose-pine": ["#191724", "#e0def4", "#eb6f92", "#f6c177", "#ebbcba",
                  "#31748f", "#9ccfd8", "#c4a7e7", "#6e6a86", "#26233a"],
    "everforest": ["#2d353b", "#d3c6aa", "#e67e80", "#a7c080", "#dbbc7f",
                   "#7fbbb3", "#d699b6", "#83c092", "#859289", "#e69875"],
    "grayscale": ["#111111", "#2b2b2b", "#454545", "#5f5f5f", "#7a7a7a",
                  "#969696", "#b3b3b3", "#d1d1d1", "#f0f0f0"],
    "sepia": ["#3e2b16", "#704214", "#8a5a2b", "#a0764a", "#b8926a",
              "#d0ae8b", "#e8caad", "#f6e7d3"],
    "pastel": ["#ffd1dc", "#ffe4b5", "#fdfd96", "#c1f0c1", "#aec6cf",
               "#c3b1e1", "#f4c2c2", "#b2e2e2"],
    "neon": ["#ff2079", "#04d9ff", "#39ff14", "#ffe700", "#ff6ec7",
             "#7df9ff", "#fe00fe", "#00ff9f", "#0d0221"],
    "ocean": ["#012a4a", "#013a63", "#01497c", "#2a6f97", "#468faf",
              "#61a5c2", "#89c2d9", "#a9d6e5"],
    "forest": ["#081c15", "#1b4332", "#2d6a4f", "#40916c", "#52b788",
               "#74c69d", "#95d5b2", "#d8f3dc"],
    "sunset": ["#f72585", "#b5179e", "#7209b7", "#560bad", "#3a0ca3",
               "#ff6d00", "#ff9e00", "#ffd166"],
    "earth": ["#582f0e", "#7f4f24", "#936639", "#a68a64", "#b6ad90",
              "#c2c5aa", "#a4ac86", "#656d4a", "#414833", "#333d29"],
    "candy": ["#ff70a6", "#ff9770", "#ffd670", "#e9ff70", "#70d6ff",
              "#ff70e5", "#fff0f5", "#8338ec"],
    "cyberpunk": ["#0d0221", "#241734", "#2e2157", "#fd3777", "#f706cf",
                  "#fd1d53", "#00fff9", "#defe47"],
    "autumn": ["#6a040f", "#9d0208", "#d00000", "#dc2f02", "#e85d04",
               "#f48c06", "#faa307", "#ffba08"],
    "spring": ["#d8e2dc", "#ffe5d9", "#ffcad4", "#f4acb7", "#9d8189",
               "#b7e4c7", "#95d5b2", "#74c69d"],
    "coffee": ["#ede0d4", "#e6ccb2", "#ddb892", "#b08968", "#7f5539",
               "#9c6644", "#3f2e1e", "#c9a227"],
}

THEME_LABELS = {
    "nord": "Nord", "dracula": "Dracula", "solarized-light": "Solarized Light",
    "solarized-dark": "Solarized Dark", "gruvbox": "Gruvbox",
    "monokai": "Monokai", "catppuccin": "Catppuccin", "tokyo-night":
    "Tokyo Night", "one-dark": "One Dark", "rose-pine": "Rosé Pine",
    "everforest": "Everforest", "grayscale": "Grayscale", "sepia": "Sepia",
    "pastel": "Pastel", "neon": "Neon", "ocean": "Ocean", "forest": "Forest",
    "sunset": "Sunset", "earth": "Earth", "candy": "Candy",
    "cyberpunk": "Cyberpunk", "autumn": "Autumn", "spring": "Spring",
    "coffee": "Coffee",
}

_BASE_THEME_SIZES = {k: len(v) for k, v in THEMES.items()}
THEMES = {k: [_hx(c) for c in _double_theme(v)]
          for k, v in THEMES.items()}

assert len(THEMES) == 24
assert all(len(THEMES[k]) == size * 2
           for k, size in _BASE_THEME_SIZES.items())


# ---------------------------------------------------------------------------
# CSS named colors (the 147 standard names; grey spellings included for
# parsing, but the reverse map prefers the "gray" spellings).
# ---------------------------------------------------------------------------

CSS_NAMED = {
    "aliceblue": "#f0f8ff", "antiquewhite": "#faebd7", "aqua": "#00ffff",
    "aquamarine": "#7fffd4", "azure": "#f0ffff", "beige": "#f5f5dc",
    "bisque": "#ffe4c4", "black": "#000000", "blanchedalmond": "#ffebcd",
    "blue": "#0000ff", "blueviolet": "#8a2be2", "brown": "#a52a2a",
    "burlywood": "#deb887", "cadetblue": "#5f9ea0", "chartreuse": "#7fff00",
    "chocolate": "#d2691e", "coral": "#ff7f50", "cornflowerblue": "#6495ed",
    "cornsilk": "#fff8dc", "crimson": "#dc143c", "cyan": "#00ffff",
    "darkblue": "#00008b", "darkcyan": "#008b8b", "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9", "darkgreen": "#006400", "darkgrey": "#a9a9a9",
    "darkkhaki": "#bdb76b", "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f", "darkorange": "#ff8c00",
    "darkorchid": "#9932cc", "darkred": "#8b0000", "darksalmon": "#e9967a",
    "darkseagreen": "#8fbc8f", "darkslateblue": "#483d8b",
    "darkslategray": "#2f4f4f", "darkslategrey": "#2f4f4f",
    "darkturquoise": "#00ced1", "darkviolet": "#9400d3",
    "deeppink": "#ff1493", "deepskyblue": "#00bfff", "dimgray": "#696969",
    "dimgrey": "#696969", "dodgerblue": "#1e90ff", "firebrick": "#b22222",
    "floralwhite": "#fffaf0", "forestgreen": "#228b22", "fuchsia": "#ff00ff",
    "gainsboro": "#dcdcdc", "ghostwhite": "#f8f8ff", "gold": "#ffd700",
    "goldenrod": "#daa520", "gray": "#808080", "green": "#008000",
    "greenyellow": "#adff2f", "grey": "#808080", "honeydew": "#f0fff0",
    "hotpink": "#ff69b4", "indianred": "#cd5c5c", "indigo": "#4b0082",
    "ivory": "#fffff0", "khaki": "#f0e68c", "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5", "lawngreen": "#7cfc00",
    "lemonchiffon": "#fffacd", "lightblue": "#add8e6", "lightcoral": "#f08080",
    "lightcyan": "#e0ffff", "lightgoldenrodyellow": "#fafad2",
    "lightgray": "#d3d3d3", "lightgreen": "#90ee90", "lightgrey": "#d3d3d3",
    "lightpink": "#ffb6c1", "lightsalmon": "#ffa07a",
    "lightseagreen": "#20b2aa", "lightskyblue": "#87cefa",
    "lightslategray": "#778899", "lightslategrey": "#778899",
    "lightsteelblue": "#b0c4de", "lightyellow": "#ffffe0", "lime": "#00ff00",
    "limegreen": "#32cd32", "linen": "#faf0e6", "magenta": "#ff00ff",
    "maroon": "#800000", "mediumaquamarine": "#66cdaa",
    "mediumblue": "#0000cd", "mediumorchid": "#ba55d3",
    "mediumpurple": "#9370db", "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee", "mediumspringgreen": "#00fa9a",
    "mediumturquoise": "#48d1cc", "mediumvioletred": "#c71585",
    "midnightblue": "#191970", "mintcream": "#f5fffa", "mistyrose": "#ffe4e1",
    "moccasin": "#ffe4b5", "navajowhite": "#ffdead", "navy": "#000080",
    "oldlace": "#fdf5e6", "olive": "#808000", "olivedrab": "#6b8e23",
    "orange": "#ffa500", "orangered": "#ff4500", "orchid": "#da70d6",
    "palegoldenrod": "#eee8aa", "palegreen": "#98fb98",
    "paleturquoise": "#afeeee", "palevioletred": "#db7093",
    "papayawhip": "#ffefd5", "peachpuff": "#ffdab9", "peru": "#cd853f",
    "pink": "#ffc0cb", "plum": "#dda0dd", "powderblue": "#b0e0e6",
    "purple": "#800080", "rebeccapurple": "#663399", "red": "#ff0000",
    "rosybrown": "#bc8f8f", "royalblue": "#4169e1", "saddlebrown": "#8b4513",
    "salmon": "#fa8072", "sandybrown": "#f4a460", "seagreen": "#2e8b57",
    "seashell": "#fff5ee", "sienna": "#a0522d", "silver": "#c0c0c0",
    "skyblue": "#87ceeb", "slateblue": "#6a5acd", "slategray": "#708090",
    "slategrey": "#708090", "snow": "#fffafa", "springgreen": "#00ff7f",
    "steelblue": "#4682b4", "tan": "#d2b48c", "teal": "#008080",
    "thistle": "#d8bfd8", "tomato": "#ff6347", "turquoise": "#40e0d0",
    "violet": "#ee82ee", "wheat": "#f5deb3", "white": "#ffffff",
    "whitesmoke": "#f5f5f5", "yellow": "#ffff00", "yellowgreen": "#9acd32",
}

NAMED_RGB = {name: _hx(hexval) for name, hexval in CSS_NAMED.items()}

# Reverse lookup for writing a named color back out. "grey" spellings and
# duplicate values (aqua/cyan, fuchsia/magenta) collapse to one canonical name.
RGB_TO_NAME = {}
for _name, _rgb in NAMED_RGB.items():
    if "grey" in _name:
        continue
    RGB_TO_NAME.setdefault(_rgb, _name)
