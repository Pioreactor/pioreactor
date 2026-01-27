import React from "react";
import dayjs from "dayjs";

import FormLabel from '@mui/material/FormLabel';
import FormControl from '@mui/material/FormControl';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Chart from "./components/Chart";
import Select from '@mui/material/Select';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import MenuItem from '@mui/material/MenuItem';
import Checkbox from '@mui/material/Checkbox';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import { getConfig, getRelabelMap } from "./utilities";
import { colors, ColorCycler } from "./color";
import DownloadIcon from '@mui/icons-material/Download';
import { Link } from 'react-router';

// TODO:
// figure out how to display lots of data from long-running experiments without breaking the thing,
//




function ExperimentSelection(props) {
  const [experiments, setExperiments] = React.useState([])
  const selectedExperient = experiments.find(o => o.experiment === props.experimentSelection);

  React.useEffect(() => {
    async function getData() {
       await fetch("/api/experiments")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setExperiments(data);
        if (!props.experimentSelection && data.length > 0) {
          props.handleExperimentSelectionChange(data[0].experiment);
        }
      });
    }
    getData()
  }, [])

  const handleExperimentSelectionChange = (e) => {
    props.handleExperimentSelectionChange(e.target.value)
  }

  const experimentOptions = experiments.map((v, index) => {
            return <MenuItem key={index} value={v.experiment}>{v.experiment +  (v.created_at ? ` (${dayjs(v.created_at).format("MMMM D, YYYY")})` : "")}</MenuItem>
  })

  return (
    <Box sx={{maxWidth: "450px", m: 1}}>
      <FormControl fullWidth component="fieldset" sx={{my: 1}}>
        <FormLabel component="legend">Experiment</FormLabel>
        <Select
          labelId="expSelect"
          variant="standard"
          value={props.experimentSelection}
          onChange={handleExperimentSelectionChange}
        >
        {experimentOptions}
        </Select>
      </FormControl>
      <Box sx={{my: 1}}>
        <Typography sx={{ fontSize: 16 }} color="text.secondary" gutterBottom>
          Experiment created
        </Typography>
        <Typography variant="body2" style={{whiteSpace: "pre-line"}} gutterBottom>
          {dayjs(selectedExperient?.created_at).format("MMMM D, YYYY, h:mm a")}
        </Typography>
        <Typography sx={{ fontSize: 16, pt: 1}} color="text.secondary" gutterBottom>
          Description
        </Typography>
        <Typography variant="body2" style={{whiteSpace: "pre-line"}}>
          {selectedExperient?.description}
        </Typography>
      </Box>
    </Box>
  )
}


function ChartSelection(props) {

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
      <FormControl fullWidth component="fieldset" sx={{m:2}}>
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

  const [experimentSelection, setExperimentSelection] = React.useState("")
  const [chartSelection, setChartSelection] = React.useState({})
  const [config, setConfig] = React.useState({})
  const [relabelMap, setRelabelMap] = React.useState({})
  const unitsColorMap = new ColorCycler(colors)


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
      fused_optical_density : "od_readings_fused",
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
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Past experiments
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <Button to={`/export-data?experiment=${experimentSelection}&experiments=1${additionalQueryString}`} component={Link} style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary">
              <DownloadIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/> Export experiment data
            </Button>
          </Box>
        </Box>
      </Box>
      <Card>
        <CardContent sx={{p: 1}}>
          <Grid container spacing={2} justifyContent="space-between">
            <Grid size={6}>
              <ExperimentSelection
                experimentSelection={experimentSelection}
                handleExperimentSelectionChange={handleExperimentSelectionChange}
              />
            </Grid>
            <Grid size={6}>
              <ChartSelection
                chartSelection={chartSelection}
                handleChartSelectionChange={handleChartSelectionChange}
                config={config}
              />
            </Grid>
            <Grid
              container
              spacing={2}
              justifyContent="flex-start"
              style={{height: "100%"}}
              size={{
                xs: 12,
                md: 12
              }}>
              {Object.entries(chartSelection).sort()
                .map(([chart_key, chart]) =>
                  <React.Fragment key={`grid-chart-${chart_key}`}>
                    <Grid size={6}>
                      <Chart
                        chart_key={`chart-${chart_key}`}
                        config={config}
                        dataSource={chart.data_source}
                        title={chart.title}
                        topic={chart.mqtt_topic}
                        payloadKey={chart.payload_key}
                        yAxisLabel={chart.y_axis_label}
                        experiment={experimentSelection}
                        //experimentStartTime={experimentMetadata.created_at}
                        deltaHours={10}
                        downSample={true}
                        interpolation={chart.interpolation || "stepAfter"}
                        yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                        lookback={10000}
                        fixedDecimals={chart.fixed_decimals}
                        yTransformation={eval(chart.y_transformation || "(y) => y")}
                        dataSourceColumn={chart.data_source_column}
                        relabelMap={relabelMap}
                        isPartitionedBySensor={chart_key === "raw_optical_density"}
                        allowZoom={true}
                        isLiveChart={false}
                        byDuration={false}
                        unitsColorMap={unitsColorMap}
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
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <ExperimentsContainer/>
        </Grid>
      </Grid>
    );
}

export default Experiments;
