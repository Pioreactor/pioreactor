import { useState, useEffect, useMemo, Fragment } from 'react';

import Grid from "@mui/material/Grid";
import LogTable from "./components/LogTable";
import ExperimentSummary from "./components/ExperimentSummary";
import Chart from "./components/Chart";
import MediaCard from "./components/MediaCard";
import {RunningProfilesContainer} from "./Profiles";
import { RunningProfilesProvider} from './providers/RunningProfilesContext';
import {getConfig, getRelabelMap, colors, ColorCycler} from "./utilities"
import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import { useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';
import { TimeFormatSwitch, TimeWindowSwitch } from "./components/TimeControls";


function Charts(props) {
  const [charts, setCharts] = useState({})
  const config = props.config
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const enabledCharts = config['ui.overview.charts'] || {};

  useEffect(() => {
    const fetchCharts = async () => {
      try {
        const response = await fetch('/api/contrib/charts');
        if (!response.ok) {
          throw new Error('Failed to fetch charts');
        }
        const data = await response.json();
        setCharts(Object.fromEntries(data.map((chart) => [chart.chart_key, chart])));
      } catch (err) {
        console.error('Error loading charts:', err);
      }
    };

    fetchCharts();
  }, []);


  return (
    <Fragment>
      {Object.entries(charts)
        .filter(([chart_key]) => enabledCharts[chart_key] === "1")
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
  const initialTimeWindow = parseInt(localStorage.getItem('timeWindow')) >= 0 ? parseInt(localStorage.getItem('timeWindow')) :  1000000;
  const [timeScale, setTimeScale] = useState(initialTimeScale);
  const [timeWindow, setTimeWindow] = useState(initialTimeWindow);
  const [units, setUnits] = useState([])
  const [hasFetchedUnits, setHasFetchedUnits] = useState(false)
  const unitsColorMap = useMemo(() => new ColorCycler(colors), [])
  const cardsConfig = config['ui.overview.cards'] || {};


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
          setHasFetchedUnits(true);
        } else {
          console.error('Failed to fetch workers:', response.statusText);
        }
      } catch (error) {
        console.error('Error fetching workers:', error);
      }
    };


    if (experimentMetadata.experiment){
        getRelabelMap(setRelabelMap, experimentMetadata.experiment)
        setHasFetchedUnits(false)
        setUnits([])
        fetchWorkers(experimentMetadata.experiment)
    }
  }, [experimentMetadata])

  const activeUnits = units.filter(unit => unit.is_active === 1).map(unit => unit.pioreactor_unit)
  const assignedUnits = units.map(unit => unit.pioreactor_unit)

  const showAssignmentAlert = hasFetchedUnits && assignedUnits.length === 0

  return (
    <Fragment>
      <Grid container spacing={2} justifyContent="space-between">
        <Grid
          size={{
            xs: 12,
            md: 12
          }}>
          <ExperimentSummary experimentMetadata={experimentMetadata} updateExperiment={updateExperiment} showAssignmentAlert={showAssignmentAlert}/>
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

          {( cardsConfig['dosings'] === "1") &&
            <Grid size={12}>
              <MediaCard activeUnits={activeUnits} experiment={experimentMetadata.experiment} relabelMap={relabelMap}/>
            </Grid>
          }

        {( cardsConfig['profiles'] === "1") &&
        <Grid size={12}>
          <RunningProfilesProvider experiment={experimentMetadata.experiment}>
            <RunningProfilesContainer/>
          </RunningProfilesProvider>
        </Grid>
       }

        {( cardsConfig['event_logs'] === "1") &&
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
