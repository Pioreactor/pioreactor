import { useEffect, useRef } from "react";
import { readChartTheme, seriesColor, ticks } from "./chartDraw";
import { evaluateCurve } from "../utils/curve_utils";

// Canvas scatter + fitted curve, for calibration data. Series look like the
// calibration session API's chart metadata: {label, points: [{x, y}], curve}.

const COLORS = ["#0077BB", "#CC3311", "#009988", "#EE7733", "#AA3377", "#33BBEE"];
const PAD = { left: 56, right: 14, top: 12, bottom: 40 };
const CURVE_STEPS = 60;

function curvePoints(points, curve) {
  if (!curve || Array.isArray(curve) || points.length === 0) return [];
  const xs = points.map((point) => point.x);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const out = [];
  for (let i = 0; i < CURVE_STEPS; i += 1) {
    const x = xMin + ((xMax - xMin) * i) / (CURVE_STEPS - 1);
    const y = evaluateCurve(x, curve);
    if (Number.isFinite(y)) out.push({ x, y });
  }
  return out;
}

function formatTick(value, span) {
  const decimals = span >= 10 ? 0 : span >= 1 ? 1 : span >= 0.1 ? 2 : 3;
  return value.toFixed(decimals);
}

function draw(canvas, series, xLabel, yLabel) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const theme = readChartTheme(canvas);
  const k = theme.scale;
  const pad = { left: PAD.left * k, right: PAD.right * k, top: PAD.top * k, bottom: PAD.bottom * k };
  const prepared = series.map((entry, index) => ({
    ...entry,
    color: seriesColor(COLORS[index % COLORS.length]),
    fitted: curvePoints(entry.points, entry.curve),
  }));
  const all = prepared.flatMap((entry) => [...entry.points, ...entry.fitted]);
  if (all.length === 0) return;

  let xMin = Math.min(...all.map((p) => p.x));
  let xMax = Math.max(...all.map((p) => p.x));
  let yMin = Math.min(...all.map((p) => p.y));
  let yMax = Math.max(...all.map((p) => p.y));
  if (xMax === xMin) {
    xMin -= 1;
    xMax += 1;
  }
  if (yMax === yMin) {
    yMin -= 1;
    yMax += 1;
  }
  const yPad = (yMax - yMin) * 0.08;
  const xPad = (xMax - xMin) * 0.04;
  yMin -= yPad;
  yMax += yPad;
  xMin -= xPad;
  xMax += xPad;

  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const sx = (x) => pad.left + ((x - xMin) / (xMax - xMin)) * plotW;
  const sy = (y) => pad.top + (1 - (y - yMin) / (yMax - yMin)) * plotH;

  ctx.font = `${Math.round(11 * k)}px ${theme.font}`;
  ctx.lineWidth = 1;
  ctx.strokeStyle = theme.grid;
  ctx.fillStyle = theme.text2;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const value of ticks(yMin, yMax, Math.max(2, Math.floor(plotH / (45 * k))))) {
    const y = Math.round(sy(value)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillText(formatTick(value, yMax - yMin), pad.left - 6 * k, y);
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (const value of ticks(xMin, xMax, Math.max(2, Math.floor(plotW / (80 * k))))) {
    ctx.fillText(formatTick(value, xMax - xMin), sx(value), height - pad.bottom + 5 * k);
  }
  if (xLabel) ctx.fillText(xLabel, pad.left + plotW / 2, height - 16 * k);
  if (yLabel) {
    ctx.save();
    ctx.translate(12 * k, pad.top + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textBaseline = "middle";
    ctx.fillText(yLabel, 0, 0);
    ctx.restore();
  }

  ctx.save();
  ctx.beginPath();
  ctx.rect(pad.left, pad.top, plotW, plotH);
  ctx.clip();
  for (const entry of prepared) {
    if (entry.fitted.length > 1) {
      ctx.strokeStyle = entry.color;
      ctx.lineWidth = 2 * k;
      ctx.beginPath();
      entry.fitted.forEach((point, index) => (index ? ctx.lineTo(sx(point.x), sy(point.y)) : ctx.moveTo(sx(point.x), sy(point.y))));
      ctx.stroke();
    }
    ctx.fillStyle = entry.color;
    for (const point of entry.points) {
      ctx.beginPath();
      ctx.arc(sx(point.x), sy(point.y), 4 * k, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();

  ctx.strokeStyle = theme.axis;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left + 0.5, pad.top);
  ctx.lineTo(pad.left + 0.5, height - pad.bottom + 0.5);
  ctx.lineTo(width - pad.right, height - pad.bottom + 0.5);
  ctx.stroke();
}

export default function XYChart({ series, xLabel, yLabel, title }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let frame = requestAnimationFrame(() => draw(canvas, series, xLabel, yLabel));
    if (typeof ResizeObserver === "undefined") return () => cancelAnimationFrame(frame);
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => draw(canvas, series, xLabel, yLabel));
    });
    observer.observe(canvas);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [series, xLabel, yLabel]);

  return (
    <figure className="xy-chart">
      {title && <figcaption>{title}</figcaption>}
      <canvas ref={canvasRef} aria-label={title || "Calibration chart"} />
      {series.length > 1 && (
        <div className="xy-legend">
          {series.map((entry, index) => (
            <span key={entry.id || entry.label || index}>
              <i style={{ background: seriesColor(COLORS[index % COLORS.length]) }} />
              {entry.label || entry.id}
            </span>
          ))}
        </div>
      )}
    </figure>
  );
}
