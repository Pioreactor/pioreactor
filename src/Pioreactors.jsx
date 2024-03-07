import clsx from 'clsx';
import moment from 'moment';

import React, {useState, useEffect} from "react";

import Grid from '@mui/material/Grid';
import { useMediaQuery } from "@mui/material";

import { makeStyles } from '@mui/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {Typography} from '@mui/material';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import Snackbar from '@mui/material/Snackbar';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import InputAdornment from '@mui/material/InputAdornment';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Button from "@mui/material/Button";
import LoadingButton from '@mui/lab/LoadingButton';
import AddIcon from '@mui/icons-material/Add';
import ClearIcon from '@mui/icons-material/Clear';
import CloseIcon from '@mui/icons-material/Close';
import CheckIcon from '@mui/icons-material/Check';
import FlareIcon from '@mui/icons-material/Flare';
import SettingsIcon from '@mui/icons-material/Settings';
import TuneIcon from '@mui/icons-material/Tune';
import CheckBoxOutlinedIcon from '@mui/icons-material/CheckBoxOutlined';
import IndeterminateCheckBoxIcon from '@mui/icons-material/IndeterminateCheckBox';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import List from '@mui/material/List';
import IconButton from '@mui/material/IconButton';
import ListItem from '@mui/material/ListItem';
import ListSubheader from '@mui/material/ListSubheader';
import IndeterminateCheckBoxOutlinedIcon from '@mui/icons-material/IndeterminateCheckBoxOutlined';
import Switch from '@mui/material/Switch';
import { useConfirm } from 'material-ui-confirm';
import {getConfig, getRelabelMap, runPioreactorJob} from "./utilities"
import Alert from '@mui/material/Alert';


import ChangeAutomationsDialog from "./components/ChangeAutomationsDialog"
import ActionDosingForm from "./components/ActionDosingForm"
import ActionManualDosingForm from "./components/ActionManualDosingForm"
import ActionCirculatingForm from "./components/ActionCirculatingForm"
import ActionLEDForm from "./components/ActionLEDForm"
import PioreactorIcon from "./components/PioreactorIcon"
import UnderlineSpan from "./components/UnderlineSpan";
import { MQTTProvider, useMQTT } from './MQTTContext';


const readyGreen = "#4caf50"
const disconnectedGrey = "grey"
const lostRed = "#DE3618"

const useStyles = makeStyles((theme) => ({
  lostRed: {
    color: lostRed
  },
  readyGreen: {
    color: readyGreen
  },
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
  patientButton: {width: "70px", marginTop: "5px", height: "31px", marginRight: '3px'},
}));


function TabPanel(props) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`simple-tabpanel-${index}`}
      key={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && (
          <div>{children}</div>
      )}
    </div>
  );
}

function UnitSettingDisplaySubtext(props){
  const classes = useStyles();

  if (props.subtext){
    return <div className={classes.unitSettingsSubtext}><code>{props.subtext}</code></div>
  }
  else{
    return <div className={classes.unitSettingsSubtextEmpty}></div>
  };
}


function UnitSettingDisplay(props) {
  const classes = useStyles();
  const stateDisplay = {
    "init":          {display: "Starting", color: readyGreen},
    "ready":         {display: "On", color: readyGreen},
    "sleeping":      {display: "Paused", color: disconnectedGrey},
    "disconnected":  {display: "Off", color: disconnectedGrey},
    "lost":          {display: "Lost", color: lostRed},
    "NA":            {display: "Not available", color: disconnectedGrey},
  }
  const value = props.value === null ?  ""  : props.value

  function prettyPrint(x){
    if (x >= 10){
      return x.toFixed(0)
    }
    else if (x===0){
      return "0"
    }
    else if (x < 1){
      return `<1`
    } else {
      return (x).toFixed(1).replace(/[.,]0$/, "");
    }
  }

  function formatForDisplay(value){
    if (typeof value === "string"){
      return value
    } else if (typeof value === "boolean"){
      return value ? "On" : "Off"
    }
    else {
      return +value.toFixed(props.precision)
    }
  }

  if (props.isStateSetting) {
    if (!props.isUnitActive) {
      return <div className={clsx({[classes.disabledText]: !props.isUnitActive})}> {stateDisplay[value].display} </div>;
    } else {
      var displaySettings = stateDisplay[value]
      return (
        <React.Fragment>
          <div style={{ color: displaySettings.color, fontWeight: 500}}>
            {displaySettings.display}
          </div>
          <UnitSettingDisplaySubtext subtext={props.subtext}/>
        </React.Fragment>
    )}
  } else if (props.isLEDIntensity) {
    if (!props.isUnitActive || value === "—" || value === "") {
      return <div style={{ color: disconnectedGrey, fontSize: "13px"}}> {props.default} </div>;
    } else {
      const ledIntensities = JSON.parse(value)
        // the | {} is here to protect against the UI loading from a broken config.
      const LEDMap = props.config['leds']
      const renamedA = (LEDMap['A']) ? (LEDMap['A'].replace("_", " ")) : null
      const renamedB = (LEDMap['B']) ? (LEDMap['B'].replace("_", " ")) : null
      const renamedC = (LEDMap['C']) ? (LEDMap['C'].replace("_", " ")) : null
      const renamedD = (LEDMap['D']) ? (LEDMap['D'].replace("_", " ")) : null

      return(
        <React.Fragment>
          <div style={{fontSize: "13px"}}>
            <div>
              <span className={classes.ledBlock}>
                <UnderlineSpan title={renamedA ? renamedA : null}>A</UnderlineSpan>: {prettyPrint(ledIntensities["A"])}%
              </span>
              <span className={classes.ledBlock}>
                <UnderlineSpan title={renamedB ? renamedB : null}>B</UnderlineSpan>: {prettyPrint(ledIntensities["B"])}%
              </span>
            </div>
            <div>
              <span className={classes.ledBlock}>
                <UnderlineSpan title={renamedC ? renamedC : null}>C</UnderlineSpan>: {prettyPrint(ledIntensities["C"])}%
              </span>
              <span className={classes.ledBlock}>
                <UnderlineSpan title={renamedD ? renamedD : null}>D</UnderlineSpan>: {prettyPrint(ledIntensities["D"])}%
              </span>
            </div>
          </div>
          <UnitSettingDisplaySubtext subtext={props.subtext}/>
        </React.Fragment>
      )
    }
  } else if (props.isPWMDc) {
    if (!props.isUnitActive || value === "—" || value === "") {
      return <div style={{ color: disconnectedGrey, fontSize: "13px"}}> {props.default} </div>;
    } else {
      const pwmDcs = JSON.parse(value)
      const PWM_TO_PIN = {1: "17",  2: "13", 3: "16",  4: "12"}

      const PWMMap = props.config['PWM']
      const renamed1 = (PWMMap[1]) ? (PWMMap[1].replace("_", " ")) : null
      const renamed2 = (PWMMap[2]) ? (PWMMap[2].replace("_", " ")) : null
      const renamed3 = (PWMMap[3]) ? (PWMMap[3].replace("_", " ")) : null
      const renamed4 = (PWMMap[4]) ? (PWMMap[4].replace("_", " ")) : null


      return(
        <React.Fragment>
          <div style={{fontSize: "13px"}}>
            <div>
              <span className={classes.ledBlock}>
                <UnderlineSpan title={renamed1 ? renamed1 : null}>1</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[1]] || 0)}%
              </span>
              <span className={classes.ledBlock}>
               <UnderlineSpan title={renamed2 ? renamed2 : null}>2</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[2]] || 0)}%
              </span>
            </div>
            <div>
              <span className={classes.ledBlock}>
                <UnderlineSpan title={renamed3 ? renamed3 : null}>3</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[3]] || 0)}%
              </span>
              <span className={classes.ledBlock}>
                <UnderlineSpan title={renamed4 ? renamed4 : null}>4</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[4]] || 0)}%
              </span>
            </div>
          </div>
          <UnitSettingDisplaySubtext subtext={props.subtext}/>
        </React.Fragment>
      )
    }
  } else {
    if (!props.isUnitActive || value === "—" || value === "") {
      return (
        <React.Fragment>
          <div style={{ color: disconnectedGrey, fontSize: "13px"}}> {props.default} </div>
          <UnitSettingDisplaySubtext subtext={props.subtext}/>
        </React.Fragment>
      );
    } else {
      return (
        <React.Fragment>
          <div style={{ fontSize: "13px"}}>
            {formatForDisplay(value) + " " +
              (props.measurementUnit ? props.measurementUnit : "")}
          </div>
          <UnitSettingDisplaySubtext subtext={props.subtext}/>
        </React.Fragment>
      );
    }
  }
}



