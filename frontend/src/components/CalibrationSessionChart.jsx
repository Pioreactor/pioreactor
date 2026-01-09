import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  VictoryChart,
  VictoryScatter,
  VictoryLine,
  VictoryAxis,
  VictoryTheme,
  VictoryLabel,
} from "victory";

const SERIES_COLORS = [
  "#1b5e20",
  "#0d47a1",
  "#f57c00",
  "#6a1b9a",
  "#006064",
  "#c2185b",
];

function evaluatePolynomial(x, coeffs) {
  return coeffs.reduce((acc, coefficient, index) => {
    const power = coeffs.length - 1 - index;
    return acc + coefficient * Math.pow(x, power);
  }, 0);
}

function generateCurvePoints(points, coefficients, stepCount = 50) {
  if (!Array.isArray(points) || points.length === 0 || !Array.isArray(coefficients)) {
    return [];
  }
  const xs = points.map((point) => point.x);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  if (xMin === xMax) {
    return [{ x: xMin, y: evaluatePolynomial(xMin, coefficients) }];
  }
  const stepSize = (xMax - xMin) / (stepCount - 1);
  const curve = [];
  for (let i = 0; i < stepCount; i += 1) {
    const x = xMin + i * stepSize;
    curve.push({ x, y: evaluatePolynomial(x, coefficients) });
  }
  return curve;
}

export default function CalibrationSessionChart({ chart }) {
  if (!chart || !Array.isArray(chart.series) || chart.series.length === 0) {
    return null;
  }

  const width = 520;
  const height = 240;
  const title = chart.title || "Calibration progress";
  const xLabel = chart.x_label || "X";
  const yLabel = chart.y_label || "Y";

  return (
    <Box sx={{ width: "100%", overflow: "hidden", mb: 0.5 }}>
      <VictoryChart
        domainPadding={10}
        height={height}
        width={width}
        theme={VictoryTheme.material}
        padding={{ left: 50, right: 25, bottom: 45, top: 40 }}
      >
        <VictoryLabel
          text={title}
          x={width / 2}
          y={22}
          textAnchor="middle"
          style={{
            fontSize: 12,
            fontFamily: "inherit",
          }}
        />
        <VictoryAxis
          style={{
            tickLabels: {
              fontSize: 11,
              padding: 4,
              fontFamily: "inherit",
            },
          }}
          tickFormat={(value) => Number(value).toFixed(3)}
          offsetY={45}
          label={xLabel}
          axisLabelComponent={
            <VictoryLabel
              dy={18}
              style={{
                fontSize: 10,
                fontFamily: "inherit",
              }}
            />
          }
        />
        <VictoryAxis
          crossAxis={false}
          dependentAxis
          label={yLabel}
          tickFormat={(value) => Number(value).toFixed(3)}
          axisLabelComponent={
            <VictoryLabel
              dy={-34}
              style={{
                fontSize: 10,
                padding: 8,
                fontFamily: "inherit",
              }}
            />
          }
          style={{
            tickLabels: {
              fontSize: 11,
              padding: 4,
              fontFamily: "inherit",
            },
          }}
        />

        {chart.series.map((series, index) => {
          const color = SERIES_COLORS[index % SERIES_COLORS.length];
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
          if (!series.curve || !Array.isArray(series.curve.coefficients)) {
            return null;
          }
          const curvePoints = generateCurvePoints(series.points, series.curve.coefficients);
          if (curvePoints.length === 0) {
            return null;
          }
          const color = SERIES_COLORS[index % SERIES_COLORS.length];
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
        <Stack direction="row" spacing={2} sx={{ mt: 0.5, flexWrap: "wrap" }}>
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
                  backgroundColor: SERIES_COLORS[index % SERIES_COLORS.length],
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
