import React from "react";

import CircularProgress from '@mui/material/CircularProgress';
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
import Tooltip from '@mui/material/Tooltip';
import { useConfirm } from 'material-ui-confirm';
import Button from '@mui/material/Button';
import Backdrop from '@mui/material/Backdrop';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import Grid from '@mui/material/Grid';
import Divider from '@mui/material/Divider';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActions from '@mui/material/CardActions';
import List from '@mui/material/List';
import LinearProgress, { linearProgressClasses } from '@mui/material/LinearProgress';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import { Table, TableBody, TableCell, TableHead, TableRow, IconButton, Menu, MenuItem } from '@mui/material';
import ManageInventoryMenu from './components/ManageInventoryMenu';
import LogTableByUnit from './components/LogTableByUnit';
import UsbDriveCard from './components/UsbDriveCard';
import { fetchTaskResult } from "./utils/tasks";
import { getConfig } from "./utils/config";
import { disconnectedGrey, lostRed, disabledColor, readyGreen } from "./utils/color";

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
import UploadIcon from '@mui/icons-material/Upload';
import { styled } from '@mui/material/styles';
import PioreactorIconWithModel from "./components/PioreactorIconWithModel"
import Alert from '@mui/material/Alert';
import Snackbar from './components/Snackbar';

const textIcon = {verticalAlign: "middle", margin: "0px 3px"}

export const stateDisplay = {
  "ready":         {display: "On", color: readyGreen, backgroundColor: "#DDFFDC"},
  "disconnected":  {display: "Off", color: lostRed, backgroundColor: "#fbeae9"},
}


export function StateTypography({ state, isDisabled=false }) {
  const style = {
    color: isDisabled ? disabledColor : stateDisplay[state].color,
    px: "9px",
    py: "1px",
    borderRadius: "16px",
    backgroundColor: stateDisplay[state].backgroundColor,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    lineHeight: 1.3,
    whiteSpace: "nowrap",
    fontWeight: 500,
    fontSize: "0.8125rem",
    verticalAlign: "middle",
  };

  return (
    <Typography component="span" sx={style}>
      {stateDisplay[state].display}
    </Typography>
  );
}

function RestartJobMenu({ jobName, onRestart, isRestarting }) {
  const [anchorEl, setAnchorEl] = React.useState(null);
  const menuOpen = Boolean(anchorEl);

  const handleClose = () => {
    setAnchorEl(null);
  };

  return (
    <React.Fragment>
      <span>
        <IconButton
          size="small"
          aria-label={`More actions for ${jobName}`}
          disabled={isRestarting}
          onClick={(event) => setAnchorEl(event.currentTarget)}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
      </span>
      <Menu anchorEl={anchorEl} open={menuOpen} onClose={handleClose}>
        <MenuItem
          onClick={() => {
            handleClose();
            onRestart(jobName);
          }}
        >
          Restart
        </MenuItem>
      </Menu>
    </React.Fragment>
  );
}


