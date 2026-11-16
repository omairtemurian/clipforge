/**
 * WCAG 2 contrast of CSS colors as written in index.css: `#rrggbb`,
 * `rgb(r g b / a%)` and `oklch(L C H / a%)`. Translucent colors are laid
 * over the color behind them first.
 */

export interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

function alpha(text: string | undefined): number {
  if (text === undefined) return 1;
  return text.endsWith("%") ? Number(text.slice(0, -1)) / 100 : Number(text);
}

/** sRGB (0-1 channels) of an OKLCH color (Björn Ottosson's matrices). */
function oklchToRgb(l: number, c: number, h: number): [number, number, number] {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr);
  const b = c * Math.sin(hr);
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const linear = [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
  return linear.map((v) => {
    const x = Math.min(1, Math.max(0, v));
    return x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055;
  }) as [number, number, number];
}

/** Parse one color; throws on a format index.css does not use. */
export function parseColor(text: string): Rgba {
  const value = text.trim();
  const hex = /^#([0-9a-f]{6})$/i.exec(value);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return {
      r: (n >> 16) / 255,
      g: ((n >> 8) & 255) / 255,
      b: (n & 255) / 255,
      a: 1,
    };
  }
  const rgb = /^rgb\((\d+) (\d+) (\d+)(?: \/ ([\d.]+%?))?\)$/.exec(value);
  if (rgb) {
    return {
      r: Number(rgb[1]) / 255,
      g: Number(rgb[2]) / 255,
      b: Number(rgb[3]) / 255,
      a: alpha(rgb[4]),
    };
  }
  const lch = /^oklch\(([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+%?))?\)$/.exec(
    value,
  );
  if (lch) {
    const [r, g, b] = oklchToRgb(
      Number(lch[1]),
      Number(lch[2]),
      Number(lch[3]),
    );
    return { r, g, b, a: alpha(lch[4]) };
  }
  throw new Error(`Unsupported color: ${text}`);
}

/** `top` laid over the opaque `bottom`. */
export function over(top: Rgba, bottom: Rgba): Rgba {
  const mix = (t: number, b: number) => t * top.a + b * (1 - top.a);
  return {
    r: mix(top.r, bottom.r),
    g: mix(top.g, bottom.g),
    b: mix(top.b, bottom.b),
    a: 1,
  };
}

function luminance({ r, g, b }: Rgba): number {
  const lin = (c: number) =>
    c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** The WCAG contrast ratio (1 to 21) of two opaque colors. */
export function contrast(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `#rrggbb` of an opaque color. */
export function toHex({ r, g, b }: Rgba): string {
  const byte = (c: number) =>
    Math.round(c * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${byte(r)}${byte(g)}${byte(b)}`;
}
