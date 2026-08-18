"use strict";

/* Shared color math for the views — a JS mirror of the Oklab/OKLCH helpers in
 * colorlib.py, so what the sphere and the ordered view sort by is the same
 * space the engine matches in. */

const CS = (() => {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function hexToRgb(hex) {
    let s = String(hex).replace("#", "");
    if (s.length === 3 || s.length === 4) s = [...s].map((c) => c + c).join("");
    return [
      parseInt(s.slice(0, 2), 16) || 0,
      parseInt(s.slice(2, 4), 16) || 0,
      parseInt(s.slice(4, 6), 16) || 0,
    ];
  }

  function rgbToHex(rgb) {
    return "#" + rgb
      .map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, "0"))
      .join("");
  }

  function srgbToLinear(v) {
    v /= 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  }

  function linearToByte(v) {
    v = clamp(v, 0, 1);
    v = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
    return clamp(Math.round(v * 255), 0, 255);
  }

  function rgbToOklab(rgb) {
    const r = srgbToLinear(rgb[0]);
    const g = srgbToLinear(rgb[1]);
    const b = srgbToLinear(rgb[2]);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [
      0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
      1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
      0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    ];
  }

  function oklabToRgb(lab) {
    const [L, A, B] = lab;
    const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
    const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
    const s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3;
    return [
      linearToByte(+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
      linearToByte(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
      linearToByte(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    ];
  }

  /* [L, chroma, hue-in-radians] */
  function rgbToOklch(rgb) {
    const [L, a, b] = rgbToOklab(rgb);
    return [L, Math.hypot(a, b), Math.atan2(b, a)];
  }

  function mixOklab(a, b, t) {
    return [
      a[0] + (b[0] - a[0]) * t,
      a[1] + (b[1] - a[1]) * t,
      a[2] + (b[2] - a[2]) * t,
    ];
  }

  return {
    clamp, hexToRgb, rgbToHex, rgbToOklab, oklabToRgb, rgbToOklch, mixOklab,
    hexToOklch: (hex) => rgbToOklch(hexToRgb(hex)),
    hexToOklab: (hex) => rgbToOklab(hexToRgb(hex)),
  };
})();
