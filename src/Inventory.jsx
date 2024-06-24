import React, {useState, useEffect} from "react";
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import CardContent from '@mui/material/CardContent';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import InputLabel from '@mui/material/InputLabel';
import Typography from '@mui/material/Typography';
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
import {getConfig} from "./utilities"
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormControl from '@mui/material/FormControl';
import Button from '@mui/material/Button';
import PioreactorIcon from "./components/PioreactorIcon"
import Switch from '@mui/material/Switch';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import FlareIcon from '@mui/icons-material/Flare';
import DeleteIcon from '@mui/icons-material/Delete';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import InputAdornment from '@mui/material/InputAdornment';
import LoadingButton from '@mui/lab/LoadingButton';
import CheckIcon from '@mui/icons-material/Check';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RemoveCircleOutlineRoundedIcon from '@mui/icons-material/RemoveCircleOutlineRounded';
import CircularProgress from '@mui/material/CircularProgress';
import { useConfirm } from 'material-ui-confirm';
import { useNavigate } from 'react-router-dom'



const disconnectedGrey = "#585858"
const lostRed = "#DE3618"
const inactiveGrey = "#99999b"
const readyGreen = "#3f8451"

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
          <AddNewPioreactor/>
        </Box>
      </Box>
       <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />
    </Box>
  )
}



function AddNewPioreactor(props){
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [model, setModel] = useState("pioreactor_20ml"); // setModel isn't used yet
  const [version, setVersion] = useState("");

  const [isError, setIsError] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")

  const [isSuccess, setIsSuccess] = useState(false)
  const [successMsg, setSuccessMsg] = useState("")

  const [isRunning, setIsRunning] = useState(false)
  const [expectedPathMsg, setExpectedPathMsg] = useState("")

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleNameChange = evt => {
    setName(evt.target.value)
  }
  const handleVersionChange = evt => {
    setVersion(evt.target.value)
  }


  const onSubmit = (event) =>{
    event.preventDefault()
    if (!name) {
      setIsError(true)
      setErrorMsg("Provide the hostname for the new Pioreactor worker")
      return
    }
    else if (!version) {
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
        body: JSON.stringify({name: name, model: model, version: version}),
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
          response.json().then(data => setErrorMsg(`Unable to complete connection. The following error occurred: ${data.msg}`))
        } else {
          setIsSuccess(true)
          setSuccessMsg(`Success! Rebooting ${name} now. Refresh to see ${name} in your cluster.`)
        }
    })
  }

  return (
    <React.Fragment>
    <Button onClick={handleClickOpen} style={{textTransform: 'none', float: "right", marginRight: "0px"}} color="primary">
      <AddIcon fontSize="15" sx={textIcon}/> Add new Pioreactor
    </Button>
    <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title">
      <DialogTitle>
        Add new Pioreactor worker to your cluster
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
        <p>Your existing leader will automatically connect the new Pioreactor to the cluster. When finished, the new Pioreactor will show up on this page after a refresh.</p>
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
            InputProps={{
              endAdornment: <InputAdornment position="end">.local</InputAdornment>,
            }
          }
          />
        <FormControl required sx={{mt: "15px", ml: "10px", minWidth: "195px"}} variant="outlined" size="small">
          <InputLabel >Pioreactor model</InputLabel>
          <Select
            value={version}
            onChange={handleVersionChange}
            label="Pioreactor model"
          >
            <MenuItem value={"1.1"}>20ml, version 1.1</MenuItem>
            <MenuItem value={"1.0"}>20ml, version 1.0</MenuItem>
          </Select>
        </FormControl>

        </div>

        <Box sx={{minHeight: "60px", alignItems: "center", display: "flex"}}>
          {isError   ? <p><CloseIcon sx={{verticalAlign: "middle", margin: "0px 3px", color: lostRed}}/>{errorMsg}</p>           : <React.Fragment/>}
          {isRunning ? <p>{expectedPathMsg}</p>                                                                    : <React.Fragment/>}
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
            endIcon={ <PioreactorIcon /> }

          >
            Add Pioreactor
          </LoadingButton>
        </Box>

      </DialogContent>
    </Dialog>
    </React.Fragment>
  );}