function ButtonStopProcess() {
  const classes = useStyles();
  const confirm = useConfirm();

  const handleClick = () => {
    confirm({
      description: 'This will immediately stop all activities (stirring, dosing, etc.) in all Pioreactor units. Do you wish to continue?',
      title: "Stop all activities?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},

      }).then(() =>
        fetch("/api/stop_all", {method: "POST"})
    )
  };

  return (
    <Button style={{textTransform: 'none', float: "right" }} color="secondary" onClick={handleClick}>
      <ClearIcon fontSize="15" classes={{root: classes.textIcon}}/> Stop all activity
    </Button>
  );
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
        Add a Pioreactor worker to your current cluster
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



function PioreactorHeader(props) {
  const classes = useStyles()
  return (
    <div>
      <div className={classes.headerMenu}>
        <Typography variant="h5" component="h1">
          <Box fontWeight="fontWeightBold">
            Pioreactors
          </Box>
        </Typography>
        <div className={classes.headerButtons}>
          <ButtonStopProcess/>
          <AddNewPioreactor config={props.config}/>
          <SettingsActionsDialogAll config={props.config} experiment={props.experiment}/>
        </div>
      </div>
      <Divider/>
    </div>
  )
}



function PatientButton(props) {
  const classes = useStyles()
  const [buttonText, setButtonText] = useState(props.buttonText)

  useEffect(
    () => {
      setButtonText(props.buttonText)
    }
  , [props.buttonText])

  const onClick = () => {
      setButtonText(<CircularProgress color="inherit" size={21}/>)
      props.onClick()
      setTimeout(() => setButtonText(props.buttonText), 30000)
  }

  return (
    <Button
      disableElevation
      className={classes.patientButton}
      color={props.color}
      variant={props.variant}
      disabled={props.disabled}
      size="small"
      onClick={onClick}
    >
      {buttonText}
    </Button>
  )
}


function CalibrateDialog(props) {
  const classes = useStyles();
  const [open, setOpen] = useState(false);
  const [tabValue, setTabValue] = useState(0);


  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false)
    setTimeout(()=> setTabValue(0), 200) // we put a timeout here so the switching tabs doesn't occur during the close transition.
  };


  function createUserButtonsBasedOnState(jobState, job, always_disable=false){

    switch (jobState){
      case "ready":
      case "init":
      case "sleeping":
       return (<div>
               <PatientButton
                color="primary"
                variant="contained"
                buttonText="Running"
                disabled={true || always_disable}
               />
              </div>)
      default:
       return (<div>
               <PatientButton
                color="primary"
                variant="contained"
                onClick={() => runPioreactorJob(props.unit, job)}
                buttonText="Start"
                disabled={always_disable}
               />
              </div>)
    }
   }

  const isGrowRateJobRunning = props.growthRateJobState === "ready"
  const blankODButton = createUserButtonsBasedOnState(props.odBlankJobState, "od_blank", isGrowRateJobRunning)
  const stirringCalibrationButton = createUserButtonsBasedOnState(props.stirringCalibrationState, "stirring_calibration")

  return (
    <React.Fragment>
      <Button style={{textTransform: 'none', float: "right" }} color="primary" disabled={props.disabled} onClick={handleClickOpen}>
        <TuneIcon color={props.disabled ? "disabled" : "primary"} fontSize="15" classes={{root: classes.textIcon}}/> Calibrate
      </Button>
      <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title">
        <DialogTitle>
          <Typography className={classes.suptitle}>
            <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/> {(props.label) ? `${props.label} / ${props.unit}` : `${props.unit}`}
          </Typography>
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            indicatorColor="primary"
            textColor="primary"
            >
            <Tab label="Blanks"/>
            <Tab label="Stirring"/>
            <Tab label="Dosing" />
            <Tab label="OD600"  />
          </Tabs>
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
          <TabPanel value={tabValue} index={0}>
            <Typography  gutterBottom>
             Record optical densities of blank (optional)
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
              For more accurate growth rate and biomass inferences, the Pioreactor can subtract out the
              media's <i>un-inoculated</i> optical density <i>per experiment</i>. Read more about <a href="https://docs.pioreactor.com/user-guide/od-normal-growth-rate#blanking">using blanks</a>.
            </Typography>
            <Typography variant="body2" component="p" style={{margin: "20px 0px"}}>
              Recorded optical densities of blank vial: <code>{props.odBlankReading ? Object.entries(JSON.parse(props.odBlankReading)).map( ([k, v]) => `${k}:${v.toFixed(5)}` ).join(", ") : "—"}</code>
            </Typography>

            <div style={{display: "flex"}}>
              {blankODButton}
              <div>
                <Button size="small" className={classes.patientButton} color="secondary" disabled={(props.odBlankReading === null) || (isGrowRateJobRunning)} onClick={() => runPioreactorJob(props.unit, "od_blank", ['delete']) }> Clear </Button>
              </div>
            </div>
            <Divider className={classes.divider} />

          </TabPanel>
          <TabPanel value={tabValue} index={1}>
            <Typography  gutterBottom>
             Stirring calibration (optional)
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
              You can improve the responsiveness of stirring RPM changes by running this calibration. This calibration is
              optional, and stirring RPM changes can still occur without running this calibration. Only needs to be performed once - results are saved to disk.
            </Typography>

            <Typography variant="body2" component="p" gutterBottom>
            Add a vial, with a stirbar and ~15ml of liquid, to the Pioreactor, then hit Start below. This calibration will take less than five minutes.
            </Typography>

            {stirringCalibrationButton}

            <Divider className={classes.divider} />

          </TabPanel>
          <TabPanel value={tabValue} index={2}>
            <Typography  gutterBottom>
             Dosing calibration for pumps
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
            To use a peristatlic pump with your Pioreactor, you'll need to calibrate it to accuractly dose specific volumes.
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
            See instructions <a target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com/user-guide/hardware-calibrations#pump-calibration">here</a>.
            </Typography>
            <Divider className={classes.divider} />

          </TabPanel>

          <TabPanel value={tabValue} index={3}>
            <Typography  gutterBottom>
             OD600 Calibration (optional)
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
            By performing the following calibration, you can relate Pioreactor's internal OD readings (measured in volts) to an offline OD600 value. The UI and datasets will be measured in your OD600 values instead of voltages.
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
            See instructions <a target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com/user-guide/calibrate-od600">here</a>.
            </Typography>
            <Divider className={classes.divider} />
          </TabPanel>
        </DialogContent>
      </Dialog>
  </React.Fragment>
  );
}



