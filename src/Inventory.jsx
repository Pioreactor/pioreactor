import clsx from 'clsx';

import React, {useState, useEffect} from "react";
import { makeStyles } from '@mui/styles';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import CardContent from '@mui/material/CardContent';
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
import { useConfirm } from 'material-ui-confirm';
import { useNavigate } from 'react-router-dom'



const disconnectedGrey = "grey"
const lostRed = "#DE3618"
const inactiveGrey = "#99999b"


const useStyles = makeStyles((theme) => ({
  textIcon: {
    verticalAlign: "middle",
    margin: "0px 3px"
  },
  pioreactorCard: {
    marginTop: "0px",
    marginBottom: "20px",
  },
  cardContent: {
    padding: "10px 20px 20px 20px"
  },
  code: {
    backgroundColor: "rgba(0, 0, 0, 0.07)",
    padding: "1px 4px"
  },
  unitTitle: {
    fontSize: 20,
    color: "rgba(0, 0, 0, 0.87)",
    fontWeight: 500,
  },
  suptitle: {
    fontSize: "13px",
    color: "rgba(0, 0, 0, 0.60)",
  },
  disabledText: {
    color: "rgba(0, 0, 0, 0.38)",
  },
  textbox:{
    width: "130px",
    marginTop: "10px"
  },
  textboxLabel:{
    width: "100px",
    marginTop: "10px",
    marginRight: "5px"
  },
  footnote: {
    marginBottom: 0,
    fontSize: 12,
  },
  textField: {
    marginTop: "15px",
    maxWidth: "180px",
  },
  textFieldWide: {
    marginTop: "15px",
    maxWidth: "220px",
  },
  textFieldCompact: {
    marginTop: "15px",
    width: "120px",
  },
  slider: {
    width: "70%",
    margin: "40px auto 0px auto",
  },
  divider: {
    marginTop: 15,
    marginBottom: 10,
  },
  jobButton: {
    paddingRight: "15px",
    paddingLeft: "15px"
  },
  unitSettingsSubtext:{
    fontSize: "11px",
    wordBreak: "break-word"
  },
  unitSettingsSubtextEmpty:{
    minHeight: "15px"
  },
  ledBlock:{
    width: "55px",
    display: "inline-block"
  },
  rowOfUnitSettingDisplay:{
    display: "flex",
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "flex-start",
    alignItems: "stretch",
    alignContent: "stretch",
  },
  testingListItemIcon: {
    minWidth: "30px"
  },
  testingListItem : {
    paddingTop: "0px",
    paddingBottom: "0px",
  },
  headerMenu: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: "5px",
    [theme.breakpoints.down('lg')]:{
      flexFlow: "nowrap",
      flexDirection: "column",
    }
  },
  cardHeaderSettings:{
    display: "flex",
    justifyContent: "space-between",
    [theme.breakpoints.down('md')]:{
      flexFlow: "nowrap",
      flexDirection: "column",
    }
  },
  cardHeaderButtons: {
    display: "flex",
    justifyContent: "flex-end",
    flexDirection: "row",
    flexWrap: "wrap",
    [theme.breakpoints.down('md')]: {
      justifyContent: "space-between",
    }
  },
  headerButtons: {display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"},
  dataTable: {
    borderCollapse: "separate",
    borderSpacing: "5px",
    fontSize: "0.90rem"
  },
  dataTableQuestion: {textAlign: "left", minWidth: "120px", color: ""},
  dataTableResponse: {}
}));



function Header(props) {
  const classes = useStyles()
  return (
    <div>
      <div className={classes.headerMenu}>
        <Typography variant="h5" component="h1">
          <Box fontWeight="fontWeightBold">
            Inventory
          </Box>
        </Typography>
        <div className={classes.headerButtons}>
          <AddNewPioreactor/>
        </div>
      </div>
       <Divider className={classes.divider} />
    </div>
  )
}



