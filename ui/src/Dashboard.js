import React from "react";

import Grid from "@material-ui/core/Grid";
import Header from "./components/Header";
import UnitCards from "./components/UnitCards";
import LogTable from "./components/LogTable";
import ExperimentSummary from "./components/ExperimentSummary";
import Chart from "./components/Chart";
import AllUnitsManagerCard from "./components/AllUnitsManagerCard";

import CssBaseline from "@material-ui/core/CssBaseline";
import { MuiThemeProvider, createMuiTheme } from "@material-ui/core/styles";

const themeLight = createMuiTheme({
  palette: {
    background: {
      default: "#fafbfc",
    },
  },
});

function Dashboard() {
  return (
    <MuiThemeProvider theme={themeLight}>
      <CssBaseline />
      <div>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Header />
          </Grid>

          <Grid item container xs={7} direction="row" spacing={2}>
            <Grid item xs={1} />
            <Grid item xs={11}>
              <ExperimentSummary />
            </Grid>

            <Grid item xs={1} />
            <Grid item xs={11}>
              <Chart
                dataFile={"./data/implied_growth_rate.json"}
                interpolation="stepAfter"
                fontScale={1}
                title="Implied growth rate"
                topic="growth_rate"
                yAxisLabel="Growth rate, h⁻¹"
              />
            </Grid>

            <Grid item xs={1} />
            <Grid item xs={11}>
              <Chart
                dataFile={"./data/alt_media_fraction.json"}
                interpolation="stepAfter"
                fontScale={1}
                title="Fraction of volume that is alternative media"
                topic="alt_media_fraction"
                yAxisLabel="Fraction"
              />
            </Grid>

            <Grid item xs={1} />
            <Grid item xs={11}>
              <Chart
                isODReading={true}
                dataFile={"./data/implied_135.json"}
                fontScale={1.0}
                title="135° optical density"
                topic="od_filtered/135/+"
                yAxisLabel="Optical density (AU)"
              />
            </Grid>
          </Grid>

          <Grid item container xs={5} direction="row" spacing={2}>
            <Grid item xs={1} />
            <Grid item xs={5}>
              <UnitCards units={[1, 3, 5]} />
            </Grid>
            <Grid item xs={5}>
              <UnitCards units={[2, 4, 6]} />
            </Grid>
            <Grid item xs={1} />

            <Grid item xs={1} />
            <Grid item xs={10}>
              <AllUnitsManagerCard />
            </Grid>
            <Grid item xs={1} />

            <Grid item xs={1} />
            <Grid item xs={10}>
              <LogTable />
            </Grid>
            <Grid item xs={1} />
          </Grid>
        </Grid>
      </div>
    </MuiThemeProvider>
  );
}
export default Dashboard;
