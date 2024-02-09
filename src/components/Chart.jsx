import React from "react";
import { Client } from "paho-mqtt";
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
import moment from "moment";

const colors = [
  {primary: "#0077BB", "1": "#0077BB", "2": "#0077BB"},
  {primary: "#009988", "1": "#009988", "2": "#009988"},
  {primary: "#CC3311", "1": "#CC3311", "2": "#CC3311"},
  {primary: "#33BBEE", "1": "#33BBEE", "2": "#33BBEE"},
  {primary: "#EE7733", "1": "#EE7733", "2": "#EE7733"},
  {primary: "#EE3377", "1": "#EE3377", "2": "#EE3377"},
  {primary: "#BBBBBB", "1": "#BBBBBB", "2": "#BBBBBB"},
  {primary: "#a6cee3", "1": "#a6cee3", "2": "#a6cee3"},
  {primary: "#1f78b4", "1": "#1f78b4", "2": "#1f78b4"},
  {primary: "#b2df8a", "1": "#b2df8a", "2": "#b2df8a"},
  {primary: "#33a02c", "1": "#33a02c", "2": "#33a02c"},
  {primary: "#fb9a99", "1": "#fb9a99", "2": "#fb9a99"},
  {primary: "#e31a1c", "1": "#e31a1c", "2": "#e31a1c"},
  {primary: "#fdbf6f", "1": "#fdbf6f", "2": "#fdbf6f"},
  {primary: "#ff7f00", "1": "#ff7f00", "2": "#ff7f00"},
  {primary: "#cab2d6", "1": "#cab2d6", "2": "#cab2d6"},
  {primary: "#6a3d9a", "1": "#6a3d9a", "2": "#6a3d9a"},
  {primary: "#ffff99", "1": "#ffff99", "2": "#ffff99"},
  {primary: "#b15928", "1": "#b15928", "2": "#b15928"},
];

const colorMaps = {}
const sensorRe = /(.*)-[12]/;

function getColorFromName(name){
  if (name in colorMaps){
    return colorMaps[name]
  }

  if (sensorRe.test(name)){
    let primaryName = name.match(sensorRe)[1]
    return getColorFromName(primaryName)
  }
  else{
    var newPallete = colors.shift()
    colorMaps[name] = newPallete.primary
    colorMaps[name + "-1"] = newPallete["1"]
    colorMaps[name + "-2"] = newPallete["2"]
    return getColorFromName(name)
  }
}


