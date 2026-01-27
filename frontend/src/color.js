const shiftHue = (color, degrees) => {
  if (!color) {
    return color;
  }

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const wrapHue = (value) => {
    const wrapped = value % 360;
    return wrapped < 0 ? wrapped + 360 : wrapped;
  };

  const rgbToHsl = (r, g, b) => {
    const rNorm = r / 255;
    const gNorm = g / 255;
    const bNorm = b / 255;
    const max = Math.max(rNorm, gNorm, bNorm);
    const min = Math.min(rNorm, gNorm, bNorm);
    const delta = max - min;
    let h = 0;
    let s = 0;
    const l = (max + min) / 2;

    if (delta !== 0) {
      s = delta / (1 - Math.abs(2 * l - 1));
      switch (max) {
        case rNorm:
          h = ((gNorm - bNorm) / delta) % 6;
          break;
        case gNorm:
          h = (bNorm - rNorm) / delta + 2;
          break;
        default:
          h = (rNorm - gNorm) / delta + 4;
          break;
      }
      h *= 60;
    }

    return { h: wrapHue(h), s, l };
  };

  const hslToRgb = (h, s, l) => {
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const m = l - c / 2;
    let r = 0;
    let g = 0;
    let b = 0;

    if (h < 60) {
      r = c;
      g = x;
    } else if (h < 120) {
      r = x;
      g = c;
    } else if (h < 180) {
      g = c;
      b = x;
    } else if (h < 240) {
      g = x;
      b = c;
    } else if (h < 300) {
      r = x;
      b = c;
    } else {
      r = c;
      b = x;
    }

    return {
      r: Math.round((r + m) * 255),
      g: Math.round((g + m) * 255),
      b: Math.round((b + m) * 255),
    };
  };

  const hexMatch = color.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    let hex = hexMatch[1];
    if (hex.length === 3) {
      hex = hex
        .split("")
        .map((char) => char + char)
        .join("");
    }
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    const { h, s, l } = rgbToHsl(r, g, b);
    const shifted = hslToRgb(wrapHue(h + degrees), s, l);
    return `rgb(${shifted.r}, ${shifted.g}, ${shifted.b})`;
  }

  const rgbMatch = color.match(
    /^rgba?\s*\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})(?:\s*,\s*([\d.]+))?\s*\)$/i
  );
  if (rgbMatch) {
    const r = clamp(Number(rgbMatch[1]), 0, 255);
    const g = clamp(Number(rgbMatch[2]), 0, 255);
    const b = clamp(Number(rgbMatch[3]), 0, 255);
    const existingAlpha = rgbMatch[4];
    const { h, s, l } = rgbToHsl(r, g, b);
    const shifted = hslToRgb(wrapHue(h + degrees), s, l);
    if (existingAlpha !== undefined) {
      const alpha = clamp(Number(existingAlpha), 0, 1);
      return `rgba(${shifted.r}, ${shifted.g}, ${shifted.b}, ${alpha})`;
    }
    return `rgb(${shifted.r}, ${shifted.g}, ${shifted.b})`;
  }

  return color;
};

export { shiftHue };