function WorkerCard(props) {

  const worker = props.worker
  const unit = worker.pioreactor_unit
  const config = props.config
  const isLeader = (config['cluster.topology']?.leader_hostname === unit)
  const [activeStatus, setActiveStatus] = React.useState(worker.is_active ? "active" : "inactive")
  const [experimentAssigned, setExperimentAssigned] = React.useState(null)
  const {client, subscribeToTopic} = useMQTT();
  const [state, setState] = React.useState(null)
  const [versions, setVersions] = React.useState({})
  const [ipv4, setIpv4] = React.useState(null)
  const [WLANaddress, setWLANaddress] = React.useState(null)
  const [ETHAddress, setETHAddress] = React.useState(null)

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

  const indicatorDotColor = getIndicatorDotColor(state)
  const indicatorDotShadow = 2
  const indicatorLabel = getInicatorLabel(state, activeStatus === "active")


  React.useEffect(() => {
    if (unit && client) {
      subscribeToTopic(`pioreactor/${unit}/$experiment/monitor/+`, onMonitorData, "WorkerCard");

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
    }
  }, [unit, client]);

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


  var pioreactorString

  if (state !== "ready"){
    pioreactorString = "-"
  } else {
    if (versions.pioreactor_model) {
      pioreactorString = `Pioreactor ${(versions.pioreactor_model || "-").substring(11)}, v${versions.pioreactor_version || "-"}`
    }
    else {
      // ready and not available.
      pioreactorString = "Missing! Fix in the configuration file."
    }
  }

  return (
    <Card sx={{ minWidth: 275 }}>
      <CardContent>

        <div style={{display: "flex", justifyContent: "space-between"}}>
          <Typography sx={{ fontSize: 14 }} color={activeStatus === "active" ? "text.secondary" : inactiveGrey} gutterBottom>
            {isLeader ? "Leader / Worker" : "Worker"}
          </Typography>
        </div>

        <div style={{display: "flex", justifyContent: "space-between"}}>

          <div style={{display: "flex", justifyContent: "left"}}>
            <Typography sx={{
                fontSize: 20,
                color: "rgba(0, 0, 0, 0.87)",
                fontWeight: 500,
                ...(activeStatus === "active" ? {} : { color: inactiveGrey }),
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

          <div>
          <FormControl component="fieldset">
            <FormControlLabel
              checked={activeStatus === "active"}
              control={<Switch color="primary" onChange={handleStatusChange}  size="small" />}
              label={activeStatus ==="active" ? "Active" : "Inactive"}
              labelPlacement="start"
            />
          </FormControl>
          </div>


        </div>

        <Typography variant="subtitle2" color={activeStatus === "active" ? "text.secondary" : inactiveGrey}  >
          {experimentAssigned ? <>Assigned to <i>{experimentAssigned}</i></> : "Unassigned"}
        </Typography>

        <Divider sx={{margin: "5px 0px"}}/>

        <table style={{borderCollapse: "separate", borderSpacing: "5px", fontSize: "0.90rem"}}>
          <tbody style={{color: activeStatus === "active" ? "inherit" : inactiveGrey}}>
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                Model
            </td>
            <td >
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{pioreactorString}</code>
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
          <tr>
            <td style={{textAlign: "left", minWidth: "120px", color: ""}}>
                Software version
            </td>
            <td >
              <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{versions.app || "-"}</code>
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
          </tbody>
        </table>
        <Divider sx={{margin: "5px 0px"}}/>
      </CardContent>
      <CardActions sx={{display: "flex", justifyContent: "space-between"}}>
        <Box>
          <Blink unit={unit} client={client}/>
        </Box>
        <Box>
          <Unassign unit={unit} experimentAssigned={experimentAssigned} setExperimentAssigned={setExperimentAssigned} />
          <Reboot unit={unit} />
          <Remove unit={unit} isLeader={isLeader}/>
        </Box>
      </CardActions>
    </Card>
)}


function Blink({unit, client}){

  const [flashing, setFlashing] = useState(false)


  const onClick = () => {
    setFlashing(true)
    const sendMessage = () => {
      const topic = `pioreactor/${unit}/$experiment/monitor/flicker_led_response_okay`
      try{
        client.publish(topic, "1", {qos: 0});
      }
      catch (e){
        console.log(e)
        setTimeout(() => {sendMessage()}, 1000)
      }
    }

    sendMessage()
    setTimeout(() => {setFlashing(false)}, 3600 ) // .9 * 4
  }

  return (
    <Button style={{textTransform: 'none'}} className={flashing ? 'blinkled' : ''}  onClick={onClick} color="primary">
      <FlareIcon color="primary" fontSize="15" sx={textIcon}/> Identify
    </Button>
)}


function Reboot({unit, isLeader}) {

  const confirm = useConfirm();

  const rebootWorker = () => {
    confirm({
      description: 'Rebooting this Pioreactor will halt all activity and make the Pioreactor inaccessible for a few minutes.',
      title: `Reboot ${unit}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
    }).then(() => {
      fetch(`/api/units/${unit}/reboot`, {method: "POST"})
    }).catch(() => {});
  };

  return (
      <Button style={{textTransform: "none"}} size="small" onClick={rebootWorker}>
        <RestartAltIcon fontSize="small" sx={textIcon} />Reboot
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


function Remove({unit, isLeader}) {
  const navigate = useNavigate()
  const confirm = useConfirm();

  const removeWorker = () => {
    confirm({
      description: 'Removing this Pioreactor will unassign it from any experiments, halt all activity running, and remove it from your inventory. No experiment data is removed, however.',
      title: `Remove ${unit} from inventory?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
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
    <Button style={{textTransform: "none"}} disabled={isLeader} size="small" onClick={removeWorker}>
       <DeleteIcon fontSize="small" sx={textIcon}/> Remove
    </Button>
)}

function InventoryDisplay({isLoading, workers, config}){
  return (
    <Grid container spacing={2}>
      {isLoading ? <div style={{textAlign: "center", margin: 'auto', marginTop: "50px"}}><CircularProgress /> </div>: (
        <>
          {workers.map(worker =>
          <Grid key={worker.pioreactor_unit} item md={6} xs={12} sm={12}>
            <WorkerCard worker={worker} config={config}/>
          </Grid>
          )}
        </>
      )}
    </Grid>
)}



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
        <Grid item md={12} xs={12}>
          <Header />
          <InventoryDisplay isLoading={isLoading} workers={workers} config={config} />
          <Grid item xs={12}>
            <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/create-cluster" target="_blank" rel="noopener noreferrer">inventory and cluster management</a>.</p>
          </Grid>
        </Grid>
      </Grid>
    </MQTTProvider>
  )
}

export default Inventory;

