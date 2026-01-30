import React, { useRef, useState } from "react";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import ListItemText from "@mui/material/ListItemText";
import DownloadIcon from "@mui/icons-material/Download";
import SettingsIcon from "@mui/icons-material/Settings";
import Typography from '@mui/material/Typography';
import { Link } from 'react-router';

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
import { generateCurveData } from "../curve_utils";

function CalibrationChart({ calibrations, deviceName, unitsColorMap, highlightedModel, title }) {
  const [exportAnchorEl, setExportAnchorEl] = useState(null);
  const [optionsAnchorEl, setOptionsAnchorEl] = useState(null);
  const [useLogX, setUseLogX] = useState(false);
  const [useLogY, setUseLogY] = useState(false);
  const chartContainerRef = useRef(null);

  const handleOpenExportMenu = (event) => {
    setExportAnchorEl(event.currentTarget);
  };

  const handleCloseExportMenu = () => {
    setExportAnchorEl(null);
  };

  const handleOpenOptionsMenu = (event) => {
    setOptionsAnchorEl(event.currentTarget);
  };

  const handleCloseOptionsMenu = () => {
    setOptionsAnchorEl(null);
  };

  const getDownloadFilename = (extension) => {
    const raw = title || deviceName || "calibration-chart";
    const slug = raw
      .toString()
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    const safeName = slug || "calibration-chart";
    return `${safeName}.${extension}`;
  };

  const triggerBlobDownload = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const triggerDataUrlDownload = (dataUrl, filename) => {
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const exportChart = (format) => {
    const container = chartContainerRef.current;
    if (!container) {
      return;
    }

    const svgElement = container.querySelector("svg");
    if (!svgElement) {
      return;
    }

    const clonedSvg = svgElement.cloneNode(true);
    clonedSvg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clonedSvg.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");

    const styleNode = document.createElement("style");
    styleNode.setAttribute("type", "text/css");
    styleNode.innerHTML = "* { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif !important; }";
    clonedSvg.insertBefore(styleNode, clonedSvg.firstChild);

    const serializer = new XMLSerializer();
    const serializedSvg = serializer.serializeToString(clonedSvg);
    const svgWithHeader = `<?xml version=\"1.0\" encoding=\"utf-8\"?>\n${serializedSvg}`;
    const svgBlob = new Blob([svgWithHeader], { type: "image/svg+xml;charset=utf-8" });

    if (format === "svg") {
      triggerBlobDownload(svgBlob, getDownloadFilename("svg"));
      return;
    }

    if (format !== "png") {
      return;
    }

    const width = Number(clonedSvg.getAttribute("width")) || svgElement.clientWidth || 1050;
    const height = Number(clonedSvg.getAttribute("height")) || svgElement.clientHeight || 325;
    const scaleFactor = 2;

    const url = URL.createObjectURL(svgBlob);
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = width * scaleFactor;
      canvas.height = height * scaleFactor;
      const context = canvas.getContext("2d");
      if (!context) {
        URL.revokeObjectURL(url);
        return;
      }
      context.scale(scaleFactor, scaleFactor);
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);
      const dataUrl = canvas.toDataURL("image/png", 1.0);
      triggerDataUrlDownload(dataUrl, getDownloadFilename(format));
      URL.revokeObjectURL(url);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
    };
    image.src = url;
  };

  const handleDownloadSelection = (format) => {
    setExportAnchorEl(null);
    exportChart(format);
  };

  const exportMenuOpen = Boolean(exportAnchorEl);
  const optionsMenuOpen = Boolean(optionsAnchorEl);

  const isPositiveNumber = (value) => typeof value === "number" && Number.isFinite(value) && value > 0;

  const filterDataForScale = (data) => {
    if (!useLogX && !useLogY) {
      return data;
    }
    return data.filter((datum) => (
      (!useLogX || isPositiveNumber(datum.x)) &&
      (!useLogY || isPositiveNumber(datum.y))
    ));
  };

  if (!deviceName){
    return <Box display="flex" justifyContent="center" alignItems="center" minHeight="10vh"><Typography variant="body2" component="p" color="textSecondary">No calibrations exist. Try creating a calibration from a <Link to="/protocols">protocol</Link>.</Typography></Box>
  }
  else if (!calibrations || calibrations.length === 0) {
    return <Box display="flex" justifyContent="center" alignItems="center" minHeight="10vh"><Typography variant="body2" component="p" color="textSecondary">No calibrations to plot for {deviceName}.</Typography></Box>;
  }

  // Assume the x and y fields match across all calibrations for a device
  const { x: xField = "X", y: yField = "Y" } = calibrations[0] || {};

  const isHighlighted = (calibration) => {
    return (calibration.pioreactor_unit === highlightedModel.pioreactorUnit && calibration.calibration_name === highlightedModel.calibrationName);
  }

  const width = 1050
  return (
    <div ref={chartContainerRef} style={{ position: "relative" }}>
      <VictoryChart
        domainPadding={10}
        height={325}
        width={1050}
        scale={{ x: useLogX ? "log" : "linear", y: useLogY ? "log" : "linear" }}
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
          const filteredScatterData = filterDataForScale(scatterData);

          // Simple color selection (optional)
          const color = unitsColorMap[cal.pioreactor_unit + cal.calibration_name] || "black";

          return (
              <VictoryScatter
                key={cal.calibration_name}
                data={filteredScatterData}
                style={{ data: { fill: color, fillOpacity: 0.8, } }}
                size={isHighlighted(cal) ? 4 : 3}
              />
          );
        })}

        {calibrations.map((cal, index) => {

          const curveData = generateCurveData(cal);
          const filteredCurveData = filterDataForScale(curveData);

          // Simple color selection (optional)
          const color = unitsColorMap[cal.pioreactor_unit + cal.calibration_name] || "black";
          const isActive = cal.is_active;
          const baseLineWidth = isActive ? 3 : 1.5;
          const lineOpacity = isActive ? 1.0 : 0.8;

          return (
              <VictoryLine
                key={cal.calibration_name || index}
                interpolation="basis"
                data={filteredCurveData}
                style={{
                  data: {
                    stroke: color,
                    strokeWidth: isHighlighted(cal) ? 4 : baseLineWidth,
                    opacity: lineOpacity,
                  },
                }}
              />
          );
        })}

      </VictoryChart>
        <Box
          sx={{
            position: "absolute",
            bottom: 8,
            right: 8,
            display: "flex",
            gap: 0.5,
          }}
        >
          <IconButton
            aria-label={`chart-options-${deviceName || 'calibration'}`}
            size="small"
            onClick={handleOpenOptionsMenu}
            sx={{ backgroundColor: "rgba(255,255,255,0.85)" }}
          >
            <SettingsIcon fontSize="small" />
          </IconButton>
          <IconButton
            aria-label={`download-${deviceName || 'calibration'}`}
            size="small"
            onClick={handleOpenExportMenu}
            sx={{ backgroundColor: "rgba(255,255,255,0.85)" }}
          >
            <DownloadIcon fontSize="small" />
          </IconButton>
        </Box>
      <Menu
        anchorEl={exportAnchorEl}
        open={exportMenuOpen}
        onClose={handleCloseExportMenu}
        anchorOrigin={{ horizontal: "right", vertical: "top" }}
        transformOrigin={{ horizontal: "right", vertical: "bottom" }}
      >
        <MenuItem onClick={() => handleDownloadSelection('png')}>
          Download PNG
        </MenuItem>
        <MenuItem onClick={() => handleDownloadSelection('svg')}>
          Download SVG
        </MenuItem>
      </Menu>
      <Menu
        anchorEl={optionsAnchorEl}
        open={optionsMenuOpen}
        onClose={handleCloseOptionsMenu}
        anchorOrigin={{ horizontal: "right", vertical: "top" }}
        transformOrigin={{ horizontal: "right", vertical: "bottom" }}
      >
        <MenuItem onClick={() => setUseLogX((prev) => !prev)}>
          <Checkbox checked={useLogX} size="small" />
          <ListItemText primary="Log x-axis" />
        </MenuItem>
        <MenuItem onClick={() => setUseLogY((prev) => !prev)}>
          <Checkbox checked={useLogY} size="small" />
          <ListItemText primary="Log y-axis" />
        </MenuItem>
      </Menu>
    </div>
  );
}

export default CalibrationChart;
