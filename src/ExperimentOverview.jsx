import React from "react";

import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import LogTable from "./components/LogTable";
import ExperimentSummary from "./components/ExperimentSummary";
import Chart from "./components/Chart";
import MediaCard from "./components/MediaCard";
import PioreactorIcon from './components/PioreactorIcon';
import { Link } from 'react-router-dom';
import {getConfig, getRelabelMap} from "./utilities"


function Overview(props) {

  const [experimentMetadata, setExperimentMetadata] = React.useState({})
  const [relabelMap, setRelabelMap] = React.useState({})
  const [config, setConfig] = React.useState({})
  const [charts, setCharts] = React.useState({})

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
                <Chart
                  config={config}
                  dataSource={chart.data_source}
                  title={chart.title}
                  topic={chart.mqtt_topic}
                  payloadKey={chart.payload_key}
                  yAxisLabel={chart.y_axis_label}
                  experiment={experimentMetadata.experiment}
                  deltaHours={chart.delta_hours || experimentMetadata.delta_hours}
                  interpolation={chart.interpolation || "stepAfter"}
                  yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                  lookback={eval(chart.lookback) || 10000}
                  fixedDecimals={chart.fixed_decimals}
                  relabelMap={relabelMap}
                  yTransformation={eval(chart.y_transformation || "(y) => y")}
                  dataSourceColumn={chart.data_source_column}
                  key={`chart-${chart_key}`}
                  isODReading={chart_key === "raw_optical_density"}
                />
              </Grid>
              </React.Fragment>

        )}
        </Grid>

        <Grid item xs={12} md={5} container spacing={1} justifyContent="flex-end" style={{height: "100%"}}>


          {( config['ui.overview.cards'] && (config['ui.overview.cards']['dosings'] === "1")) &&
            <Grid item xs={12} >
              <MediaCard experiment={experimentMetadata.experiment} config={config} relabelMap={relabelMap}/>
              <Button to="/pioreactors" component={Link} color="primary" style={{textTransform: "none", verticalAlign: "middle", margin: "0px 3px"}}> <PioreactorIcon style={{ fontSize: 17 }} color="primary"/> See all Pioreactor details </Button>
            </Grid>
          }


          {( config['ui.overview.cards'] && (config['ui.overview.cards']['event_logs'] === "1")) &&
            <Grid item xs={12}>
              <LogTable experiment={experimentMetadata.experiment} config={config} relabelMap={relabelMap}/>
            </Grid>
          }

        </Grid>
      </Grid>
    </React.Fragment>
  );
}
export default Overview;
