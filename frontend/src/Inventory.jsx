import React, {useState, useEffect, useCallback} from "react";
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import CardContent from '@mui/material/CardContent';
import MenuItem from '@mui/material/MenuItem';
import ListSubheader from '@mui/material/ListSubheader';
import Select from '@mui/material/Select';
import InputLabel from '@mui/material/InputLabel';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
import ManageInventoryMenu from './components/ManageInventoryMenu';
import Box from '@mui/material/Box';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormControl from '@mui/material/FormControl';
import Button from '@mui/material/Button';
import Switch from '@mui/material/Switch';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import FlareIcon from '@mui/icons-material/Flare';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import LoadingButton from '@mui/lab/LoadingButton';
import CheckIcon from '@mui/icons-material/Check';
import Divider from '@mui/material/Divider';
import RemoveCircleOutlineRoundedIcon from '@mui/icons-material/RemoveCircleOutlineRounded';
import CircularProgress from '@mui/material/CircularProgress';
import Backdrop from '@mui/material/Backdrop';
import { useConfirm } from 'material-ui-confirm';
import { useNavigate, Link } from 'react-router';
import UnderlineSpan from "./components/UnderlineSpan";
import PioreactorIcon from "./components/PioreactorIcon";
import PioreactorIconWithModel from "./components/PioreactorIconWithModel";
import { getConfig } from "./utilities";
import { disconnectedGrey, lostRed, inactiveGrey, readyGreen } from "./color";
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import Snackbar from '@mui/material/Snackbar';
import Menu from "@mui/material/Menu";
import ListItemText from "@mui/material/ListItemText";
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import Alert from '@mui/material/Alert';
import RefreshIcon from '@mui/icons-material/Refresh';
import SelfTestDialog from "./components/SelfTestDialog";



import { useExperiment } from './providers/ExperimentContext';

// Hook to fetch available models from backend
const useAvailableModels = () => {
  const [models, setModels] = useState([]);
  useEffect(() => {
    fetch('/api/models')
      .then((r) => r.json())
      .then((data) => setModels(data.models || []));
  }, []);
  return models;
};

let cachedSelfTestJobDefinition = null;
let selfTestJobDefinitionPromise = null;

function requestSelfTestJobDefinition() {
  if (cachedSelfTestJobDefinition) {
    return Promise.resolve(cachedSelfTestJobDefinition);
  }
  if (!selfTestJobDefinitionPromise) {
    const pendingRequest = fetch("/api/jobs/descriptors")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch contrib jobs");
        }
        return response.json();
      })
      .then((data) => {
        const selfTestJob = data.find((job) => job.job_name === "self_test") || null;
        cachedSelfTestJobDefinition = selfTestJob;
        return selfTestJob;
      });
    selfTestJobDefinitionPromise = pendingRequest
      .catch((error) => {
        selfTestJobDefinitionPromise = null;
        throw error;
      })
      .then((job) => {
        selfTestJobDefinitionPromise = null;
        return job;
      });
  }
  return selfTestJobDefinitionPromise;
}

function useSelfTestJobDefinition() {
  const [definition, setDefinition] = useState(cachedSelfTestJobDefinition);

  useEffect(() => {
    if (cachedSelfTestJobDefinition) {
      return;
    }

    let isActive = true;
    requestSelfTestJobDefinition()
      .then((job) => {
        if (!isActive) {
          return;
        }
        setDefinition(job);
      })
      .catch(() => {});

    return () => {
      isActive = false;
    };
  }, []);

  return definition;
}

function parsePayloadToType(payloadString, typeOfSetting) {
  if (typeOfSetting === "numeric") {
    return [null, ""].includes(payloadString) ? payloadString : parseFloat(payloadString);
  }
  if (typeOfSetting === "boolean") {
    if ([null, ""].includes(payloadString)) {
      return null;
    }
    return (["1", "true", "True", 1].includes(payloadString));
  }
  return payloadString;
}

const textIcon = {verticalAlign: "middle", margin: "0px 3px"}

function Header(props) {
  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h1">
          <Box fontWeight="fontWeightBold">
            Inventory
          </Box>
        </Typography>
        <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
          <AddNewPioreactor setWorkers={props.setWorkers}/>
          <Divider orientation="vertical" flexItem variant="middle"/>
          <ManageInventoryMenu/>
        </Box>
      </Box>
      <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />
    </Box>
  )
}