function AddNewPioreactor(props){
  const classes = useStyles();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

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


  const onSubmit = (event) =>{
    event.preventDefault()
    if (!name) {
      setIsError(true)
      setErrorMsg("Provide the hostname for the new Pioreactor worker")
      return
    }
    setIsError(false)
    setIsSuccess(false)
    setIsRunning(true)
    setExpectedPathMsg("Setting up new Pioreactor...")
    fetch('/api/setup_worker_pioreactor', {
        method: "POST",
        body: JSON.stringify({newPioreactorName: name}),
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
          response.json().then(data => setErrorMsg(`Unable to complete installation. The following error occurred: ${data.msg}`))
        } else {
          setIsSuccess(true)
          setSuccessMsg(`Success! Rebooting ${name} now. Refresh to see ${name} in your cluster.`)
        }
    })
  }

  return (
    <React.Fragment>
    <Button onClick={handleClickOpen} style={{textTransform: 'none', float: "right", marginRight: "0px"}} color="primary">
      <AddIcon fontSize="15" classes={{root: classes.textIcon}}/> Add new Pioreactor
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
        <p>Follow the instructions at <a rel="noopener noreferrer" target="_blank" href="https://docs.pioreactor.com/user-guide/software-set-up#adding-additional-workers-to-your-cluster">set up your new Pioreactor's Raspberry Pi</a>.</p>

        <p>After

        <ol>
         <li> worker image installation is complete and,</li>
         <li> the new Pioreactor worker is powered on, </li>
        </ol>

        provide the hostname you used when installing the Pioreactor image onto the Raspberry Pi.
        Your existing Pioreactor will automatically connect the new Pioreactor to the cluster. When finished, the new Pioreactor will show up on this page (after a refresh).</p>
        <div>
          <TextField
            size="small"
            id="new-pioreactor-name"
            label="Hostname"
            variant="outlined"
            className={classes.textFieldWide}
            onChange={handleNameChange}
            value={name}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <PioreactorIcon style={{fontSize: "1.1em"}}/>
                </InputAdornment>
              ),
              endAdornment: <InputAdornment position="end">.local</InputAdornment>,
            }
          }
          />
        </div>

        <div style={{minHeight: "60px", alignItems: "center", display: "flex"}}>
          {isError   ? <p><CloseIcon className={clsx(classes.textIcon, classes.lostRed)}/>{errorMsg}</p>           : <React.Fragment/>}
          {isRunning ? <p>{expectedPathMsg}</p>                                                                    : <React.Fragment/>}
          {isSuccess ? <p><CheckIcon className={clsx(classes.textIcon, classes.readyGreen)}/>{successMsg}</p>      : <React.Fragment/>}
        </div>

        <LoadingButton
          variant="contained"
          color="primary"
          style={{marginTop: "10px"}}
          onClick={onSubmit}
          type="submit"
          loading={isRunning}
          endIcon={<AddIcon />}
        >
          Add Pioreactor
        </LoadingButton>

      </DialogContent>
    </Dialog>
    </React.Fragment>
  );}



function WorkerCard(props) {
  const classes = useStyles()

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
        setVersions(JSON.parse(message.toString()));
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
      return "#1AFF1A"
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
      subscribeToTopic(`pioreactor/${unit}/$experiment/monitor/+`, onMonitorData);

      fetch(`/api/workers/${unit}/experiment`)
         .then((response) => { return response.json() })
         .then((json) => setExperimentAssigned(json['experiment']))
    }
  }, [unit, client])

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

  return (
    <Card sx={{ minWidth: 275 }}>
      <CardContent>

        <div style={{display: "flex", justifyContent: "space-between"}}>
          <Typography sx={{ fontSize: 14 }} style={{paddingTop: "10px"}} color={activeStatus === "active" ? "text.secondary" : inactiveGrey} gutterBottom>
            {isLeader ? "Leader / Worker" : "Worker"}
          </Typography>
        </div>

        <div style={{display: "flex", justifyContent: "space-between"}}>

          <div style={{display: "flex", justifyContent: "left"}}>
            <Typography color={activeStatus === "active" ? "inherit" : inactiveGrey} variant="h5" component="div">
              <PioreactorIcon  style={{verticalAlign: "middle", marginRight: "3px"}} sx={{ display: {xs: 'none', sm: 'none', md: 'inline' } }}/>
              {unit}
            </Typography>
            <Tooltip title={indicatorLabel} placement="left">
              <div>
                <div aria-label={indicatorLabel} className="indicator-dot" style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
              </div>
            </Tooltip>
          </div>

          <div>
          <FormControl component="fieldset">
            <FormControlLabel
              checked={activeStatus === "active"}
              control={<Switch color="primary" onChange={handleStatusChange} />}
              label={activeStatus ==="active" ? "Active" : "Inactive"}
              labelPlacement="start"
            />
          </FormControl>
          </div>


        </div>

        <Typography variant="subtitle2" color={activeStatus === "active" ? "text.secondary" : inactiveGrey}  >
          {experimentAssigned ? <>Assigned to {experimentAssigned}</> : "Unassigned"}
        </Typography>

        <Divider style={{margin: "5px 0px"}}/>

        <table className={classes.dataTable}>
          <tbody style={{color: activeStatus === "active" ? "inherit" : inactiveGrey}}>
          <tr>
            <td className={classes.dataTableQuestion}>
                IPv4
            </td>
            <td>
              <code className={classes.code}>{ipv4 || "-"}</code>
            </td>
          </tr>
          <tr>
            <td className={classes.dataTableQuestion}>
                WLAN MAC
            </td>
            <td>
              <code className={classes.code}>{WLANaddress || "-"}</code>
            </td>
          </tr>
          <tr>
            <td className={classes.dataTableQuestion}>
                Ethernet MAC
            </td>
            <td>
              <code className={classes.code}>{ETHAddress || "-"}</code>
            </td>
          </tr>
          <tr>
            <td className={classes.dataTableQuestion}>
                Software version
            </td>
            <td className={classes.dataTableResponse}>
              <code className={classes.code}>{versions.app || "-"}</code>
            </td>
          </tr>
          </tbody>
        </table>
        <Divider style={{margin: "5px 0px"}}/>
      </CardContent>
      <CardActions style={{display: "flex", justifyContent: "space-between"}}>
        <div>
        <Blink unit={unit} client={client}/>
          </div>
        <div>
          <Unassign unit={unit} experimentAssigned={experimentAssigned} setExperimentAssigned={setExperimentAssigned} />
          <Reboot unit={unit} />
          <Remove unit={unit} isLeader={isLeader}/>
          </div>
      </CardActions>
    </Card>
)}