function SelfTestDialog(props) {
  const classes = useStyles();
  const [open, setOpen] = useState(false);

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };


  function displayIcon(key, state){
    if (props.selfTestTests == null){
      return <IndeterminateCheckBoxIcon />
    }
    else if (props.selfTestTests.publishedSettings[key].value === true){
      return <CheckIcon className={classes.readyGreen}/>
    }
    else if (props.selfTestTests.publishedSettings[key].value === false){
      return <CloseIcon className={classes.lostRed}/>
    }
    else if (state === "ready") {
      return <CircularProgress size={20} />
    }
    else {
      return <IndeterminateCheckBoxIcon />
    }
  }


  function createUserButtonsBasedOnState(jobState, job){

    switch (jobState){
      case "init":
      case "ready":
      case "sleeping":
       return (<div key={"ready_" + job}>
               <PatientButton
                color="primary"
                variant="contained"
                disabled={true}
                buttonText="Running"
               />
              </div>)
      default:
       return (<div key={"disconnected_" + job}>
               <PatientButton
                color="primary"
                variant="contained"
                onClick={() => runPioreactorJob(props.unit, job)}
                buttonText="Start"
               />
              </div>)
    }
  }

  function colorOfIcon(){
    return props.disabled ? "disabled" : "primary"
  }

  function Icon(){
    if (props.selfTestTests == null){
      return <IndeterminateCheckBoxOutlinedIcon color={colorOfIcon()} fontSize="15" classes={{root: classes.textIcon}}/>
    }
    else {
      return props.selfTestTests.publishedSettings["all_tests_passed"].value ? <CheckBoxOutlinedIcon color={colorOfIcon()} fontSize="15" classes={{root: classes.textIcon}}/> : <IndeterminateCheckBoxOutlinedIcon color={colorOfIcon()} fontSize="15" classes={{root: classes.textIcon}}/>
    }
  }

  const selfTestButton = createUserButtonsBasedOnState(props.selfTestState, "self_test")

  return (
    <React.Fragment>
      <Button style={{textTransform: 'none', float: "right" }} color="primary" disabled={props.disabled} onClick={handleClickOpen}>
        {Icon()} Self test
      </Button>
      <Dialog open={open} onClose={handleClose}>
        <DialogTitle>
          <Typography className={classes.suptitle} gutterBottom>
            <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/> {props.label ? `${props.label} / ${props.unit}` : `${props.unit}`}
          </Typography>
           Self test
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
          <Typography variant="body2" component="p" gutterBottom>
            Perform a check of the heating & temperature sensor, LEDs & photodiodes, and stirring.
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Add a closed vial with water and stirbar into the Pioreactor.
          </Typography>

            {selfTestButton}
            <Divider className={classes.divider} />

            <List component="nav"
              subheader={
                <ListSubheader style={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                  LEDs & photodiodes
                </ListSubheader>
              }
            >
              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_pioreactor_HAT_present", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Pioreactor HAT is detected" />
              </ListItem>
              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_all_positive_correlations_between_pds_and_leds", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Photodiodes are responsive to IR LED" secondary={
                    props.selfTestTests ?
                      JSON.parse(props.selfTestTests.publishedSettings["correlations_between_pds_and_leds"].value).map(led_pd => `${led_pd[0]} ⇝ ${led_pd[1]}`).join(",  ") :
                      ""
                    }/>
              </ListItem>

              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_ambient_light_interference", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="No ambient IR light detected" />
              </ListItem>

              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_REF_is_lower_than_0_dot_256_volts", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Reference photodiode is correct magnitude" />
              </ListItem>

              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_REF_is_in_correct_position", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Reference photodiode is in correct position" />
              </ListItem>

              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_PD_is_near_0_volts_for_blank", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Photodiode measures near zero signal for clear water" />
              </ListItem>

            </List>

            <List component="nav"
              subheader={
                <ListSubheader style={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                  Heating & temperature
                </ListSubheader>
              }
            >
              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_detect_heating_pcb", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Heating PCB is detected" />
              </ListItem>

              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_positive_correlation_between_temperature_and_heating", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Heating is responsive" />
              </ListItem>
            </List>


            <List component="nav"
              subheader={
                <ListSubheader style={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                  Stirring
                </ListSubheader>
              }
            >
              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_positive_correlation_between_rpm_and_stirring", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Stirring RPM is responsive" />
              </ListItem>

              <ListItem className={classes.testingListItem}>
                <ListItemIcon className={classes.testingListItemIcon}>
                  {displayIcon("test_aux_power_is_not_too_high", props.selfTestState)}
                </ListItemIcon>
                <ListItemText primary="AUX power supply is appropriate value" />
              </ListItem>


            </List>

          <Divider className={classes.divider} />
          <Typography variant="body2" component="p" gutterBottom>
            Learn more about self tests and <a rel="noopener noreferrer" target="_blank" href="https://docs.pioreactor.com/user-guide/running-self-test#explanation-of-each-test">what to do if a test fails.</a>
          </Typography>
        </DialogContent>
      </Dialog>
  </React.Fragment>
  );
}






function SettingsActionsDialog(props) {
  const classes = useStyles();
  const [open, setOpen] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [tabValue, setTabValue] = useState(0);
  const [rebooting, setRebooting] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);
  const [openChangeDosingDialog, setOpenChangeDosingDialog] = useState(false);
  const [openChangeLEDDialog, setOpenChangeLEDDialog] = useState(false);
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = useState(false);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };


  function setPioreactorJobState(job, state) {
    return function() {
      setPioreactorJobAttr(`${job}/$state`, state)
    };
  }


  function rebootRaspberryPi(){
    return function() {
      setRebooting(true)
      fetch("/api/reboot/" + props.unit, {method: "POST"})
    }
  }

  function shutDownRaspberryPi(){
    return function() {
      setShuttingDown(true)
      fetch("/api/shutdown/" + props.unit, {method: "POST"})
    }
  }

  function stopPioreactorJob(job){
    return function() {
      setPioreactorJobAttr(`${job}/$state`, "disconnected")
      //fetch("/api/stop/" + job + "/" + props.unit, {method: "PATCH"}).then(res => {})
    }
  }

  function setPioreactorJobAttr(job_attr, value) {
    const topic = `pioreactor/${props.unit}/${props.experiment}/${job_attr}/set`
    props.client.publish(topic, String(value), {qos: 1});
  }


  function updateRenameUnit(_, value) {
      const relabeledTo = value
      setSnackbarMessage(`Updating to ${relabeledTo}`)
      setSnackbarOpen(true)
      fetch('/api/unit_labels/current',{
          method: "PUT",
          body: JSON.stringify({label: relabeledTo, unit: props.unit}),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
        }).then(res => {
          if (res.ok) {
            props.setLabel(relabeledTo)
          }
        })
    }


  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setTimeout(()=> setTabValue(0), 200) // we put a timeout here so the switching tabs doesn't occur during the close transition.
  };

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  function createUserButtonsBasedOnState(jobState, job){
    switch (jobState){
      case "lost":
        return (<div key={"patient_buttons_lost" + job}>
                  <PatientButton
                    color="primary"
                    variant="contained"
                    onClick={() => runPioreactorJob(props.unit, job)}
                    buttonText="Start"
                  />
        </div>)
      case "disconnected":
       return (<div key={"patient_buttons_disconnected" + job}>
                 <PatientButton
                  color="primary"
                  variant="contained"
                  onClick={() => runPioreactorJob(props.unit, job)}
                  buttonText="Start"
                 />
                <PatientButton
                  color="secondary"
                  disabled={true}
                  buttonText="Stop"
                />
              </div>)
      case "init":
        return (
          <div key={"patient_buttons_init" + job}>
            <PatientButton
              color="primary"
              variant="contained"
              onClick={()=>(false)}
              buttonText=<CircularProgress color="inherit" size={22}/>
              disabled={true}
            />
            <PatientButton
              color="secondary"
              onClick={stopPioreactorJob(job)}
              buttonText="Stop"
            />
          </div>
        )
      case "ready":
        return (
          <div key={"patient_buttons_ready" + job}>
            <PatientButton
              color="secondary"
              variant="contained"
              onClick={setPioreactorJobState(job, "sleeping")}
              buttonText="Pause"
            />
            <PatientButton
              color="secondary"
              onClick={stopPioreactorJob(job)}
              buttonText="Stop"
            />
          </div>
          )
      case "sleeping":
        return (
          <div key={"patient_buttons_sleeping" + job}>
            <PatientButton
              color="primary"
              variant="contained"
              onClick={setPioreactorJobState(job, "ready")}
              buttonText="Resume"
            />
            <PatientButton
              color="secondary"
              onClick={stopPioreactorJob(job)}
              buttonText="Stop"
            />
          </div>
          )
      default:
        return(<div key={"patient_buttons_empty" + job}></div>)
    }
   }
  const LEDMap = props.config['leds']
  const buttons = Object.fromEntries(Object.entries(props.jobs).map( ([job_key, job], i) => [job_key, createUserButtonsBasedOnState(job.state, job_key)]))
  const versionInfo = JSON.parse(props.jobs.monitor.publishedSettings.versions.value || "{}")
  const voltageInfo = JSON.parse(props.jobs.monitor.publishedSettings.voltage_on_pwm_rail.value || "{}")
  const ipInfo = props.jobs.monitor.publishedSettings.ipv4.value
  const macInfo = props.jobs.monitor.publishedSettings.wlan_mac_address.value

  const stateDisplay = {
    "init":          {display: "Starting", color: readyGreen},
    "ready":         {display: "On", color: readyGreen},
    "sleeping":      {display: "Paused", color: disconnectedGrey},
    "disconnected":  {display: "Off", color: disconnectedGrey},
    "lost":          {display: "Lost", color: lostRed},
    "NA":            {display: "Not available", color: disconnectedGrey},
  }

  const isLargeScreen = useMediaQuery(theme => theme.breakpoints.down('xl'));
  var dosingControlJob = props.jobs.dosing_control
  var dosingControlJobRunning = ["ready", "sleeping", "init"].includes(dosingControlJob?.state)

  var ledControlJob = props.jobs.led_control
  var ledControlJobRunning = ["ready", "sleeping", "init"].includes(ledControlJob?.state)

  var temperatureControlJob = props.jobs.temperature_control
  var temperatureControlJobRunning = ["ready", "sleeping", "init"].includes(temperatureControlJob?.state)

  return (
    <div>
    <Button style={{textTransform: 'none', float: "right" }} disabled={props.disabled} onClick={handleClickOpen} color="primary">
      <SettingsIcon color={props.disabled ? "disabled" : "primary"} fontSize="15" classes={{root: classes.textIcon}}/> Manage
    </Button>
    <Dialog maxWidth={isLargeScreen ? "sm" : "md"} fullWidth={true} open={open} onClose={handleClose} PaperProps={{
      sx: {
        height: "calc(100% - 64px)"
      }
    }}>
      <DialogTitle>
        <Typography className={classes.suptitle}>
          <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/>
          <span> {props.label ? `${props.label} / ${props.unit}` : `${props.unit}`} </span>
        </Typography>
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
      <Tabs
        value={tabValue}
        onChange={handleTabChange}
        indicatorColor="primary"
        textColor="primary"
        variant="scrollable"
        scrollButtons
        allowScrollButtonsMobile
        >
        <Tab label="Activities"/>
        <Tab label="Settings"/>
        <Tab label="Dosing"/>
        <Tab label="LEDs"/>
        <Tab label="System"/>
      </Tabs>
      </DialogTitle>
      <DialogContent>
        <TabPanel value={tabValue} index={0}>
          {/* Unit Specific Activites */}
          {Object.entries(props.jobs)
            .filter(([job_key, job]) => job.metadata.display)
            .filter(([job_key, job]) => !['dosing_control', 'led_control', 'temperature_control'].includes(job_key))
            .map(([job_key, job]) =>
            <div key={job_key}>
              <div style={{justifyContent: "space-between", display: "flex"}}>
                <Typography display="block">
                  {job.metadata.display_name}
                </Typography>
                <Typography display="block" gutterBottom>
                  <span style={{color: stateDisplay[job.state].color}}>{stateDisplay[job.state].display}</span>
                </Typography>
              </div>
              <Typography variant="caption" display="block" gutterBottom color="textSecondary">
                {job.metadata.source !== "app" ? `Installed by ${job.metadata.source || "unknown"}` : ""}
              </Typography>
              <Typography variant="body2" component="p" gutterBottom>
                <div dangerouslySetInnerHTML={{__html: job.metadata.description}}/>
              </Typography>

              {buttons[job_key]}

              <Divider className={classes.divider} />
            </div>
          )}


          {/* Unit Specific Automations */}
          {temperatureControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                Temperature automation
              </Typography>
              <Typography display="block" gutterBottom>
                <span style={{color:stateDisplay[temperatureControlJob.state].color}}>{stateDisplay[temperatureControlJob.state].display}</span>
              </Typography>
            </div>
            <Typography variant="caption" display="block" gutterBottom color="textSecondary">
            </Typography>
            <div key={temperatureControlJob.metadata.key}>
              {(temperatureControlJob.state === "ready") || (temperatureControlJob.state === "sleeping") || (temperatureControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                Currently running temperature automation <code className={classes.code}>{temperatureControlJob.publishedSettings.automation_name.value}</code>.
                Learn more about <a target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com/user-guide/temperature-automations">temperature automations</a>.
                </Typography>
                {buttons[temperatureControlJob.metadata.key]}
               </React.Fragment>
              :<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                  <div dangerouslySetInnerHTML={{__html: temperatureControlJob.metadata.description}}/>
                </Typography>

                <Button
                  className={classes.patientButton}
                  size="small"
                  color="primary"
                  variant="contained"
                  onClick={() => setOpenChangeTemperatureDialog(true)}
                >
                  Start
                </Button>
                <Button
                  className={classes.patientButton}
                  size="small"
                  color="primary"
                  disabled={true}
                >
                  Stop
                </Button>

               </React.Fragment>
              }
            </div>

            <Button
              onClick={() => setOpenChangeTemperatureDialog(true)}
              style={{marginTop: "10px"}}
              size="small"
              color="primary"
              disabled={!temperatureControlJobRunning}
            >
              Change temperature automation
            </Button>

            <ChangeAutomationsDialog
              open={openChangeTemperatureDialog}
              onFinished={() => setOpenChangeTemperatureDialog(false)}
              unit={props.unit}
              label={props.label}
              experiment={props.experiment}
              isJobRunning={temperatureControlJobRunning}
              automationType="temperature"
              no_skip_first_run={true}
            />
          </React.Fragment>
          }

          <Divider className={classes.divider} />

          {dosingControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                Dosing automation
              </Typography>
              <Typography display="block" gutterBottom>
                <span style={{color:stateDisplay[dosingControlJob.state].color}}>{stateDisplay[dosingControlJob.state].display}</span>
              </Typography>
            </div>
            <Typography variant="caption" display="block" gutterBottom color="textSecondary">
            </Typography>
            <div key={dosingControlJob.metadata.key}>
              {(dosingControlJob.state === "ready") || (dosingControlJob.state === "sleeping") || (temperatureControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                Currently running dosing automation <code>{dosingControlJob.publishedSettings.automation_name.value}</code>.
                Learn more about <a target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com/user-guide/dosing-automations">dosing automations</a>.
                </Typography>
                {buttons[dosingControlJob.metadata.key]}
               </React.Fragment>
              :<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                  <div dangerouslySetInnerHTML={{__html: dosingControlJob.metadata.description}}/>
                </Typography>

                <Button
                  className={classes.patientButton}
                  size="small"
                  color="primary"
                  variant="contained"
                  onClick={() => setOpenChangeDosingDialog(true)}
                >
                  Start
                </Button>
                <Button
                  className={classes.patientButton}
                  size="small"
                  color="primary"
                  disabled={true}
                >
                  Stop
                </Button>
               </React.Fragment>
              }
            </div>

            <Button
              onClick={() => setOpenChangeDosingDialog(true)}
              style={{marginTop: "10px"}}
              size="small"
              color="primary"
              disabled={!dosingControlJobRunning}
            >
              Change dosing automation
            </Button>

            <ChangeAutomationsDialog
              automationType="dosing"
              open={openChangeDosingDialog}
              onFinished={() => setOpenChangeDosingDialog(false)}
              unit={props.unit}
              label={props.label}
              experiment={props.experiment}
              isJobRunning={dosingControlJobRunning}
              no_skip_first_run={false}
            />
          </React.Fragment>
          }

          <Divider className={classes.divider} />


          {ledControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                LED automation
              </Typography>
              <Typography display="block" gutterBottom>
                <span style={{color:stateDisplay[ledControlJob.state].color}}>{stateDisplay[ledControlJob.state].display}</span>
              </Typography>
            </div>
            <Typography variant="caption" display="block" gutterBottom color="textSecondary">
            </Typography>
            <div key={ledControlJob.metadata.key}>
              {(ledControlJob.state === "ready") || (ledControlJob.state === "sleeping") || (temperatureControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                Currently running LED automation <code>{ledControlJob.publishedSettings.automation_name.value}</code>.
                Learn more about <a target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com/user-guide/led-automations">LED automations</a>.
                </Typography>
                {buttons[ledControlJob.metadata.key]}
               </React.Fragment>
              :<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                  <div dangerouslySetInnerHTML={{__html: ledControlJob.metadata.description}}/>
                </Typography>

                <Button
                  className={classes.patientButton}
                  size="small"
                  color="primary"
                  variant="contained"
                  onClick={() => setOpenChangeLEDDialog(true)}
                >
                  Start
                </Button>
                <Button
                  className={classes.patientButton}
                  size="small"
                  color="primary"
                  disabled={true}
                >
                  Stop
                </Button>
               </React.Fragment>
              }
            </div>

            <Button
              onClick={() => setOpenChangeLEDDialog(true)}
              style={{marginTop: "10px"}}
              size="small"
              color="primary"
              disabled={!ledControlJobRunning}
            >
              Change LED automation
            </Button>

            <ChangeAutomationsDialog
              automationType="led"
              open={openChangeLEDDialog}
              onFinished={() => setOpenChangeLEDDialog(false)}
              unit={props.unit}
              label={props.label}
              experiment={props.experiment}
              isJobRunning={ledControlJobRunning}
              no_skip_first_run={false}
            />
          </React.Fragment>
          }

          <Divider className={classes.divider} />


        </TabPanel>


        <TabPanel value={tabValue} index={1}>
          <Typography  gutterBottom>
            Assign label to Pioreactor
          </Typography>
          <Typography variant="body2" component="p">
            Assign a temporary label to this Pioreactor for this experiment. The new label will display in graph legends, and throughout the interface.
          </Typography>
          <SettingTextField
            value={props.label}
            onUpdate={updateRenameUnit}
            setSnackbarMessage={setSnackbarMessage}
            setSnackbarOpen={setSnackbarOpen}
            id={'relabeller' + props.unit}
            disabled={false}
          />
          <Divider className={classes.divider} />

          {Object.values(props.jobs)
            .filter(job => job.metadata.display)
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings], index) => (
              Object.entries(settings)
                .filter(([setting_key, setting],_) => setting.display)
                .map(([setting_key, setting],_) =>
                        <React.Fragment key={setting_key}>
                          <Typography gutterBottom>
                            {setting.label}
                          </Typography>

                          <Typography variant="body2" component="p">
                            {setting.description}
                          </Typography>

                          {(setting.type === "boolean") && (
                            <SettingSwitchField
                              onUpdate={setPioreactorJobAttr}
                              setSnackbarMessage={setSnackbarMessage}
                              setSnackbarOpen={setSnackbarOpen}
                              value={setting.value}
                              units={setting.unit}
                              id={`${job_key.replace("_control", "_automation")}/${setting_key}`}
                              disabled={state === "disconnected"}
                            />
                          )}

                          {(setting.type !== "boolean") && (
                              <SettingTextField
                                onUpdate={setPioreactorJobAttr}
                                setSnackbarMessage={setSnackbarMessage}
                                setSnackbarOpen={setSnackbarOpen}
                                value={setting.value}
                                units={setting.unit}
                                id={`${job_key.replace("_control", "_automation")}/${setting_key}`}
                                disabled={state === "disconnected"}
                              />
                          )}

                          <Divider className={classes.divider} />
                        </React.Fragment>
          )))}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Typography  gutterBottom>
            Cycle Media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle media in and out of your Pioreactor for a set duration (seconds) by running the media and waste pump simultaneously.
          </Typography>

          <ActionCirculatingForm action="circulate_media" unit={props.unit} job={props.jobs.circulate_media} />

          <Divider classes={{root: classes.divider}} />

          <Typography  gutterBottom>
            Cycle alternative media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle alternative media in and out of your Pioreactor for a set duration (seconds) by running the alt-media and waste pump simultaneously.
          </Typography>

          <ActionCirculatingForm action="circulate_alt_media" unit={props.unit} job={props.jobs.circulate_alt_media} />

          <Divider classes={{root: classes.divider}} />

          <Alert severity="warning" style={{marginBottom: '10px', marginTop: '10px'}}>It's easy to overflow your vial. Make sure you don't add too much media.</Alert>

          <Typography  gutterBottom>
            Add media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the media pump for a set duration (s), moving a set volume (mL), or continuously add until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add media:
          </Typography>
          <ActionDosingForm action="add_media" unit={props.unit} job={props.jobs.add_media} />
          <Divider classes={{root: classes.divider}} />
          <Typography  gutterBottom>
            Remove waste
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the waste pump for a set duration (s), moving a set volume (mL), or continuously remove until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to remove waste:
          </Typography>
          <ActionDosingForm action="remove_waste" unit={props.unit} job={props.jobs.remove_waste} />
          <Divider className={classes.divider} />
          <Typography gutterBottom>
            Add alternative media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the alt-media pump for a set duration (s), moving a set volume (mL), or continuously add until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add alt-media:
          </Typography>
          <ActionDosingForm action="add_alt_media" unit={props.unit} job={props.jobs.add_alt_media} />
          <Divider className={classes.divider} />
          <Typography gutterBottom>
            Manual adjustments
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Record adjustments before manually adding or removing from the vial. This is recorded in the database and will ensure accurate metrics.
          </Typography>
          <ActionManualDosingForm unit={props.unit}/>


        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['A']) ? (LEDMap['A'].replace("_", " ").replace("led", "LED")) : "Channel A" }
          </Typography>
          <Typography className={clsx(classes.suptitle)} color="textSecondary">
            {(LEDMap['A']) ? "Channel A" : ""}
          </Typography>
          <ActionLEDForm channel="A" unit={props.unit} />
          <Divider className={classes.divider} />

          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['B']) ? (LEDMap['B'].replace("_", " ").replace("led", "LED")) : "Channel B" }
          </Typography>
          <Typography className={clsx(classes.suptitle)} color="textSecondary">
            {(LEDMap['B']) ? "Channel B" : ""}
          </Typography>
          <ActionLEDForm channel="B" unit={props.unit} />
          <Divider className={classes.divider} />

          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['C']) ? (LEDMap['C'].replace("_", " ").replace("led", "LED")) : "Channel C" }
          </Typography>
          <Typography className={clsx(classes.suptitle)} color="textSecondary">
            {(LEDMap['C']) ? "Channel C" : ""}
          </Typography>

          <ActionLEDForm channel="C" unit={props.unit} />
          <Divider className={classes.divider} />

          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['D']) ? (LEDMap['D'].replace("_", " ").replace("led", "LED")) : "Channel D" }
          </Typography>
          <Typography className={clsx(classes.suptitle)} color="textSecondary">
            {(LEDMap['D']) ? "Channel D" : ""}
          </Typography>
          <ActionLEDForm channel="D" unit={props.unit} />
          <Divider className={classes.divider} />
        </TabPanel>
        <TabPanel value={tabValue} index={4}>

          <Typography  gutterBottom>
            Addresses and hostname
          </Typography>

            <Typography variant="body2" component="p" gutterBottom>
              Learn about how to <a target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com/user-guide/accessing-raspberry-pi">access the Pioreactor's Raspberry Pi</a>.
            </Typography>

            <Typography variant="body2" component="p">
              IPv4: <code className={classes.code}>{ipInfo}</code>
            </Typography>

            <Typography variant="body2" component="p">
              Hostname: <code className={classes.code}>{props.unit}.local</code>
            </Typography>

            <Typography variant="body2" component="p">
              WLAN MAC: <code className={classes.code}>{macInfo}</code>
            </Typography>


          <Divider className={classes.divider} />

          <Typography  gutterBottom>
            Version information
          </Typography>

            <Typography variant="body2" component="p">
              Software version: {versionInfo.app}
            </Typography>
            <Typography variant="body2" component="p">
              Raspberry Pi: {versionInfo.rpi_machine}
            </Typography>
            <Typography variant="body2" component="p">
              HAT version: {versionInfo.hat}
            </Typography>
            <Typography variant="body2" component="p">
              HAT serial number: <code className={classes.code}>{versionInfo.hat_serial}</code>
            </Typography>


          <Divider className={classes.divider} />

          <Typography  gutterBottom>
            Voltage on PWM rail
          </Typography>

            <Typography variant="body2" component="p">
              Voltage: {voltageInfo.voltage}V
            </Typography>
            <Typography variant="body2" component="p">
              Last updated at: {moment.utc(voltageInfo.timestamp || "", 'YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]').local().format('MMMM Do, h:mm a') }
            </Typography>

          <Divider className={classes.divider} />

          <Typography  gutterBottom>
            Reboot
          </Typography>
          <Typography variant="body2" component="p">
            Reboot the Raspberry Pi operating system. This will stop all jobs, and the Pioreactor will be inaccessible for a few minutes. It will blink its blue LED when back up, or press the onboard button to light up the blue LED.
          </Typography>

          <LoadingButton
            loadingIndicator="Rebooting"
            loading={rebooting}
            variant="contained"
            color="primary"
            size="small"
            style={{marginTop: "15px"}}
            disabled={props.jobs.monitor.state !== "ready"}
            onClick={rebootRaspberryPi()}
          >
            Reboot RPi
          </LoadingButton>

          <Divider className={classes.divider} />

          <Typography  gutterBottom>
            Shut down
          </Typography>
          <Typography variant="body2" component="p">
            After 20 seconds, shut down the Pioreactor. This will stop all jobs, and the Pioreactor will be inaccessible until it is restarted by unplugging and replugging the power supply.
          </Typography>
          <LoadingButton
            loadingIndicator="😵"
            loading={shuttingDown}
            variant="contained"
            color="primary"
            size="small"
            style={{marginTop: "15px"}}
            disabled={props.jobs.monitor.state !== "ready"}
            onClick={shutDownRaspberryPi()}
          >
            Shut down
          </LoadingButton>

          <Divider className={classes.divider} />



        </TabPanel>

      </DialogContent>
    </Dialog>
    <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={snackbarOpen}
      onClose={handleSnackbarClose}
      message={snackbarMessage}
      autoHideDuration={7000}
      resumeHideDuration={2000}
      key={"snackbar" + props.unit + "settings"}
    />
    </div>
  );
}


