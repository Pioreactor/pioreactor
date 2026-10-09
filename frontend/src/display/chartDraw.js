import { lighten } from "@mui/material/styles";

// Canvas line chart. Canvas keeps redraw cost flat no matter how many points
// there are, which matters far more on a Pi + WPE than SVG chart libraries do.

// Layout in CSS pixels at a 16px root size; scaled with the root font size.
const BASE_PAD = { left: 52, right: 12, top: 10, bottom: 26 };

function niceStep(range, target) {
  const raw = range / Math.max(1, target);
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const nice = fraction < 1.5 ? 1 : fraction < 3 ? 2 : fraction < 7 ? 5 : 10;
  return nice * power;
}

function ticks(min, max, target) {
  if (!(max > min)) return [min];
  const step = niceStep(max - min, target);
  const result = [];
  for (let value = Math.ceil(min / step) * step; value <= max + step * 1e-9; value += step) {
    result.push(Number(value.toPrecision(12)));
  }
  return result;
}

export function computeDomain(seriesList, hidden, domainHint) {
  let xMin = Infinity;
  let xMax = -Infinity;
  let yMin = Infinity;
  let yMax = -Infinity;
  for (const series of seriesList) {
    if (hidden.has(series.name)) continue;
    for (const point of series.points) {
      if (point.x < xMin) xMin = point.x;
      if (point.x > xMax) xMax = point.x;
      if (point.y < yMin) yMin = point.y;
      if (point.y > yMax) yMax = point.y;
    }
  }
  if (!Number.isFinite(xMin)) return null;
  if (domainHint && domainHint.length === 2) {
    yMin = Math.min(yMin, domainHint[0]);
    yMax = Math.max(yMax, domainHint[1]);
  }
  if (yMax === yMin) {
    const spread = Math.abs(yMax) * 0.05 || 1;
    yMin -= spread;
    yMax += spread;
  }
  const padY = (yMax - yMin) * 0.06;
  if (xMax === xMin) xMax = xMin + 60000;
  return { xMin, xMax, yMin: yMin - padY, yMax: yMax + padY };
}

function formatX(ms, mode, startMs, spanMs, precise = false) {
  if (precise && mode !== "clock") return `${((ms - startMs) / 3600000).toFixed(2)} h`;
  if (mode === "clock") {
    const date = new Date(ms);
    const hm = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return spanMs > 36 * 3600000 ? `${date.getMonth() + 1}/${date.getDate()} ${hm}` : hm;
  }
  const hours = (ms - startMs) / 3600000;
  return `${Number(hours.toFixed(Math.abs(hours) < 10 && spanMs < 6 * 3600000 ? 1 : 0))}h`;
}

function formatY(value, decimals) {
  if (Math.abs(value) >= 1000) return value.toFixed(0);
  return value.toFixed(decimals);
}

function xTicks(domain, mode, startMs, target) {
  if (mode === "clock") return ticks(domain.xMin, domain.xMax, target);
  // Ticks on round hour offsets from the experiment start.
  const toH = (ms) => (ms - startMs) / 3600000;
  return ticks(toH(domain.xMin), toH(domain.xMax), target).map((h) => startMs + h * 3600000);
}

