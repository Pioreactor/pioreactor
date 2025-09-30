import React from "react";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

import CircularProgress from '@mui/material/CircularProgress';
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
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
import List from '@mui/material/List';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import LoadingButton from "@mui/lab/LoadingButton";
import { Table, TableBody, TableCell, TableHead, TableRow, TableContainer } from '@mui/material';
import ManageInventoryMenu from './components/ManageInventoryMenu';
import LogTableByUnit from './components/LogTableByUnit';
import {disconnectedGrey, lostRed, disabledColor, readyGreen, checkTaskCallback, getConfig} from "./utilities"
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import { Link } from 'react-router-dom';

import {
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemButton,
} from '@mui/material';
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined';
import InsertDriveFileOutlinedIcon from '@mui/icons-material/InsertDriveFileOutlined';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DownloadIcon from '@mui/icons-material/Download';
import { styled } from '@mui/material/styles';
import Chip from '@mui/material/Chip';
import PioreactorIconWithModel from "./components/PioreactorIconWithModel"
import PioreactorIcon from "./components/PioreactorIcon"

// Activate the UTC plugin
dayjs.extend(utc);

const textIcon = {verticalAlign: "middle", margin: "0px 3px"}

export const stateDisplay = {
  "ready":         {display: "On", color: readyGreen, backgroundColor: "#DDFFDC"},
  "disconnected":  {display: "Off", color: lostRed, backgroundColor: "#fbeae9"},
}


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
      <Button sx={{textTransform: "none"}} size="small" onClick={rebootWorker}>
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


const Path = styled(Box)(({ theme }) => ({
  display: 'inline-block',
  fontFamily: 'monospace',
  backgroundColor: theme.palette.grey[100],
  padding: theme.spacing(1),
  paddingLeft: theme.spacing(2),
  paddingRight: theme.spacing(2),
  borderRadius: theme.shape.borderRadius,
  color: theme.palette.text.primary,
  marginLeft: theme.spacing(0),
  marginTop: theme.spacing(2),
}));

const FileDir = styled(Box)(({ theme }) => ({
  fontFamily: 'monospace',
  color: theme.palette.text.primary,
}));


function PathViewer({ path }) {
  return (
    <Path>
      {path || '/'}
    </Path>
  );
}

function FileDirViewer({ filedir }) {
  return (
    <FileDir>
      {filedir}
    </FileDir>
  );
}

