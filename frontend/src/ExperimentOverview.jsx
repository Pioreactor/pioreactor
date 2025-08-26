import { useState, useEffect, Fragment } from 'react';

import Grid from "@mui/material/Grid";
import LogTable from "./components/LogTable";
import ExperimentSummary from "./components/ExperimentSummary";
import Chart from "./components/Chart";
import MediaCard from "./components/MediaCard";
import {RunningProfilesContainer} from "./Profiles";
import { RunningProfilesProvider} from './providers/RunningProfilesContext';
import {getConfig, getRelabelMap, colors, ColorCycler} from "./utilities"
import Card from "@mui/material/Card";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Stack from "@mui/material/Stack";
import { useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';

const TimeFormatSwitch = (props) => {
  const [state, setState] = useState(props.initTimeScale);

  // Update state when props.init changes
  useEffect(() => {
    setState(props.initTimeScale);
  }, [props.initTimeScale]);

  const onChange = (
    event,
    newAlignment,
  ) => {
    if (newAlignment !== null) {
      setState(newAlignment);
      props.setTimeScale(newAlignment);
      localStorage.setItem('timeScale', newAlignment);
    }
  };

  return (
    <ToggleButtonGroup
      color="primary"
      value={state}
      exclusive
      onChange={onChange}
      size="small"
    >
      <ToggleButton style={{textTransform: "None"}} value="hours">Elapsed time</ToggleButton>
      <ToggleButton style={{textTransform: "None"}} value="clock_time">Timestamp</ToggleButton>
    </ToggleButtonGroup>

  );
}



const TimeWindowSwitch = (props) => {
  const [state, setState] = useState(props.initTimeWindow);

  // Update state when props.init changes
  useEffect(() => {
    setState(props.initTimeWindow);
  }, [props.initTimeWindow]);

  const onChange = (
    event,
    newAlignment,
  ) => {
    if (newAlignment !== null) {
      setState(newAlignment);
      props.setTimeWindow(newAlignment);
      localStorage.setItem('timeWindow', newAlignment.toString());
    }
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
      <ToggleButton style={{textTransform: "None"}} value={12}>Past 12h</ToggleButton>
      <ToggleButton style={{textTransform: "None"}} value={1}>Past hour</ToggleButton>
      <ToggleButton style={{textTransform: "None"}} value={0}>Now</ToggleButton>
    </ToggleButtonGroup>

  );
}

function Charts(props) {
  const [charts, setCharts] = useState({})
  const config = props.config
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();

  useEffect(() => {
    fetch('/api/contrib/charts')
      .then((response) => response.json())
      .then((data) => {
        setCharts(data.reduce((map, obj) => ((map[obj.chart_key] = obj), map), {}));
      });
  }, []);


  return (
    <Fragment>
      {Object.entries(charts)
        .filter(([chart_key, _]) => config['ui.overview.charts'] && (config['ui.overview.charts'][chart_key] === "1"))
        .map(([chart_key, chart]) =>
          <Fragment key={`grid-chart-${chart_key}`}>
            <Grid size={12}>
              <Card sx={{ maxHeight: "100%"}}>
                <Chart
                  key={`chart-${chart_key}`}
                  chartKey={chart_key}
                  config={config}
                  dataSource={chart.data_source}
                  title={chart.title}
                  topic={chart.mqtt_topic}
                  payloadKey={chart.payload_key}
                  yAxisLabel={chart.y_axis_label}
                  experiment={props.experimentMetadata.experiment}
                  experimentStartTime={props.experimentMetadata.created_at}
                  downSample={chart.down_sample}
                  interpolation={chart.interpolation || "stepAfter"}
                  yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                  lookback={(props.timeWindow >= 0) ? props.timeWindow : (chart.lookback ? eval(chart.lookback) : 10000)}
                  fixedDecimals={chart.fixed_decimals}
                  relabelMap={props.relabelMap}
                  yTransformation={eval(chart.y_transformation || "(y) => y")}
                  dataSourceColumn={chart.data_source_column}
                  isPartitionedBySensor={["raw_optical_density", 'optical_density'].includes(chart_key)}
                  isLiveChart={true}
                  byDuration={props.timeScale === "hours"}
                  client={client}
                  subscribeToTopic={subscribeToTopic}
                  unsubscribeFromTopic={unsubscribeFromTopic}
                  unitsColorMap={props.unitsColorMap}
                />
              </Card>
            </Grid>
          </Fragment>
     )}
    </Fragment>
  );}


function Overview(props) {

  const {experimentMetadata, updateExperiment} = useExperiment()
  const [config, setConfig] = useState({})
  const [relabelMap, setRelabelMap] = useState({})

  const initialTimeScale = localStorage.getItem('timeScale') || config['ui.overview.settings']?.['time_display_mode'] || 'hours';
  const initialTimeWindow = parseInt(localStorage.getItem('timeWindow')) >= 0 ? parseInt(localStorage.getItem('timeWindow')) :  10000000;
  const [timeScale, setTimeScale] = useState(initialTimeScale);
  const [timeWindow, setTimeWindow] = useState(initialTimeWindow);
  const [units, setUnits] = useState([])
  const unitsColorMap = new ColorCycler(colors)


  useEffect(() => {
    document.title = props.title;
    getConfig(setConfig)
  }, [props.title])

  useEffect(() => {
    async function fetchWorkers(experiment) {
      try {
        const response = await fetch(`/api/experiments/${experiment}/workers`);
        if (response.ok) {
          const units = await response.json();
          setUnits(units);
        } else {
          console.error('Failed to fetch workers:', response.statusText);
        }
      } catch (error) {
        console.error('Error fetching workers:', error);
      }
    };


    if (experimentMetadata.experiment){
        getRelabelMap(setRelabelMap, experimentMetadata.experiment)
        fetchWorkers(experimentMetadata.experiment)
    }
  }, [experimentMetadata])

  const activeUnits = units.filter(unit => unit.is_active === 1).map(unit => unit.pioreactor_unit)
  const assignedUnits = units.map(unit => unit.pioreactor_unit)

  return (
    <Fragment>
      <Grid container spacing={2} justifyContent="space-between">
        <Grid
          size={{
            xs: 12,
            md: 12
          }}>
          <ExperimentSummary experimentMetadata={experimentMetadata} updateExperiment={updateExperiment}/>
        </Grid>


        <Grid
          container
          spacing={2}
          justifyContent="flex-start"
          style={{height: "100%"}}
          size={{
            xs: 12,
            md: 7
          }}>
          <Charts unitsColorMap={unitsColorMap} config={config} timeScale={timeScale} timeWindow={timeWindow} experimentMetadata={experimentMetadata} relabelMap={relabelMap}/>
        </Grid>

        <Grid
          container
          spacing={2}
          justifyContent="flex-end"
          style={{height: "100%"}}
          size={{
            xs: 12,
            md: 5
          }}>

          <Grid
            size={{
              xs: 7,
              md: 7
            }}>
            <Stack direction="row" justifyContent="start">
              <TimeWindowSwitch setTimeWindow={setTimeWindow} initTimeWindow={timeWindow}/>
            </Stack>
          </Grid>
          <Grid
            size={{
              xs: 5,
              md: 5
            }}>
            <Stack direction="row" justifyContent="end">
              <TimeFormatSwitch setTimeScale={setTimeScale} initTimeScale={timeScale}/>
            </Stack>
          </Grid>

          {( config['ui.overview.cards'] && (config['ui.overview.cards']['dosings'] === "1")) &&
            <Grid size={12}>
              <MediaCard activeUnits={activeUnits} experiment={experimentMetadata.experiment} relabelMap={relabelMap}/>
            </Grid>
          }

        {( config['ui.overview.cards'] && (config['ui.overview.cards']['profiles'] === "1")) &&
        <Grid size={12}>
          <RunningProfilesProvider experiment={experimentMetadata.experiment}>
            <RunningProfilesContainer/>
          </RunningProfilesProvider>
        </Grid>
       }

        {( config['ui.overview.cards'] && (config['ui.overview.cards']['event_logs'] === "1")) &&
          <Grid size={12}>
            <LogTable units={assignedUnits} byDuration={timeScale==="hours"} experimentStartTime={experimentMetadata.created_at} experiment={experimentMetadata.experiment} config={config} relabelMap={relabelMap}/>
          </Grid>
        }
        </Grid>

      </Grid>
    </Fragment>
  );
}
export default Overview;