// Index of the last point with x <= target (points sorted by x).
export function nearestIndex(points, target) {
  let lo = 0;
  let hi = points.length - 1;
  if (hi < 0 || points[0].x > target) return -1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (points[mid].x <= target) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

export function drawChart(canvas, options) {
  const { seriesList, hidden, domain, cursorX, theme, xMode, startMs, decimals, stepped } = options;
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return null;
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  if (!domain) return null;

  const k = theme.scale;
  const PAD = { left: BASE_PAD.left * k, right: BASE_PAD.right * k, top: BASE_PAD.top * k, bottom: BASE_PAD.bottom * k };
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const sx = (x) => PAD.left + ((x - domain.xMin) / (domain.xMax - domain.xMin)) * plotW;
  const sy = (y) => PAD.top + (1 - (y - domain.yMin) / (domain.yMax - domain.yMin)) * plotH;

  ctx.font = `${Math.round(11 * k)}px ${theme.font}`;
  ctx.lineWidth = 1;

  // Grid and axes
  ctx.strokeStyle = theme.grid;
  ctx.fillStyle = theme.text2;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const value of ticks(domain.yMin, domain.yMax, Math.max(2, Math.floor(plotH / (55 * k))))) {
    const y = Math.round(sy(value)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(width - PAD.right, y);
    ctx.stroke();
    ctx.fillText(formatY(value, decimals), PAD.left - 6 * k, y);
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const span = domain.xMax - domain.xMin;
  for (const value of xTicks(domain, xMode, startMs, Math.max(2, Math.floor(plotW / (90 * k))))) {
    const x = sx(value);
    if (x < PAD.left - 1 || x > width - PAD.right + 1) continue;
    ctx.fillText(formatX(value, xMode, startMs, span), x, height - PAD.bottom + 6 * k);
  }

  // Series
  ctx.save();
  ctx.beginPath();
  ctx.rect(PAD.left, PAD.top, plotW, plotH);
  ctx.clip();
  ctx.lineWidth = 1.75 * k;
  ctx.lineJoin = "round";
  for (const series of seriesList) {
    if (hidden.has(series.name) || series.points.length === 0) continue;
    ctx.strokeStyle = theme.series(series.color);
    ctx.beginPath();
    // Skip points that land on the same pixel column; keeps work ~O(width).
    let lastPx = -Infinity;
    let previousY = null;
    series.points.forEach((point, index) => {
      const px = sx(point.x);
      const py = sy(point.y);
      if (index === 0) {
        ctx.moveTo(px, py);
      } else if (px - lastPx >= 0.75 || index === series.points.length - 1) {
        if (stepped && previousY !== null) ctx.lineTo(px, previousY);
        ctx.lineTo(px, py);
      } else {
        return;
      }
      lastPx = px;
      previousY = py;
    });
    ctx.stroke();
  }
  ctx.restore();

  ctx.strokeStyle = theme.axis;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.left + 0.5, PAD.top);
  ctx.lineTo(PAD.left + 0.5, height - PAD.bottom + 0.5);
  ctx.lineTo(width - PAD.right, height - PAD.bottom + 0.5);
  ctx.stroke();

  if (cursorX === null || cursorX === undefined) return null;

  // Tap-to-inspect: a vertical line and the value of each visible series at that time.
  const xValue = domain.xMin + ((Math.min(Math.max(cursorX, PAD.left), width - PAD.right) - PAD.left) / plotW) * span;
  const px = sx(xValue);
  ctx.strokeStyle = theme.text2;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(px, PAD.top);
  ctx.lineTo(px, height - PAD.bottom);
  ctx.stroke();
  ctx.setLineDash([]);

  const rows = [];
  for (const series of seriesList) {
    if (hidden.has(series.name)) continue;
    const index = nearestIndex(series.points, xValue);
    if (index < 0) continue;
    const point = series.points[index];
    rows.push({ label: series.label, color: theme.series(series.color), value: formatY(point.y, decimals + 1) });
    ctx.fillStyle = theme.series(series.color);
    ctx.beginPath();
    ctx.arc(px, sy(point.y), 3.5 * k, 0, Math.PI * 2);
    ctx.fill();
  }
  rows.sort((a, b) => Number(b.value) - Number(a.value));
  const line = 16 * k;
  const shown = rows.slice(0, Math.max(1, Math.floor((plotH - 24 * k) / line)));
  ctx.font = `${Math.round(12 * k)}px ${theme.font}`;
  const title = formatX(xValue, xMode, startMs, span, true);
  const boxW = Math.max(ctx.measureText(title).width, ...shown.map((row) => ctx.measureText(`${row.label}  ${row.value}`).width)) + 28 * k;
  const boxH = 22 * k + shown.length * line;
  const boxX = px + boxW + 10 > width - PAD.right ? px - boxW - 10 : px + 10;
  const boxY = PAD.top + 4 * k;
  ctx.fillStyle = theme.surface;
  ctx.strokeStyle = theme.axis;
  ctx.fillRect(boxX, boxY, boxW, boxH);
  ctx.strokeRect(boxX + 0.5, boxY + 0.5, boxW, boxH);
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillStyle = theme.text2;
  ctx.fillText(title, boxX + 8 * k, boxY + 5 * k);
  shown.forEach((row, i) => {
    const y = boxY + 21 * k + i * line;
    ctx.fillStyle = row.color;
    ctx.fillRect(boxX + 8 * k, y + 3 * k, 8 * k, 8 * k);
    ctx.fillStyle = theme.text;
    ctx.fillText(`${row.label}  ${row.value}`, boxX + 21 * k, y);
  });
  return xValue;
}

const liftedColors = new Map();

// Same rule as the main UI's chart theme: keep hue, lift dark lines off a dark canvas.
export function seriesColor(color) {
  if (!color || document.documentElement.dataset.theme !== "dark") return color;
  if (!liftedColors.has(color)) liftedColors.set(color, lighten(color, 0.35));
  return liftedColors.get(color);
}

export function readChartTheme(element) {
  const style = getComputedStyle(element);
  const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  return {
    text: read("--mui-palette-ui-text", "#222"),
    text2: read("--mui-palette-ui-textSecondary", "#666"),
    grid: read("--mui-palette-ui-subtleBackground", "#eee"),
    axis: read("--mui-palette-ui-border", "#ccc"),
    surface: read("--mui-palette-ui-surface", "#fff"),
    font: style.fontFamily || "sans-serif",
    series: seriesColor,
    scale: (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16) / 16,
  };
}
