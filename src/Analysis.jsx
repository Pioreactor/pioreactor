import React from "react";
import moment from "moment";

import FormLabel from '@mui/material/FormLabel';
import FormControl from '@mui/material/FormControl';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Chart from "./components/Chart";
import PioreactorIcon from './components/PioreactorIcon';
import { makeStyles } from '@mui/styles';
import Select from '@mui/material/Select';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';

import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {getConfig} from "./utilities"


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
       await fetch("/api/experiments")
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

  const options = experiments.map((v, index) => {
            return <option key={`${v.experiment}`} value={v.experiment}>{v.experiment +  (v.created_at ? ` (started ${moment(v.created_at).format("MMMM D, YYYY")})` : "")}</option>
  })

  return (
    <div style={{maxWidth: "450px", margin: "10px"}}>
      <FormControl fullWidth component="fieldset" className={classes.formControl}>
        <FormLabel component="legend">Choose experiment to display</FormLabel>
        <Select
          native
          labelId="expSelect"
          variant="standard"
          value={props.ExperimentSelection}
          onChange={handleExperimentSelectionChange}
          inputProps={{
            name: 'experiment',
            id: 'experiment',
          }}
        >
          {options}
        </Select>
      </FormControl>
    </div>
  )
}



function AnalysisContainer(props) {
  const classes = useStyles();

  const [experimentSelection, setExperimentSelection] = React.useState("")
  const [charts, setCharts] = React.useState({})
  const [config, setConfig] = React.useState({})


  React.useEffect(() => {
    document.title = props.title;

    function getCharts() {
        fetch("/api/contrib/charts")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setCharts(data.reduce((map, obj) => (map[obj.chart_key] = obj, map), {}))
        });
      }
    getCharts()
    getConfig(setConfig)

  }, [props.title]);

  function handleExperimentSelectionChange(value) {
    setExperimentSelection(value)
  };

  return (
    <React.Fragment>
      <div>
        <div className={classes.headerMenu}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Analysis
            </Box>
          </Typography>
        </div>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <Grid container spacing={2} justifyContent="space-between">
            <Grid item xs={12}>
              <ExperimentSelection
                experimentSelection={experimentSelection}
                handleChange={handleExperimentSelectionChange}
              />
            </Grid>
            <Grid item xs={12} md={12} container spacing={2} justifyContent="flex-start" style={{height: "100%"}}>
              {Object.entries(charts)
                .filter(([chart_key, _]) => config['ui.overview.charts'] && (config['ui.overview.charts'][chart_key] === "1"))
                .map(([chart_key, chart]) =>
                  <React.Fragment key={`grid-chart-${chart_key}`}>
                    <Grid item xs={6}>
                      <Chart
                        key={`chart-${chart_key}`}
                        config={config}
                        dataSource={chart.data_source}
                        title={chart.title}
                        topic={chart.mqtt_topic}
                        payloadKey={chart.payload_key}
                        yAxisLabel={chart.y_axis_label}
                        experiment={experimentSelection}
                        deltaHours={1}
                        interpolation={chart.interpolation || "stepAfter"}
                        yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                        lookback={eval(chart.lookback) || 10000}
                        fixedDecimals={chart.fixed_decimals}
                        yTransformation={eval(chart.y_transformation || "(y) => y")}
                        dataSourceColumn={chart.data_source_column}
                        id={chart_key}
                        isPartitionedBySensor={chart_key === "raw_optical_density"}
                      />
                    </Grid>
                  </React.Fragment>

            )}
            </Grid>
          </Grid>
        </CardContent>
      </Card>
    </React.Fragment>
  );
}

function Analysis(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <AnalysisContainer/>
          </Grid>
        </Grid>
    )
}

export default Analysis;
