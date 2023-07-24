import React from "react";
import moment from "moment";

import FormLabel from '@mui/material/FormLabel';
import FormControl from '@mui/material/FormControl';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Chart from "./components/Chart";
import { makeStyles } from '@mui/styles';
import Select from '@mui/material/Select';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import MenuItem from '@mui/material/MenuItem';
import Checkbox from '@mui/material/Checkbox';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {getConfig, getRelabelMap} from "./utilities"
import GetAppIcon from '@mui/icons-material/GetApp';
import { Link } from 'react-router-dom';

// TODO:
// figure out how to display lots of data from long-running experiments without breaking the thing,
//



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
  },
  headerMenu: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: "5px",
    [theme.breakpoints.down('lg')]:{
      flexFlow: "nowrap",
      flexDirection: "column",
    }
  },
  headerButtons: {display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}

}));


function ExperimentSelection(props) {
  const classes = useStyles();
  const [experiments, setExperiments] = React.useState([])
  const selectedExperient = experiments.find(o => o.experiment === props.experimentSelection);

  React.useEffect(() => {
    async function getData() {
       await fetch("/api/experiments")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setExperiments(prevState => [ ...data, ...prevState])
        props.handleExperimentSelectionChange(data[0].experiment)
      });
    }
    getData()
  }, [])

  const handleExperimentSelectionChange = (e) => {
    props.handleExperimentSelectionChange(e.target.value)
  }


  return (
    <div style={{maxWidth: "450px", margin: "10px"}}>
      <FormControl fullWidth component="fieldset" className={classes.formControl}>
        <FormLabel component="legend">Experiment</FormLabel>
        <Select
          labelId="expSelect"
          variant="standard"
          value={props.experimentSelection}
          onChange={handleExperimentSelectionChange}
        >
          {experiments.map((v) => {
            return <MenuItem key={v.experiment} value={v.experiment}>{v.experiment +  (v.created_at ? ` (${moment(v.created_at).format("MMMM D, YYYY")})` : "")}</MenuItem>
            }
          )}
        </Select>
      </FormControl>
      <Box sx={{ p: 2, pt: 0 }}>
        <Typography sx={{ fontSize: 16 }} color="text.secondary" gutterBottom>
          Experiment started
        </Typography>
        <Typography variant="body2" style={{whiteSpace: "pre-line"}} gutterBottom>
          {moment(selectedExperient?.created_at).format("MMMM D, YYYY, h:mm a")}
        </Typography>
        <Typography sx={{ fontSize: 16, pt: 1}} color="text.secondary" gutterBottom>
          Description
        </Typography>
        <Typography variant="body2" style={{whiteSpace: "pre-line"}}>
          {selectedExperient?.description}
        </Typography>
      </Box>
    </div>
  )
}


function ChartSelection(props) {
  const classes = useStyles();

  const [charts, setCharts] = React.useState({})

  React.useEffect(() => {
    async function getCharts() {
        await fetch("/api/contrib/charts")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setCharts(data.reduce((map, obj) => (map[obj.chart_key] = obj, map), {}))
        });
      }
    getCharts()
  }, [])

  const handleChange = (e) => {
      props.handleChartSelectionChange(charts[e.target.name], e.target.checked)
    };

  return (
    <div style={{maxWidth: "450px", margin: "10px"}}>
      <FormControl fullWidth component="fieldset" className={classes.formControl}>
        <FormLabel component="legend">Charts</FormLabel>
        <FormGroup>
          {Object.entries(charts)
            .filter(([chart_key, _]) => props.config['ui.overview.charts'] && (props.config['ui.overview.charts'][chart_key] === "1"))
            .map(([chart_key, chart]) =>
            <FormControlLabel
              key={chart_key}
              control={
                <Checkbox checked={chart_key in props.chartSelection} onChange={handleChange} name={chart_key} size="small"/>
              }
              label={chart.title}/>
            )}
        </FormGroup>
      </FormControl>
    </div>
  )
}



function ExperimentsContainer(props) {
  const classes = useStyles();

  const [experimentSelection, setExperimentSelection] = React.useState("")
  const [chartSelection, setChartSelection] = React.useState({})
  const [config, setConfig] = React.useState({})
  const [relabelMap, setRelabelMap] = React.useState({})


  React.useEffect(() => {
    document.title = props.title;
    getConfig(setConfig)

  }, [props.title]);

  function handleExperimentSelectionChange(experimentName) {
    setExperimentSelection(experimentName)
    getRelabelMap(setRelabelMap, experimentName)
  };

  function handleChartSelectionChange(chart_obj, is_checked) {
    if (is_checked){
      setChartSelection({ ...chartSelection, [chart_obj.chart_key]: chart_obj })
    } else {
      const { [chart_obj.chart_key]: tmp, ...rest } = chartSelection;
      setChartSelection(rest)
    }
  };


  function objectToQueryString(obj) {
    const chartKeyToDataKey = {
      implied_growth_rate : "growth_rates",
      raw_optical_density : "od_readings",
      temperature : "temperature_readings",
      normalized_optical_density : "od_readings_filtered",
      fraction_of_volume_that_is_alternative_media : "alt_media_fraction",
    }

    let queryString = "";
    for (const key in obj) {
      if (obj.hasOwnProperty(key) && chartKeyToDataKey.hasOwnProperty(key)) {
        queryString += `&${chartKeyToDataKey[key]}=1`;
      }
    }
    return queryString;
  }


  const additionalQueryString = objectToQueryString(chartSelection)

  return (
    <React.Fragment>
      <div>
        <div className={classes.headerMenu}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Past Experiments
            </Box>
          </Typography>
          <div className={classes.headerButtons}>
            <Button to={`/export-data?experiment=${experimentSelection}&experiments=1${additionalQueryString}`} component={Link} style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary">
              <GetAppIcon fontSize="15" classes={{root: classes.textIcon}}/> Export experiment data
            </Button>
          </div>
        </div>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <Grid container spacing={2} justifyContent="space-between">
            <Grid item xs={6}>
              <ExperimentSelection
                experimentSelection={experimentSelection}
                handleExperimentSelectionChange={handleExperimentSelectionChange}
              />
            </Grid>
            <Grid item xs={6}>
              <ChartSelection
                chartSelection={chartSelection}
                handleChartSelectionChange={handleChartSelectionChange}
                config={config}
              />
            </Grid>
            <Grid item xs={12} md={12} container spacing={2} justifyContent="flex-start" style={{height: "100%"}}>
              {Object.entries(chartSelection).sort()
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
                        deltaHours={10}
                        interpolation={chart.interpolation || "stepAfter"}
                        yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                        lookback={10000}
                        fixedDecimals={chart.fixed_decimals}
                        yTransformation={eval(chart.y_transformation || "(y) => y")}
                        dataSourceColumn={chart.data_source_column}
                        id={chart_key}
                        relabelMap={relabelMap}
                        isODReading={chart_key === "raw_optical_density"}
                        allowZoom={true}
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

function Experiments(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <ExperimentsContainer/>
          </Grid>
        </Grid>
    )
}

export default Experiments;
