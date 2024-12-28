import React from "react";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

import CircularProgress from '@mui/material/CircularProgress';
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
import PioreactorIcon from "./components/PioreactorIcon";
import Tooltip from '@mui/material/Tooltip';
import { useConfirm } from 'material-ui-confirm';
import Button from '@mui/material/Button';
import RestartAltIcon from '@mui/icons-material/RestartAlt';

import Grid from '@mui/material/Grid';
import TextField from '@mui/material/TextField';
import Divider from '@mui/material/Divider';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActions from '@mui/material/CardActions';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import LoadingButton from "@mui/lab/LoadingButton";
import { Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import ManageInventoryMenu from './components/ManageInventoryMenu';
import {disconnectedGrey, lostRed, disabledColor, stateDisplay, checkTaskCallback, getConfig} from "./utilities"

import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';

// Activate the UTC plugin
dayjs.extend(utc);

const textIcon = {verticalAlign: "middle", margin: "0px 3px"}

function StateTypography({ state, isDisabled=false }) {
  const style = {
    color: isDisabled ? disabledColor : stateDisplay[state].color,
    padding: "1px 9px",
    borderRadius: "16px",
    backgroundColor: stateDisplay[state].backgroundColor,
    display: "inline-block",
    fontWeight: 500
  };

  return (
    <Typography display="block" gutterBottom sx={style}>
      {stateDisplay[state].display}
    </Typography>
  );
}


function Reboot({unit}) {

  const confirm = useConfirm();

  const rebootWorker = () => {
    confirm({
      description: 'Rebooting this Pioreactor will halt all activity and make the Pioreactor inaccessible for a few minutes.',
      title: `Reboot ${unit}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
    }).then(() => {
      fetch(`/api/units/${unit}/system/reboot`, {method: "POST"})
    }).catch(() => {});
  };

  return (
      <Button style={{textTransform: "none"}} size="small" onClick={rebootWorker}>
        <RestartAltIcon fontSize="small" sx={textIcon} />Reboot
      </Button>
)}


function Shutdown({unit}) {

  const confirm = useConfirm();

  const shworker = () => {
    confirm({
      description: 'Shutting down this Pioreactor will halt all activity and require a power-cycle to bring it back up.',
      title: `Shutdown ${unit}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
    }).then(() => {
      fetch(`/api/units/${unit}/system/shutdown`, {method: "POST"})
    }).catch(() => {});
  };

  return (
      <Button style={{textTransform: "none"}} size="small" onClick={shworker}>
        <PowerSettingsNewIcon fontSize="small" sx={textIcon} />Shutdown
      </Button>
)}




function LeaderCard({config}) {

  const [unit, setUnit] = React.useState("")
  const {client, subscribeToTopic} = useMQTT();
  const [state, setState] = React.useState(null)
  const [versions, setVersions] = React.useState({})
  const [ipv4, setIpv4] = React.useState(null)
  const [WLANaddress, setWLANaddress] = React.useState(null)
  const [ETHAddress, setETHAddress] = React.useState(null)


  React.useEffect(() => {
    setUnit(config['cluster.topology']?.leader_hostname)
    if (unit && client) {
      subscribeToTopic(`pioreactor/${unit}/$experiment/monitor/+`, onMonitorData, "WorkerCard");
    }
  }, [config, unit, client]);


  const onMonitorData = (topic, message, packet) => {
    const setting = topic.toString().split('/').pop()
    switch (setting) {
      case "$state":
        setState(message.toString());
        break;
      case "versions":
        if (message.toString()){
          setVersions(JSON.parse(message.toString()));
        } else {
          setVersions({})
        }
        break;
      case "ipv4":
        setIpv4(message.toString());
        break;
      case "wlan_mac_address":
        setWLANaddress(message.toString());
        break;
      case "eth_mac_address":
        setETHAddress(message.toString());
        break;
      default:
        break;
    }
  }

  const getIndicatorDotColor = (state) => {
    if (state === "disconnected") {
      return disconnectedGrey
    }
    else if (state === "lost"){
      return lostRed
    }
    else if (state === null){
      return "#ececec"
    }
    else {
      return "#2FBB39"
    }
  }

  const getInicatorLabel = (state) => {
    if ((state === "disconnected") ) {
      return "Offline"
    }
    else if ((state === "disconnected")){
      return "Offline, change inventory status in config.ini"
    }
    else if (state === "lost"){
      return "Lost, something went wrong. Try manually power-cycling the unit."
    }
    else if (state === null){
      return "Waiting for information..."
    }
    else {
      return "Online"
    }
  }

  const indicatorDotColor = getIndicatorDotColor(state)
  const indicatorDotShadow = 2
  const indicatorLabel = getInicatorLabel(state)

  const softwareVersion = () => {
    const { app: version } = versions;
    return version || "-";
  };

  const uiVersion = () => {
    const { ui: version } = versions;
    return version || "-";
  };

  return (
    <Card sx={{ minWidth: 275 }}>
      <CardContent>

        <div style={{display: "flex", justifyContent: "space-between"}}>
          <Typography sx={{ fontSize: 14 }} color={"text.secondary" } gutterBottom>
           Leader
          </Typography>
        </div>

        <div style={{display: "flex", justifyContent: "space-between"}}>

          <div style={{display: "flex", justifyContent: "left"}}>
            <Typography sx={{
                fontSize: 20,
                color: "rgba(0, 0, 0, 0.87)",
                fontWeight: 500,
              }}
              gutterBottom>
              <PioreactorIcon  style={{verticalAlign: "middle", marginRight: "3px"}} sx={{ display: {xs: 'none', sm: 'none', md: 'inline' } }}/>
              {unit}
            </Typography>
            <Tooltip title={indicatorLabel} placement="right">
              <div>
                <div className="indicator-dot" style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
              </div>
            </Tooltip>
          </div>


        </div>


        <Divider sx={{margin: "5px 0px"}}/>

        <table style={{borderCollapse: "separate", borderSpacing: "5px", fontSize: "0.90rem"}}>
          <tbody style={{color: "inherit"}}>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                Software version
            </td>
            <td >
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{softwareVersion()}</code>
            </td>
          </tr>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                UI version
            </td>
            <td >
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{uiVersion()}</code>
            </td>
          </tr>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                IPv4
            </td>
            <td>
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{ipv4 || "-"}</code>
            </td>
          </tr>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                Raspberry Pi
            </td>
            <td >
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{versions.rpi_machine || "-"}</code>
            </td>
          </tr>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                WLAN MAC
            </td>
            <td>
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{WLANaddress || "-"}</code>
            </td>
          </tr>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                Ethernet MAC
            </td>
            <td>
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{ETHAddress || "-"}</code>
            </td>
          </tr>
          </tbody>
        </table>
        <Divider sx={{margin: "5px 0px"}}/>
      </CardContent>
      <CardActions sx={{display: "flex", justifyContent: "space-between"}}>
        <Box>
          <Reboot unit={unit} />
          <Shutdown unit={unit} />
        </Box>
      </CardActions>
    </Card>
)}




function LeaderJobs(){

  const [mqtt_to_db_streaming_state, set_mqtt_to_db_streaming_state] = React.useState("disconnected")
  const [monitor_state, set_monitor_state] = React.useState("disconnected")
  const [otherLongRunningJobs, setOtherLongRunningJobs] = React.useState([])

  React.useEffect(() => {
    let ignore = false;
    fetch("/unit_api/long_running_jobs/running")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to fetch long-running jobs: ${response.statusText}`);
        }
        return response.json();
      })
      .then((data) => {
        data.map(job => {
          switch (job.job_name) {
            case "mqtt_to_db_streaming":
              set_mqtt_to_db_streaming_state("ready");
              break;
            case "monitor":
              set_monitor_state("ready");
              break;
            default:
              // Assume anything else goes to other long-running jobs
              if (!ignore){
                setOtherLongRunningJobs((prevJobs) => [...prevJobs, { job_name: job.job_name, state: "ready" }]);
              }
              break;
          }
        }
      )})
      .catch((error) => {
        console.error("Error fetching long-running jobs:", error);
        // Optionally, handle the error state here
      });
  return () => {
    ignore = true;
  };
  }, []);

  return (
    <Card >
      <CardContent sx={{p: "10px 20px 20px 20px"}}>
        <Typography variant="h6" component="h3" gutterBottom>
          Leader's long-running jobs
        </Typography>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Job name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Systemd logs</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>mqtt_to_db_streaming</TableCell>
                <TableCell><StateTypography state={mqtt_to_db_streaming_state}/></TableCell>
                <TableCell></TableCell>
              </TableRow>
              <TableRow>
                <TableCell>monitor</TableCell>
                <TableCell><StateTypography state={monitor_state}/></TableCell>
                <TableCell></TableCell>
              </TableRow>
              {otherLongRunningJobs.map(element => (
                <React.Fragment key={element.job_name}>
                <TableRow>
                  <TableCell>{element.job_name}</TableCell>
                  <TableCell><StateTypography state={element.state}/></TableCell>
                  <TableCell></TableCell>
                </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>

      </CardContent>
    </Card>)}

function ClusterClockCard(){
  const [clockData, setClockData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [updatingClock, setUpdatingClock] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [timestampLocal, setTimestampLocal] = React.useState(dayjs().local().format('YYYY-MM-DD HH:mm:ss'));

  async function fetchBroadcastData() {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch('/api/units/$broadcast/system/utc_clock', {
        method: 'GET'
      });

      if (!response.ok) {
        throw new Error(`Broadcast request failed with status ${response.status}`);
      }

      const broadcastData = await response.json();

      // Poll for the final result using checkTaskCallback
      const finalResult = await checkTaskCallback(broadcastData.result_url_path);

      setClockData(finalResult.result);
    } catch (err) {
      setError(err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    fetchBroadcastData();
  }, []);


  async function handlePostTimestamp() {
    setUpdatingClock(true)
    try {
      const response = await fetch('/api/system/utc_clock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ utc_clock_time: dayjs(timestampLocal, 'YYYY-MM-DD HH:mm:ss').utc().format() })
      });
      if (!response.ok) {
        throw new Error(`Request failed with status: ${response.status}`);
      }
      const broadcastData = await response.json();
      const finalResult = await checkTaskCallback(broadcastData.result_url_path);
      await new Promise(r => setTimeout(r, 1000));

      setUpdatingClock(false)
      fetchBroadcastData();

      // Optionally handle success, e.g., show a confirmation message
    } catch (err) {
      console.error('Error posting timestamp:', err);
    }
  }

  return (
    <Card>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="h6" component="h3" gutterBottom>
          Cluster clocks
        </Typography>

        {loading && (
          <Box sx={{textAlign: "center"}}>
            <CircularProgress size={33}/>
          </Box>
        )}

        {error && (
          <Typography variant="body1" color="error">
            {error}
          </Typography>
        )}

        {!loading && !error && clockData && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Unit</TableCell>
                <TableCell>Clock time (localtime)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(clockData).map(([unitName, info]) => {
                return (
                  <TableRow key={unitName}>
                    <TableCell>{unitName}</TableCell>
                    <TableCell>{info?.clock_time ? dayjs.utc(info.clock_time, 'YYYY-MM-DD[T]HH:mm:ss.SSS[Z]').local().format('MMM D, YYYY HH:mm:ss') : "No data"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}

        <Box sx={{ mt: 4 }}>
        <TextField
          size="small"
          variant="outlined"
          label="Timestamp (localtime)"
          value={timestampLocal}
          onChange={(e) => setTimestampLocal(e.target.value)}
        />
        <LoadingButton
          variant="text"
          loading={updatingClock}
          sx={{ ml: 2, textTransform: "none" }}
          onClick={handlePostTimestamp}
        >
          Update clocks
        </LoadingButton>
      </Box>
      </CardContent>
    </Card>
  );
}

function ClusterSettingsContainer({config}) {
  return (
    <React.Fragment>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Cluster settings
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <ManageInventoryMenu/>
          </Box>
        </Box>
        <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />

      </Box>

      <Grid container spacing={2}>
        <Grid item md={5} xs={12} sm={12}>
          <LeaderCard config={config}/>
        </Grid>
        <Grid item xs={7} md={7}>
          <LeaderJobs/>
        </Grid>
        <Grid item xs={5} md={5}>
          <ClusterClockCard/>
        </Grid>
      </Grid>
    </React.Fragment>
  );
}

function ClusterSettings({title}) {
  const [config, setConfig] = React.useState({})

  React.useEffect(() => {
    document.title = title;
  }, [title]);

  React.useEffect(() => {
    getConfig(setConfig)
  }, []);


  return (
    <MQTTProvider name="cluster-settings" config={config}>
      <Grid container spacing={2}>
        <Grid item md={12} xs={12}>
          <ClusterSettingsContainer config={config}/>
        </Grid>
      </Grid>
    </MQTTProvider>
  );
}

export default ClusterSettings;
