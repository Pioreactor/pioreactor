import React from 'react';
import {VictoryChart, VictoryLabel, VictoryAxis, VictoryTheme, VictoryLine, VictoryLegend, VictoryVoronoiContainer, VictoryTooltip} from 'victory';
import moment from 'moment';
import {Client, Message} from 'paho-mqtt';

import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/Card';

import {Typography} from '@material-ui/core';
import MenuIcon from '@material-ui/icons/Menu';
import Paper from '@material-ui/core/Paper';
import Grid from '@material-ui/core/Grid';
import {makeStyles, ThemeProvider} from '@material-ui/styles';

import Header from "./Header"
import UnitCards from "./UnitCards"
import LogTable from "./LogTable"

import CssBaseline from "@material-ui/core/CssBaseline";
import { MuiThemeProvider, createMuiTheme } from "@material-ui/core/styles";

const themeLight = createMuiTheme({
  palette: {
    background: {
      default: "#fafbfc"
    }
  }
});

const useStyles = makeStyles({
  root: {
    minWidth: 100,
    marginTop: "15px"
  },
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "10px"
  },
  pos: {
    marginBottom: 0,
  },
});

function linspace(startValue, stopValue, cardinality) {
  var arr = [];
  var step = (stopValue - startValue) / (cardinality - 1);
  for (var i = 0; i < cardinality; i++) {
    arr.push(startValue + (step * i));
  }
  return arr;
}

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

function ExperimentSummary(props){
  const classes = useStyles();

  return(
    <Card className={classes.root}>
      <CardContent className={classes.cardContent}>
        <Typography className={classes.title} color="textSecondary" gutterBottom>
          Experiment
        </Typography>
        <Typography variant="h5" component="h2">
          Trial 14
        </Typography>
        <Typography variant="body2" component="p">
          This is the description of the experiment. This description is stored in a database, along with
          the other metadata in the experiment, like <code>started date</code>.
        </Typography>
      </CardContent>
    </Card>
  )
}




