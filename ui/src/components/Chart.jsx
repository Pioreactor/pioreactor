import React from "react";
import { Client } from "paho-mqtt";
import {
  VictoryChart,
  VictoryLabel,
  VictoryAxis,
  VictoryTheme,
  VictoryLine,
  VictoryLegend,
  createContainer,
  VictoryTooltip,
} from "victory";
import moment from "moment";
import Card from "@material-ui/core/Card";

const colors = {
  1: "#087e8b",
  "1-A": "#087e8b",
  "1-B": "#08278C",

  2: "#bfd7ea",
  "2-A": "#bfd7ea",
  "2-B": "#C3BEEA",

  3: "#ff5a5f",
  "3-A": "#ff5a5f",
  "3-B": "#FF5CCE",
};

function linspace(startValue, stopValue, cardinality) {
  var arr = [];
  var step = (stopValue - startValue) / (cardinality - 1);
  for (var i = 0; i < cardinality; i++) {
    arr.push(startValue + step * i);
  }
  return arr;
}

class Chart extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      seriesMap: {},
      maxTimestamp: parseInt(moment().format("x")),
      hiddenSeries: new Set(),
      lastMsgRecievedAt: parseInt(moment().format("x")),
      names: [],
      legendEvents: [],
      minTimestamp: 0,
    };
    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
    this.experiment = "Trial-22-a3cfb599c7ea4693a8e6c4b5f4f6e240";
  }

  onConnect() {
    this.client.subscribe(
      ["morbidostat", "+", this.experiment, this.props.topic].join("/")
    );
  }

  componentDidMount() {
    this.getData();
    this.client = new Client(
      "ws://morbidostatws.ngrok.io/",
      "client" + Math.random()
    );
    this.client.connect({ onSuccess: this.onConnect });
    this.client.onMessageArrived = this.onMessageArrived;
  }

  async getData() {
    await fetch(this.props.dataFile)
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        data = data[0];
        let initialSeriesMap = {};
        for (const [i, v] of data["series"].entries()) {
          if (data["data"][i].length > 0) {
            initialSeriesMap[v] = {
              data: data["data"][i],
              name: v,
              color: colors[v],
            };
          }
        }
        let names = Object.keys(initialSeriesMap);
        let mts = Math.min(
          ...Object.values(initialSeriesMap).map((s) => parseInt(s.data[0].x))
        );
        this.setState({
          seriesMap: initialSeriesMap,
          legendEvents: this.createLegendEvents(names),
          names: names,
          minTimestamp: mts,
        });
      });
  }

  createLegendEvents(names) {
    return names.map((name, idx) => {
      return {
        childName: ["legend"],
        target: "data",
        eventKey: String(idx),
        eventHandlers: {
          onClick: () => {
            return [
              {
                childName: ["line-" + name],
                target: "data",
                eventKey: "all",
                mutation: () => {
                  if (!this.state.hiddenSeries.delete(name)) {
                    // Was not already hidden => add to set
                    this.state.hiddenSeries.add(name);
                  }
                  this.setState({
                    hiddenSeries: new Set(this.state.hiddenSeries),
                  });
                  return null;
                },
              },
            ];
          },
        },
      };
    });
  }

  onMessageArrived(message) {
    const currentTime = parseInt(moment().format("x"));

    var key = this.props.isODReading
      ? message.topic.split("/")[1] + "-" + message.topic.split("/")[5]
      : message.topic.split("/")[1];

    this.state.seriesMap[key].data.push({
      x: currentTime,
      y: parseFloat(message.payloadString),
    });
    this.setState({
      seriesMap: this.state.seriesMap,
      maxTimestamp: currentTime,
      lastMsgRecievedAt: currentTime,
    });
    return;
  }

  render() {
    let delta_ts = moment(this.state.maxTimestamp, "x").diff(
      moment(this.state.minTimestamp, "x"),
      "hours"
    );
    let axis_display_ts_format =
      delta_ts >= 16 ? (delta_ts >= 5 * 24 ? "MMM DD" : "dd HH:mm") : "H:mm";
    let tooltip_display_ts_format =
      delta_ts >= 16
        ? delta_ts >= 5 * 24
          ? "MMM DD HH:mm"
          : "dd HH:mm"
        : "H:mm";

    const VictoryZoomVoronoiContainer = createContainer("zoom", "voronoi");
    var tv = linspace(
      this.state.minTimestamp,
      this.state.maxTimestamp + 100000,
      7
    ).map((x) =>
      moment(Math.round(x), "x").startOf(delta_ts >= 16 ? "hour" : "minute")
    );
    return (
      <Card>
        <VictoryChart
          title={this.props.title}
          domainPadding={10}
          padding={{ left: 70, right: 80, bottom: 50, top: 50 }}
          width={600}
          height={285}
          events={this.state.legendEvents}
          responsive={false}
          theme={VictoryTheme.material}
          containerComponent={
            <VictoryZoomVoronoiContainer
              zoomDimension="x"
              labels={(d) => `${moment(d.datum.x, "x").format(
                tooltip_display_ts_format
              )}
${Math.round(d.datum.y * 1000) / 1000}`}
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
              fontSize: 15 * this.props.fontScale,
              fontFamily: "inherit",
            }}
          />
          <VictoryAxis
            tickFormat={(mt) => mt.format(axis_display_ts_format)}
            tickValues={tv}
            style={{
              tickLabels: {
                fontSize: 13 * this.props.fontScale,
                padding: 5,
                fontFamily: "inherit",
              },
            }}
            offsetY={50}
            orientation="bottom"
          />
          <VictoryAxis
            crossAxis={false}
            dependentAxis
            label={this.props.yAxisLabel}
            axisLabelComponent={
              <VictoryLabel
                dy={-40}
                style={{
                  fontSize: 15 * this.props.fontScale,
                  padding: 10,
                  fontFamily: "inherit",
                }}
              />
            }
            style={{
              tickLabels: {
                fontSize: 13 * this.props.fontScale,
                padding: 5,
                fontFamily: "inherit",
              },
            }}
          />
          <VictoryLegend
            x={527}
            y={60}
            name={"legend"}
            borderPadding={{ right: 8 }}
            orientation="vertical"
            cursor={"pointer"}
            style={{
              border: { stroke: "#90a4ae" },
              labels: { fontSize: 13 * this.props.fontScale },
              data: { stroke: "black", strokeWidth: 1, size: 6 },
            }}
            data={this.state.names.map((name) => {
              const line = this.state.seriesMap[name];
              const item = {
                name: line.name,
                symbol: { fill: line.color, type: "square" },
              };
              if (this.state.hiddenSeries.has(name)) {
                return { ...item, symbol: { fill: "white", type: "square" } };
              }
              return item;
            })}
          />
          {Object.keys(this.state.seriesMap).map((name) => {
            if (this.state.hiddenSeries.has(name)) {
              return undefined;
            }
            return (
              <VictoryLine
                interpolation={this.props.interpolation}
                key={"line-" + name}
                name={"line-" + name}
                style={{
                  data: {
                    stroke: this.state.seriesMap[name].color,
                    strokeWidth: 2,
                  },
                  parent: { border: "1px solid #ccc" },
                }}
                data={this.state.seriesMap[name].data}
                x="x"
                y="y"
              />
            );
          })}
        </VictoryChart>
      </Card>
    );
  }
}

export default Chart;
