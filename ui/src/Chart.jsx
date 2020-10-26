import React from 'react';
import {VictoryChart, VictoryLabel, VictoryAxis, VictoryTheme, VictoryLine, VictoryLegend, createContainer, VictoryTooltip} from 'victory';
import moment from 'moment';
import Card from '@material-ui/core/Card';

const colors = {
  "1": "#087e8b",
  "1-A": "#088C41",
  "1-B": "#08278C",

  "2": "#bfd7ea",
  "2-A": "#BEEAE0",
  "2-B": "#C3BEEA",

  "3": "#ff5a5f",
  "3-A": "#FFC35C",
  "3-B": "#FF5CCE",
}

function linspace(startValue, stopValue, cardinality) {
  var arr = [];
  var step = (stopValue - startValue) / (cardinality - 1);
  for (var i = 0; i < cardinality; i++) {
    arr.push(startValue + (step * i));
  }
  return arr;
}

class Chart extends React.Component {
  render() {
    let lines = [];
    let names = this.props.chart_data["series"];
    let nLines = names.length;
    let x_y_data = this.props.chart_data["data"];
    let interpolation = this.props.interpolation

    let min_timestamp = x_y_data[0][0]['x']
    let max_timestamp = x_y_data[0].slice(-1)[0]['x']
    let delta_ts = moment(max_timestamp, 'x').diff(moment(min_timestamp,'x'), 'hours')
    let axis_display_ts_format = ((delta_ts >= 16)
      ?  ((delta_ts >= 5 * 24) ? 'MMM DD' : 'dd HH:mm') : 'H:mm'
    )
    let tooltip_display_ts_format = ((delta_ts >= 16)
      ?  ((delta_ts >= 5 * 24) ? 'MMM DD HH:mm' : 'dd HH:mm') : 'H:mm'
    )

    const VictoryZoomVoronoiContainer = createContainer("zoom", "voronoi");

    for (let i = 0; i < nLines; i++) {
      let name = names[i]
      if (name === "1") {
        lines.push(
            <VictoryLine
              interpolation={interpolation}
              key={name}
              style={{
                data: { stroke: colors[name], strokeWidth: 2 },
                parent: { border: "1px solid #ccc"}
              }}
              data={x_y_data[i]}
              x="x"
              y="y"
            />
          )
      }
    }
    return (
      <Card>
      <VictoryChart
        title={this.props.title}
        domainPadding={10}
        padding={{left: 70, right:80, bottom: 50, top: 50}}
        width={600} height={300}
        responsive={false}
        theme={VictoryTheme.material}
        containerComponent={
          <VictoryZoomVoronoiContainer
            labels={(d) => `${moment(d.datum.x, 'x').format(tooltip_display_ts_format)}
${Math.round(d.datum.y * 1000)/1000}`}
            labelComponent={<VictoryTooltip cornerRadius={0} flyoutStyle={{fill: "white", "stroke": "#90a4ae", strokeWidth: 1.5}}/>}
          />
        }
        >
        <VictoryLabel text={this.props.title} x={300} y={30} textAnchor="middle" style={{fontSize: 15 * this.props.fontScale}}/>
        <VictoryAxis
          tickFormat={(mt) => mt.format(axis_display_ts_format)}
          tickValues={linspace(min_timestamp, max_timestamp + 100000, 7).map(x => moment(x, 'x').startOf(((delta_ts >= 16) ? 'hour' : 'minute')))}
          style={{
            tickLabels: {fontSize: 13 * this.props.fontScale, padding: 5}
          }}
          offsetY={50}
        />
        <VictoryAxis
          dependentAxis
          label={this.props.yAxisLabel}
          axisLabelComponent={<VictoryLabel  dy={-40} style={{fontSize: 15 * this.props.fontScale, padding:10}}/>}
          style={{
            tickLabels: {fontSize: 13 * this.props.fontScale, padding: 5}
          }}
        />
        <VictoryLegend x={520} y={100}
          borderPadding={{right: 10}}
          orientation="vertical"
          style={{
            border: { stroke: "#90a4ae" },
            labels: { fontSize: 13 * this.props.fontScale },
            data: { stroke: "black", strokeWidth: 1 },
          }}
          data={names.map((n, i) => ({name: n, symbol: {fill: colors[n]}}))}
        />
      {lines}
    </VictoryChart>
    </Card>
    )
  }
}

export default Chart;