function SettingsActionsDialogAll({config, experiment}) {

  const classes = useStyles();
  const unit = "$broadcast"
  const [open, setOpen] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [tabValue, setTabValue] = useState(0);
  const [jobs, setJobs] = useState({});
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = useState(false);
  const [openChangeDosingDialog, setOpenChangeDosingDialog] = useState(false);
  const [openChangeLEDDialog, setOpenChangeLEDDialog] = useState(false);
  const {client } = useMQTT();

  useEffect(() => {
    function fetchContribBackgroundJobs() {
      fetch("/api/contrib/jobs")
        .then((response) => {
            if (response.ok) {
              return response.json();
            } else {
              throw new Error('Something went wrong');
            }
          })
        .then((listOfJobs) => {
          var jobs_ = {}
          for (const job of listOfJobs){
            var metaData_ = {publishedSettings: {}, metadata: {display_name: job.display_name, display: job.display, description: job.description, key: job.job_name, source:job.source}}
            for(var i = 0; i < job["published_settings"].length; ++i){
              var field = job["published_settings"][i]
              metaData_.publishedSettings[field.key] = {value: field.default || null, label: field.label, type: field.type, unit: field.unit || null, display: field.display, description: field.description}
            }
            jobs_[job.job_name] = metaData_
          }
          setJobs((prev) => ({...prev, ...jobs_}))
        })
        .catch((error) => {})
    }
    fetchContribBackgroundJobs();
  }, [])


  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  function setPioreactorJobState(job, state) {
    return function sendMessage() {
      const topic = [
        "pioreactor",
        unit,
        experiment,
        job.metadata.key,
        "$state",
        "set",
      ].join("/");
      try{
        client.publish(topic, String(state), {qos: 1});
      }
      catch (e){
        console.log(e)
        setTimeout(() => {sendMessage()}, 750)
      }
      finally {
        const verbs = {
          "sleeping":  "Pausing",
          "disconnected":  "Stopping",
          "ready":  "Resuming",
        }
        setSnackbarMessage(`${verbs[state]} ${job.metadata.display_name.toLowerCase()} on all active Pioreactors`)
        setSnackbarOpen(true)
      }
    };
  }


  function setPioreactorJobAttr(job_attr, value) {
    const topic = [
      "pioreactor",
      unit,
      experiment,
      job_attr,
      "set",
    ].join("/");
    client.publish(topic, String(value), {qos: 1});
    setSnackbarOpen(true)
  }

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setTimeout(()=> setTabValue(0), 200) // we put a timeout here so the switching tabs doesn't occur during the close transition.

  };

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }


  function createUserButtonsBasedOnState(job){

    const handleRunPioreactorJobResponse = (response) => {
      if (response.ok) {
        setSnackbarMessage(`Starting ${job.metadata.display_name.toLowerCase()} on all active Pioreactors`)
        setSnackbarOpen(true)
        return;
      }
    };

    if (job.metadata.key === "temperature_control"){
      var startAction = () => setOpenChangeTemperatureDialog(true)
    }
    else if (job.metadata.key === "dosing_control"){
      startAction = () => setOpenChangeDosingDialog(true)
    }
    else if (job.metadata.key === "led_control"){
      startAction = () => setOpenChangeLEDDialog(true)
    }
    else {
      startAction = () => runPioreactorJob(unit, job.metadata.key, [], {}, handleRunPioreactorJobResponse)
    }


    return (<div key={job.metadata.key}>
        <Button
          className={classes.jobButton}
          disableElevation
          color="primary"
          onClick={startAction}
        >
          Start
        </Button>
        <Button
          className={classes.jobButton}
          disableElevation
          color="primary"
          onClick={setPioreactorJobState(job, "sleeping")}
        >
          Pause
        </Button>
        <Button
          className={classes.jobButton}
          disableElevation
          color="primary"
          onClick={setPioreactorJobState(job, "ready")}
        >
          Resume
        </Button>
        <Button
          className={classes.jobButton}
          disableElevation
          color="secondary"
          onClick={setPioreactorJobState(job, "disconnected")}
        >
          Stop
        </Button>
      </div>
  )}


  const buttons = Object.fromEntries(Object.entries(jobs).map( ([job_key, job], i) => [job_key, createUserButtonsBasedOnState(job)]))
  const isLargeScreen = useMediaQuery(theme => theme.breakpoints.down('xl'));
  var dosingControlJob = jobs.dosing_control
  var ledControlJob = jobs.led_control
  var temperatureControlJob = jobs.temperature_control

  return (
    <React.Fragment>
    <Button style={{textTransform: 'none', float: "right" }} onClick={handleClickOpen} color="primary">
      <SettingsIcon fontSize="15" classes={{root: classes.textIcon}}/> Manage all Pioreactors
    </Button>
    <Dialog  maxWidth={isLargeScreen ? "sm" : "md"} fullWidth={true}  open={open} onClose={handleClose} aria-labelledby="form-dialog-title"  PaperProps={{
      sx: {
        height: "calc(100% - 64px)"
      }
    }}>
      <DialogTitle style={{backgroundImage: "linear-gradient(to bottom left, rgba(83, 49, 202, 0.4), rgba(0,0,0,0))"}}>
        <Typography className={classes.suptitle}>
          <b>All active Pioreactors</b>
        </Typography>
        <IconButton
          aria-label="close"
          onClick={handleClose}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[600],
          }}
          size="large">
          <CloseIcon />
        </IconButton>
      <Tabs
        value={tabValue}
        onChange={handleTabChange}
        indicatorColor="primary"
        textColor="primary"
        variant="scrollable"
        scrollButtons
        allowScrollButtonsMobile
      >
        <Tab label="Activities"/>
        <Tab label="Settings"/>
        <Tab label="Dosing"/>
        <Tab label="LEDs"/>
      </Tabs>
      </DialogTitle>
      <DialogContent>

        <TabPanel value={tabValue} index={0}>
          {Object.entries(jobs)
            .filter(([job_key, job]) => job.metadata.display)
            .filter(([job_key, job]) => !['dosing_control', 'led_control', 'temperature_control'].includes(job_key))
            .map(([job_key, job]) =>
            <div key={job_key}>
              <Typography gutterBottom>
                {job.metadata.display_name}
              </Typography>
              <Typography variant="body2" component="p" gutterBottom>
                <div dangerouslySetInnerHTML={{__html: job.metadata.description}}/>
              </Typography>

              {buttons[job_key]}

              <Divider classes={{root: classes.divider}} />
            </div>
          )}


          {temperatureControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                Temperature automation
              </Typography>
            </div>
            <div>
              <Typography variant="body2" component="p" gutterBottom>
                <div dangerouslySetInnerHTML={{__html: temperatureControlJob.metadata.description}}/>
              </Typography>

              {buttons['temperature_control']}
            </div>

            <ChangeAutomationsDialog
              open={openChangeTemperatureDialog}
              onFinished={() => setOpenChangeTemperatureDialog(false)}
              unit={unit}
              config={config}
              experiment={experiment}
              isJobRunning={false}
              automationType="temperature"
              no_skip_first_run={true}
            />
          </React.Fragment>
          }

          <Divider className={classes.divider} />



          {dosingControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                Dosing automation
              </Typography>
            </div>
            <div>
              <Typography variant="body2" component="p" gutterBottom>
                <div dangerouslySetInnerHTML={{__html: dosingControlJob.metadata.description}}/>
              </Typography>

              {buttons['dosing_control']}
            </div>

            <ChangeAutomationsDialog
              automationType="dosing"
              open={openChangeDosingDialog}
              onFinished={() => setOpenChangeDosingDialog(false)}
              unit={unit}
              config={config}
              experiment={experiment}
              isJobRunning={false}
              no_skip_first_run={false}
            />
          </React.Fragment>
          }

          <Divider className={classes.divider} />


          {ledControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                LED automation
              </Typography>
            </div>
            <div>
              <Typography variant="body2" component="p" gutterBottom>
                <div dangerouslySetInnerHTML={{__html: ledControlJob.metadata.description}}/>
              </Typography>

              {buttons['led_control']}
            </div>

            <ChangeAutomationsDialog
              automationType="led"
              open={openChangeLEDDialog}
              onFinished={() => setOpenChangeLEDDialog(false)}
              unit={unit}
              config={config}
              experiment={experiment}
              isJobRunning={false}
              no_skip_first_run={false}
            />
          </React.Fragment>
          }

          <Divider className={classes.divider} />

        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {Object.values(jobs)
            .filter(job => job.metadata.display)
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings], index) => (
              Object.entries(settings)
                .filter(([setting_key, setting],_) => setting.display)
                .map(([setting_key, setting],_) =>
              <React.Fragment key={job_key + setting_key}>
                <Typography  gutterBottom>
                  {setting.label}
                </Typography>
                <Typography variant="body2" component="p">
                  {setting.description}
                </Typography>

                  {(setting.type === "boolean") && (
                    <SettingSwitchField
                      onUpdate={setPioreactorJobAttr}
                      setSnackbarMessage={setSnackbarMessage}
                      setSnackbarOpen={setSnackbarOpen}
                      value={setting.value}
                      units={setting.unit}
                      id={`${job_key.replace("_control", "_automation")}/${setting_key}`}
                      disabled={false}
                    />
                  )}

                  {(setting.type !== "boolean") && (
                  <SettingTextField
                    onUpdate={setPioreactorJobAttr}
                    setSnackbarMessage={setSnackbarMessage}
                    setSnackbarOpen={setSnackbarOpen}
                    value={setting.value}
                    units={setting.unit}
                    id={`${job_key.replace("_control", "_automation")}/${setting_key}`}
                    disabled={false}
                  />
                  )}
                <Divider classes={{root: classes.divider}} />
              </React.Fragment>

          )))}

        </TabPanel>
        <TabPanel value={tabValue} index={2}>
          <Typography  gutterBottom>
            Cycle Media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle media in and out of your Pioreactor for a set duration (seconds).
          </Typography>

          <ActionCirculatingForm action="circulate_media" unit={unit} />

          <Divider classes={{root: classes.divider}} />

          <Typography  gutterBottom>
            Cycle alternative media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle alternative media in and out of your Pioreactor for a set duration (seconds).
          </Typography>

          <ActionCirculatingForm action="circulate_alt_media" unit={unit} />

          <Divider classes={{root: classes.divider}} />

          <Alert severity="warning" style={{marginBottom: '10px', marginTop: '10px'}}>It's easy to overflow your vial. Make sure you don't add too much media.</Alert>

          <Typography  gutterBottom>
            Add media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the media pumps for a set duration (seconds), moving a set volume (mL), or continuously add until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add media:
          </Typography>
          <ActionDosingForm action="add_media" unit={unit} />
          <Divider className={classes.divider} />
          <Typography  gutterBottom>
            Remove waste
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the waste pumps for a set duration (seconds), moving a set volume (mL), or continuously add until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to remove media:
          </Typography>
          <ActionDosingForm action="remove_waste" unit={unit} />
          <Divider className={classes.divider} />
          <Typography gutterBottom>
            Add alternative media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the alternative media pumps for a set duration (seconds), moving a set
            volume (mL), or continuously add until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add alt-media:
          </Typography>
          <ActionDosingForm action="add_alt_media" unit={unit} />
          <Divider className={classes.divider} />
          <Typography gutterBottom>
            Manual adjustments
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Record adjustments before manually adding or removing from the vial. This is recorded in the database and will ensure accurate metrics.
          </Typography>
          <ActionManualDosingForm unit={unit}/>

        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Typography style={{textTransform: "capitalize"}}>
            Channel A
          </Typography>
          <ActionLEDForm channel="A" unit={unit} />
          <Divider className={classes.divider} />

          <Typography style={{textTransform: "capitalize"}}>
            Channel B
          </Typography>
          <ActionLEDForm channel="B" unit={unit} />
          <Divider className={classes.divider} />

          <Typography style={{textTransform: "capitalize"}}>
            Channel C
          </Typography>
          <ActionLEDForm channel="C" unit={unit} />

          <Divider className={classes.divider} />
          <Typography style={{textTransform: "capitalize"}}>
            Channel D
          </Typography>
          <ActionLEDForm channel="D" unit={unit} />

          <Divider className={classes.divider} />
        </TabPanel>


      </DialogContent>
    </Dialog>
    <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={snackbarOpen}
      onClose={handleSnackbarClose}
      message={snackbarMessage}
      autoHideDuration={7000}
      resumeHideDuration={2000}
      key={"snackbar" + unit + "settings"}
    />
    </React.Fragment>
  );
}


