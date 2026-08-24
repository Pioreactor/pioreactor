import { useState, useEffect, useMemo, Fragment } from 'react';

import Grid from "@mui/material/Grid";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import LogTable from "./components/LogTable";
import ExperimentSummary from "./components/ExperimentSummary";
import Chart from "./components/Chart";
import ChartPreferencesControl from "./components/ChartPreferencesControl";
import MediaCard from "./components/MediaCard";
import {RunningProfilesContainer} from "./Profiles";
import { RunningProfilesProvider} from './providers/RunningProfilesContext';
import { getConfig, getRelabelMap } from "./utils/config";
import { colors, ColorCycler } from "./utils/color";
import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import { useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';
import { TimeFormatSwitch, TimeWindowSwitch } from "./components/TimeControls";
import useExperimentChartPreferences from "./hooks/useExperimentChartPreferences";
import { experimentPathSegment } from "./utils/url";

function evaluateChartLookback(timeWindow, lookbackExpression) {
  if (timeWindow >= 0) {
    return timeWindow;
  }
  if (!lookbackExpression) {
    return 10000;
  }
  // Chart descriptors provide legacy JavaScript expressions for lookback values.
  // eslint-disable-next-line no-eval
  return eval(lookbackExpression);
}

function evaluateChartTransformation(transformation) {
  // Chart descriptors provide legacy JavaScript functions for y-axis transformations.
  // eslint-disable-next-line no-eval
  return eval(transformation || "(y) => y");
}


function Charts(props) {
  const config = props.config
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const experiment = props.experimentMetadata.experiment;
  const descriptorsByKey = new Map(
    props.chartPreferences.descriptors.map((descriptor) => [descriptor.chart_key, descriptor]),
  );
  const charts = props.chartPreferences.selectedChartKeys
    .map((chartKey) => descriptorsByKey.get(chartKey))
    .filter(Boolean);

  if (props.chartPreferences.isLoading) {
    return <CircularProgress aria-label="Loading charts" size={24} />;
  }

  if (props.chartPreferences.error) {
    return (
      <Alert
        severity="error"
        action={<Button onClick={() => props.chartPreferences.refresh()}>Retry</Button>}
      >
        {props.chartPreferences.error}
      </Alert>
    );
  }

  if (charts.length === 0) {
    return (
        <Typography variant="body2" color="text.secondary">
        No charts are selected for this page. Use the settings to add one.
        </Typography>
    );
  }


  return (
    <Fragment>
      {charts.map((chart) => {
        const chart_key = chart.chart_key;
        return (
          <Fragment key={`grid-chart-${chart_key}`}>
            <Grid size={12}>
              <Card sx={{ maxHeight: "100%"}}>
                <Chart
                  key={`chart-${chart_key}-${experiment}-all-${props.timeWindow}-${props.timeScale}`}
                  chartKey={chart_key}
                  config={config}
                  dataSource={chart.data_source}
                  title={chart.title}
                  topic={chart.mqtt_topic}
                  payloadKey={chart.payload_key}
                  yAxisLabel={chart.y_axis_label}
                  experiment={experiment}
                  experimentStartTime={props.experimentMetadata.created_at}
                  downSample={chart.down_sample}
                  interpolation={chart.interpolation || "stepAfter"}
                  yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                  lookback={evaluateChartLookback(props.timeWindow, chart.lookback)}
                  fixedDecimals={chart.fixed_decimals}
                  relabelMap={props.relabelMap}
                  yTransformation={evaluateChartTransformation(chart.y_transformation)}
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
        );
      })}
    </Fragment>
  );}


function Overview(props) {

  const {experimentMetadata, updateExperiment} = useExperiment()
  const [config, setConfig] = useState({})
  const [configReady, setConfigReady] = useState(false)
  const [relabelMap, setRelabelMap] = useState({})

  const initialTimeScale = localStorage.getItem('timeScale') || config['ui.overview.settings']?.['time_display_mode'] || 'hours';
  const initialTimeWindow = parseInt(localStorage.getItem('timeWindow')) >= 0 ? parseInt(localStorage.getItem('timeWindow')) :  1000000;
  const [timeScale, setTimeScale] = useState(initialTimeScale);
  const [timeWindow, setTimeWindow] = useState(initialTimeWindow);
  const [units, setUnits] = useState([])
  const [hasFetchedUnits, setHasFetchedUnits] = useState(false)
  const unitsColorMap = useMemo(() => new ColorCycler(colors), [])
  const cardsConfig = config['ui.overview.cards'] || {};
  const chartPreferences = useExperimentChartPreferences({
    chartPage: "overview",
    config,
    configReady,
    experiment: experimentMetadata.experiment,
  });


  useEffect(() => {
    document.title = props.title;
    getConfig(setConfig).finally(() => setConfigReady(true))
  }, [props.title])

  useEffect(() => {
    if (!experimentMetadata.experiment) {
      return;
    }

    getRelabelMap(setRelabelMap, experimentMetadata.experiment)
  }, [experimentMetadata.experiment])

  useEffect(() => {
    async function fetchWorkers(experiment) {
      try {
        const response = await fetch(`/api/experiments/${experimentPathSegment(experiment)}/workers`);
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
        setHasFetchedUnits(false)
        setUnits([])
        fetchWorkers(experimentMetadata.experiment)
    }
  }, [experimentMetadata.experiment])

  const activeUnits = units.filter(unit => unit.is_active === 1).map(unit => unit.pioreactor_unit)
  const assignedUnits = units.map(unit => unit.pioreactor_unit)

  const showAssignmentAlert = hasFetchedUnits && assignedUnits.length === 0

  return (
    <Fragment>
      <Grid container spacing={2} sx={{ justifyContent: "space-between" }}>
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
          sx={{height: "100%",  justifyContent: "flex-start" }}
          size={{
            xs: 12,
            md: 7
          }}>
          <Charts chartPreferences={chartPreferences} unitsColorMap={unitsColorMap} config={config} timeScale={timeScale} timeWindow={timeWindow} experimentMetadata={experimentMetadata} relabelMap={relabelMap}/>
        </Grid>

        <Grid
          container
          spacing={1}
          sx={{height: "100%",  justifyContent: "flex-end" }}
          size={{
            xs: 12,
            md: 5
          }}>

          <Grid
            size={{
              xs: 12,
              sm: 7,
              md: 7
            }}>
            <Stack direction="row" sx={{ justifyContent: "start" }}>
              <TimeWindowSwitch setTimeWindow={setTimeWindow} timeWindow={timeWindow}/>
            </Stack>
          </Grid>
          <Grid
            size={{
              xs: 12,
              sm: 4,
              md: 4
            }}>
              <TimeFormatSwitch setTimeScale={setTimeScale} timeScale={timeScale}/>
          </Grid>
          <Grid
            size={{
              xs: 1,
              sm: 1,
              md: 1
            }}>
              <ChartPreferencesControl
                chartPageLabel="Overview"
                chartPreferences={chartPreferences}
                experiment={experimentMetadata.experiment}
              />
          </Grid>

          {( cardsConfig['dosings'] === "1") &&
            <Grid size={12}>
              <MediaCard key={experimentMetadata.experiment} activeUnits={activeUnits} experiment={experimentMetadata.experiment} relabelMap={relabelMap}/>
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
