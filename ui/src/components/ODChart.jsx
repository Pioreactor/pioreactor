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


class ODChart extends React.Component {
  render() {
    let lines = [];
    let names = this.props.chartData["series"];
    let nLines = names.length;
    let x_y_data = this.props.chartData["data"];

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
      lines.push(
          <VictoryLine
            key={name}
            style={{
              data: { stroke: colors[name], strokeWidth: 3 },
              parent: { border: "1px solid #ccc"}
            }}
            data={x_y_data[i]}
            x="x"
            y="y"
          />
        )
    }
    return (
      <Card>
      <VictoryChart
        title={this.props.title}
        domainPadding={10}
        padding={{left: 110, right:20, bottom: 100, top: 20}}
        width={600}
        responsive={false}
        theme={VictoryTheme.material}
        containerComponent={
          <VictoryZoomVoronoiContainer
            labels={(d) => `${moment(d.datum.x, 'x').format(tooltip_display_ts_format)}
${Math.round(d.datum.y * 1000)/1000}`}
            labelComponent={<VictoryTooltip
              cornerRadius={0}
              flyoutStyle={{fill: "white", "stroke": "#90a4ae", strokeWidth: 1.5}}
              style={{ fontSize: 10 * this.props.fontScale}}
              />}
          />
        }
        >
        <VictoryLabel text={this.props.title} x={350} y={20} textAnchor="middle" style={{fontSize: 13 * this.props.fontScale}}/>
        <VictoryAxis
          tickFormat={(mt) => mt.format(axis_display_ts_format)}
          tickValues={linspace(min_timestamp, max_timestamp + 100000, 4).map(x => moment(x, 'x').startOf(((delta_ts >= 16) ? 'hour' : 'minute')))}
          style={{
            tickLabels: {fontSize: 13 * this.props.fontScale, padding: 5}
          }}
          offsetY={100}
        />
        <VictoryAxis
          dependentAxis
          label={this.props.yAxisLabel}
          axisLabelComponent={<VictoryLabel  dy={-50} style={{fontSize: 15 * this.props.fontScale, padding:10}}/>}
          style={{
            tickLabels: {fontSize: 13 * this.props.fontScale, padding: 5}
          }}
        />
        <VictoryLegend x={200} y={290}
          borderPadding={{right: 10}}
          orientation="horizontal"
          style={{
            border: { stroke: "#90a4ae" },
            labels: { fontSize: 13 * this.props.fontScale },
            data: { stroke: "black", strokeWidth: 1 },
          }}
          gutter={30}
          data={names.map((n, i) => ({name: n, symbol: {fill: colors[n]}}))}
        />
      {lines}
    </VictoryChart>
    </Card>
    )
  }
}

export default ODChart
;
