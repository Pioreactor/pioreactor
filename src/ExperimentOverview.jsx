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
import Card from "@mui/material/Card";
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';

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
                      lookback={chart.lookback ? eval(chart.lookback) : 10000}
                      fixedDecimals={chart.fixed_decimals}
                      relabelMap={relabelMap}
                      yTransformation={eval(chart.y_transformation || "(y) => y")}
                      dataSourceColumn={chart.data_source_column}
                      isPartitionedBySensor={chart_key === "raw_optical_density"}
                      isLiveChart={true}
                      byDuration={config['ui.overview.settings']['time_display_mode'] === 'hours'}
                    />
                  </Card>
                </Grid>
              </React.Fragment>

        )}
        </Grid>

        <Grid item xs={12} md={5} container spacing={1} justifyContent="flex-end" style={{height: "100%"}}>


          {( config['ui.overview.cards'] && (config['ui.overview.cards']['dosings'] === "1")) &&
            <Grid item xs={12} >
              <MediaCard experiment={experimentMetadata.experiment} config={config} relabelMap={relabelMap}/>
              <Button to="/pioreactors" component={Link} color="primary" style={{textTransform: "none", verticalAlign: "middle", margin: "0px 3px"}}>
                <PioreactorIcon style={{ fontSize: 17, margin: "0px 3px"}} color="primary"/> See all Pioreactor details
              </Button>
            </Grid>
          }


          {( config['ui.overview.cards'] && (config['ui.overview.cards']['event_logs'] === "1")) &&
            <Grid item xs={12}>
              <LogTable experiment={experimentMetadata.experiment} config={config} relabelMap={relabelMap}/>
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
