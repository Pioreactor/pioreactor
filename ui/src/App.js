import React from "react";

import Grid from '@material-ui/core/Grid';
import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import Button from '@material-ui/core/Button';


import Header from "./Header"
import UnitCards from "./UnitCards"
import LogTable from "./LogTable"
import ExperimentSummary from "./ExperimentSummary"
import Chart from "./Chart"
import ODChart from "./ODChart"

import CssBaseline from "@material-ui/core/CssBaseline";
import { MuiThemeProvider, createMuiTheme } from "@material-ui/core/styles";

const themeLight = createMuiTheme({
  palette: {
    background: {
      default: "#fafbfc"
    }
  }
});



const chartData90 = require('./data/implied_90.json')[0];
const chartData135 = require('./data/implied_135.json')[0];
const chartGrowthRate = require('./data/implied_growth_rate.json')[0];
const chartAltMediaFraction = require('./data/alt_media_fraction.json')[0];
const listOfLogs = require('./data/all_morbidostat.log.json');
//console.log(import('./data/all_morbidostat.log.json'));

function App() {
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
              <Chart chart_data={chartGrowthRate} interpolation="natural" fontScale={1.} title="Implied growth rate" yAxisLabel="Growth rate, h⁻¹"/>
            </Grid>

            <Grid item xs={1}/>
            <Grid item xs={11}>
              <Chart chart_data={chartAltMediaFraction} interpolation="stepAfter" fontScale={1.} title="Fraction of volume that is alternative media" yAxisLabel="Fraction"/>
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
              <Card variant="outlined">
                <CardContent>
                  <Button variant="outlined" color="secondary">
                  Stop all processes
                  </Button>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={1}/>

            <Grid item xs={1}/>
            <Grid item xs={10}><LogTable listOfLogs={listOfLogs} /></Grid>
            <Grid item xs={1}/>
          </Grid>
        </Grid>
      </div>
    </MuiThemeProvider>
    )
}
export default App;