function ManageLeaderMenu({unit}) {
  const [anchorEl, setAnchorEl] = React.useState(null);
  const open = Boolean(anchorEl);
  const confirm = useConfirm();
  const [isRepairing, setIsRepairing] = React.useState(false);
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");

  const showSnackbar = (message) => {
    setSnackbarMessage(message);
    setSnackbarOpen(true);
  };

  const handleSnackbarClose = (_event, reason) => {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  };

  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleReboot = () => {
    confirm({
      description: 'Rebooting this Pioreactor will halt all activity and make the Pioreactor inaccessible for a few minutes.',
      title: `Reboot ${unit}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
      cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},
    }).then(() => {
      handleClose();
      fetch(`/api/units/${unit}/system/reboot`, {method: "POST"})
    }).catch(() => {});
  };

  const handleShutdown = () => {
    confirm({
      description: 'Shutting down this Pioreactor will halt all activity and require a power-cycle to bring it back up.',
      title: `Shutdown ${unit}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
      cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},
    }).then(() => {
      handleClose();
      fetch(`/api/units/${unit}/system/shutdown`, {method: "POST"})
    }).catch(() => {});
  };

  const handleRepair = async () => {
    let dialogResult;
    try {
      dialogResult = await confirm({
        description: `Repair file permissions on ${unit} and run a system status check. This does not reboot the Pioreactor or stop running jobs.`,
        title: `Repair system on ${unit}?`,
        confirmationText: "Repair system",
        confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
        cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},
      });
    } catch (_) {
      return;
    }

    if (dialogResult && dialogResult.confirmed === false) {
      return;
    }

    handleClose();
    setIsRepairing(true);
    try {
      const payload = await fetchTaskResult(`/api/units/${unit}/system/repair`, {
        fetchOptions: {method: "POST"},
        maxRetries: 300,
        delayMs: 200,
      });
      const repairResult = payload?.result?.[unit] || payload?.result;
      if (repairResult?.success) {
        showSnackbar(`Repair completed on ${unit}.`);
      } else {
        showSnackbar(`Repair completed with warnings on ${unit}. Check system logs for details.`);
        console.warn("Repair system result:", repairResult);
      }
    } catch (err) {
      console.error('Repair failed:', err);
      showSnackbar(`Repair failed on ${unit}. Please try again.`);
    } finally {
      setIsRepairing(false);
    }
  };

  return (
    <React.Fragment>
      <Button
        id="manage-leader-button"
        aria-controls={open ? 'manage-leader-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        onClick={handleClick}
        style={{textTransform: "none"}}
      >
        Manage leader <ArrowDropDownIcon/>
      </Button>
      <Menu
        id="manage-leader-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        slotProps={{
          list: {
            'aria-labelledby': 'manage-leader-button',
          },
        }}
      >
        <MenuItem onClick={handleReboot}>
          <ListItemText>Reboot</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleShutdown}>
          <ListItemText>Shutdown</ListItemText>
        </MenuItem>
        <Divider/>
        <MenuItem onClick={handleRepair}>
          <ListItemText>Repair system</ListItemText>
        </MenuItem>
      </Menu>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
        autoHideDuration={2500}
        key={`snackbar-repair-system-${unit}`}
      />
      <Backdrop
        sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.modal + 1 }}
        open={isRepairing}
      >
        <CircularProgress color="inherit" />
      </Backdrop>
    </React.Fragment>
  );
}


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

