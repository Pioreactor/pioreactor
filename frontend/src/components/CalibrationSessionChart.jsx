import useChartTheme from "../theme/useChartTheme";
import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  VictoryChart,
  VictoryContainer,
  VictoryScatter,
  VictoryLine,
  VictoryAxis,
  VictoryLabel,
} from "victory";
import { evaluateCurve } from "../utils/curve_utils";

const SERIES_COLORS = [
  "#1b5e20",
  "#0d47a1",
  "#f57c00",
  "#6a1b9a",
  "#006064",
  "#c2185b",
];

function generateCurvePoints(points, curveData, stepCount = 50) {
  if (!Array.isArray(points) || points.length === 0) {
    return [];
  }
  const xs = points.map((point) => point.x);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  if (xMin === xMax) {
    const y = evaluateCurve(xMin, curveData);
    return y === null ? [] : [{ x: xMin, y }];
  }
  const stepSize = (xMax - xMin) / (stepCount - 1);
  const curve = [];
  for (let i = 0; i < stepCount; i += 1) {
    const x = xMin + i * stepSize;
    const y = evaluateCurve(x, curveData);
    if (y !== null) {
      curve.push({ x, y });
    }
  }
  return curve;
}

export default function CalibrationSessionChart({ chart, review = false }) {
  const chartTheme = useChartTheme();
  const containerRef = React.useRef(null);
  const [width, setWidth] = React.useState(520);
  const hasSeries = Array.isArray(chart?.series) && chart.series.length > 0;

  React.useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const updateWidth = () => setWidth(container.clientWidth || 520);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(container);
    return () => observer.disconnect();
  }, [hasSeries]);

  if (!hasSeries) {
    return null;
  }

  // Match chart coordinates to the container so labels stay readable on narrow screens.
  const height = review ? 360 : 240;
  const padding = { left: 65, right: 25, bottom: 50, top: 40 };
  const title = chart.title || "Calibration progress";
  const xLabel = chart.x_label || "X";
  const yLabel = chart.y_label || "Y";

  return (
    <Box ref={containerRef} sx={{ width: "100%", minWidth: 0, flexShrink: 0, mb: 0.5 }}>
      <VictoryChart
        domainPadding={10}
        height={height}
        width={width}
        containerComponent={<VictoryContainer responsive={false} title={title} style={{ touchAction: "pan-y" }} />}
        theme={chartTheme.theme}
        padding={padding}
      >
        <VictoryLabel
          text={title}
          x={width / 2}
          y={15}
          textAnchor="middle"
          style={{
            fontSize: 14,
            fontFamily: "inherit",
            fill: chartTheme.text,
          }}
        />
        <VictoryAxis
          style={{
            tickLabels: {
              fontSize: 12,
              padding: 4,
              fontFamily: "inherit",
              fill: chartTheme.text,
            },
          }}
          tickFormat={(value) => Number(value).toFixed(2)}
          tickCount={width < 400 ? 4 : 6}
          offsetY={padding.bottom}
          label={xLabel}
          axisLabelComponent={
            <VictoryLabel
              dy={18}
              style={{
                fontSize: 12,
                fontFamily: "inherit",
                fill: chartTheme.text,
              }}
            />
          }
        />
        <VictoryAxis
          crossAxis={false}
          dependentAxis
          label={yLabel}
          tickFormat={(value) => Number(value).toFixed(2)}
          tickCount={5}
          axisLabelComponent={
            <VictoryLabel
              dy={-44}
              style={{
                fontSize: 12,
                padding: 8,
                fontFamily: "inherit",
                fill: chartTheme.text,
              }}
            />
          }
          style={{
            tickLabels: {
              fontSize: 12,
              padding: 4,
              fontFamily: "inherit",
              fill: chartTheme.text,
            },
          }}
        />

        {chart.series.map((series, index) => {
          const color = chartTheme.seriesColor(SERIES_COLORS[index % SERIES_COLORS.length]);
          return (
            <VictoryScatter
              key={`scatter-${series.id || index}`}
              data={series.points || []}
              style={{ data: { fill: color, fillOpacity: 0.8 } }}
              size={3}
            />
          );
        })}

        {chart.series.map((series, index) => {
          if (!series.curve || Array.isArray(series.curve)) {
            return null;
          }
          const curvePoints = generateCurvePoints(series.points, series.curve);
          if (curvePoints.length === 0) {
            return null;
          }
          const color = chartTheme.seriesColor(SERIES_COLORS[index % SERIES_COLORS.length]);
          return (
            <VictoryLine
              key={`curve-${series.id || index}`}
              interpolation="basis"
              data={curvePoints}
              style={{ data: { stroke: color, strokeWidth: 1.5 } }}
            />
          );
        })}
      </VictoryChart>
      {chart.series.length > 1 && (
        <Stack direction="row" spacing={2} useFlexGap sx={{ mt: 0.5, flexWrap: "wrap" }}>
          {chart.series.map((series, index) => (
            <Stack
              direction="row"
              spacing={0.75}
              alignItems="center"
              key={`legend-${series.id || index}`}
            >
              <Box
                sx={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  backgroundColor: chartTheme.seriesColor(SERIES_COLORS[index % SERIES_COLORS.length]),
                }}
              />
              <Typography variant="caption" color="text.secondary">
                {series.label || series.id || "Series"}
              </Typography>
            </Stack>
          ))}
        </Stack>
      )}
    </Box>
  );
}