function SettingTextField(props){
    const classes = useStyles();

    const [value, setValue] = useState(props.value || "")
    const [activeSubmit, setActiveSumbit] = useState(false)

    useEffect(() => {
      if (props.value !== value) {
        setValue(props.value || "");
      }
    }, [props.value]);


    const onChange = (e) => {
      setActiveSumbit(true)
      setValue(e.target.value)
    }

    const onKeyPress = (e) => {
        if ((e.key === "Enter") && (e.target.value)) {
          onSubmit()
      }
    }

    const onSubmit = () => {
        props.onUpdate(props.id, value);
        if (value !== "") {
          props.setSnackbarMessage(`Updating to ${value}${(!props.units) ? "" : (" "+props.units)}.`)
        } else {
          props.setSnackbarMessage("Updating.")
        }
        props.setSnackbarOpen(true)
        setActiveSumbit(false)
    }

    return (
     <div style={{display: "flex"}}>
        <TextField
          size="small"
          autoComplete="off"
          disabled={props.disabled}
          id={props.id}
          value={value}
          InputProps={{
            endAdornment: <InputAdornment position="end">{props.units}</InputAdornment>,
            autoComplete: 'new-password',
          }}
          variant="outlined"
          onChange={onChange}
          onKeyPress={onKeyPress}
          className={classes.textFieldCompact}
        />
        <Button
          size="small"
          color="primary"
          disabled={!activeSubmit}
          onClick={onSubmit}
          style={{marginTop: "15px", marginLeft: "7px", display: (props.disabled ? "None" : "") }}
        >
          Update
        </Button>
     </div>
    )
}