const BorderLinearProgress = styled(LinearProgress, {
  shouldForwardProp: (prop) => prop !== "isLowSpace",
})(({ theme, isLowSpace }) => ({
  height: 10,
  borderRadius: 5,
  [`&.${linearProgressClasses.colorPrimary}`]: {
    backgroundColor: theme.palette.grey[200],
  },
  [`& .${linearProgressClasses.bar}`]: {
    borderRadius: 5,
    backgroundColor: isLowSpace ? theme.palette.error.light : theme.palette.primary.light,
  },
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
  const [isImporting, setIsImporting] = React.useState(false);
  const confirm = useConfirm();
  const fileInputRef = React.useRef(null);

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

  const handleImport = async (event) => {
    const input = event.target;
    const file = input.files && input.files[0];
    if (!file) {
      input.value = null;
      return;
    }

    const formData = new FormData();
    formData.append('archive', file);

    setIsImporting(true);
    try {
      const response = await fetch('/unit_api/import_zipped_dot_pioreactor', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        let errorMessage = `Import failed with status ${response.status}`;
        try {
          const error = await response.json();
          if (error && error.error) {
            errorMessage = error.error;
          }
        } catch (_) {
        }
        window.alert(errorMessage);
        return;
      }

      window.alert(`Import succeeded. ${leaderHostname} will reboot now.`);
    } catch (err) {
      console.error('Import failed:', err);
      window.alert('Import failed. Please try again.');
    } finally {
      setIsImporting(false);
      input.value = null;
    }
  };

  const handleImportClick = async () => {
    try {
      await confirm({
        description: <><p>Import a previously exported system archive and overwrite this Pioreactor's system data (configuration, calibrations, plugins, etc). The Pioreactor will reboot after the import.</p><p>The name of the Pioreactor you exported from and the name of this Pioreactor must be identical.</p><Alert severity="warning">This will overwrite the existing system data on {leaderHostname}.</Alert></>,
        title: `Import a system archive into ${leaderHostname}?`,
        confirmationText: "Select system archive file",
        confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
        cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},
      });
    } catch (_) {
      return;
    }

    if (fileInputRef.current) {
      fileInputRef.current.click();
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
          <Box sx={{ fontWeight: "fontWeightRegular" }}>System file browser</Box>
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
          <DownloadIcon fontSize="small" sx={textIcon} /> Export system archive
        </Button>
        <Button
          size="small"
          disabled={isImporting}
          onClick={handleImportClick}
          sx={{textTransform: "none"}}
        >
          <UploadIcon fontSize="small" sx={textIcon} /> Import system archive
        </Button>
      </CardActions>
      <input
        type="file"
        accept="application/zip"
        ref={fileInputRef}
        style={{display: 'none'}}
        onChange={handleImport}
      />
      <Backdrop
        sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.modal + 1 }}
        open={isImporting}
      >
        <CircularProgress color="inherit" />
      </Backdrop>
    </Card>
  );
}



function LeaderCard({leaderHostname}) {

  const unit = leaderHostname
  const {client, subscribeToTopic, unsubscribeFromTopic} = useMQTT();
  const [state, setState] = React.useState(null)
  const [versions, setVersions] = React.useState({})
  const [ipv4, setIpv4] = React.useState(null)
  const [WLANaddress, setWLANaddress] = React.useState(null)
  const [ETHAddress, setETHAddress] = React.useState(null)


  React.useEffect(() => {
    if (!client) {
      return undefined;
    }
    const topic = `pioreactor/${unit}/$experiment/monitor/+`;
    subscribeToTopic(topic, onMonitorData, "WorkerCard");
    return () => {
      unsubscribeFromTopic(topic, "WorkerCard");
    };
  }, [client, subscribeToTopic, unsubscribeFromTopic, unit]);


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
              <PioreactorIconWithModel badgeContent={"L"} badgeColor="#fff2cc" sx={{verticalAlign: "middle", mr: "3px", mb: "2px"}} />
              {unit}
            </Typography>
            <Tooltip title={indicatorLabel} placement="right">
              <div>
                <div className="indicator-dot"  style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
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
      <CardActions sx={{display: "flex", justifyContent: "flex-end"}}>
        <ManageLeaderMenu unit={unit} />
      </CardActions>
    </Card>
)}


function formatBytes(bytes) {
  if (bytes == null) {
    return "-";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const precision = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function systemSpaceUsedPercent(space) {
  if (!space?.total_bytes) {
    return 0;
  }

  return Math.min(100, Math.max(0, ((space.total_bytes - space.available_bytes) / space.total_bytes) * 100));
}

function hasLowAvailableSpace(space) {
  if (!space?.total_bytes) {
    return false;
  }

  return (space.available_bytes / space.total_bytes) < 0.1;
}

function SpaceProgressRow({label, space}) {
  const usedPercent = systemSpaceUsedPercent(space);
  const isLowSpace = hasLowAvailableSpace(space);

  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.75 }}>
        <Typography variant="body2" component="div">
          {label}
        </Typography>
        <Typography variant="body2" component="div" color={isLowSpace ? "error" : "text.secondary"}>
          {formatBytes(space?.available_bytes)} available of {formatBytes(space?.total_bytes)}
        </Typography>
      </Box>
      <BorderLinearProgress variant="determinate" value={usedPercent} isLowSpace={isLowSpace} />
    </Box>
  );
}