function AddNewPioreactor({setWorkers}){
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [model, setModel] = React.useState(["pioreactor_40ml", "1.5"])

  const [isError, setIsError] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")

  const [isSuccess, setIsSuccess] = useState(false)
  const [successMsg, setSuccessMsg] = useState("")

  const [isRunning, setIsRunning] = useState(false)
  const [expectedPathMsg, setExpectedPathMsg] = useState("")

  // Discovery state for auto-detected workers
  const [discoveredWorkers, setDiscoveredWorkers] = useState([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const availableModels = useAvailableModels();

  const loadDiscoveredWorkers = useCallback(() => {
    setIsDiscovering(true);
    fetch('/api/workers/discover')
      .then((res) => res.json())
      .then((data) => setDiscoveredWorkers(data))
      .catch(() => setDiscoveredWorkers([]))
      .finally(() => setIsDiscovering(false));
  }, []);

  useEffect(() => {
    if (open) {
      loadDiscoveredWorkers();
    }
  }, [open, loadDiscoveredWorkers]);

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleNameChange = evt => {
    setName(evt.target.value)
  }




  const onSubmit = (event) =>{
    event.preventDefault()
    if (!name) {
      setIsError(true)
      setErrorMsg("Provide the hostname for the new Pioreactor worker")
      return
    }
    else if (!model) {
      setIsError(true)
      setErrorMsg("Provide the model for the new Pioreactor worker. You can change the model later, too.")
      return
    }
    setIsError(false)
    setIsSuccess(false)
    setIsRunning(true)
    setExpectedPathMsg("Setting up your new Pioreactor...")
    fetch('/api/workers/setup', {
        method: "POST",
        body: JSON.stringify({name: name, model: model[0], version: model[1]}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
    })
    .then(response => {
        setIsRunning(false)
        setExpectedPathMsg("")
        if(!response.ok){
          setIsError(true)
          response.json().then(data => setErrorMsg(`Unable to complete connection. The following error occurred: ${data.error}`))
        } else {
          setIsSuccess(true)
          setWorkers((prevWorkers) => [...prevWorkers, {pioreactor_unit: name, is_active: true, model_name: model[0], model_version: model[1]}].sort((a, b) => (a.pioreactor_unit > b.pioreactor_unit) ? 1 : -1))
          setSuccessMsg(`Success! Rebooting ${name} now. Add another?`)
        }
    })
  }

  const standard = availableModels.filter(m => !(m.is_contrib) && !(m.is_legacy));
  const contrib = availableModels.filter(m => (m.is_contrib));
  const legacy = availableModels.filter(m => (m.is_legacy));
  return (
    <React.Fragment>
    <Button
      id="add-new-pioreactor-button"
      onClick={handleClickOpen}
      sx={{ textTransform: 'none', float: 'right', marginRight: 0 }}
      color="primary"
    >
      <AddIcon fontSize="small" sx={textIcon}/> Add new Pioreactor
    </Button>
    <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title">
      <DialogTitle>
        Add a new Pioreactor to your cluster
        <IconButton
          aria-label="close"
          onClick={handleClose}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[500],
          }}
          size="large">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <p>First, follow the instructions <a rel="noopener noreferrer" target="_blank" href="https://docs.pioreactor.com/user-guide/software-set-up#adding-additional-workers-to-your-cluster">here</a> to set up your new Pioreactor's worker software.</p>

        <p>After,

        <ol>
         <li> worker image installation is complete and,</li>
         <li> the new worker is powered on and, </li>
         <li> the new worker is displaying a blue light, </li>
        </ol>

        provide the hostname you used when installing the Pioreactor image onto the Raspberry Pi, and the Pioreactor model (this can be changed later).</p>
        <p>Your existing leader will automatically connect the new Pioreactor to the cluster.</p>
        <Box sx={{ mt: 2, mb: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
            <Typography variant="subtitle1" sx={{ mr: 1 }}>Discovered available workers:</Typography>
            <Tooltip title="Refresh discovered workers">
              <span>
                <IconButton size="small" onClick={loadDiscoveredWorkers} disabled={isDiscovering}>
                  {isDiscovering ? <CircularProgress size={16} /> : <RefreshIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>
          </Box>
          {isDiscovering ? (
            <CircularProgress size={20} sx={{ mt: 1 }} />
          ) : discoveredWorkers.length === 0 ? (
            <Typography variant="body2" component="p" color="textSecondary">No workers found. This discovery process isn't guaranteed however.</Typography>
          ) : (
            discoveredWorkers.map((w) => (
              <Chip
                icon={<PioreactorIcon/>}
                key={w.pioreactor_unit}
                label={w.pioreactor_unit}
                onClick={() => setName(w.pioreactor_unit)}
                sx={{ mr: 1, mb: 1 }}
              />
            ))
          )}
        </Box>
        <div>
          <TextField
            required
            size="small"
            id="new-pioreactor-name"
            label="Hostname"
            variant="outlined"
            sx={{mt: "15px", maxWidth: "195px"}}
            onChange={handleNameChange}
            value={name}
          />
        <FormControl required sx={{mt: "15px", ml: "10px", minWidth: "195px"}} variant="outlined" size="small">
          <InputLabel id="add-model-label">Pioreactor model</InputLabel>
          <Select
            labelId="add-model-label"
            value={`${model[0]}::${model[1]}`}
            onChange={(evt) => {
              const [modelName, modelVersion] = String(evt.target.value).split('::');
              setModel([modelName, modelVersion]);
            }}
            label="Pioreactor model"
            MenuProps={{ disablePortal: true }}
            renderValue={(val) => {
              const [mn, mv] = String(val).split('::');
              const m = availableModels.find(x => x.model_name === mn && String(x.model_version) === String(mv));
              return m ? m.display_name : `${mn}, v${mv}`;
            }}
          >
            {standard.length > 0 && <ListSubheader disableSticky>Latest</ListSubheader>}
            {standard.map(({ model_name, model_version, display_name }) => (
              <MenuItem key={`${model_name}-${model_version}`} value={`${model_name}::${model_version}`}>
                {display_name}
              </MenuItem>
            ))}
            {contrib.length > 0 && <ListSubheader disableSticky>Custom</ListSubheader>}
            {contrib.map(({ model_name, model_version, display_name }) => (
              <MenuItem key={`${model_name}-${model_version}`} value={`${model_name}::${model_version}`}>
                {display_name}
              </MenuItem>
            ))}
            {legacy.length > 0 && <ListSubheader disableSticky>Legacy</ListSubheader>}
            {legacy.map(({ model_name, model_version, display_name }) => (
              <MenuItem key={`${model_name}-${model_version}`} value={`${model_name}::${model_version}`}>
                {display_name}
              </MenuItem>
            ))}

          </Select>
        </FormControl>

        </div>

        <Box sx={{minHeight: "60px", alignItems: "center", display: "flex"}}>
          {isError   ? <Alert severity="error">{errorMsg}</Alert> : <React.Fragment/>}
          {isRunning ? <p>{expectedPathMsg}</p> : <React.Fragment/>}
          {isSuccess ? <p><CheckIcon sx={{verticalAlign: "middle", margin: "0px 3px", color: readyGreen}}/>{successMsg}</p>      : <React.Fragment/>}
        </Box>

        <Box sx={{display: "flex", justifyContent: "flex-end"}}>
          <LoadingButton
            variant="contained"
            color="primary"
            sx={{marginTop: "10px", textTransform: 'none'}}
            onClick={onSubmit}
            type="submit"
            loading={isRunning}
            disabled={!name || !model}
            endIcon={ <PioreactorIcon /> }

          >
            Add Pioreactor
          </LoadingButton>
        </Box>

      </DialogContent>
    </Dialog>
    </React.Fragment>
  );}


function WorkerCard({worker, config, leaderVersion}) {

  const availableModels = useAvailableModels();
  const unit = worker.pioreactor_unit
  const isLeader = (config['cluster.topology']?.leader_hostname === unit)
  const [activeStatus, setActiveStatus] = React.useState(worker.is_active ? "active" : "inactive")
  const [model, setModel] = React.useState([worker.model_name, worker.model_version])

  const currentModelDetails =
    availableModels.find(
      ({model_name, model_version}) => model_name === model[0] && model_version === model[1]
    );
  const currentModelCapacity = currentModelDetails ? currentModelDetails.reactor_capacity_ml : "";
  const modelBadgeContent = model[0]?.endsWith("XR") ? "XR" : currentModelCapacity;


  const [experimentAssigned, setExperimentAssigned] = React.useState(null)
  const {client, subscribeToTopic, unsubscribeFromTopic} = useMQTT();
  const selfTestDefinition = useSelfTestJobDefinition();
  const [state, setState] = React.useState(null)
  const [versions, setVersions] = React.useState({})
  const [ipv4, setIpv4] = React.useState(null)
  const [WLANaddress, setWLANaddress] = React.useState(null)
  const [ETHAddress, setETHAddress] = React.useState(null)
  const [selfTestJob, setSelfTestJob] = React.useState(null)
  const { selectExperiment } = useExperiment();
  const navigate = useNavigate()
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const selfTestExperiment = "$experiment";


  const isActive = () => {
    return activeStatus === "active"
  }

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }
  const showSnackbar = (message) => {
    setSnackbarMessage(message);
    setSnackbarOpen(true);
  };

  const selfTestSettingTypes = React.useMemo(() => {
    if (!selfTestDefinition) {
      return {};
    }
    return selfTestDefinition.published_settings.reduce((acc, field) => {
      acc[field.key] = field.type;
      return acc;
    }, {});
  }, [selfTestDefinition]);

  React.useEffect(() => {
    if (!selfTestDefinition) {
      return;
    }
    const publishedSettings = {};
    for (const field of selfTestDefinition.published_settings) {
      publishedSettings[field.key] = {
        value: field.default || null,
        type: field.type,
      };
    }
    setSelfTestJob({ state: null, publishedSettings });
  }, [selfTestDefinition]);

  const onSelfTestData = React.useCallback((topic, message, packet) => {
    if (!message || !topic) return;

    const [job, setting] = topic.toString().split('/').slice(-2);
    if (job !== "self_test") {
      return;
    }
    if (setting === "$state") {
      setSelfTestJob((prev) => (prev ? { ...prev, state: message.toString() } : prev));
      return;
    }
    const payload = parsePayloadToType(message.toString(), selfTestSettingTypes[setting]);
    setSelfTestJob((prev) => {
      if (!prev) {
        return prev;
      }
      const previousSetting = prev.publishedSettings[setting] || { type: selfTestSettingTypes[setting] };
      return {
        ...prev,
        publishedSettings: {
          ...prev.publishedSettings,
          [setting]: {
            ...previousSetting,
            value: payload,
          },
        },
      };
    });
  }, [selfTestSettingTypes]);

  const onMonitorData = (topic, message, packet) => {
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

  const getInicatorLabel = (state, isActive) => {
    if ((state === "disconnected") && isActive) {
      return "Offline"
    }
    else if ((state === "disconnected") && !isActive){
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

  const handleModelChange = (event) => {
    const [modelName, modelVersion] = event.target.value.split(',');
    setModel([modelName, modelVersion]);
    const selectedModel = availableModels.find(
      ({model_name, model_version}) => model_name === modelName && String(model_version) === String(modelVersion)
    );
    const displayName = selectedModel ? selectedModel.display_name : `${modelName}, v${modelVersion}`;
    showSnackbar(`Updated ${unit} to ${displayName}`);
    fetch(`/api/workers/${unit}/model`, {
      method: "PUT",
      body: JSON.stringify({model_name: modelName, model_version: modelVersion}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    });
  }

  const indicatorDotColor = getIndicatorDotColor(state)
  const indicatorDotShadow = 2
  const indicatorLabel = getInicatorLabel(state, isActive())


  React.useEffect(() => {
    if (!unit || !client) {
      return undefined;
    }
    const topic = `pioreactor/${unit}/$experiment/monitor/+`;
    subscribeToTopic(topic, onMonitorData, "WorkerCard");

    const fetchExperiment = async () => {
      try {
        const response = await fetch(`/api/workers/${unit}/experiment`);
        if (!response.ok) {
          throw new Error(`No experiment found.`);
        }
        const json = await response.json();
        setExperimentAssigned(json['experiment']);
      } catch (error) {
        return
      }
    };

    fetchExperiment();

    return () => {
      unsubscribeFromTopic(topic, "WorkerCard");
    };
  }, [unit, client, subscribeToTopic, unsubscribeFromTopic]);

  React.useEffect(() => {
    if (!client || !selfTestDefinition) {
      return undefined;
    }
    const baseTopic = `pioreactor/${unit}/${selfTestExperiment}/self_test`;
    const topics = [
      `${baseTopic}/$state`,
      ...selfTestDefinition.published_settings.map((setting) => `${baseTopic}/${setting.key}`),
    ];
    subscribeToTopic(topics, onSelfTestData, "WorkerCard-self-test");
    return () => {
      unsubscribeFromTopic(topics, "WorkerCard-self-test");
    };
  }, [client, onSelfTestData, selfTestDefinition, subscribeToTopic, unsubscribeFromTopic, unit]);

  const handleStatusChange = (event) => {

    setActiveStatus(event.target.checked ? "active" : "inactive");
    fetch(`/api/workers/${unit}/is_active`, {
      method: "PUT",
      body: JSON.stringify({is_active: Number(event.target.checked) }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
  };

  const onExperimentClick = () => {
    selectExperiment(experimentAssigned)
    navigate("/overview")
  }


  const softwareVersion = () => {
    const { app: workerVersion } = versions;

    if (!workerVersion) return "-";

    if (leaderVersion && workerVersion !== leaderVersion) {
      return (
        <UnderlineSpan title={`Not aligned with leader's version, ${leaderVersion}`}>
          {workerVersion} <ErrorOutlineIcon fontSize="small" sx={{ verticalAlign: "middle", marginLeft: "-5px", marginBottom: "3px", color: lostRed }} />
        </UnderlineSpan>
      );
    }

    return workerVersion;
  };

  const standard = availableModels.filter(m => !(m.is_contrib) && !(m.is_legacy));
  const contrib = availableModels.filter(m => (m.is_contrib));
  const legacy = availableModels.filter(m => (m.is_legacy));
  const modelValue = `${model[0]},${model[1]}`;
  const selectValue = availableModels.some(
    ({model_name, model_version}) => model_name === model[0] && String(model_version) === String(model[1])
  ) ? modelValue : "";
  return (
    <>
    <Card sx={{ minWidth: 275 }}>
      <CardContent>

        <div style={{display: "flex", justifyContent: "space-between"}}>

          <div style={{display: "flex", justifyContent: "left"}}>
            <PioreactorIconWithModel badgeContent={modelBadgeContent}/>
            <Typography sx={{
                fontSize: 20,
                color: "rgba(0, 0, 0, 0.87)",
                fontWeight: 500,
                ...(isActive() ? {} : { color: inactiveGrey }),
              }}
              gutterBottom>

              {unit}

            </Typography>
            <Tooltip title={indicatorLabel} placement="right">
              <div>
                <div className="indicator-dot" style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
              </div>
            </Tooltip>
          </div>

          <div>
          <FormControl component="fieldset">
            <FormControlLabel
              checked={isActive()}
              control={<Switch color="primary" onChange={handleStatusChange}  size="small" />}
              label={activeStatus ==="active" ? "Active" : "Inactive"}
              labelPlacement="start"
            />
          </FormControl>
          </div>


        </div>

        <Box sx={{display: "flex", justifyContent: "left", ml: .5}}>
          {experimentAssigned ? (
            <>
            <Typography variant="subtitle2" color={isActive() ? "inherit" : inactiveGrey}> Assigned to <Chip icon=<PlayCircleOutlinedIcon/> disabled={!isActive()} size="small" label={experimentAssigned} component={Link} clickable onClick={onExperimentClick} data-experiment-name={experimentAssigned} /> </Typography>
            </>)
          : <Typography variant="subtitle2" color={isActive() ? "inherit" : inactiveGrey}> Unassigned </Typography>
        }
        </Box>

        <Divider sx={{margin: "5px 0px"}}/>

        <table style={{borderCollapse: "separate", borderSpacing: "5px", fontSize: "0.90rem"}}>
          <tbody style={{color: isActive() ? "inherit" : inactiveGrey}}>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                Model
            </td>
            <td >
              <Select
                labelId="modelSelect"
                variant="standard"
                value={selectValue}
                onChange={handleModelChange}
                label="Model"
                disableUnderline={true}
                sx={{
                  "& .MuiSelect-standard": {
                    color: isActive() ? "inherit" : inactiveGrey
                  }
                }}
              >

                {standard.length > 0 && <ListSubheader disableSticky>Latest</ListSubheader>}
                {standard.map(({ model_name, model_version, display_name }) => (
                  <MenuItem key={`${model_name}-${model_version}`} value={`${model_name},${model_version}`}>
                    {display_name}
                  </MenuItem>
                ))}
                {contrib.length > 0 && <ListSubheader disableSticky>Custom</ListSubheader>}
                {contrib.map(({ model_name, model_version, display_name }) => (
                  <MenuItem key={`${model_name}-${model_version}`} value={`${model_name},${model_version}`}>
                    {display_name}
                  </MenuItem>
                ))}
                {legacy.length > 0 && <ListSubheader disableSticky>Legacy</ListSubheader>}
                {legacy.map(({ model_name, model_version, display_name }) => (
                  <MenuItem key={`${model_name}-${model_version}`} value={`${model_name},${model_version}`}>
                    {display_name}
                  </MenuItem>
                ))}

              </Select>
            </td>
          </tr>
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
          <Blink unit={unit}/>
          <SelfTestDialog
            client={client}
            disabled={!isActive()}
            experiment={selfTestExperiment}
            unit={unit}
            label={null}
            selfTestState={selfTestJob ? selfTestJob.state : null}
            selfTestTests={selfTestJob}
          />
          <Unassign unit={unit} experimentAssigned={experimentAssigned} setExperimentAssigned={setExperimentAssigned} />
        </Box>
        <Box>
          <ManagePioreactorMenu unit={unit} isLeader={isLeader} showSnackbar={showSnackbar} />
        </Box>
      </CardActions>
    </Card>
    <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={snackbarOpen}
      onClose={handleSnackbarClose}
      message={snackbarMessage}
      autoHideDuration={2500}
      key={"snackbar" + unit + "model"}
    />
    </>
)}


function Blink({unit}){

  const [flashing, setFlashing] = useState(false)


  const onClick = () => {
    setFlashing(true)
    fetch(`/api/workers/${unit}/blink`, {method: "POST"})
  }

  return (
    <Button style={{textTransform: 'none'}} className={flashing ? 'blinkled' : ''}  onClick={onClick} color="primary">
      <FlareIcon color="primary" fontSize="small" sx={textIcon}/> Identify
    </Button>
)}


function Unassign({unit, experimentAssigned, setExperimentAssigned}) {

  const unassignWorker = () => {
    fetch(`/api/experiments/${experimentAssigned}/workers/${unit}`, {method: "DELETE"})
    .then((res) => {
      if (res.ok){
        setExperimentAssigned(null)
      }
    })
  };

  return (
      <Button disabled={!experimentAssigned} style={{textTransform: "none"}} size="small" onClick={unassignWorker}>
        <RemoveCircleOutlineRoundedIcon fontSize="small" sx={textIcon} />Unassign
      </Button>
)}



function InventoryDisplay({isLoading, workers, config}){
  const [leaderVersion, setLeaderVersion] = React.useState(null)

  React.useEffect(() => {
    async function getLeaderVersion() {
       await fetch("/unit_api/versions/app")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setLeaderVersion(data['version'])
      });
    }
    getLeaderVersion()
  }, [])

  return (
    <Grid container spacing={2}>
      {isLoading
        ? <div style={{textAlign: "center", margin: 'auto', marginTop: "50px"}}><CircularProgress /> </div>
        : (
          <>
            {workers.map(worker =>
              <Grid
                key={worker.pioreactor_unit}
                size={{ md: 6, xs: 12, sm: 12 }}>
                <WorkerCard worker={worker} config={config} leaderVersion={leaderVersion}/>
              </Grid>
            )}
            <Grid key="add-new" size={{ md: 6, xs: 12, sm: 12 }}>
              <Card
                variant="outlined"
                onClick={() => document.getElementById('add-new-pioreactor-button')?.click()}
                sx={{
                  minWidth: 275,
                  minHeight: 360,
                  border: '2px dashed rgb(200, 200, 200)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}>
                <CardContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <PioreactorIconWithModel badgeContent={"＋"} fontSize="small" sx={textIcon} color={'rgba(0, 0, 0, 0.6)'}/>
                  <Typography color="text.secondary" align="center">
                    Add new Pioreactor
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </>
        )}
    </Grid>
  );}



function Inventory({title}) {
  const [workers, setWorkers] = useState([]);
  const [config, setConfig] = useState({})
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    document.title = title;
  }, [title]);

  useEffect(() => {
    getConfig(setConfig)
    fetchWorkers();
  }, []);


  const fetchWorkers = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`/api/workers`);
      if (response.ok) {
        const data = await response.json();
        setWorkers(data);
      } else {
        console.error('Failed to fetch workers:', response.statusText);
      }
    } catch (error) {
      console.error('Error fetching workers:', error);
    } finally {
      setIsLoading(false)
    }
  };
  return (
    <MQTTProvider name="cluster" config={config}>
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <Header setWorkers={setWorkers}/>
          <InventoryDisplay isLoading={isLoading} workers={workers} config={config} />
          <Grid size={12}>
            <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/create-cluster" target="_blank" rel="noopener noreferrer">inventory and cluster management</a>.</p>
          </Grid>
        </Grid>
      </Grid>
    </MQTTProvider>
  );
}


function ManagePioreactorMenu({unit, isLeader, showSnackbar}){
  const [anchorEl, setAnchorEl] = React.useState(null);
  const open = Boolean(anchorEl);
  const confirm = useConfirm();
  const navigate = useNavigate();
  const [isExporting, setIsExporting] = React.useState(false);
  const [isImporting, setIsImporting] = React.useState(false);

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
      fetch(`/api/units/${unit}/system/shutdown`, {method: "POST"})
    }).catch(() => {});
  };

  const handleExport = async () => {
    let dialogResult;
    try {
      dialogResult = await confirm({
        description: 'Export an archive containing this Pioreactor\'s system data (ex: configuration and calibration files) so you can back up or migrate settings.',
        title: `Export system archive from ${unit}?`,
        confirmationText: "Export",
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
    setIsExporting(true);
    try {
      const response = await fetch(`/api/units/${unit}/zipped_dot_pioreactor`);
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${unit}_dot_pioreactor.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
      if (showSnackbar) {
        showSnackbar('Export failed. Please try again.');
      }
    } finally {
      setIsExporting(false);
    }
  };

  const handleImport = async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) {
      return;
    }

    const formData = new FormData();
    formData.append('archive', file);

    setIsImporting(true);
    try {
      const response = await fetch(`/api/units/${unit}/import_zipped_dot_pioreactor`, {
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
        showSnackbar(`${errorMessage}`);
        return;
      }
      showSnackbar(`Import succeeded. The Pioreactor ${unit} will reboot now.`);
    } catch (err) {
      console.error('Import failed:', err);
      showSnackbar('Import failed. Please try again.');
    } finally {
      setIsImporting(false);
      event.target.value = null;
    }
  };

  const handleImportClick = async () => {
    let dialogResult;
    try {
      dialogResult = await confirm({
        description: <><p>Import a previously exported system archive and overwrite this Pioreactor's system data (configuration, calibrations, plugins, etc). The Pioreactor will reboot after the import.</p><p>The name of the Pioreactor you exported from and the name of this Pioreactor must be identical.</p><Alert severity="warning">This will overwrite the existing system data on {unit}.</Alert></>,
        title: `Import a system archive into ${unit}?`,
        confirmationText: "Select system archive file",
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
    const fileInput = document.getElementById(`import-dot-pioreactor-${unit}`);
    if (fileInput) {
      fileInput.click();
    }
  };

  const handleRemove = () => {
    confirm({
      description: 'Removing this Pioreactor will unassign it from any experiments, halt all activity running, and remove it from your inventory. No experiment data is removed, and calibration data still exists on the worker.',
      title: `Remove ${unit} from inventory?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
      cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},
    }).then(() => {
      fetch(`/api/workers/${unit}`, {method: "DELETE"})
      .then((response) => {
        if (response.ok){
           navigate(0)
        }
      })
    }).catch(() => {});
  };

  return (
    <div>
      <Button
        aria-controls={open ? 'manage-pioreactor-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        onClick={handleClick}
        style={{textTransform: "none"}}
      >
        Manage Pioreactor <ArrowDropDownIcon/>
      </Button>
      <Menu
        id="manage-pioreactor-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        MenuListProps={{
          'aria-labelledby': 'manage-pioreactor-button',
        }}
      >
        <MenuItem onClick={handleReboot}>
          <ListItemText>Reboot</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleShutdown}>
          <ListItemText>Shutdown</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleExport}>
          <ListItemText>Export system archive</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleImportClick}>
          <ListItemText>Import system archive</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleRemove} disabled={isLeader} sx={{ color: 'secondary.main' }}>
          <ListItemText>Remove</ListItemText>
        </MenuItem>
      </Menu>
      <input
        id={`import-dot-pioreactor-${unit}`}
        type="file"
        accept="application/zip"
        style={{display: 'none'}}
        onChange={handleImport}
      />
      <Backdrop
        sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.modal + 1 }}
        open={isExporting || isImporting}
      >
        <CircularProgress color="inherit" />
      </Backdrop>
    </div>
  );
}

export default Inventory;