class Chart extends React.Component {
  render() {
    let lines = [];
    let names = this.props.chart_data["series"];
    let nLines = names.length;
    let x_y_data = this.props.chart_data["data"];
    let nPoints = x_y_data[0].length

    let min_timestamp = moment(x_y_data[0][0]['x'], 'x')
    let max_timestamp = moment(x_y_data[0].slice(-1)[0]['x'], 'x')
    let delta_ts = max_timestamp.diff(min_timestamp, 'hours')
    let axis_display_ts_format = ((delta_ts >= 16)
      ?  ((delta_ts >= 5 * 24) ? 'MMM DD' : 'dd HH:mm') : 'H:mm'
    )
    let tooltip_display_ts_format = ((delta_ts >= 16)
      ?  ((delta_ts >= 5 * 24) ? 'MMM DD HH:mm' : 'dd HH:mm') : 'H:mm'
    )


    for (let i = 0; i < nLines; i++) {
      let name = names[i]
      if (name === "1") {
        lines.push(
            <VictoryLine
              key={name}
              style={{
                data: { stroke: colors[name], strokeWidth: 2 },
                parent: { border: "1px solid #ccc"}
              }}
              data={x_y_data[i].filter((x, i) => i % 3 === 0)}
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
          <VictoryVoronoiContainer
            labels={(d) => `${moment(d.datum.x, 'x').format(tooltip_display_ts_format)}
${Math.round(d.datum.y * 1000)/1000}`}
            labelComponent={<VictoryTooltip cornerRadius={0} flyoutStyle={{fill: "white", "stroke": "#90a4ae", strokeWidth: 1.5}}/>}
          />
        }
        >
        <VictoryLabel text={this.props.title} x={300} y={30} textAnchor="middle" style={{fontSize: 15 * this.props.fontScale}}/>
        <VictoryAxis
          tickFormat={(mt) => mt.format(axis_display_ts_format)}
          tickValues={linspace(x_y_data[0][0]['x'], x_y_data[0].slice(-1)[0]['x'] + 100000, 6).map(x => moment(x, 'x').startOf(((delta_ts >= 16) ? 'hour' : 'minute')))}
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
          events={[
            {
              target: "data",
              eventHandlers: {
                onClick: () => {
                  return [{
                    mutation: (props) => {
                      return props.style.fill === "white" ?
                      {style: {fill: colors[props.datum.name], stroke: "black", strokeWidth: 1}} :
                      {style: {fill: "white", stroke: "black", strokeWidth: 1 }}
                    }
                  }]
                }
              }
            }


            ]}
        />
      {lines}
    </VictoryChart>
    </Card>
    )
  }
}


class ODChart extends React.Component {
  render() {
    let lines = [];
    let names = this.props.chart_data["series"];
    let nLines = names.length;
    let x_y_data = this.props.chart_data["data"];
    let nPoints = x_y_data[0].length

    let min_timestamp = moment(x_y_data[0][0]['x'], 'x')
    let max_timestamp = moment(x_y_data[0].slice(-1)[0]['x'], 'x')
    let delta_ts = max_timestamp.diff(min_timestamp, 'hours')
    let axis_display_ts_format = ((delta_ts >= 16)
      ?  ((delta_ts >= 5 * 24) ? 'MMM DD' : 'dd HH:mm') : 'H:mm'
    )
    let tooltip_display_ts_format = ((delta_ts >= 16)
      ?  ((delta_ts >= 5 * 24) ? 'MMM DD HH:mm' : 'dd HH:mm') : 'H:mm'
    )

    for (let i = 0; i < nLines; i++) {
      let name = names[i]
      lines.push(
          <VictoryLine
            key={name}
            style={{
              data: { stroke: colors[name], strokeWidth: 3 },
              parent: { border: "1px solid #ccc"}
            }}
            data={x_y_data[i].filter((x, i) => i % Math.round(nPoints/80) === 0)}
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
          <VictoryVoronoiContainer
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
          tickValues={linspace(x_y_data[0][0]['x'], x_y_data[0].slice(-1)[0]['x'] + 100000, 6).map(x => moment(x, 'x').startOf(((delta_ts >= 16) ? 'hour' : 'minute')))}
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
          events={[
            {
              target: "data",
              eventHandlers: {
                onClick: () => {
                  return [{
                    mutation: (props) => {
                      return props.style.fill === "white" ?
                      {style: {fill: colors[props.datum.name], stroke: "black", strokeWidth: 1}} :
                      {style: {fill: "white", stroke: "black", strokeWidth: 1 }}
                    }
                  }]
                }
              }
            }


            ]}
        />
      {lines}
    </VictoryChart>
    </Card>
    )
  }
}

const chartData90 = require('./data/implied_90.json')[0];
const chartData135 = require('./data/implied_135.json')[0];
const chartGrowthRate = require('./data/implied_growth_rate.json')[0];
const chartAltMediaFraction = require('./data/alt_media_fraction.json')[0];
const listOfLogs = require('./data/all_morbidostat.log.json');

class App extends React.Component {
  render() {
    return (
    <MuiThemeProvider theme={themeLight}>
      <CssBaseline />
      <div>
        <Grid container spacing={2} >

          <Grid item xs={12}><Header /></Grid>

          <Grid item container xs={7} direction="row" spacing={0}>
            <Grid item xs={1}/>
            <Grid item xs={11}><ExperimentSummary/></Grid>

            <Grid item xs={1}/>
            <Grid item xs={11}>
              <Chart chart_data={chartGrowthRate} fontScale={1.} title="Implied growth rate" yAxisLabel="Growth rate, h⁻¹"/>
            </Grid>

            <Grid item xs={1}/>
            <Grid item xs={11}>
              <Chart chart_data={chartAltMediaFraction} fontScale={1.} title="Fraction of volume that is alternative media" yAxisLabel="Fraction"/>
            </Grid>

            <Grid item xs={1}/>
            <Grid item container xs={11} direction="row" spacing={0}>
              <Grid item xs={6}>
                <ODChart chart_data={chartData135} fontScale={1.7} title="135° optical density" yAxisLabel="Optical density (AU)"/>
              </Grid>
              <Grid item xs={6}>
                <ODChart chart_data={chartData90} fontScale={1.7} title="90° optical density" yAxisLabel="Optical density (AU)"/>
              </Grid>

            </Grid>
          </Grid>

          <Grid item container xs={5} direction="row" spacing={2} >
            <Grid item xs={1}/>
            <Grid item xs={5}><UnitCards units={[1,3,5]}/></Grid>
            <Grid item xs={5}><UnitCards units={[2,4,6]}/></Grid>
            <Grid item xs={1}/>

            <Grid item xs={1}/>
            <Grid item xs={10}>
              <LogTable listOfLogs={listOfLogs} />
            </Grid>
            <Grid item xs={1}/>
          </Grid>
        </Grid>
      </div>
    </MuiThemeProvider>
    )
  }
}
export default App;