function SettingSwitchField(props){
    const [value, setValue] = useState(props.value || false)

    useEffect(() => {
      if (props.value !== value) {
        setValue(props.value|| false);
      }
    }, [props]);

    const onChange = (e) => {
      setValue(e.target.checked)
      props.onUpdate(props.id,  e.target.checked ? 1 : 0);
      props.setSnackbarMessage(`Updating to ${e.target.checked ? "on" : "off"}.`)
      props.setSnackbarOpen(true)
    }

    return (
      <Switch
        checked={value}
        disabled={props.disabled}
        onChange={onChange}
        id={props.id}
      />
    )
}



function ActiveUnits(props){
  const [relabelMap, setRelabelMap] = useState({})

  useEffect(() => {
    getRelabelMap(setRelabelMap)
  }, [])

  const cards = props.units.map(unit =>
      <PioreactorCard isUnitActive={true} key={unit} unit={unit} config={props.config} experiment={props.experiment} label={relabelMap[unit]}/>
  )
  var emptyState = (
    <div style={{textAlign: "center", marginBottom: '50px', marginTop: "50px"}}>
      <Typography component='div' variant='body2'>
        <Box fontWeight="fontWeightRegular">
          No active Pioreactors. Do you need to update `cluster.inventory` section in the <a href="/config">configuration</a>?
        </Box>
        <Box fontWeight="fontWeightRegular">
          Or, <a href="https://docs.pioreactor.com/user-guide/create-cluster">read our documentation</a> about managing inventory.
        </Box>
      </Typography>
    </div>
  )

  return (
  <React.Fragment>
    <div style={{display: "flex", justifyContent: "space-between", marginBottom: "10px", marginTop: "15px"}}>
      <Typography variant="h5" component="h2">
        <Box fontWeight="fontWeightRegular">
          Active Pioreactors
        </Box>
      </Typography>
      <div >

      </div>
    </div>

    {(props.units.length === 0) && (props.experiment) ? emptyState : cards }

  </React.Fragment>
)}


