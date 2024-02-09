import React from "react";

import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import LogTable from "./components/LogTable";
import ExperimentSummary from "./components/ExperimentSummary";
import Chart from "./components/Chart";
import MediaCard from "./components/MediaCard";
import { Link } from 'react-router-dom';
import {getConfig, getRelabelMap} from "./utilities"
import Card from "@mui/material/Card";
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";


const TimeFormatSwitch = (props) => {
  const [state, setState] = React.useState(props.initTimeScale);

  // Update state when props.init changes
  React.useEffect(() => {
    setState(props.initTimeScale);
  }, [props.initTimeScale]);

  const onChange = (
    event,
    newAlignment,
  ) => {
    setState(newAlignment);
    props.setTimeScale(newAlignment);
  };

  return (
    <ToggleButtonGroup
      color="primary"
      value={state}
      exclusive
      onChange={onChange}
      size="small"
    >
      <ToggleButton style={{textTransform: "None"}} value="hours">Hours</ToggleButton>
      <ToggleButton style={{textTransform: "None"}} value="clock_time">Time</ToggleButton>
    </ToggleButtonGroup>

  );
}



const TimeWindowSwitch = (props) => {
  const [state, setState] = React.useState(props.initTimeWindow);

  // Update state when props.init changes
  React.useEffect(() => {
    setState(props.initTimeWindow);
  }, [props.initTimeWindow]);

  const onChange = (
    event,
    newAlignment,
  ) => {
    setState(newAlignment);
    props.setTimeWindow(newAlignment);
  };

  return (
    <ToggleButtonGroup
      color="primary"
      value={state}
      exclusive
      onChange={onChange}
      size="small"
    >
      <ToggleButton style={{textTransform: "None"}} value={10000000}>All time</ToggleButton>
      <ToggleButton style={{textTransform: "None"}} value={1}>Past hour</ToggleButton>
      <ToggleButton style={{textTransform: "None"}} value={12}>Past 12h</ToggleButton>
      <ToggleButton style={{textTransform: "None"}} value={24}>Past day</ToggleButton>
    </ToggleButtonGroup>

  );
}


function Overview(props) {

  const [experimentMetadata, setExperimentMetadata] = React.useState({})
  const [relabelMap, setRelabelMap] = React.useState({})
  const [config, setConfig] = React.useState({})
  const [charts, setCharts] = React.useState({})
  const [timeScale, setTimeScale] = React.useState(null)
  const [timeWindow, setTimeWindow] = React.useState(null)

  React.useEffect(() => {
    document.title = props.title;

    function getLatestExperiment() {
        fetch("/api/experiments/latest")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setExperimentMetadata(data)
        });
      }

    function getCharts() {
        fetch("/api/contrib/charts")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setCharts(data.reduce((map, obj) => (map[obj.chart_key] = obj, map), {}))
        });
      }
    getLatestExperiment()
    getCharts()
    getRelabelMap(setRelabelMap)
    getConfig(setConfig)
  }, [props.title])

  React.useEffect(() => {
    // Check if the 'ui.overview.settings' and 'time_display_mode' exist in the config
    const timeDisplayMode = config['ui.overview.settings']?.['time_display_mode'];
    if (timeDisplayMode !== undefined) {
      // Set 'isByDuration' based on whether 'time_display_mode' is 'hours'
      setTimeScale(timeDisplayMode);
    } else {
      // Optionally, set a default value or take other actions if 'time_display_mode' is not available
      setTimeScale("hours");
    }
  }, [config]);

  return (
    <React.Fragment>
      <Grid container spacing={2} justifyContent="space-between">
        <Grid item xs={12} md={12}>
          <ExperimentSummary experimentMetadata={experimentMetadata}/>
        </Grid>

        <Grid item xs={12} md={7} container spacing={2} justifyContent="flex-start" style={{height: "100%"}}>


          {Object.entries(charts)
            .filter(([chart_key, _]) => config['ui.overview.charts'] && (config['ui.overview.charts'][chart_key] === "1"))
            .map(([chart_key, chart]) =>
              <React.Fragment key={`grid-chart-${chart_key}`}>
                <Grid item xs={12} >
                  <Card style={{ maxHeight: "100%"}}>
                    <Chart
                      key={`chart-${chart_key}`}
                      chartKey={chart_key}
                      config={config}
                      dataSource={chart.data_source}
                      title={chart.title}
                      topic={chart.mqtt_topic}
                      payloadKey={chart.payload_key}
                      yAxisLabel={chart.y_axis_label}
                      experiment={experimentMetadata.experiment}
                      deltaHours={experimentMetadata.delta_hours}
                      experimentStartTime={experimentMetadata.created_at}
                      downSample={chart.down_sample}
                      interpolation={chart.interpolation || "stepAfter"}
                      yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                      lookback={timeWindow ?  timeWindow : (chart.lookback ? eval(chart.lookback) : 10000)}
                      fixedDecimals={chart.fixed_decimals}
                      relabelMap={relabelMap}
                      yTransformation={eval(chart.y_transformation || "(y) => y")}
                      dataSourceColumn={chart.data_source_column}
                      isPartitionedBySensor={chart_key === "raw_optical_density"}
                      isLiveChart={true}
                      byDuration={timeScale === "hours"}
                    />
                  </Card>
                </Grid>
              </React.Fragment>

        )}
        </Grid>

        <Grid item xs={12} md={5} container spacing={1} justifyContent="flex-end" style={{height: "100%"}}>

          <Grid item xs={9} md={9}>
            <Stack direction="row" justifyContent="start">
              <TimeWindowSwitch setTimeWindow={setTimeWindow} initTimeWindow={10000000}/>
            </Stack>
          </Grid>
          <Grid item xs={3} md={3}>
            <Stack direction="row" justifyContent="end">
              <TimeFormatSwitch setTimeScale={setTimeScale} initTimeScale={timeScale}/>
            </Stack>
          </Grid>

          {( config['ui.overview.cards'] && (config['ui.overview.cards']['dosings'] === "1")) &&
            <Grid item xs={12} >
              <MediaCard experiment={experimentMetadata.experiment} config={config} relabelMap={relabelMap}/>
            </Grid>
          }


          {( config['ui.overview.cards'] && (config['ui.overview.cards']['event_logs'] === "1")) &&
            <Grid item xs={12}>
              <LogTable byDuration={timeScale==="hours"} experimentStartTime={experimentMetadata.created_at} experiment={experimentMetadata.experiment} config={config} relabelMap={relabelMap}/>
              <Button to={`/export-data?experiment=${experimentMetadata.experiment}&logs=1`} component={Link} color="primary" style={{textTransform: "none", verticalAlign: "middle", margin: "0px 3px"}}>
                <ListAltOutlinedIcon style={{ fontSize: 17, margin: "0px 3px"}} color="primary"/> Export all logs
              </Button>
            </Grid>
          }

        </Grid>
      </Grid>
    </React.Fragment>
  );
}
export default Overview;
