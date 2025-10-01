import React from "react";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
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

const sensorRe = /(.*)-[12]/;


function toArray(thing){
   if (Array.isArray(thing)){
      return thing
  } else {
    return [thing]
  }
}


class Chart extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      seriesMap: {},
      hiddenSeries: new Set(),
      names: [],
      fetched: false,
      exportAnchorEl: null,
    };

    this.topics = toArray(this.props.topic)
    this.subscribedTopics = []
    this.onMessage = this.onMessage.bind(this);
    this.selectLegendData = this.selectLegendData.bind(this);
    this.selectVictoryLines = this.selectVictoryLines.bind(this);
    this.createLegendEvents = this.createLegendEvents.bind(this);
    this.yTransformation = this.props.yTransformation || ((y) => y)
    this.VictoryVoronoiContainer = (this.props.allowZoom  || false) ? createContainer("zoom", "voronoi") : createContainer("voronoi");
    this.chartContainerRef = React.createRef();
    this.handleOpenExportMenu = this.handleOpenExportMenu.bind(this);
    this.handleCloseExportMenu = this.handleCloseExportMenu.bind(this);
    this.handleDownloadSelection = this.handleDownloadSelection.bind(this);
  }

  componentDidUpdate(prevProps) {

    // the client is connected async, so we need to set this up when it is connected
    if (!prevProps.client && this.props.client && this.props.isLiveChart) {
      const topicPaths = this.topics.map(topic =>
        `pioreactor/+/${this.props.experiment}/${topic}`
      )
      topicPaths.forEach(topic => {
        this.props.subscribeToTopic(topic, this.onMessage, "Chart")
      })
      this.subscribedTopics = topicPaths
      return
    }

    const experimentChanged = prevProps.experiment !== this.props.experiment
    const topicChanged = prevProps.topic !== this.props.topic
    if (experimentChanged || topicChanged) {
      this.getHistoricalDataFromServer()
      if (this.props.isLiveChart && this.props.client){
        this.subscribedTopics.forEach(topic => {
          this.props.unsubscribeFromTopic(topic, "Chart")
        })

        this.topics = toArray(this.props.topic)
        const newTopics = this.topics.map(topic => `pioreactor/+/${this.props.experiment}/${topic}`)
        newTopics.forEach(topic => {
          this.props.subscribeToTopic(topic, this.onMessage, "Chart")
        })
        this.subscribedTopics = newTopics
      }
    }

    if (this.props.byDuration !== prevProps.byDuration){
      this.getHistoricalDataFromServer()
    }

    if (this.props.lookback !== prevProps.lookback){
      this.getHistoricalDataFromServer()
    }



  }

  componentDidMount() {
    this.getHistoricalDataFromServer()
    if (this.props.client && this.props.isLiveChart) {
      const topicPaths = this.topics.map(topic => `pioreactor/+/${this.props.experiment}/${topic}`)
      topicPaths.forEach(topic => {
        this.props.subscribeToTopic(topic, this.onMessage, "Chart")
      })
      this.subscribedTopics = topicPaths
    }
  }

  componentWillUnmount() {
    if (this.props.client) {
      this.subscribedTopics.forEach(topic => {
        this.props.unsubscribeFromTopic(topic, "Chart")
      })
    }
  }


  async getHistoricalDataFromServer() {
    if (!this.props.experiment){
      return
    }

    const queryParams = new URLSearchParams({
        // 720 is equal to running od reading at 5s interval for 1 hour, a reasonable default.
        target_points: this.props.downSample ? 720 : 10000000, // # todo: scale with number of units - however I don't know how many units until I get back the result...
        lookback: this.props.lookback
    })

    var transformX
    if (this.props.byDuration){
      const experimentStartTime = dayjs.utc(this.props.experimentStartTime)
      transformX = (x) => Math.round(dayjs.utc(x, 'YYYY-MM-DDTHH:mm:ss.SSS').diff(experimentStartTime, 'hours', true) * 1e3)/1e3
    } else {
      transformX = (x) => dayjs.utc(x, 'YYYY-MM-DDTHH:mm:ss.SSS').local()
    }

    var url;
    if (this.props.unit){
      url = `/api/workers/${this.props.unit}/experiments/${this.props.experiment}/time_series/${this.props.dataSource}${this.props.dataSourceColumn ? "/" + this.props.dataSourceColumn : ""}?${queryParams}`
    }
    else {
      url = `/api/experiments/${this.props.experiment}/time_series/${this.props.dataSource}${this.props.dataSourceColumn ? "/" + this.props.dataSourceColumn : ""}?${queryParams}`
    }

    await fetch(url)
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        let initialSeriesMap = {};
        for (const [i, unit] of data["series"].entries()) {

          if (this.props.unit){
            if (this.props.isPartitionedBySensor && ((unit !== this.props.unit + "-2") && (unit !== this.props.unit + "-1"))){
              continue
            }
            else if (!this.props.isPartitionedBySensor && unit !== this.props.unit){
              continue
            }
          }
          if (data["data"][i].length > 0) {
            initialSeriesMap[unit] = {
              data: (data["data"][i]).map(item => ({y: item.y, x: transformX(item.x) })),
              name: unit,
              color: this.getUnitColor(unit),
            };
          }
        }
        let names = Object.keys(initialSeriesMap);
        this.setState({
          seriesMap: initialSeriesMap,
          names: names,
          fetched: true
        });
      })
      .catch((e) => {
        console.log(e)
        this.setState({fetched: true})
      });
      this.forceUpdate()

  }

  getUnitColor(name){
    if (sensorRe.test(name)){
      let primaryName = name.match(sensorRe)[1]
      return this.getUnitColor(primaryName)
    } else {
      if (this.props.unitsColorMap){
        return this.props.unitsColorMap[name]
      } else {
        return
      }
    }
  }

  createLegendEvents() {
    return [
      {
        childName: "legend",
        target: "data",
        eventHandlers: {
          onClick: (_, props) => {
            return [
              {
                childName: props.datum.name,
                target: "data",
                mutation: () => {
                  const seriesName = props.datum.name;
                  this.setState((prevState) => {
                    const hiddenSeries = new Set(prevState.hiddenSeries);
                    if (hiddenSeries.has(seriesName)) {
                      hiddenSeries.delete(seriesName);
                    } else {
                      hiddenSeries.add(seriesName);
                    }
                    return { hiddenSeries };
                  });
                  return null;
                },
              },
            ];
          },
        },
      },
    ];
  }

  handleOpenExportMenu(event) {
    this.setState({ exportAnchorEl: event.currentTarget });
  }

  handleCloseExportMenu() {
    this.setState({ exportAnchorEl: null });
  }

  handleDownloadSelection(format) {
    this.setState({ exportAnchorEl: null }, () => {
      this.exportChart(format);
    });
  }

  getDownloadFilename(extension) {
    const slugify = (value) =>
      value
        .toString()
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");

    const raw = this.props.title || this.props.chartKey || "chart";
    const safeName = slugify(raw) || "chart";
    const experimentSegment = this.props.experiment ? slugify(this.props.experiment) : null;
    const timestampSegment = dayjs().utc().format("YYYYMMDD-HHmmss");
    const filenameParts = [safeName];
    if (experimentSegment) {
      filenameParts.push(experimentSegment);
    }
    filenameParts.push(timestampSegment);
    return `${filenameParts.join("-")}.${extension}`;
  }

  exportChart(format) {
    const container = this.chartContainerRef.current;
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
    const svgWithHeader = `<?xml version="1.0" encoding="utf-8"?>\n${serializedSvg}`;
    const svgBlob = new Blob([svgWithHeader], { type: "image/svg+xml;charset=utf-8" });

    if (format === "svg") {
      this.triggerBlobDownload(svgBlob, this.getDownloadFilename("svg"));
      return;
    }

    if (format !== "png") {
      return;
    }

    const width = Number(clonedSvg.getAttribute("width")) || svgElement.clientWidth || 600;
    const height = Number(clonedSvg.getAttribute("height")) || svgElement.clientHeight || 400;
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
      this.triggerDataUrlDownload(dataUrl, this.getDownloadFilename(format));
      URL.revokeObjectURL(url);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
    };
    image.src = url;
  }

  triggerBlobDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  triggerDataUrlDownload(dataUrl, filename) {
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  onMessage(topic, message, packet) {
    if (!this.state.fetched){
      return
    }
    if (packet.retain){
      return
    }

    if (!message || !topic) return;


    if (!message.toString()){
      return
    }

    try {
        if (this.props.payloadKey) {
            var payload = JSON.parse(message.toString());
            if (!payload.hasOwnProperty(this.props.payloadKey)) {
                throw new Error(`Payload key '${this.props.payloadKey}' not found in the message.`);
            }
            var timestamp = dayjs.utc(payload.timestamp);
            var y_value = parseFloat(payload[this.props.payloadKey]);
        } else {
            var y_value = parseFloat(message.toString());
            var timestamp = dayjs.utc();
        }
    } catch (error) {
        // Exit or handle the error appropriately
        return;
    }
    var duration = Math.round(timestamp.diff(dayjs.utc(this.props.experimentStartTime), 'hours', true) * 1e3)/1e3
    var local_timestamp = timestamp.local()
    const x_value = this.props.byDuration ? duration : local_timestamp
    var unit = this.props.isPartitionedBySensor
      ? topic.split("/")[1] + "-" + (topic.split("/")[4]).replace('raw_od', '').replace('od', '')
      : topic.split("/")[1];

    if (this.props.unit){
      if (this.props.isPartitionedBySensor && ((unit !== this.props.unit + "-2") && (unit !== this.props.unit + "-1"))){
        return
      }
      else if (!this.props.isPartitionedBySensor && unit !== this.props.unit){
        return
      }
    }

    try {
      if (!(unit in this.state.seriesMap)) {
        const newSeriesMap = {
          ...this.state.seriesMap,
          [unit]: {
            data: [{ x: x_value, y: y_value }],
            name: unit,
            color: this.getUnitColor(unit),
          },
        };
        this.setState({ seriesMap: newSeriesMap, names: [...this.state.names, unit] });
      } else {
        this.state.seriesMap[unit].data.push({
          x: x_value,
          y: y_value,
        });
        this.setState({ seriesMap: this.state.seriesMap });
      }
    }
    catch (error) {
      console.log(error)
    }
    return;
  }

  xTransformation(x){
    return x
  }

  breakString = (n) => (string) => {
    if (string.length > n){
      return string.slice(0, n-5) + "..." + string.slice(string.length-2, string.length)
    }
    return string
  }

  relabelAndFormatSeries(name){
    if (!this.props.relabelMap){
      return name
    }

    const regexResults = name.match(/(.*)-([12])/);
    if (regexResults) {
      const [_, mainPart, sensor] = regexResults;
      return `${this.breakString(12)(this.props.relabelMap[mainPart] || mainPart)}-ch${sensor}`;
    } else {
      return this.breakString(12)(this.props.relabelMap[name] || name);
    }
  }

  createToolTip = (d) => {
    var x_value
    let seriesLabel = d.datum.childName || "unknown";
    try {
      if (this.props.byDuration) {
        x_value = `${d.datum.x.toFixed(2)} hours elapsed`
      } else {
        x_value = d.datum.x.format("MMM DD HH:mm")
      }
    } catch {
      x_value = d.datum.x
    }

    return `${x_value}
${this.relabelAndFormatSeries(seriesLabel)}: ${Math.round(this.yTransformation(d.datum.y) * 10 ** this.props.fixedDecimals) / 10 ** this.props.fixedDecimals}`
  }


  relabelAndFormatSeriesForLegend(name){
    if (!this.props.relabelMap){
      return name
    }

    const nElements = Object.keys(this.props.relabelMap).length;
    let truncateString = this.breakString( Math.floor(100 / nElements) )

    const regexResults = name.match(/(.*)-([12])/);
    if (regexResults) {
      const [_, mainPart, sensor] = regexResults;
      return `${truncateString(this.props.relabelMap[mainPart] || mainPart)}-ch${sensor}`;
    } else {
      return truncateString(this.props.relabelMap[name] || name);
    }
  }


  selectLegendData(name){
    if (Object.keys(this.state.seriesMap).length === 0) {
      return {}
    } else if (!(name in this.state.seriesMap)){
      return {}
    }

    var reformattedName = this.relabelAndFormatSeriesForLegend(name)
    const line = this.state.seriesMap[name];
    const item = {
      name: reformattedName,
      symbol: { fill: line?.color },
    };
    if (this.state.hiddenSeries.has(reformattedName)) {
      return { ...item, symbol: { fill: "white" } };
    }
    return item;
  }

  selectVictoryLines(name) {
    var reformattedName = this.relabelAndFormatSeries(name)

    var marker = null;
    if (this.state.seriesMap?.[name]?.data?.length === 1){
      marker = <VictoryScatter
          size={4}
          key={"line-" + reformattedName + this.props.chartKey}
          name={reformattedName}
          style={{
            data: {
              fill: this.state.seriesMap?.[name]?.color
            },
          }}
        />
    }
    else {
        marker = <VictoryLine
          interpolation={this.props.interpolation}
          key={"line-" + reformattedName + this.props.chartKey}
          name={reformattedName}
          style={{
            labels: {fill: this.state.seriesMap?.[name]?.color},
            data: {
              stroke: this.state.seriesMap?.[name]?.color,
              strokeWidth: 2,
            },
            parent: { border: "1px solid #ccc" },
          }}
        />
    }

    return (
      <VictoryGroup
        key={this.props.chartKey}
        data={(this.state.hiddenSeries.has(reformattedName)) ? [] : this.state.seriesMap?.[name]?.data}
        x={(datum) => this.xTransformation(datum.x)}
        y={(datum) => this.yTransformation(datum.y)}
      >
        {marker}

      </VictoryGroup>
    );
  }

  render() {
    const legendEvents = this.createLegendEvents();
    const chartKey = this.state.names.join('-');
    const exportMenuOpen = Boolean(this.state.exportAnchorEl);
    return (
      <div ref={this.chartContainerRef} style={{ position: "relative" }}>
        <VictoryChart
          key={chartKey}
          style={{ parent: { maxWidth: "700px"}}}
          title={this.props.title}
          domainPadding={10}
          padding={{ left: 70, right: 50, bottom: 40 + 25 * Math.ceil(this.state.names.length / 4), top: 50 }}
          events={legendEvents}
          height={285 + 25 * Math.ceil(this.state.names.length / 4)}
          width={600}
          scale={{x: this.props.byDuration ? 'linear' : "time"}}
          theme={VictoryTheme.material}
          containerComponent={
           <this.VictoryVoronoiContainer
             zoomDimension={'x'}
             responsive={true}
             voronoiBlacklist={['parent']}
             labels={this.createToolTip}
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
            text={this.props.title}
            x={300}
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
            offsetY={40 + 25 * Math.ceil(this.state.names.length / 4)}
            label={this.props.byDuration ? "Hours" : "Time"}
            orientation="bottom"
            fixLabelOverlap={true}
            axisLabelComponent={
              <VictoryLabel
                dy={-15}
                dx={262}
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
            domain={this.props.allowZoom ? null : this.props.yAxisDomain}
            tickFormat={(t) => `${t.toFixed(this.props.fixedDecimals)}`}
            label={this.props.yAxisLabel}
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
            itemsPerRow={4}
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
            data={this.state.names.map(this.selectLegendData).filter(item => item && item.name)}
          />
          {Object.keys(this.state.seriesMap).map(this.selectVictoryLines)}
        </VictoryChart>
          <IconButton
            aria-label={`download-${this.props.chartKey}`}
            size="small"
            onClick={this.handleOpenExportMenu}
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
          anchorEl={this.state.exportAnchorEl}
          open={exportMenuOpen}
          onClose={this.handleCloseExportMenu}
          anchorOrigin={{ horizontal: "right", vertical: "top" }}
          transformOrigin={{ horizontal: "right", vertical: "bottom" }}
        >
          <MenuItem onClick={() => this.handleDownloadSelection('png')}>
            Download PNG
          </MenuItem>
          <MenuItem onClick={() => this.handleDownloadSelection('svg')}>
            Download SVG
          </MenuItem>
        </Menu>
      </div>
    );
  }
}

export default Chart;