function DirectoryNavigatorCard({leaderHostname}) {
  const [currentPath, setCurrentPath] = React.useState('');
  const [dirs, setDirs] = React.useState([]);
  const [files, setFiles] = React.useState([]);
  const [loading, setLoading] = React.useState(false);

  const handleExport = async () => {
    try {
      const response = await fetch('/unit_api/zipped_dot_pioreactor');
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${leaderHostname}_dot_pioreactor.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    }
  };

  React.useEffect(() => {
    fetchDirectory(currentPath);
  }, [currentPath]);

  const fetchDirectory = async (path = '') => {
    setLoading(true);
    try {
      // build the endpoint from current path
      const apiPath = path ? `/unit_api/system/path/${path}` : '/unit_api/system/path/';
      const resp = await fetch(apiPath);
      if (!resp.ok) {
        // handle errors appropriately in real code
        throw new Error(`Failed to fetch: ${resp.status}`);
      }
      const data = await resp.json();
      setDirs(data.dirs || []);
      setFiles(data.files || []);
    } catch (error) {
      console.error(error);
      // handle error state if desired
    } finally {
      setLoading(false);
    }
  };

  const handleDirClick = (dirName) => {
    // Navigate deeper into the directory tree
    setCurrentPath((prev) => (prev ? `${prev}/${dirName}` : dirName));
  };

  const handleFileClick = (fileName) => {
    // Trigger a file download or open in a new tab
    // Construct path from currentPath + file
    const filePath = currentPath ? `${currentPath}/${fileName}` : fileName;
    window.open(`/unit_api/system/path/${filePath}`, '_blank');
  };

  const handleGoUp = () => {
    // Go up one directory
    setCurrentPath((prev) => {
      if (!prev) return '';
      const parts = prev.split('/');
      parts.pop();
      return parts.join('/');
    });
  };

  return (
    <Card sx={{minHeight: "300px"}}>
      <CardContent sx={{p:2}}>
        <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">System file browser</Box>
        </Typography>
        <Box sx={{maxHeight: "450px", overflowY: "scroll"}}>
          <PathViewer path=
          {
          currentPath
            ? `~/.pioreactor/${currentPath}`
            : `~/.pioreactor/`
           }
          />

        {!loading && (
          <List dense={true}>

              <ListItem onClick={() => handleGoUp()} disablePadding={true}>
                <ListItemButton disabled={!currentPath}>
                <ListItemIcon>
                  <ArrowBackIcon />
                </ListItemIcon>
                <ListItemText primary={"Back"} />
                </ListItemButton>
              </ListItem>

            {/* Directories */}
            {dirs.map((dir) => (
              <ListItem onClick={() => handleDirClick(dir)} key={dir} disablePadding={true}>
                <ListItemButton>
                <ListItemIcon>
                  <FolderOutlinedIcon />
                </ListItemIcon>
                <ListItemText primary={<FileDirViewer filedir={dir}/> } />
                </ListItemButton>
              </ListItem>
            ))}

            {/* Files */}
            {files.map((file) => (
              <ListItem
                onClick={() => handleFileClick(file)}
                key={file}
                disablePadding={true}
                >
                <ListItemButton>
                <ListItemIcon>
                  <InsertDriveFileOutlinedIcon />
                </ListItemIcon>
                <ListItemText primary={<FileDirViewer filedir={file}/> } />
                </ListItemButton>
              </ListItem>
            ))}

            {dirs.length === 0 && files.length === 0 && (
              <ListItem>
                <ListItemText
                  primary={
                    <Typography variant="body2" component="p" color="textSecondary">
                      Directory is empty.
                    </Typography>
                  }
                />
              </ListItem>
            )}
          </List>
        )}
        </Box>
      <Divider sx={{margin: "5px 0px"}}/>
      </CardContent>
      <CardActions sx={{ display: 'flex', justifyContent: 'flex-end', mr: 2}}>
        <Button
          size="small"
          onClick={handleExport}

          sx={{textTransform: "none"}}
        >
          <DownloadIcon fontSize="small" sx={textIcon} /> Export system files
        </Button>
      </CardActions>
    </Card>
  );
}



