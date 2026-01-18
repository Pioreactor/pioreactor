import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import DownloadIcon from "@mui/icons-material/Download";
import {
  VictoryChart,
  VictoryLabel,
  VictoryAxis,
  VictoryTheme,
  VictoryLine,
  VictoryScatter,
  VictoryGroup,
  VictoryLegend,
  VictoryTooltip,
  createContainer
} from "victory";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

// Activate the UTC plugin
dayjs.extend(utc);

const sensorRe = /^(.*)-(\d+)$/;

function toArray(thing){
   if (Array.isArray(thing)){
      return thing
  } else {
    return [thing]
  }
}

const splitPartitionedName = (name) => {
  const match = name.match(sensorRe);
  if (!match) {
    return { base: name, suffix: null };
  }
  return { base: match[1], suffix: match[2] };
};

const resolveUnitColor = (name, colorMap) => {
  const { base, suffix } = splitPartitionedName(name);
  if (suffix) {
    const primaryName = base;
    return resolveUnitColor(primaryName, colorMap);
  }
  if (colorMap) {
    return colorMap[name];
  }
  return undefined;
};

function Chart(props) {
  const {
    allowZoom,
    byDuration,
    chartKey,
    client,
    config,
    dataSource,
    dataSourceColumn,
    downSample,
    experiment,
    experimentStartTime,
    fixedDecimals,
    interpolation,
    isLiveChart,
    isPartitionedBySensor,
    lookback,
    payloadKey,
    relabelMap,
    subscribeToTopic,
    title,
    topic,
    unit,
    unitsColorMap,
    unsubscribeFromTopic,
    yAxisDomain,
    yAxisLabel,
    yTransformation: yTransformationProp,
  } = props;

  const topics = useMemo(() => toArray(topic), [topic]);
  const chartContainerRef = useRef(null);
  const canvasMeasureRef = useRef(null);
  const [chartWidth, setChartWidth] = useState(600);
  const [seriesMap, setSeriesMap] = useState({});
  const [hiddenSeries, setHiddenSeries] = useState(() => new Set());
  const [fetched, setFetched] = useState(false);
  const [exportAnchorEl, setExportAnchorEl] = useState(null);

  const names = useMemo(() => Object.keys(seriesMap), [seriesMap]);

  const ChartContainer = useMemo(
    () => (allowZoom ? createContainer("zoom", "voronoi") : createContainer("voronoi")),
    [allowZoom]
  );

  const channelAngleMap = useMemo(() => {
    const rawMap = config?.["od_config.photodiode_channel"] || {};
    const entries = Object.entries(rawMap)
      .filter(([, angle]) => angle && angle !== "REF")
      .map(([channel, angle]) => [String(channel), String(angle)]);
    return Object.fromEntries(entries);
  }, [config]);

  const yTransformation = useMemo(
    () => yTransformationProp || ((y) => y),
    [yTransformationProp]
  );

  const getUnitColor = useCallback(
    (name) => resolveUnitColor(name, unitsColorMap),
    [unitsColorMap]
  );

  const breakString = useCallback((n) => (string) => {
    if (string.length > n) {
      return string.slice(0, n - 5) + "..." + string.slice(string.length - 2, string.length);
    }
    return string;
  }, []);

  const relabelAndFormatSeries = useCallback(
    (name) => {
      if (isPartitionedBySensor) {
        const { base, suffix } = splitPartitionedName(name);
        if (suffix) {
          const displayBase = relabelMap ? (relabelMap[base] || base) : base;
          return `${breakString(12)(displayBase)}-${suffix}°`;
        }
      }
      if (!relabelMap) {
        return name;
      }
      return breakString(12)(relabelMap[name] || name);
    },
    [breakString, isPartitionedBySensor, relabelMap]
  );

  const relabelAndFormatSeriesForLegend = useCallback(
    (name) => {
      const nElements = Object.keys(relabelMap || {}).length || 1;
      const truncateString = breakString(Math.floor(100 / nElements));

      if (isPartitionedBySensor) {
        const { base, suffix } = splitPartitionedName(name);
        if (suffix) {
          const displayBase = relabelMap ? (relabelMap[base] || base) : base;
          return `${truncateString(displayBase)}-${suffix}°`;
        }
      }
      if (!relabelMap) {
        return name;
      }
      return truncateString(relabelMap[name] || name);
    },
    [breakString, isPartitionedBySensor, relabelMap]
  );

  const measureLegendLabel = useMemo(() => {
    if (!canvasMeasureRef.current) {
      canvasMeasureRef.current = document.createElement("canvas");
    }
    const context = canvasMeasureRef.current.getContext("2d");
    if (context) {
      context.font = "13px Helvetica, Arial, sans-serif";
      return (text) => context.measureText(text).width;
    }
    return (text) => text.length * 8;
  }, []);

  const createToolTip = useCallback(
    (d) => {
      let xValue;
      const seriesLabel = d.datum.childName || "unknown";
      try {
        if (byDuration) {
          xValue = `${d.datum.x.toFixed(2)} hours elapsed`;
        } else {
          xValue = d.datum.x.format("MMM DD HH:mm");
        }
      } catch {
        xValue = d.datum.x;
      }

      const rounded =
        Math.round(yTransformation(d.datum.y) * 10 ** fixedDecimals) / 10 ** fixedDecimals;
      return `${xValue}\n${seriesLabel}: ${rounded}`;
    },
    [byDuration, fixedDecimals, yTransformation]
  );

  const mapPartitionedSeriesName = useCallback(
    (seriesName) => {
      if (!isPartitionedBySensor) {
        return seriesName;
      }
      const { base, suffix } = splitPartitionedName(seriesName);
      if (!suffix) {
        return seriesName;
      }
      const angle = channelAngleMap[suffix];
      if (!angle) {
        return null;
      }
      return `${base}-${angle}`;
    },
    [channelAngleMap, isPartitionedBySensor]
  );

  const shouldIncludeUnit = useCallback(
    (seriesName) => {
      if (!unit) {
        return true;
      }
      if (!isPartitionedBySensor) {
        return seriesName === unit;
      }
      const { base } = splitPartitionedName(seriesName);
      return base === unit;
    },
    [isPartitionedBySensor, unit]
  );

  const selectLegendData = useCallback(
    (name) => {
      if (!seriesMap[name]) {
        return {};
      }

      const reformattedName = relabelAndFormatSeriesForLegend(name);
      const line = seriesMap[name];
      const item = {
        name: reformattedName,
        symbol: { fill: line?.color },
      };
      if (hiddenSeries.has(reformattedName)) {
        return { ...item, symbol: { fill: "white" } };
      }
      return item;
    },
    [hiddenSeries, relabelAndFormatSeriesForLegend, seriesMap]
  );

  const legendItems = useMemo(
    () => names.map(selectLegendData).filter((item) => item && item.name),
    [names, selectLegendData]
  );

  const legendLayout = useMemo(() => {
    if (!legendItems.length) {
      return { itemsPerRow: 1, rows: 0, rowHeight: 24 };
    }

    const legendPadding = 130; // left + right padding for legend area inside the chart
    const availableWidth = Math.max(200, chartWidth - legendPadding);
    const gutter = 15;
    const symbolWidth = 14; // approx symbol + stroke width

    const estimatedWidths = legendItems.map(
      (item) => measureLegendLabel(item.name) + symbolWidth + gutter + 8
    );
    const avgWidth = estimatedWidths.reduce((sum, width) => sum + width, 0) / estimatedWidths.length;
    const minWidth = Math.max(60, Math.max(...estimatedWidths));
    const targetWidth = Math.max(minWidth, avgWidth + gutter);
    const itemsPerRow = Math.max(
      1,
      Math.min(legendItems.length, Math.floor(availableWidth / targetWidth) || 1)
    );
    const rows = Math.ceil(legendItems.length / itemsPerRow);
    return { itemsPerRow, rows, rowHeight: 24 };
  }, [chartWidth, legendItems, measureLegendLabel]);

  useLayoutEffect(() => {
    const node = chartContainerRef.current;
    if (!node) {
      return undefined;
    }

    const updateWidth = () => {
      const nextWidth = Math.max(400, node.clientWidth || 600);
      setChartWidth(nextWidth);
    };

    updateWidth();
    const resizeObserver = new ResizeObserver(updateWidth);
    resizeObserver.observe(node);
    window.addEventListener("resize", updateWidth);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateWidth);
    };
  }, []);

  const selectVictoryLines = useCallback(
    (name) => {
      const reformattedName = relabelAndFormatSeries(name);
      const series = seriesMap?.[name];
      if (!series) {
        return null;
      }

      let marker = null;
      if (series.data?.length === 1) {
        marker = (
          <VictoryScatter
            size={4}
            key={`line-${reformattedName}${chartKey}`}
            name={reformattedName}
            style={{
              data: {
                fill: series?.color,
              },
            }}
          />
        );
      } else {
        marker = (
          <VictoryLine
            interpolation={interpolation}
            key={`line-${reformattedName}${chartKey}`}
            name={reformattedName}
            style={{
              labels: { fill: series?.color },
              data: {
                stroke: series?.color,
                strokeWidth: 2,
              },
              parent: { border: "1px solid #ccc" },
            }}
          />
        );
      }

      const isHidden = hiddenSeries.has(reformattedName);
      const chartData = isHidden ? [] : series.data;

      return (
        <VictoryGroup
          key={`${chartKey}-${name}`}
          data={chartData}
          x={(datum) => datum.x}
          y={(datum) => yTransformation(datum.y)}
        >
          {marker}
        </VictoryGroup>
      );
    },
    [chartKey, hiddenSeries, interpolation, relabelAndFormatSeries, seriesMap, yTransformation]
  );

  const legendEvents = useMemo(
    () => [
      {
        childName: "legend",
        target: "data",
        eventHandlers: {
          onClick: (_, legendProps) => {
            return [
              {
                childName: legendProps.datum.name,
                target: "data",
                mutation: () => {
                  const seriesName = legendProps.datum.name;
                  setHiddenSeries((prevHidden) => {
                    const next = new Set(prevHidden);
                    if (next.has(seriesName)) {
                      next.delete(seriesName);
                    } else {
                      next.add(seriesName);
                    }
                    return next;
                  });
                  return null;
                },
              },
            ];
          },
        },
      },
    ],
    [setHiddenSeries]
  );

  const triggerBlobDownload = useCallback((blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, []);

  const triggerDataUrlDownload = useCallback((dataUrl, filename) => {
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, []);

  const getDownloadFilename = useCallback(
    (extension) => {
      const slugify = (value) =>
        value
          .toString()
          .trim()
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "");

      const raw = title || chartKey || "chart";
      const safeName = slugify(raw) || "chart";
      const experimentSegment = experiment ? slugify(experiment) : null;
      const timestampSegment = dayjs().utc().format("YYYYMMDD-HHmmss");
      const filenameParts = [safeName];
      if (experimentSegment) {
        filenameParts.push(experimentSegment);
      }
      filenameParts.push(timestampSegment);
      return `${filenameParts.join("-")}.${extension}`;
    },
    [chartKey, experiment, title]
  );

  const addWatermarkToSvg = useCallback((svgElement, width, height) => {
    const watermark = document.createElementNS("http://www.w3.org/2000/svg", "text");
    watermark.textContent = "Prepared via Pioreactor";
    watermark.setAttribute("x", `${width - 8}`);
    watermark.setAttribute("y", `${height - 8}`);
    watermark.setAttribute("text-anchor", "end");
    watermark.setAttribute("fill", "#90a4ae");
    watermark.setAttribute("font-size", "10");
    watermark.setAttribute("font-family", "Helvetica Neue, Helvetica, Arial, sans-serif");
    svgElement.appendChild(watermark);
  }, []);

  const exportChart = useCallback(
    (format) => {
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

      const width = Number(clonedSvg.getAttribute("width")) || svgElement.clientWidth || 600;
      const height = Number(clonedSvg.getAttribute("height")) || svgElement.clientHeight || 400;
      clonedSvg.setAttribute("width", `${width}`);
      clonedSvg.setAttribute("height", `${height}`);
      addWatermarkToSvg(clonedSvg, width, height);

      const serializer = new XMLSerializer();
      const serializedSvg = serializer.serializeToString(clonedSvg);
      const svgWithHeader = `<?xml version="1.0" encoding="utf-8"?>\n${serializedSvg}`;
      const svgBlob = new Blob([svgWithHeader], { type: "image/svg+xml;charset=utf-8" });

      if (format === "svg") {
        triggerBlobDownload(svgBlob, getDownloadFilename("svg"));
        return;
      }

      if (format !== "png") {
        return;
      }

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
    },
    [addWatermarkToSvg, getDownloadFilename, triggerBlobDownload, triggerDataUrlDownload]
  );

  const handleOpenExportMenu = useCallback((event) => {
    setExportAnchorEl(event.currentTarget);
  }, []);

  const handleCloseExportMenu = useCallback(() => {
    setExportAnchorEl(null);
  }, []);

  const handleDownloadSelection = useCallback(
    (format) => {
      setExportAnchorEl(null);
      exportChart(format);
    },
    [exportChart]
  );

  const onMessage = useCallback(
    (incomingTopic, message, packet) => {
      if (!fetched) {
        return;
      }
      if (packet.retain) {
        return;
      }
      if (!message || !incomingTopic) {
        return;
      }

      const payloadString = message.toString();
      if (!payloadString) {
        return;
      }

      let timestamp;
      let yValue;
      try {
        if (payloadKey) {
          const payload = JSON.parse(payloadString);
          if (!Object.prototype.hasOwnProperty.call(payload, payloadKey)) {
            throw new Error(`Payload key '${payloadKey}' not found in the message.`);
          }
          timestamp = dayjs.utc(payload.timestamp);
          yValue = parseFloat(payload[payloadKey]);
        } else {
          yValue = parseFloat(payloadString);
          timestamp = dayjs.utc();
        }
      } catch (error) {
        return;
      }

      const duration = Math.round(
        timestamp.diff(dayjs.utc(experimentStartTime), "hours", true) * 1e3
      ) / 1e3;
      const localTimestamp = timestamp.local();
      const xValue = byDuration ? duration : localTimestamp;

      const baseUnit = incomingTopic.split("/")[1];
      const channel = incomingTopic
        .split("/")[4]
        .replace("raw_od", "")
        .replace("od", "");
      const parsedUnit = isPartitionedBySensor
        ? mapPartitionedSeriesName(`${baseUnit}-${channel}`)
        : baseUnit;

      if (!parsedUnit) {
        return;
      }

      if (unit) {
        if (!shouldIncludeUnit(parsedUnit)) {
          return;
        }
      }

      setSeriesMap((prevMap) => {
        const existingSeries = prevMap[parsedUnit];
        if (!existingSeries) {
          return {
            ...prevMap,
            [parsedUnit]: {
              data: [{ x: xValue, y: yValue }],
              name: parsedUnit,
              color: getUnitColor(parsedUnit),
            },
          };
        }

        return {
          ...prevMap,
          [parsedUnit]: {
            ...existingSeries,
            data: [...(existingSeries.data || []), { x: xValue, y: yValue }],
          },
        };
      });
    },
    [byDuration, experimentStartTime, fetched, getUnitColor, isPartitionedBySensor, mapPartitionedSeriesName, payloadKey, shouldIncludeUnit, unit]
  );

  const getHistoricalDataFromServer = useCallback(async () => {
    if (!experiment) {
      return;
    }

    const queryParams = new URLSearchParams({
      target_points: downSample ? 1400 : 1000000,
      lookback,
    });

    let transformX;
    if (byDuration) {
      const experimentStart = dayjs.utc(experimentStartTime);
      transformX = (x) =>
        Math.round(dayjs.utc(x, "YYYY-MM-DDTHH:mm:ss.SSS").diff(experimentStart, "hours", true) * 1e3) /
        1e3;
    } else {
      transformX = (x) => dayjs.utc(x, "YYYY-MM-DDTHH:mm:ss.SSS").local();
    }

    const basePath = unit
      ? `/api/workers/${unit}/experiments/${experiment}/time_series/${dataSource}`
      : `/api/experiments/${experiment}/time_series/${dataSource}`;
    const columnSegment = dataSourceColumn ? `/${dataSourceColumn}` : "";
    const url = `${basePath}${columnSegment}?${queryParams}`;

    try {
      const response = await fetch(url);
      const data = await response.json();
      const initialSeriesMap = {};
      for (const [index, unitName] of data["series"].entries()) {
        const mappedUnitName = mapPartitionedSeriesName(unitName);
        if (!mappedUnitName) {
          continue;
        }
        if (!shouldIncludeUnit(mappedUnitName)) {
          continue;
        }
        if (data["data"][index].length > 0) {
          initialSeriesMap[mappedUnitName] = {
            data: data["data"][index].map((item) => ({
              y: item.y,
              x: transformX(item.x),
            })),
            name: mappedUnitName,
            color: getUnitColor(mappedUnitName),
          };
        }
      }
      setSeriesMap(initialSeriesMap);
      setFetched(true);
    } catch (error) {
      console.log(error);
      setFetched(true);
    }
  }, [byDuration, dataSource, dataSourceColumn, downSample, experiment, experimentStartTime, getUnitColor, isPartitionedBySensor, lookback, mapPartitionedSeriesName, shouldIncludeUnit, unit]);

  useEffect(() => {
    getHistoricalDataFromServer();
  }, [getHistoricalDataFromServer]);

  useEffect(() => {
    if (!client || !isLiveChart) {
      return undefined;
    }
    const topicPaths = topics.map((topicName) => `pioreactor/+/${experiment}/${topicName}`);
    topicPaths.forEach((topicPath) => {
      subscribeToTopic(topicPath, onMessage, "Chart");
    });
    return () => {
      topicPaths.forEach((topicPath) => {
        unsubscribeFromTopic(topicPath, "Chart");
      });
    };
  }, [client, experiment, isLiveChart, onMessage, subscribeToTopic, topics, unsubscribeFromTopic]);

  const exportMenuOpen = Boolean(exportAnchorEl);
  const chartStateKey = names.join("-");

  const legendRows = legendLayout.rows;
  const legendItemsPerRow = legendLayout.itemsPerRow;
  const legendRowHeight = legendLayout.rowHeight;
  const legendBottomPadding = 40 + legendRows * legendRowHeight;
  const chartHeight = 285 + legendRows * legendRowHeight;

  return (
    <div ref={chartContainerRef} style={{ position: "relative" }}>
      <VictoryChart
        key={chartStateKey}
        style={{ parent: { maxWidth: "700px", width: "100%" } }}
        title={title}
        domainPadding={10}
        padding={{ left: 70, right: 50, bottom: legendBottomPadding, top: 50 }}
        events={legendEvents}
        height={chartHeight}
        width={chartWidth}
        scale={{ x: byDuration ? "linear" : "time" }}
        theme={VictoryTheme.material}
        containerComponent={
          <ChartContainer
            zoomDimension={"x"}
            responsive={true}
            voronoiBlacklist={["parent"]}
            labels={createToolTip}
            labelComponent={
              <VictoryTooltip
                cornerRadius={0}
                flyoutStyle={{
                  fill: "white",
                  stroke: "#90a4ae",
                  strokeWidth: 1.5,
                }}
              />
            }
          />
        }
      >
        <VictoryLabel
          text={title}
          x={360}
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
          offsetY={legendBottomPadding}
          label={byDuration ? "Hours" : "Time"}
          orientation="bottom"
          fixLabelOverlap={true}
          axisLabelComponent={
            <VictoryLabel
              dy={-15}
              x={chartWidth - 12}
              textAnchor="end"
              style={{
                fontSize: 12,
                fontFamily: "inherit",
                fill: "grey",
              }}
            />
          }
        />
        <VictoryAxis
          crossAxis={false}
          dependentAxis
          domain={allowZoom ? null : yAxisDomain}
          tickFormat={(t) => `${t.toFixed(fixedDecimals)}`}
          label={yAxisLabel}
          axisLabelComponent={
            <VictoryLabel
              dy={-41}
              style={{
                fontSize: 15,
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
        <VictoryLegend
          x={65}
          y={285}
          symbolSpacer={6}
          itemsPerRow={legendItemsPerRow}
          name="legend"
          borderPadding={{ right: 8 }}
          orientation="horizontal"
          cursor="pointer"
          gutter={15}
          rowGutter={5}
          style={{
            labels: { fontSize: 13 },
            data: { stroke: "#485157", strokeWidth: 0.5, size: 6.5, cursor: "pointer" },
          }}
          data={legendItems}
          width={chartWidth}
        />
        {names.map(selectVictoryLines)}
      </VictoryChart>
      <IconButton
        aria-label={`download-${chartKey}`}
        size="small"
        onClick={handleOpenExportMenu}
        sx={{
          position: "absolute",
          bottom: 8,
          right: 8,
          backgroundColor: "rgba(255,255,255,0.85)",
          zIndex: 2,
        }}
      >
        <DownloadIcon fontSize="small" />
      </IconButton>
      <Menu
        anchorEl={exportAnchorEl}
        open={exportMenuOpen}
        onClose={handleCloseExportMenu}
        anchorOrigin={{ horizontal: "right", vertical: "top" }}
        transformOrigin={{ horizontal: "right", vertical: "bottom" }}
      >
        <MenuItem onClick={() => handleDownloadSelection("png")}>
          Download PNG
        </MenuItem>
        <MenuItem onClick={() => handleDownloadSelection("svg")}>
          Download SVG
        </MenuItem>
      </Menu>
    </div>
  );
}

export default Chart;