function FlashLEDButton(props){
  const classes = useStyles();

  const [flashing, setFlashing] = useState(false)


  const onClick = () => {
    setFlashing(true)
    const sendMessage = () => {
      const topic = `pioreactor/${props.unit}/$experiment/monitor/flicker_led_response_okay`
      try{
        props.client.publish(topic, "1", {qos: 0});
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
    <Button style={{textTransform: 'none', float: "right"}} className={clsx({blinkled: flashing})} disabled={props.disabled} onClick={onClick} color="primary">
      <FlareIcon color={props.disabled ? "disabled" : "primary"} fontSize="15" classes={{root: classes.textIcon}}/> <span > Identify </span>
    </Button>
)}



function PioreactorCard(props){
  const classes = useStyles();
  const unit = props.unit
  const isUnitActive = props.isUnitActive
  const experiment = props.experiment
  const config = props.config
  const [jobFetchComplete, setJobFetchComplete] = useState(false)
  const [label, setLabel] = useState("")
  const {client, subscribeToTopic } = useMQTT();

  const [jobs, setJobs] = useState({
    monitor: {
      state : null,
      metadata: {display: false},
      publishedSettings: {
        versions: {
            value: null, label: null, type: "json", unit: null, display: false, description: null
        },
        voltage_on_pwm_rail: {
            value: null, label: null, type: "json", unit: null, display: false, description: null
        },
        ipv4: {
            value: null, label: null, type: "string", unit: null, display: false, description: null
        },
        wlan_mac_address: {
            value: null, label: null, type: "string", unit: null, display: false, description: null
        },
      },
    },
  })

  useEffect(() => {
    setLabel(props.label)
  }, [props.label])


  useEffect(() => {
    function fetchContribBackgroundJobs() {
      fetch("/api/contrib/jobs")
        .then((response) => {
            if (response.ok) {
              return response.json();
            } else {
              throw new Error('Something went wrong');
            }
          })
        .then((listOfJobs) => {
          var jobs_ = {}
          for (const job of listOfJobs){
            var metaData_ = {state: "disconnected", publishedSettings: {}, metadata: {display_name: job.display_name, subtext: job.subtext, display: job.display, description: job.description, key: job.job_name, source: job.source, is_testing: job.is_testing}}
            for(var i = 0; i < job["published_settings"].length; ++i){
              var field = job["published_settings"][i]
              metaData_.publishedSettings[field.key] = {value: field.default || null, label: field.label, type: field.type, unit: field.unit || null, display: field.display, description: field.description}
            }
            jobs_[job.job_name] = metaData_
          }
          setJobs((prev) => ({...prev, ...jobs_}))
          setJobFetchComplete(true)
        })
        .catch((error) => {})
    }
    fetchContribBackgroundJobs();
  }, [])

  const parseToType = (payloadString, typeOfSetting) => {
    if (typeOfSetting === "numeric"){
      return [null, ""].includes(payloadString) ? payloadString : parseFloat(payloadString)
    }
    else if (typeOfSetting === "boolean"){
      if ([null, ""].includes(payloadString)){
        return null
      }
      return (["1", "true", "True", 1].includes(payloadString))
    }
    return payloadString
  }

  useEffect(() => {

    if (!isUnitActive){
      return
    }

    if (!jobFetchComplete){
      return
    }

    if (!experiment){
      return
    }

    subscribeToTopic(`pioreactor/${unit}/$experiment/monitor/$state`, onMessage);
    for (const job of Object.keys(jobs)) {

      // for some jobs (self_test), we use a different experiment name to not clutter datasets,
      const experimentName = jobs[job].metadata.is_testing ? "_testing_" + experiment : experiment

      subscribeToTopic(`pioreactor/${unit}/${experimentName}/${job}/$state`, onMessage);
      for (const setting of Object.keys(jobs[job].publishedSettings)){
          var topic = [
            "pioreactor",
            unit,
            (job === "monitor" ? "$experiment" : experimentName),
            (setting === "automation_name") ? job : job.replace("_control", "_automation"), // this is for, ex, automation_name
            setting
          ].join("/")
          subscribeToTopic(topic, onMessage);
      }
    }

  },[experiment, jobFetchComplete, isUnitActive, client])

  const onMessage = (topic, message, packet) => {
    var [job, setting] = topic.toString().split('/').slice(-2)
    if (setting === "$state"){
      var payload = message.toString()
      setJobs((prev) => ({...prev, [job]: {...prev[job], state: payload}}))
    } else if (job.endsWith("_automation")) {
      // needed because settings are attached to _automations, not _control
      job = job.replace("_automation", "_control")
      var payload = parseToType(message.toString(), jobs[job].publishedSettings[setting].type)
      setJobs((prev) => ({...prev, [job]: {...prev[job], publishedSettings:
          {...prev[job].publishedSettings,
            [setting]:
              {...prev[job].publishedSettings[setting], value: payload }}}}))
    } else {
      var payload = parseToType(message.toString(), jobs[job].publishedSettings[setting].type)
      setJobs(prev => {
        const updatedJob = { ...prev[job] };
        const updatedSetting = { ...updatedJob.publishedSettings[setting], value: payload };

        updatedJob.publishedSettings = { ...updatedJob.publishedSettings, [setting]: updatedSetting };

        return { ...prev, [job]: updatedJob };
      });
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
      return "Online and ready"
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

  const indicatorDotColor = getIndicatorDotColor(jobs.monitor.state)
  const indicatorDotShadow = 0
  const indicatorLabel = getInicatorLabel(jobs.monitor.state, isUnitActive)

  return (
    <Card className={classes.pioreactorCard} id={unit}>
      <CardContent className={classes.cardContent}>
        <div className={"fixme"}>
          <Typography className={clsx(classes.suptitle)} color="textSecondary">
            {(label) ? unit : ""}
          </Typography>
          <div className={classes.cardHeaderSettings}>
            <div style={{display: "flex", justifyContent: "left"}}>
              <Typography className={clsx(classes.unitTitle, {[classes.disabledText]: !isUnitActive})} gutterBottom>
                <PioreactorIcon color={isUnitActive ? "inherit" : "disabled"} style={{verticalAlign: "middle", marginRight: "3px"}} sx={{ display: {xs: 'none', sm: 'none', md: 'inline' } }}/>
                {(label ) ? label : unit }
              </Typography>
              <Tooltip title={indicatorLabel} placement="right">
                <div>
                  <div aria-label={indicatorLabel} className="indicator-dot" style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
                </div>
              </Tooltip>
            </div>
            <div className={classes.cardHeaderButtons}>
              <div>
                <SelfTestDialog
                  client={client}
                  disabled={!isUnitActive}
                  unit={unit}
                  label={label}
                  selfTestState={jobs['self_test'] ? jobs['self_test'].state : null}
                  selfTestTests={jobs['self_test'] ? jobs['self_test'] : null}
                />
              </div>
              <div>
                <FlashLEDButton client={client} disabled={!isUnitActive} config={config} unit={unit}/>
              </div>
              <div>
                <CalibrateDialog
                  client={client}
                  odBlankReading={jobs['od_blank'] ? jobs['od_blank'].publishedSettings.means.value : null}
                  odBlankJobState={jobs['od_blank'] ? jobs['od_blank'].state : null}
                  growthRateJobState={jobs['growth_rate_calculating'] ? jobs['growth_rate_calculating'].state : null}
                  stirringCalibrationState={jobs['stirring_calibration'] ? jobs['stirring_calibration'].state : null}
                  experiment={experiment}
                  unit={unit}
                  label={label}
                  disabled={!isUnitActive}
                />
              </div>
              <SettingsActionsDialog
                config={config}
                client={client}
                unit={unit}
                label={label}
                disabled={!isUnitActive}
                experiment={experiment}
                jobs={jobs}
                setLabel={setLabel}
              />
            </div>
          </div>
        </div>


      <div style={{
          display: "flex",
          margin: "15px 20px 20px 0px",
          flexDirection: "row",
        }}>
        <div className={classes.textboxLabel}>
          <Typography variant="body2">
            <Box fontWeight="fontWeightBold" className={clsx({[classes.disabledText]: !isUnitActive})}>
              Activities:
            </Box>
          </Typography>
        </div>
        <div
         className={classes.rowOfUnitSettingDisplay}
        >
          {Object.values(jobs)
              .filter(job => job.metadata.display)
              .map(job => (
            <div className={classes.textbox} key={job.metadata.key}>
              <Typography variant="body2" style={{fontSize: "0.84rem"}} className={clsx({[classes.disabledText]: !isUnitActive})}>
                {job.metadata.display_name}
              </Typography>
              <UnitSettingDisplay
                value={job.state}
                isUnitActive={isUnitActive}
                default="disconnected"
                subtext={job.metadata.subtext ? job.publishedSettings[job.metadata.subtext].value : null}
                isStateSetting
              />
            </div>
         ))}

        </div>
      </div>

      <Divider/>

      <div style={{
          display: "flex",
          margin: "15px 20px 20px 0px",
          flexDirection: "row",
        }}>
        <div className={classes.textboxLabel}>
          <Typography variant="body2">
            <Box fontWeight="fontWeightBold" className={clsx({[classes.disabledText]: !isUnitActive})}>
              Settings:
            </Box>
          </Typography>
        </div>
        <div className={classes.rowOfUnitSettingDisplay}>
          {Object.values(jobs)
            //.filter(job => (job.state !== "disconnected") || (job.metadata.key === "leds"))
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings], index) => (
              Object.entries(settings)
                .filter(([setting_key, setting], _) => setting.display)
                .map(([setting_key, setting], _) =>
                  <div className={classes.textbox} key={job_key + setting_key}>
                    <Typography variant="body2" style={{fontSize: "0.84rem"}} className={clsx({[classes.disabledText]: !isUnitActive})}>
                      {setting.label}
                    </Typography>
                    <UnitSettingDisplay
                      value={setting.value}
                      isUnitActive={isUnitActive}
                      measurementUnit={setting.unit}
                      precision={2}
                      default="—"
                      isLEDIntensity={setting.label === "LED intensity"}
                      isPWMDc={setting.label === "PWM intensity"}
                      config={config}
                    />
                  </div>
            )))}
        </div>
      </div>


      </CardContent>
    </Card>
)}


function InactiveUnits(props){
  return (
  <React.Fragment>
    <div style={{display: "flex", justifyContent: "space-between", marginBottom: "10px", marginTop: "15px"}}>
      <Typography variant="h5" component="h2">
        <Box fontWeight="fontWeightRegular">
          Inactive Pioreactors
        </Box>
      </Typography>
    </div>
    {props.units.map(unit =>
      <PioreactorCard isUnitActive={false} key={unit} unit={unit} config={props.config} experiment={props.experiment}/>
  )}
    </React.Fragment>
)}

function Pioreactors({title}) {
  const [experimentMetadata, setExperimentMetadata] = useState({})
  const [config, setConfig] = useState({})

  useEffect(() => {
    document.title = title;

    function getLatestExperiment() {
        fetch("/api/experiments/latest")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setExperimentMetadata(data)
        });
      }

    getConfig(setConfig)
    getLatestExperiment()
  }, [title])

  const entries = (a) => Object.entries(a)
  const activeUnits = config['cluster.inventory'] ? entries(config['cluster.inventory']).filter((v) => v[1] === "1").map((v) => v[0]) : []
  const inactiveUnits = config['cluster.inventory'] ? entries(config['cluster.inventory']).filter((v) => v[1] === "0").map((v) => v[0]) : []

  return (
    <MQTTProvider name="pioreactor" config={config}>
      <Grid container spacing={2} >
        <Grid item md={12} xs={12}>
          <PioreactorHeader config={config} experiment={experimentMetadata.experiment}/>
          <ActiveUnits experiment={experimentMetadata.experiment} config={config} units={activeUnits} />
          { (inactiveUnits.length > 0) &&
          <InactiveUnits experiment={experimentMetadata.experiment} config={config} units={inactiveUnits}/>
          }
        </Grid>
      </Grid>
    </MQTTProvider>
  )
}

export default Pioreactors;