function Blink({unit, client}){
  const classes = useStyles();

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
    <Button style={{textTransform: 'none'}} className={clsx({blinkled: flashing})}  onClick={onClick} color="primary">
      <FlareIcon color="primary" fontSize="15" classes={{root: classes.textIcon}}/> Identify
    </Button>
)}


function Reboot({unit, isLeader}) {
  const classes = useStyles()

  const confirm = useConfirm();

  const rebootWorker = () => {
    confirm({
      description: 'Rebooting this Pioreactor will halt all activity and make the Pioreactor inaccessible for a few minutes.',
      title: `Reboot ${unit}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
    }).then(() => {
      fetch(`/api/reboot/${unit}`, {method: "POST"})
    }).catch(() => {});
  };

  return (
      <Button style={{textTransform: "none"}} size="small" onClick={rebootWorker}>
        <RestartAltIcon fontSize="small" classes={{root: classes.textIcon}} />Reboot
      </Button>
)}


function Unassign({unit, experimentAssigned, setExperimentAssigned}) {
  const classes = useStyles()

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
        <RemoveCircleOutlineRoundedIcon fontSize="small" classes={{root: classes.textIcon}} />Unassign
      </Button>
)}


function Remove({unit, isLeader}) {
  const classes = useStyles()
  const navigate = useNavigate()
  const confirm = useConfirm();

  const removeWorker = () => {
    confirm({
      description: 'Removing this Pioreactor will unassign it from any experiments, halt all activity running, and remove it from your inventory.',
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
       <DeleteIcon fontSize="small" classes={{root: classes.textIcon}}/> Remove
    </Button>
)}

function InventoryDisplay(props){
  return (
    <Grid container spacing={2}>
      {props.workers.map(worker =>
        <Grid key={worker.pioreactor_unit} item md={6} xs={12} sm={12}>
          <WorkerCard worker={worker} config={props.config}/>
        </Grid>
      )}
    </Grid>
)}



function Inventory({title}) {
  const [workers, setWorkers] = useState([]);
  const [config, setConfig] = useState({})

  useEffect(() => {
    document.title = title;
  }, [title]);

  useEffect(() => {
    getConfig(setConfig)
    fetchWorkers();
  }, []);


  const fetchWorkers = async () => {
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
    }
  };

  return (
    <MQTTProvider name="cluster" config={config}>
      <Grid container spacing={2} >
        <Grid item md={12} xs={12}>
          <Header />
          <InventoryDisplay workers={workers} config={config} />
        </Grid>
      </Grid>
    </MQTTProvider>
  )
}

export default Inventory;

