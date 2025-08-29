import React from "react";
import Typography from '@mui/material/Typography';

import {
  VictoryChart,
  VictoryScatter,
  VictoryLine,
  VictoryAxis,
  VictoryTheme,
  VictoryLabel,
  VictoryCursorContainer,
  VictoryTooltip,
  LineSegment
} from "victory";

/**
 * Evaluates a polynomial at x given an array of coefficients in descending order.
 * e.g., [a, b, c] => a*x^2 + b*x + c
 */
function evaluatePolynomial(x, coeffs) {
  return coeffs.reduce((acc, coefficient, i) => {
    const power = coeffs.length - 1 - i; // descending power
    return acc + coefficient * Math.pow(x, power);
  }, 0);
}

/**
 * Generates a set of [x, y] points along a polynomial curve for plotting.
 * We base the domain on the recorded_data.x for each calibration.
 */
function generatePolynomialData(calibration, stepCount = 50) {
  const { x: xValues } = calibration.recorded_data;
  const coeffs = calibration.curve_data_ || [];

  if (!xValues || xValues.length === 0) {
    // No recorded data => fallback domain
    // Adjust these as needed or handle differently
    const fallbackXMin = 0;
    const fallbackXMax = 1;
    const stepSize = (fallbackXMax - fallbackXMin) / (stepCount - 1);

    return Array.from({ length: stepCount }).map((_, i) => {
      const x = fallbackXMin + i * stepSize;
      return { x, y: evaluatePolynomial(x, coeffs) };
    });
  }

  // Determine min/max from recorded data
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);

  // If all xValues are the same, give some small range
  if (xMin === xMax) {
    return [{ x: xMin, y: evaluatePolynomial(xMin, coeffs) }];
  }

  const stepSize = (xMax - xMin) / (stepCount - 1);
  const points = [];

  for (let i = 0; i < stepCount; i++) {
    const x = xMin + i * stepSize;
    points.push({ x, y: evaluatePolynomial(x, coeffs) });
  }
  return points;
}

function CalibrationChart({ calibrations, deviceName, unitsColorMap, highlightedModel, title }) {
  if (!deviceName){
    return <Typography variant="body2" component="p" color="textSecondary">No calibrations exist. Try creating a calibration from the command line.</Typography>
  }
  else if (!calibrations || calibrations.length === 0) {
    return <Typography variant="body2" component="p" color="textSecondary">No calibrations to plot for {deviceName}.</Typography>;
  }

  // Assume the x and y fields match across all calibrations for a device
  const { x: xField = "X", y: yField = "Y" } = calibrations[0] || {};

  const isHighlighted = (calibration) => {
    return (calibration.pioreactor_unit === highlightedModel.pioreactorUnit && calibration.calibration_name === highlightedModel.calibrationName);
  }

  const width = 1050
  return (
      <VictoryChart
        domainPadding={10}
        height={350}
        width={1050}
        theme={VictoryTheme.material}
        padding={{ left: 50, right: 50, bottom: 40, top: 45 }}
        containerComponent={
          <VictoryCursorContainer
            // only draw a vertical line; change to "both" for cross-hairs

            // supply the text but use a tooltip component for styling
            cursorLabel={({ datum }) =>
              `${datum.x.toFixed(2)}, ${datum.y.toFixed(2)}`
            }
            cursorLabelComponent={
              <VictoryTooltip
                dy={0}
                dx={-5}
                cornerRadius={0}
                constrainToVisibleArea      // keep it on–screen
                flyoutStyle={{
                  fill: "white",
                  stroke: "#90a4ae",
                  strokeWidth: 1.0,
                }}
                style={{
                  fontSize: 10,
                  fontFamily: "inherit",
                  fill: "#333",
                }}
              />
            }

            cursorComponent={
              <LineSegment
                  style={{
                    strokeDasharray: [6, 6],
                    stroke: "#888",
                    strokeWidth: 1,
                  }}
              />
            }
          />
        }
      >
        <VictoryLabel
            text={title}
            x={width/2}
            y={30}
            textAnchor="middle"
            style={{
              fontSize: 16,
              fontFamily: "inherit",
            }}
        />

          <VictoryAxis
            style={{
              tickLabels: {
                fontSize: 14,
                padding: 5,
                fontFamily: "inherit",
              },
            }}
            offsetY={40}
            label={xField}
            orientation="bottom"
            fixLabelOverlap={true}
            axisLabelComponent={
              <VictoryLabel
                dy={20}
                dx={0}
                style={{
                  fontSize: 12,
                  fontFamily: "inherit",
                }}
              />
            }
          />


          <VictoryAxis
            crossAxis={false}
            dependentAxis
            label={yField}
            axisLabelComponent={
              <VictoryLabel
                dy={-30}
                style={{
                  fontSize: 12,
                  padding: 10,
                  fontFamily: "inherit",
                }}
              />
            }
            style={{
              tickLabels: {
                fontSize: 14,
                padding: 5,
                fontFamily: "inherit",
              },
            }}
          />

        {calibrations.map((cal, index) => {
          // Convert recorded_data into an array of {x, y} for scatter
          const scatterData = (cal.recorded_data?.x || []).map((xVal, i) => ({
            x: xVal,
            y: cal.recorded_data.y?.[i] ?? null,
          }));

          // Simple color selection (optional)
          const color = unitsColorMap[cal.pioreactor_unit + cal.calibration_name] || "black";

          return (
              <VictoryScatter
                key={cal.calibration_name}
                data={scatterData}
                style={{ data: { fill: color, fillOpacity: 0.8, } }}
                size={isHighlighted(cal) ? 4 : 3}
              />
          );
        })}

        {calibrations.map((cal, index) => {

          // Generate polynomial curve
          const polynomialData = generatePolynomialData(cal);

          // Simple color selection (optional)
          const color = unitsColorMap[cal.pioreactor_unit + cal.calibration_name] || "black";

          return (
              <VictoryLine
                key={cal.calibration_name || index}
                interpolation='basis'
                data={polynomialData}
                style={{ data: { stroke: color, strokeWidth: isHighlighted(cal) ? 4 : 1.5 } }}
              />
          );
        })}

      </VictoryChart>
  );
}

export default CalibrationChart;