function SystemSpaceCard() {
  const [space, setSpace] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    let isActive = true;

    async function fetchSystemSpace() {
      setLoading(true);
      setError(null);
      try {
        const [diskResponse, memoryResponse] = await Promise.all([
          fetch("/unit_api/system/disk_space"),
          fetch("/unit_api/system/memory"),
        ]);

        if (!diskResponse.ok || !memoryResponse.ok) {
          throw new Error("Failed to fetch system space.");
        }

        const [disk, memory] = await Promise.all([
          diskResponse.json(),
          memoryResponse.json(),
        ]);

        if (isActive) {
          setSpace({disk, memory});
        }
      } catch (err) {
        console.error(err);
        if (isActive) {
          setError(err.message);
        }
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    }

    fetchSystemSpace();

    return () => {
      isActive = false;
    };
  }, []);

  return (
    <Card>
      <CardContent sx={{p: 2}}>
        <Typography variant="h6" component="h2">
          <Box sx={{ fontWeight: "fontWeightRegular" }}>System space</Box>
        </Typography>

        {loading && (
          <Box sx={{textAlign: "center", mt: 2}}>
            <CircularProgress size={33}/>
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{mt: 2}}>{error}</Alert>
        )}

        {!loading && !error && space && (
          <React.Fragment>
            <SpaceProgressRow label="Disk" space={space.disk} />
            <SpaceProgressRow label="Memory" space={space.memory} />
          </React.Fragment>
        )}
      </CardContent>
    </Card>
  );
}