class Chart extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      seriesMap: {},
      hiddenSeries: new Set(),
      names: [],
      legendEvents: [],
      fetched: false,
    };

    if (Array.isArray(this.props.topic)){
      this.topics = this.props.topic
    } else {
      this.topics = [this.props.topic]
    }


    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
    this.selectLegendData = this.selectLegendData.bind(this);
    this.selectVictoryLines = this.selectVictoryLines.bind(this);
    this.yTransformation = this.props.yTransformation || ((y) => y)
    this.VictoryVoronoiContainer = (this.props.allowZoom  || false) ? createContainer("zoom", "voronoi") : createContainer("voronoi");
  }

  onConnect() {

      this.topics.forEach(topic => {
        this.client.subscribe(`pioreactor/+/${this.props.experiment}/${topic}`);
      });

  }

  componentDidUpdate(prevProps) {
    if (prevProps.experiment !== this.props.experiment) {
      this.getHistoricalDataFromServer()

      if (this.props.isLiveChart){
        try{
          this.topics.forEach(topic => {
            this.client.unsubscribe(`pioreactor/+/${this.props.experiment}/${topic}`);
          });
          this.topics.forEach(topic => {
            this.client.subscribe(`pioreactor/+/${this.props.experiment}/${topic}`);
          });
        }
        catch (error){
          // not important.
        }
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

    if (!this.props.isLiveChart){
      return
    }


    if (!this.props.config || !this.props.config['cluster.topology']){
      return
    }

    if (this.props.config.remote && this.props.config.remote.ws_url) {
      this.client = new Client(
        `${this.props.config.remote.ws_url}/`,
        "webui_Chart" + Math.floor(Math.random()*10000)
      )}
    else {
      this.client = new Client(
        `${this.props.config['cluster.topology']['leader_address']}`, 9001,
        "webui_Chart" + Math.floor(Math.random()*10000)
      );
    }

    this.client.connect({userName: 'pioreactor', password: 'raspberry', keepAliveInterval: 60 * 15,  onSuccess: this.onConnect, reconnect: true});
    this.client.onMessageArrived = this.onMessageArrived;
  }

  async getHistoricalDataFromServer() {
    if (!this.props.experiment){
      return
    }
    const tweak = 0.60 // increase to filter more
    const queryParams = new URLSearchParams({
        filter_mod_N: this.props.downSample ? Math.max(Math.floor(tweak * Math.min(this.props.deltaHours, this.props.lookback)), 1) : 1,
        lookback: this.props.lookback
    })

    var transformX
    if (this.props.byDuration){
      const experimentStartTime = moment.utc(this.props.experimentStartTime)
      transformX = (x) => Math.round(moment.utc(x, 'YYYY-MM-DDTHH:mm:ss.SSSSS').diff(experimentStartTime, 'hours', true) * 1e3)/1e3
    } else {
      transformX = (x) => moment.utc(x, 'YYYY-MM-DDTHH:mm:ss.SSSSS').local()
    }

    await fetch(`/api/time_series/${this.props.dataSource}/${this.props.experiment}${this.props.dataSourceColumn ? "/" + this.props.dataSourceColumn : ""}?${queryParams}`)
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        let initialSeriesMap = {};
        for (const [i, v] of data["series"].entries()) {
          if (data["data"][i].length > 0) {
            initialSeriesMap[v] = {
              data: (data["data"][i]).map(item => ({y: item.y, x: transformX(item.x) })),
              name: v,
              color: getColorFromName(v),
            };
          }
        }
        let names = Object.keys(initialSeriesMap);
        this.setState({
          seriesMap: initialSeriesMap,
          legendEvents: this.createLegendEvents(),
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

  deleteAndReturnSet(set, value){
    set.delete(value)
    return set
  }

  createLegendEvents() {
    return [{
      childName: "legend",
      target: "data",
      eventHandlers: {
        onClick: (_, props) => {
          return [
            {
              childName: props.datum.name,
              target: "data",
              eventKey: "all",
              mutation: () => {
                if (!this.state.hiddenSeries.has(props.datum.name)) {
                  // Was not already hidden => add to set
                  this.setState((prevState) => ({
                    hiddenSeries: prevState.hiddenSeries.add(props.datum.name)
                  }));
                } else {
                  // remove from set
                  this.setState((prevState) => ({
                    hiddenSeries: this.deleteAndReturnSet(prevState.hiddenSeries, props.datum.name)
                  }));
                }
                return null;
              },
            },
          ];
        },
      },
    }]
  }

  onMessageArrived(message) {
    if (!this.state.fetched){
      return
    }
    if (message.retained){
      return
    }

    if (!message.payloadString){
      return
    }

    if (this.props.payloadKey){
      var payload = JSON.parse(message.payloadString)
      var timestamp = moment.utc(payload.timestamp)
      var y_value = parseFloat(payload[this.props.payloadKey])
    } else {
      y_value = parseFloat(message.payloadString)
      timestamp = moment.utc()
    }
    var duration = Math.round(timestamp.diff(moment.utc(this.props.experimentStartTime), 'hours', true) * 1e3)/1e3
    var local_timestamp = timestamp.local()
    const x_value = this.props.byDuration ? duration : local_timestamp

    var key = this.props.isPartitionedBySensor
      ? message.topic.split("/")[1] + "-" + (message.topic.split("/")[4]).replace('od', '')
      : message.topic.split("/")[1];

    try {
      if (!(key in this.state.seriesMap)){
        const newSeriesMap = {...this.state.seriesMap, [key]:  {
          data: [{x: x_value, y: y_value}],
          name: key,
          color: getColorFromName(key)
        }}

        this.setState({ seriesMap: newSeriesMap })
        this.setState({
          names: [...this.state.names, key]
        })
      } else {
        // .push seems like bad state management, and maybe a hit to performance...
        this.state.seriesMap[key].data.push({
          x: x_value,
          y: y_value,
        });
        this.setState({ seriesMap: this.state.seriesMap })
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

  breakString(string){
    if (string.length > 12){
      return string.slice(0, 5) + "..." + string.slice(string.length-2, string.length)
    }
    return string
  }

  relabelAndFormatSeries(name){
    if (!this.props.relabelMap){
      return name
    }

    if (name.match(/(.*)-([12])/g)){
      const results = name.match(/(.*)-([12])/);
      const index = results[1];
      const sensor = results[2];
      return this.breakString(this.props.relabelMap[index] || index) + "-ch" + sensor
    }
    else {
      return this.breakString(this.props.relabelMap[name] || name)
    }
  }

  createToolTip = (d) => {
    var x_value
    if (this.props.byDuration) {
      x_value = `${d.datum.x.toFixed(2)} hours elapsed`
    } else {
      x_value = d.datum.x.format("MMM DD HH:mm")
    }

    return `${x_value}
${this.relabelAndFormatSeries(d.datum.childName)}: ${Math.round(this.yTransformation(d.datum.y) * 10 ** this.props.fixedDecimals) / 10 ** this.props.fixedDecimals}`
  }


  selectLegendData(name){
    var reformattedName = this.relabelAndFormatSeries(name)
    if (!this.state.seriesMap) {
      return {}
    }
    const line = this.state.seriesMap[name];
    const item = {
      name: reformattedName,
      symbol: { fill: line.color },
    };
    if (this.state.hiddenSeries.has(reformattedName)) {
      return { ...item, symbol: { fill: "white" } };
    }
    return item;
  }

  selectVictoryLines(name) {
    var reformattedName = this.relabelAndFormatSeries(name)

    var marker = null;
    if (this.state.seriesMap[name].data.length === 1){
      marker = <VictoryScatter
          size={4}
          key={"line-" + reformattedName + this.props.chartKey}
          name={reformattedName}
          style={{
            data: {
              fill: this.state.seriesMap[name].color
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
            labels: {fill: this.state.seriesMap[name].color},
            data: {
              stroke: this.state.seriesMap[name].color,
              strokeWidth: 2,
            },
            parent: { border: "1px solid #ccc" },
          }}
        />
    }

    return (
      <VictoryGroup
        key={this.props.chartKey}
        data={(this.state.hiddenSeries.has(reformattedName)) ? [] : this.state.seriesMap[name].data}
        x={(datum) => this.xTransformation(datum.x)}
        y={(datum) => this.yTransformation(datum.y)}
      >
        {marker}

      </VictoryGroup>
    );
  }

  render() {
    return (
        <VictoryChart
          style={{ parent: { maxWidth: "700px"}}}
          title={this.props.title}
          domainPadding={10}
          padding={{ left: 70, right: 50, bottom: 80, top: 50 }}
          events={this.state.legendEvents}
          height={315}
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
            offsetY={80}
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
            y={270}
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
              data: { stroke: "#485157", strokeWidth: 0.5, size: 6.5 },
            }}
            data={this.state.names.map(this.selectLegendData)}
          />
          {Object.keys(this.state.seriesMap).map(this.selectVictoryLines)}
        </VictoryChart>
    );
  }
}

export default Chart;
