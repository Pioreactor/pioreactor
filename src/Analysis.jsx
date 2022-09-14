import React from "react";
import moment from "moment";

import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Chart from "./components/Chart";
import PioreactorIcon from './components/PioreactorIcon';
import FormControl from '@mui/material/FormControl';
import { makeStyles } from '@mui/styles';
import Select from '@mui/material/Select';


const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  formControl: {
    margin: theme.spacing(2),
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
  caption: {
    marginLeft: "30px",
    maxWidth: "650px"
  }
}));


function ExperimentSelection(props) {
  const classes = useStyles();

  const [experiments, setExperiments] = React.useState([{experiment: "<All experiments>"}])

  React.useEffect(() => {
    async function getData() {
       await fetch("/api/get_experiments")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setExperiments(prevState => [ ...data, ...prevState])
        props.handleChange(data[0].experiment)
      });
    }
    getData()
  }, [])

  const handleExperimentSelectionChange = (e) => {
    props.handleChange(e.target.value)
  }

  return (
    <div className={classes.root}>
      <FormControl component="fieldset" className={classes.formControl}>

        <Select
          native
          variant="standard"
          value={props.ExperimentSelection}
          onChange={handleExperimentSelectionChange}
          inputProps={{
            name: 'experiment',
            id: 'experiment',
          }}
        >
          {experiments.map((v) => {
            return <option value={v.experiment}>{v.experiment +  (v.created_at ? ` (started ${moment(v.created_at).format("MMMM D, YYYY")})` : "")}</option>
            }
          )}
        </Select>
      </FormControl>

    </div>
  )
}



function Analysis(props) {

  const [experimentSelection, setExperimentSelection] = React.useState("")

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  function handleExperimentSelectionChange(value) {
    setExperimentSelection(value)
  };

  return (
    <React.Fragment>
      <Grid container spacing={2} justifyContent="space-between">
        <Grid item xs={12}>
          <ExperimentSelection
          experimentSelection={experimentSelection}
          handleChange={handleExperimentSelectionChange}
          />
        </Grid>
        <Grid item xs={12} md={6} container spacing={2} justifyContent="flex-start" style={{height: "100%"}}>
          <Grid item xs={12}>
            <Chart

              dataSource="growth_rates"
              title="Implied growth rate"
              topic="growth_rate_calculating/growth_rate"
              payloadKey="growth_rate"
              yAxisLabel="Growth rate, h⁻¹"
              experiment={experimentSelection}
              deltaHours={20}
              interpolation="stepAfter"
              yAxisDomain={[-0.02, 0.1]}
              lookback={100000}
              fixedDecimals={2}
            />
          </Grid>

          <Grid item xs={12}>
            <Chart

              dataSource="temperature_readings"
              title="Temperature of vials"
              topic="temperature_control/temperature"
              yAxisLabel="temperature, ℃"
              payloadKey="temperature"
              experiment={experimentSelection}
              interpolation="stepAfter"
              lookback={10000}
              deltaHours={1}
              yAxisDomain={[22.5, 37.5]}
              fixedDecimals={1}
            />
          </Grid>


          <Grid item xs={12}>
            <Chart

              yAxisDomain={[0.00, 0.05]}
              dataSource="alt_media_fraction"
              interpolation="stepAfter"
              payloadKey="alt_media_fraction"
              title="Fraction of volume that is alternative media"
              topic="alt_media_calculating/alt_media_fraction"
              yAxisLabel="Fraction"
              experiment={experimentSelection}
              deltaHours={1} // hack to make all points display
              fixedDecimals={3}
              lookback={100000}
            />
          </Grid>

        </Grid>
        <Grid item xs={12} md={6} container spacing={2} justifyContent="flex-start" style={{height: "100%"}}>

          <Grid item xs={12}>
            <Chart

              isODReading={true}
              dataSource="od_readings_filtered"
              title="Normalized optical density"
              payloadKey="od_filtered"
              topic="growth_rate_calculating/od_filtered"
              yAxisLabel="Current OD / initial OD"
              experiment={experimentSelection}
              deltaHours={20}
              interpolation="stepAfter"
              lookback={100000}
              fixedDecimals={2}
            />
          </Grid>

          <Grid item xs={12}>
            <Chart

              isODReading={true}
              dataSource="od_readings"
              title="Optical density"
              payloadKey="od"
              topic="od_reading/od/+"
              yAxisLabel="Reading"
              experiment={experimentSelection}
              deltaHours={20}
              interpolation="stepAfter"
              lookback={10000}
              fixedDecimals={3}
            />
          </Grid>

        </Grid>

      </Grid>
    </React.Fragment>
  );
}

export default Analysis;