function LeaderCard({leaderHostname}) {

  const unit = leaderHostname
  const {client, subscribeToTopic} = useMQTT();
  const [state, setState] = React.useState(null)
  const [versions, setVersions] = React.useState({})
  const [ipv4, setIpv4] = React.useState(null)
  const [WLANaddress, setWLANaddress] = React.useState(null)
  const [ETHAddress, setETHAddress] = React.useState(null)


  React.useEffect(() => {
    if (client) {
      subscribeToTopic(`pioreactor/${unit}/$experiment/monitor/+`, onMonitorData, "WorkerCard");
    }
  }, [client]);


  const onMonitorData = (topic, message) => {
    if (!message || !topic) return;

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


  return (
    <Card sx={{ minWidth: 275 }}>
      <CardContent>

        <div style={{display: "flex", justifyContent: "space-between"}}>

          <div style={{display: "flex", justifyContent: "left"}}>
            <Typography sx={{
                fontSize: 20,
                color: "rgba(0, 0, 0, 0.87)",
                fontWeight: 500,
              }}
              gutterBottom>
              <PioreactorIconWithModel badgeContent={"◎"}  sx={{verticalAlign: "middle", mr: "3px", mb: "2px"}} />
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
              if (!ignore){
                setOtherLongRunningJobs((prevJobs) => [...prevJobs, { job_name: job.job_name, state: "ready" }]);
              }
              break;
          }
        }
      )})
      .catch((error) => {
        console.error("Error fetching long-running jobs:", error);
      });
  return () => {
    ignore = true;
  };
  }, []);

  return (
    <Card >
      <CardContent sx={{p: 2}}>
         <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">Long-running jobs</Box>
        </Typography>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{padding: "6px 0px"}}>Job name</TableCell>
                <TableCell align="right" >Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell sx={{padding: "6px 0px"}}>mqtt_to_db_streaming</TableCell>
                <TableCell align="right"><StateTypography state={mqtt_to_db_streaming_state}/></TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{padding: "6px 0px"}}>monitor</TableCell>
                <TableCell align="right"><StateTypography state={monitor_state}/></TableCell>
              </TableRow>
              {otherLongRunningJobs.map(element => (
                <React.Fragment key={element.job_name}>
                <TableRow>
                  <TableCell sx={{padding: "6px 0px"}}>{element.job_name}</TableCell>
                  <TableCell align="right"><StateTypography state={element.state}/></TableCell>
                </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>

      </CardContent>
    </Card>)}

function ClusterClockCard({leaderHostname}){
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
      await checkTaskCallback(broadcastData.result_url_path);
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
        <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">Cluster clocks</Box>
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
          <TableContainer sx={{ maxHeight: '400px', width: '100%', overflowY: 'auto' }}>
            <Table size="small" sx={{mt: 1}}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{padding: "6px 0px"}}>Pioreactor</TableCell>
                  <TableCell align="right" sx={{padding: "6px 0px"}}>Clock time (localtime)</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.entries(clockData).map(([unitName, info]) => {
                  return (
                    <TableRow key={unitName}>
                      <TableCell sx={{padding: "6px 0px"}}>
                        <Chip
                          size="small"
                          icon={<PioreactorIcon/>}
                          label={unitName}
                          clickable
                          component={Link}
                          to={leaderHostname === unitName ? "/leader" : "/pioreactors/" + unitName}
                          />
                      </TableCell>
                      <TableCell align="right" sx={{padding: "6px 0px"}}>{info?.clock_time ? dayjs.utc(info.clock_time, 'YYYY-MM-DD[T]HH:mm:ss.SSS[Z]').local().format('MMM D, YYYY HH:mm:ss') : "No data received"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
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

function LeaderContainer({config}) {

  const [leaderHostname, setLeaderHostname] = React.useState(null)

  React.useEffect(()=>{
    if (config?.['cluster.topology']){
      setLeaderHostname(config['cluster.topology']['leader_hostname'])
    }
  })

  return (
    <React.Fragment>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Leader
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <ManageInventoryMenu/>
          </Box>
        </Box>
        <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />

      </Box>
      <Grid container spacing={2} justifyContent="flex-start" alignItems="flex-start">
        <Grid
          container
          spacing={2}
          size={{
            md: 5,
            xs: 12,
            sm: 12
          }}>
          <Grid
            size={{
              xs: 12,
              sm: 12
            }}>
            <LeaderCard leaderHostname={leaderHostname}/>
          </Grid>
          <Grid
            size={{
              xs: 12,
              sm: 12
            }}>
            <LeaderJobs/>
          </Grid>
          <Grid
            size={{
              xs: 12,
              sm: 12
            }}>
            <ClusterClockCard leaderHostname={leaderHostname}/>
          </Grid>
        </Grid>

        <Grid
          container
          spacing={2}
          size={{
            md: 7,
            xs: 12,
            sm: 12
          }}>
          <Grid
            size={{
              xs: 12,
              sm: 12
            }}>
            <DirectoryNavigatorCard leaderHostname={leaderHostname}/>
          </Grid>
          <Grid
            size={{
              xs: 12,
              sm: 12
            }}>
            <LogTableByUnit experiment="$experiment" unit={leaderHostname} level="debug"/>
          </Grid>
        </Grid>
      </Grid>
    </React.Fragment>
  );
}

function Leader({title}) {
  const [config, setConfig] = React.useState({})

  React.useEffect(() => {
    document.title = title;
  }, [title]);

  React.useEffect(() => {
    getConfig(setConfig)
  }, []);


  return (
    <MQTTProvider name="leader" config={config}>
      <Grid container spacing={2}>
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <LeaderContainer config={config}/>
        </Grid>
      </Grid>
    </MQTTProvider>
  );
}

export default Leader;