function LeaderJobs(){

  const webServerJobName = "web server and queue"
  const [mqtt_to_db_streaming_state, set_mqtt_to_db_streaming_state] = React.useState("disconnected")
  const [monitor_state, set_monitor_state] = React.useState("disconnected")
  const [webServerState, setWebServerState] = React.useState("disconnected")
  const [otherLongRunningJobs, setOtherLongRunningJobs] = React.useState([])
  const [restartingJob, setRestartingJob] = React.useState(null)

  async function restartLongRunningJob(jobName) {
    setRestartingJob(jobName);
    try {
      const response = await fetch("/unit_api/jobs/stop", {
        method: "PATCH",
        body: JSON.stringify({ job_name: jobName }),
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json'
        },
      });
      if (!response.ok) {
        throw new Error(`Failed to stop job ${jobName}: ${response.statusText}`);
      }
    } catch (error) {
      console.error(`Error restarting job ${jobName}:`, error);
    } finally {
      setRestartingJob(null);
    }
  }

  async function restartWebServer() {
    setRestartingJob(webServerJobName);
    try {
      const response = await fetch("/unit_api/system/web_server/restart", {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Failed to restart web server: ${response.statusText}`);
      }
    } catch (error) {
      console.error("Error restarting web server:", error);
    } finally {
      setRestartingJob(null);
    }
  }

  React.useEffect(() => {
    let ignore = false;
    const fetchJobs = async () => {
      try {
        const [jobsResult, webResult] = await Promise.allSettled([
          fetch("/unit_api/long_running_jobs/running"),
          fetch("/unit_api/system/web_server/status"),
        ]);

        if (jobsResult.status === "fulfilled") {
          const response = jobsResult.value;
          if (!response.ok) {
            throw new Error(`Failed to fetch long-running jobs: ${response.statusText}`);
          }
          const data = await response.json();

          if (!ignore) {
            let mqttState = "disconnected";
            let monitorState = "disconnected";
            const remainingJobs = [];

            data.forEach((job) => {
              switch (job.job_name) {
                case "mqtt_to_db_streaming":
                  mqttState = "ready";
                  break;
                case "monitor":
                  monitorState = "ready";
                  break;
                default:
                  remainingJobs.push({ job_name: job.job_name, state: "ready" });
                  break;
              }
            });

            set_mqtt_to_db_streaming_state(mqttState);
            set_monitor_state(monitorState);
            setOtherLongRunningJobs(remainingJobs);
          }
        } else {
          console.error("Error fetching long-running jobs:", jobsResult.reason);
        }

        if (webResult.status === "fulfilled") {
          const response = webResult.value;
          if (response.ok) {
            const webData = await response.json();
            if (!ignore) {
              setWebServerState(webData?.state || "disconnected");
            }
          } else {
            console.error("Failed to fetch web server status:", response.statusText);
            if (!ignore) {
              setWebServerState("disconnected");
            }
          }
        } else {
          console.error("Error fetching web server status:", webResult.reason);
          if (!ignore) {
            setWebServerState("disconnected");
          }
        }
      } catch (error) {
        console.error("Error fetching long-running jobs:", error);
        if (!ignore) {
          setWebServerState("disconnected");
        }
      }
    };

    fetchJobs();
  return () => {
    ignore = true;
  };
  }, []);

  return (
    <Card >
      <CardContent sx={{p: 2}}>
         <Typography variant="h6" component="h2">
          <Box sx={{ fontWeight: "fontWeightRegular" }}>Long-running jobs</Box>
        </Typography>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{padding: "6px 0px"}}>Job name</TableCell>
                <TableCell align="right" >Status</TableCell>
                <TableCell align="right" sx={{padding: "6px 0px", width: 36}} />
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell sx={{padding: "6px 0px"}}>{webServerJobName}</TableCell>
                <TableCell align="right"><StateTypography state={webServerState}/></TableCell>
                <TableCell align="right" sx={{padding: "6px 0px"}}>
                  <RestartJobMenu
                    jobName={webServerJobName}
                    onRestart={restartWebServer}
                    isRestarting={restartingJob === webServerJobName}
                  />
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{padding: "6px 0px"}}>mqtt_to_db_streaming</TableCell>
                <TableCell align="right"><StateTypography state={mqtt_to_db_streaming_state}/></TableCell>
                <TableCell align="right" sx={{padding: "6px 0px"}}>
                  <RestartJobMenu
                    jobName="mqtt_to_db_streaming"
                    onRestart={restartLongRunningJob}
                    isRestarting={restartingJob === "mqtt_to_db_streaming"}
                  />
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{padding: "6px 0px"}}>monitor</TableCell>
                <TableCell align="right"><StateTypography state={monitor_state}/></TableCell>
                <TableCell align="right" sx={{padding: "6px 0px"}}>
                  <RestartJobMenu
                    jobName="monitor"
                    onRestart={restartLongRunningJob}
                    isRestarting={restartingJob === "monitor"}
                  />
                </TableCell>
              </TableRow>
              {otherLongRunningJobs.map(element => (
                <React.Fragment key={element.job_name}>
                <TableRow>
                  <TableCell sx={{padding: "6px 0px"}}>{element.job_name}</TableCell>
                  <TableCell align="right"><StateTypography state={element.state}/></TableCell>
                  <TableCell align="right" sx={{padding: "6px 0px"}}>
                    <RestartJobMenu
                      jobName={element.job_name}
                      onRestart={restartLongRunningJob}
                      isRestarting={restartingJob === element.job_name}
                    />
                  </TableCell>
                </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>

      </CardContent>
    </Card>)}

function LeaderContainer({config}) {
  const leaderHostname = config?.["cluster.topology"]?.leader_hostname ?? null;

  return (
    <React.Fragment>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box sx={{ fontWeight: "fontWeightBold" }}>
              Leader
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <ManageInventoryMenu/>
          </Box>
        </Box>
        <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />

      </Box>
      <Grid container spacing={2} sx={{ justifyContent: "flex-start", alignItems: "flex-start" }}>
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
            <SystemSpaceCard/>
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
            <UsbDriveCard/>
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
