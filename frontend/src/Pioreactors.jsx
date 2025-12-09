import dayjs from 'dayjs';

import React, {useState, useEffect} from "react";

import Grid from '@mui/material/Grid';
import { useMediaQuery } from "@mui/material";
import { styled } from '@mui/material/styles';



import Chip from '@mui/material/Chip';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import {Typography} from '@mui/material';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Checkbox from '@mui/material/Checkbox';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormGroup from '@mui/material/FormGroup';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import Snackbar from '@mui/material/Snackbar';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import FormLabel from '@mui/material/FormLabel';
import InputAdornment from '@mui/material/InputAdornment';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Button from "@mui/material/Button";
import LoadingButton from '@mui/lab/LoadingButton';
import ClearIcon from '@mui/icons-material/Clear';
import CloseIcon from '@mui/icons-material/Close';
import FlareIcon from '@mui/icons-material/Flare';
import SettingsIcon from '@mui/icons-material/Settings';
import TuneIcon from '@mui/icons-material/Tune';
import IconButton from '@mui/material/IconButton';
import Switch from '@mui/material/Switch';
import { useConfirm } from 'material-ui-confirm';
import Alert from '@mui/material/Alert';
import LibraryAddCheckOutlinedIcon from '@mui/icons-material/LibraryAddCheckOutlined';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import { Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';

import { useNavigate, Link } from 'react-router'

import AdvancedConfigButton from "./components/AdvancedConfigDialog"
import ChangeAutomationsDialog from "./components/ChangeAutomationsDialog"
import ChangeDosingAutomationsDialog from "./components/ChangeDosingAutomationsDialog"
import AutomationAdvancedConfigButton from "./components/AutomationAdvancedConfigDialog"
import ActionDosingForm from "./components/ActionDosingForm"
import ActionManualDosingForm from "./components/ActionManualDosingForm"
import ActionCirculatingForm from "./components/ActionCirculatingForm"
import ActionLEDForm from "./components/ActionLEDForm"
import PioreactorIcon from "./components/PioreactorIcon"
import PioreactorIconWithModel from "./components/PioreactorIconWithModel"
import PioreactorsIcon from "./components/PioreactorsIcon"
import SelfTestDialog from "./components/SelfTestDialog"
import UnderlineSpan from "./components/UnderlineSpan";
import ManageExperimentMenu from "./components/ManageExperimentMenu";
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';
import PatientButton from './components/PatientButton';
import {getConfig, getRelabelMap, runPioreactorJob, disconnectedGrey, lostRed, disabledColor, stateDisplay, checkTaskCallback} from "./utilities"
import cloudImage from './assets/pioreactor_cloud.webp'
import MissingWorkerModelModal from "./components/MissingWorkerModelModal";

const workerMissingModelDetails = (worker) =>
  worker?.model_name == null || worker?.model_version == null;



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


const textIcon = {verticalAlign: "middle", margin: "0px 3px"}

const StylizedCode = styled('code')(() => ({
  backgroundColor: "rgba(0, 0, 0, 0.07)",
  padding: "1px 4px"
}));

const DisplaySettingsTable = styled('span')(({ theme }) => ({
  width: "55px",
  display: "inline-block"
}));

const ControlDivider = styled(Divider)(({ theme }) => ({
  marginTop: theme.spacing(2), // equivalent to 16px if the default spacing unit is 8px
  marginBottom: theme.spacing(1.25) // equivalent to 10px
}));

const RowOfUnitSettingDisplayBox  = styled(Box)(({ theme }) => ({
    display: "flex",
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "flex-start",
    alignItems: "stretch",
    alignContent: "stretch",
}));

let cachedContribJobsList = null;
let contribJobsListPromise = null;

function requestContribJobsList() {
  if (cachedContribJobsList) {
    return Promise.resolve(cachedContribJobsList);
  }
  if (!contribJobsListPromise) {
    const pendingRequest = fetch("/api/contrib/jobs")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch contrib jobs");
        }
        return response.json();
      })
      .then((data) => {
        cachedContribJobsList = data;
        return data;
      });
    contribJobsListPromise = pendingRequest
      .catch((error) => {
        contribJobsListPromise = null;
        throw error;
      })
      .then((data) => {
        contribJobsListPromise = null;
        return data;
      });
  }
  return contribJobsListPromise;
}

function useContribJobsList() {
  const [jobs, setJobs] = useState(cachedContribJobsList);

  useEffect(() => {
    if (cachedContribJobsList) {
      return;
    }

    let isActive = true;
    requestContribJobsList()
      .then((data) => {
        if (!isActive) {
          return;
        }
        setJobs(data);
      })
      .catch(() => {});

    return () => {
      isActive = false;
    };
  }, []);

  return jobs;
}


function TabPanel({ children, value, index, ...other }) {

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

function UnitSettingDisplaySubtext({ subtext }) {
  if (subtext) {
    return <Chip size="small" sx={{fontSize: "11px", wordBreak: "break-word", padding: "5px 0px"}} label={subtext.replaceAll("_", " ")} />;
  }
  return <Box sx={{minHeight: "24px"}} />;
}


function UnitSettingDisplay(props) {

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
      return (
        <React.Fragment>
          <StateTypography state={value} isDisabled={!props.isUnitActive}/>
          <br/>
          <UnitSettingDisplaySubtext subtext={props.subtext}/>
        </React.Fragment>
    )
  } else if (props.isLEDIntensity) {
    if (!props.isUnitActive || value === "—" || value === "") {
      return <div style={{ color: disconnectedGrey, fontSize: "13px"}}> {props.default} </div>;
    } else {
      const ledIntensities = JSON.parse(value)
        // the | {} is here to protect against the UI loading from a missing config.
      const LEDMap = props.config['leds'] || {}
      const renamedA = (LEDMap['A']) ? (LEDMap['A'].replace("_", " ")) : null
      const renamedB = (LEDMap['B']) ? (LEDMap['B'].replace("_", " ")) : null
      const renamedC = (LEDMap['C']) ? (LEDMap['C'].replace("_", " ")) : null
      const renamedD = (LEDMap['D']) ? (LEDMap['D'].replace("_", " ")) : null

      return(
        <React.Fragment>
          <div style={{fontSize: "13px"}}>
            <div>
              <DisplaySettingsTable>
                <UnderlineSpan title={renamedA ? renamedA : null}>A</UnderlineSpan>: {prettyPrint(ledIntensities["A"])}%
              </DisplaySettingsTable>
              <DisplaySettingsTable>
                <UnderlineSpan title={renamedB ? renamedB : null}>B</UnderlineSpan>: {prettyPrint(ledIntensities["B"])}%
              </DisplaySettingsTable>
            </div>
            <div>
              <DisplaySettingsTable>
                <UnderlineSpan title={renamedC ? renamedC : null}>C</UnderlineSpan>: {prettyPrint(ledIntensities["C"])}%
              </DisplaySettingsTable>
              <DisplaySettingsTable>
                <UnderlineSpan title={renamedD ? renamedD : null}>D</UnderlineSpan>: {prettyPrint(ledIntensities["D"])}%
              </DisplaySettingsTable>
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
              <DisplaySettingsTable>
                <UnderlineSpan title={renamed1 ? renamed1 : null}>1</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[1]] || 0)}%
              </DisplaySettingsTable>
              <DisplaySettingsTable>
               <UnderlineSpan title={renamed2 ? renamed2 : null}>2</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[2]] || 0)}%
              </DisplaySettingsTable>
            </div>
            <div>
              <DisplaySettingsTable>
                <UnderlineSpan title={renamed3 ? renamed3 : null}>3</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[3]] || 0)}%
              </DisplaySettingsTable>
              <DisplaySettingsTable>
                <UnderlineSpan title={renamed4 ? renamed4 : null}>4</UnderlineSpan>: {prettyPrint(pwmDcs[PWM_TO_PIN[4]] || 0)}%
              </DisplaySettingsTable>
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
          <Chip size="small" style={{ fontSize: "13px"}}
            label={formatForDisplay(value) + " " +
              (props.measurementUnit ? props.measurementUnit : "")}
          />
          <UnitSettingDisplaySubtext subtext={props.subtext}/>
        </React.Fragment>
      );
    }
  }
}



function ButtonStopProcess({experiment}) {
  const confirm = useConfirm();

  const handleClick = () => {
    confirm({
      description: 'This will immediately stop all running activities in assigned Pioreactor units, and any experiment profiles running for this experiment. Do you wish to continue?',
      title: "Stop all activities?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
      cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},

      }).then(() =>
        fetch(`/api/workers/$broadcast/jobs/stop/experiments/${experiment}`, {method: "POST"})
    ).catch(() => {});

  };

  return (
    <Button sx={{textTransform: 'none', float: "right" }} color="secondary" onClick={handleClick}>
      <ClearIcon fontSize="small" sx={textIcon}/> Stop all activity
    </Button>
  );
}




const CustomFormControlLabel = ({ label, sublabel, control, ...props }) => (
  <FormControlLabel
    control={control}
    label={
      <Box>
        <Typography variant="body1">{label}</Typography>
        {sublabel && <Typography variant="body2" color={disabledColor}>{sublabel}</Typography>}
      </Box>
    }
    {...props}
  />
);

function AssignPioreactors({ experiment, variant="text" }) {
  const [workers, setWorkers] = React.useState([]);
  const [assigned, setAssigned] = React.useState({});
  const [initialAssigned, setInitialAssigned] = React.useState({});
  const [selectAll, setSelectAll] = React.useState(false);
  const [open, setOpen] = React.useState(false);
  const navigate = useNavigate();
  const { selectExperiment } = useExperiment();

  useEffect(() => {
    if (!open){
      return
    }

    fetch("/api/workers/assignments")
      .then((data) => data.json())
      .then((json) => {
        setWorkers(json);
        const assignments = json.reduce((map, item) => {
          map[item.pioreactor_unit] = item.experiment === experiment;
          return map;
        }, {});
        setAssigned(assignments);
        setInitialAssigned(assignments);
      });
  }, [experiment, open]);

  function compareObjects(o1, o2) {
    const differences = {};
    for (const key in o1) {
      if (o1[key] !== o2[key]) {
        differences[key] = { current: o1[key], initial: o2[key] };
      }
    }
    return differences;
  }

  const updateAssignments = async () => {
    const delta = compareObjects(assigned, initialAssigned);
    const promises = [];

    for (const worker in delta) {
      if (delta[worker].current && !delta[worker].initial) {
        const promise = fetch(`/api/experiments/${experiment}/workers`, {
          method: "PUT",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ pioreactor_unit: worker }),
        });
        promises.push(promise);
      } else {
        const promise = fetch(`/api/experiments/${experiment}/workers/${worker}`, {
          method: "DELETE",
        });
        promises.push(promise);
      }
    }

    await Promise.all(promises);
    setOpen(false);
    navigate(0);
  };

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleChange = (event) => {
    setAssigned({
      ...assigned,
      [event.target.name]: event.target.checked,
    });
  };

  const handleSelectAllChange = (event) => {
    const newValue = event.target.checked;
    const newAssigned = { ...assigned };

    workers.forEach((worker) => {
      if (!worker.experiment || worker.experiment === experiment) {
        newAssigned[worker.pioreactor_unit] = newValue;
      }
    });
    setAssigned(newAssigned);
    setSelectAll(newValue);
  };

  useEffect(() => {
    const allSelected = workers.every(
      (worker) => (worker.experiment && worker.experiment !== experiment) || assigned[worker.pioreactor_unit]
    );
    const noneSelected = workers.every(
      (worker) => (worker.experiment && worker.experiment !== experiment) || !assigned[worker.pioreactor_unit]
    );
    setSelectAll(allSelected ? true : (noneSelected ? false : null));
  }, [assigned, workers, experiment]);

  return (
    <React.Fragment>
      <Button variant={variant} style={{ textTransform: "none" }} onClick={handleClickOpen}>
        <LibraryAddCheckOutlinedIcon
          fontSize="small"
          sx={{ verticalAlign: "middle", margin: "0px 3px" }}
        />
        Assign Pioreactors
      </Button>
      <Dialog
        open={open}
        onClose={handleClose}
        fullWidth={true}
        aria-labelledby="form-dialog-title"
      >
        <DialogTitle>
          Assign Pioreactors
          <IconButton
            aria-label="close"
            onClick={handleClose}
            sx={{
              position: "absolute",
              right: 8,
              top: 8,
              color: (theme) => theme.palette.grey[500],
            }}
            size="large"
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <p>
            Assign and unassign Pioreactors to experiment{" "}
            <Chip icon={<PlayCircleOutlinedIcon/>} size="small" label={experiment} clickable component={Link} onClick={() => selectExperiment(experiment)} data-experiment-name={experiment} />.
          </p>
          <FormControl sx={{ m: "auto" }} component="fieldset" variant="standard">
            <FormLabel component="legend">Pioreactors</FormLabel>
            {workers.length > 1 &&
            <FormControlLabel
              control={
                <Checkbox
                  checked={selectAll || false}
                  indeterminate={selectAll === null}
                  onChange={handleSelectAllChange}
                />
              }
              label={<span><i>Select all available</i></span>}
              sx={{mb: 1}}
            />
            }
            <FormGroup
              sx={
                workers.length > 8
                  ? {
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      columnGap: "30px",
                    }
                  : {}
              }
            >
              {(workers || []).map((worker) => {
                const unit = worker.pioreactor_unit;
                const exp = worker.experiment;
                const disabled = exp !== null && exp !== experiment;
                const sublabel = disabled ?
                  <>assigned to <Chip icon={<PlayCircleOutlinedIcon/>} size="small" label={exp} clickable component={Link} onClick={() => selectExperiment(exp)} data-experiment-name={exp} /> </>
                  : null;

                return (
                  <CustomFormControlLabel
                    key={unit}
                    control={
                      <Checkbox
                        disabled={disabled}
                        onChange={handleChange}
                        checked={!disabled && assigned[unit]}
                        name={unit}
                        sx={{ mb: sublabel ? 3 : 0 }}
                      />
                    }
                    label={unit}
                    sublabel={sublabel}
                  />
                );
              })}
            </FormGroup>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button
            variant="contained"
            onClick={updateAssignments}
            disabled={Object.keys(compareObjects(assigned, initialAssigned)).length === 0}
            style={{ textTransform: "none" }}
          >
            Update {Object.keys(compareObjects(assigned, initialAssigned)).length}
          </Button>
        </DialogActions>
      </Dialog>
    </React.Fragment>
  );
}

function PioreactorHeader({experiment, config}) {
  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h1">
          <Box fontWeight="fontWeightBold">
            Pioreactors
          </Box>
        </Typography>
        <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
          <ButtonStopProcess experiment={experiment}/>
          <AssignPioreactors experiment={experiment}/>
          <SettingsActionsDialogAll experiment={experiment} config={config}/>
          <Divider orientation="vertical" flexItem variant="middle"/>
          <ManageExperimentMenu experiment={experiment}/>
        </Box>
      </Box>
      <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />
    </Box>
  )
}



function CalibrateDialog({ unit, experiment, odBlankReading, odBlankJobState, growthRateJobState, label, disabled }) {
  const [open, setOpen] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [activeCalibrations, setActiveCalibrations] = useState({});
  const [loadingCalibrations, setLoadingCalibrations] = useState(false);

  useEffect(() => {
    if (!open) return;

    setLoadingCalibrations(true)

    const apiUrl = `/api/workers/${unit}/active_calibrations`;

    const fetchCalibrations = async () => {
      try {
        const response = await fetch(apiUrl);
        const firstResponse = await response.json();
        const data = await checkTaskCallback(firstResponse.result_url_path, {delayMs: 2000})
        setActiveCalibrations(data.result[unit]);
        setLoadingCalibrations(false)
      } catch (err) {
        console.error("Failed to fetch calibration:", err);
      }
    };

    fetchCalibrations();
  }, [open, unit]);


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
                onClick={() => runPioreactorJob(unit, experiment, job)}
                buttonText="Start"
                disabled={always_disable}
               />
              </div>)
    }
   }

  const isGrowRateJobRunning = growthRateJobState === "ready";
  const hasActiveODCalibration = "od" in (activeCalibrations || {});
  const blankODButton = createUserButtonsBasedOnState(odBlankJobState, "od_blank", (isGrowRateJobRunning || hasActiveODCalibration));

  return (
    <React.Fragment>
      <Button style={{textTransform: 'none', float: "right" }} color="primary" disabled={disabled} onClick={handleClickOpen}>
        <TuneIcon color={disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon}/> Calibrate
      </Button>
      <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title">
        <DialogTitle>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}}>
          <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/> {(label) ? `${label} / ${unit}` : `${unit}`}
          </Typography>
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            indicatorColor="primary"
            textColor="primary"

            >
            <Tab sx={{textTransform: 'none'}} label="Calibrations"/>
            <Tab sx={{textTransform: 'none'}} label="Blanks"/>
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
          <TabPanel value={tabValue} index={1}>
            <Typography  gutterBottom>
             Record optical densities of blank (optional)
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
              For more accurate growth rate and biomass inferences, the Pioreactor can subtract out the
              media's <i>un-inoculated</i> optical density <i>per experiment</i>. Read more about <a href="https://docs.pioreactor.com/user-guide/od-normal-growth-rate#blanking">using blanks</a>. If your Pioreactor has an active OD calibration, this isn't required.
            </Typography>
            <Typography variant="body2" component="p" style={{margin: "20px 0px"}}>
              Recorded optical densities of blank vial: <code>{odBlankReading ? Object.entries(JSON.parse(odBlankReading)).map( ([k, v]) => `${k}:${v.toFixed(5)}` ).join(", ") : "—"}</code>
            </Typography>

            <div style={{display: "flex"}}>
              {hasActiveODCalibration &&
                <UnderlineSpan title="If an active OD calibration is present, this isn't used.">
                  {blankODButton}
                </UnderlineSpan>
                }
              {!hasActiveODCalibration &&
                <div>
                {blankODButton}
                </div>
              }
              <div>
              <Button size="small" sx={{width: "70px", mt: "5px", height: "31px", mr: '3px'}} color="secondary" disabled={(odBlankReading === null) || (isGrowRateJobRunning)} onClick={() => runPioreactorJob(unit, experiment, "od_blank", ['delete']) }> Clear </Button>
              </div>
            </div>
            <ControlDivider/>

          </TabPanel>
          <TabPanel value={tabValue} index={0}>
            <Typography gutterBottom>
              Active calibrations
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
              Below are the active calibrations that will be used when running devices like pumps, stirring, etc. Read more about{' '}
              <a href="https://docs.pioreactor.com/user-guide/hardware-calibrations">calibrations</a>.
            </Typography>
            {loadingCalibrations ? (
              <Box sx={{ textAlign: 'center', marginTop: '2rem' }}>
                <CircularProgress />
              </Box>
            ) : Object.entries(activeCalibrations || {}).length === 0 ? (
              // Empty state message when there are no active calibrations.
              (<Typography variant="body2" component="p" color="textSecondary" sx={{ mt: 3 }}>There are no active calibrations available.
                              </Typography>)
            ) : (
              // Table rendering when active calibrations exist.
              (<Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell align="left" sx={{ padding: '6px 0px' }}>Device</TableCell>
                    <TableCell align="left" sx={{ padding: '6px 0px' }}>Calibration name</TableCell>
                    <TableCell align="left" sx={{ padding: '6px 0px' }}>Calibrated on</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(activeCalibrations).map(([device, calibration]) => {
                    const calName = calibration.calibration_name;
                    return (
                      <TableRow key={`${calName}-${device}`}>
                        <TableCell align="left" sx={{ padding: '6px 0px' }}>
                          {device}
                        </TableCell>
                        <TableCell align="left" sx={{ padding: '6px 0px' }}>
                          <Chip
                            size="small"
                            icon={<TuneIcon />}
                            label={calName}
                            data-calibration-name={calName}
                            data-device={device}
                            clickable
                            component={Link}
                            to={`/calibrations/${unit}/${device}/${calName}`}
                          />
                        </TableCell>
                        <TableCell align="left" sx={{ padding: '6px 0px' }}>
                          {dayjs(calibration.created_at).format('YYYY-MM-DD')}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>)
            )}


          </TabPanel>
        </DialogContent>
      </Dialog>
    </React.Fragment>
  );
}




function SettingsActionsDialog({ unit, experiment, jobs, setLabel, label, disabled, modelDetails }) {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState({})
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [tabValue, setTabValue] = useState(0);
  const [rebooting, setRebooting] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);
  const [openChangeDosingDialog, setOpenChangeDosingDialog] = useState(false);
  const [openChangeLEDDialog, setOpenChangeLEDDialog] = useState(false);
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = useState(false);
  useEffect(() => {
    if (!open){
      return
    }

    fetch(`/api/workers/${unit}/configuration`).then((response) => {
      if (!response.ok) {
        return response.json().then((errorData) => {
          console.log(errorData)
          throw new Error(errorData.error);
        });
      }
      return response.json();
    })
    .then((data) => setConfig(data[unit]))
    .catch((error) => {
      console.error("Fetching configuration failed:", error);
    });


  }, [open]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };


  function setPioreactorJobState(job, state) {
    return function() {
      setPioreactorJobAttr(job, "$state", state)
    };
  }


  function rebootRaspberryPi(){
    return function() {
      setRebooting(true)
      fetch(`/api/units/${unit}/system/reboot`, {method: "POST"})
    }
  }

  function shutDownRaspberryPi(){
    return function() {
      setShuttingDown(true)
      fetch(`/api/units/${unit}/system/shutdown`, {method: "POST"})
    }
  }

  function stopPioreactorJob(job){
    return setPioreactorJobState(job, "disconnected")
  }

  function setPioreactorJobAttr(job, setting, value) {

    fetch(`/api/workers/${unit}/jobs/update/job_name/${job}/experiments/${experiment}`, {
      method: "PATCH",
      body: JSON.stringify({settings: {[setting]: value}}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
  }


  function updateRenameUnit(_, __, value) {
      const relabeledTo = value
      setSnackbarMessage(`Updating to ${relabeledTo}`)
      setSnackbarOpen(true)
      fetch(`/api/experiments/${experiment}/unit_labels`,{
          method: "PUT",
          body: JSON.stringify({label: relabeledTo, unit: unit}),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
        }).then(res => {
          if (res.ok) {
            setLabel(relabeledTo)
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
                    onClick={() => runPioreactorJob(unit, experiment, job)}
                    buttonText="Start"
                  />
        </div>)
      case "disconnected":
       return (<div key={"patient_buttons_disconnected" + job}>
                 <PatientButton
                  color="primary"
                  variant="contained"
                  onClick={() => runPioreactorJob(unit, experiment, job)}
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
              onClick={()=>(false)}
              buttonText=<CircularProgress color="inherit" size={22}/>
              disabled={true}
            />
            <PatientButton
              color="secondary"
              onClick={stopPioreactorJob(job)}
              buttonText="Stop"
              variant="contained"
            />
          </div>
        )
      case "ready":
        return (
          <div key={"patient_buttons_ready" + job}>
            <PatientButton
              color="secondary"
              onClick={setPioreactorJobState(job, "sleeping")}
              buttonText="Pause"
            />
            <PatientButton
              variant="contained"
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
              onClick={setPioreactorJobState(job, "ready")}
              buttonText="Resume"
            />
            <PatientButton
              variant="contained"
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

  // Define a function to determine which component to render based on the type of setting
  function renderSettingComponent(setting, job_key, setting_key, state) {
    const commonProps = {
      onUpdate: setPioreactorJobAttr,
      setSnackbarMessage: setSnackbarMessage,
      setSnackbarOpen: setSnackbarOpen,
      value: setting.value,
      units: setting.unit,
      job: job_key,
      setting: setting_key,
      disabled: state === "disconnected",
    };

    switch (setting.type) {
      case "boolean":
        return <SettingSwitchField {...commonProps} />;
      case "numeric":
        return <SettingNumericField {...commonProps} />;
      default:
        return <SettingTextField {...commonProps} />;
    }
  }


  const LEDMap = config['leds'] || {}
  const buttons = Object.fromEntries(Object.entries(jobs || {}).map(([job_key, job]) => [job_key, createUserButtonsBasedOnState(job.state, job_key)]));
  const versionInfo = JSON.parse(jobs.monitor.publishedSettings.versions.value || "{}");
  const voltageInfo = JSON.parse(jobs.monitor.publishedSettings.voltage_on_pwm_rail.value || "{}");
  const ipInfo = jobs.monitor.publishedSettings.ipv4.value;
  const macInfoWlan = jobs.monitor.publishedSettings.wlan_mac_address.value;
  const macInfoEth = jobs.monitor.publishedSettings.eth_mac_address.value;

  const isLargeScreen = useMediaQuery(theme => theme.breakpoints.down('xl'));
  const dosingControlJob = jobs.dosing_automation;
  const ledControlJob = jobs.led_automation;
  const temperatureControlJob = jobs.temperature_automation;

  return (
    <div>
    <Button style={{textTransform: 'none', float: "right" }} disabled={disabled} onClick={handleClickOpen} color="primary">
      <SettingsIcon color={disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon}/> Control
    </Button>
    <Dialog maxWidth={isLargeScreen ? "sm" : "md"} fullWidth={true} open={open} onClose={handleClose} PaperProps={{
      sx: {
        height: "calc(100% - 64px)"
      }
    }}>
      <DialogTitle>
        <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}}>
          <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/>
          <span> {label ? `${label} / ${unit}` : `${unit}`} </span>
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
        <Tab sx={{textTransform: 'none'}} label="Activities"/>
        <Tab sx={{textTransform: 'none'}} label="Settings"/>
        <Tab sx={{textTransform: 'none'}} label="Dosing"/>
        <Tab sx={{textTransform: 'none'}} label="LEDs"/>
        <Tab sx={{textTransform: 'none'}} label="System"/>
      </Tabs>
      </DialogTitle>
      <DialogContent>
        <TabPanel value={tabValue} index={0}>
          {/* Unit Specific Activites */}
          {Object.entries(jobs)
            .filter(([_, job]) => job.metadata.display)
            .filter(([job_key, job]) => !['dosing_automation', 'led_automation', 'temperature_automation'].includes(job_key)) // added later
            .map(([job_key, job]) =>
            <div key={job_key}>
              <div style={{justifyContent: "space-between", display: "flex"}}>
                <Typography display="block">
                  {job.metadata.display_name}
                </Typography>
                <StateTypography state={job.state}/>
              </div>
              <Typography variant="caption" display="block" gutterBottom color="textSecondary">
                {job.metadata.source !== "app" ? `Installed by ${job.metadata.source || "unknown"}` : ""}
              </Typography>
              <Typography variant="body2" component="p" gutterBottom>
                <div dangerouslySetInnerHTML={{__html: job.metadata.description}}/>
              </Typography>
              <Box sx={{justifyContent:"space-between", display:"flex"}}>
                {buttons[job_key]}

                <AdvancedConfigButton jobName={job_key} displayName={job.metadata.display_name} unit={unit} experiment={experiment} config={config[`${job_key}.config`]} disabled={job.state !== "disconnected"} />
              </Box>
              <ControlDivider/>
            </div>
          )}


          {/* Unit Specific Automations */}
          {temperatureControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                Temperature automation
              </Typography>
              <StateTypography state={temperatureControlJob.state}/>
            </div>

            <div key={temperatureControlJob.metadata.key}>
              {(temperatureControlJob.state === "ready") || (temperatureControlJob.state === "sleeping") || (temperatureControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                Currently running temperature automation <Chip size="small" label={temperatureControlJob.publishedSettings.automation_name.value}/>
                </Typography>
                {buttons[temperatureControlJob.metadata.key]}
               </React.Fragment>
              :<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                  <span dangerouslySetInnerHTML={{__html: temperatureControlJob.metadata.description}}/>
                </Typography>

                <Button
                  sx={{width: "70px", mt: "5px", height: "31px", mr: '3px'}}
                  size="small"
                  color="primary"
                  variant="contained"
                  onClick={() => setOpenChangeTemperatureDialog(true)}
                >
                  Start
                </Button>
                <Button
                  sx={{width: "70px", mt: "5px", height: "31px", mr: '3px'}}
                  size="small"
                  color="primary"
                  disabled={true}
                >
                  Stop
                </Button>

                <AutomationAdvancedConfigButton
                  jobName="temperature_automation"
                  displayName="Temperature automation"
                  automationType="temperature"
                  unit={unit}
                  experiment={experiment}
                  label={label}
                  config={config?.["temperature_automation.config"] || {}}
                  no_skip_first_run={true}
                />

               </React.Fragment>
              }
            </div>

            <ChangeAutomationsDialog
              open={openChangeTemperatureDialog}
              onFinished={() => setOpenChangeTemperatureDialog(false)}
              unit={unit}
              label={label}
              experiment={experiment}
              automationType="temperature"
              no_skip_first_run={true}
            />
          </React.Fragment>
          }

          <ControlDivider/>

          {dosingControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                Dosing automation
              </Typography>
              <StateTypography state={dosingControlJob.state}/>
            </div>
            <div key={dosingControlJob.metadata.key}>
              {(dosingControlJob.state === "ready") || (dosingControlJob.state === "sleeping") || (dosingControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                Currently running dosing automation <Chip size="small" label={dosingControlJob.publishedSettings.automation_name.value}/>.
                </Typography>
                {buttons[dosingControlJob.metadata.key]}
               </React.Fragment>
              :<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                  <span dangerouslySetInnerHTML={{__html: dosingControlJob.metadata.description}}/>
                </Typography>

                <Button
                  sx={{width: "70px", mt: "5px", height: "31px", mr: '3px'}}
                  size="small"
                  color="primary"
                  variant="contained"
                  onClick={() => setOpenChangeDosingDialog(true)}
                >
                  Start
                </Button>
                <Button
                  sx={{width: "70px", mt: "5px", height: "31px", mr: '3px'}}
                  size="small"
                  color="primary"
                  disabled={true}
                >
                  Stop
                </Button>

                <AutomationAdvancedConfigButton
                  jobName="dosing_automation"
                  displayName="Dosing automation"
                  automationType="dosing"
                  unit={unit}
                  experiment={experiment}
                  label={label}
                  config={config?.["dosing_automation.config"] || {}}
                  maxVolume={parseFloat(dosingControlJob.publishedSettings.max_working_volume_ml.value) || parseFloat(config?.bioreactor?.max_working_volume_ml) || 10}
                  liquidVolume={parseFloat(dosingControlJob.publishedSettings.current_volume_ml.value) || parseFloat(config?.bioreactor?.current_volume_ml) || 10}
                  threshold={modelDetails.reactor_max_fill_volume_ml}
                />
               </React.Fragment>
              }
            </div>


            <ChangeDosingAutomationsDialog
              automationType="dosing"
              open={openChangeDosingDialog}
              onFinished={() => setOpenChangeDosingDialog(false)}
              unit={unit}
              label={label}
              experiment={experiment}
              no_skip_first_run={false}
              maxVolume={parseFloat(dosingControlJob.publishedSettings.max_working_volume_ml.value) || parseFloat(config?.bioreactor?.max_working_volume_ml) || 10}
              liquidVolume={parseFloat(dosingControlJob.publishedSettings.current_volume_ml.value) || parseFloat(config?.bioreactor?.current_volume_ml) || 10}
              threshold={modelDetails.reactor_max_fill_volume_ml}
            />
          </React.Fragment>
          }

          <ControlDivider/>


          {ledControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                LED automation
              </Typography>
              <StateTypography state={ledControlJob.state}/>
            </div>

            <div key={ledControlJob.metadata.key}>
              {(ledControlJob.state === "ready") || (ledControlJob.state === "sleeping") || (ledControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                Currently running LED automation <Chip size="small" label={ledControlJob.publishedSettings.automation_name.value}/>.
                </Typography>
                {buttons[ledControlJob.metadata.key]}
               </React.Fragment>
              :<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                  <span dangerouslySetInnerHTML={{__html: ledControlJob.metadata.description}}/>
                </Typography>

                <Button
                  sx={{width: "70px", mt: "5px", height: "31px", mr: '3px'}}
                  size="small"
                  color="primary"
                  variant="contained"
                  onClick={() => setOpenChangeLEDDialog(true)}
                >
                  Start
                </Button>
                <Button
                  sx={{width: "70px", mt: "5px", height: "31px", mr: '3px'}}
                  size="small"
                  color="primary"
                  disabled={true}
                >
                  Stop
                </Button>

                <AutomationAdvancedConfigButton
                  jobName="led_automation"
                  displayName="LED automation"
                  automationType="led"
                  unit={unit}
                  experiment={experiment}
                  label={label}
                  config={config?.["led_automation.config"] || {}}
                  no_skip_first_run={false}
                />
               </React.Fragment>
              }
            </div>

            <ChangeAutomationsDialog
              automationType="led"
              open={openChangeLEDDialog}
              onFinished={() => setOpenChangeLEDDialog(false)}
              unit={unit}
              label={label}
              experiment={experiment}
              no_skip_first_run={false}
            />
          </React.Fragment>
          }

          <ControlDivider/>


        </TabPanel>


        <TabPanel value={tabValue} index={1}>
          <Typography  gutterBottom>
            Assign temporary label to Pioreactor
          </Typography>
          <Typography variant="body2" component="p">
            Assign a temporary label to this Pioreactor for this experiment. The new label will display in graph legends, and throughout the interface.
          </Typography>
          <SettingTextField
            value={label}
            onUpdate={updateRenameUnit}
            setSnackbarMessage={setSnackbarMessage}
            setSnackbarOpen={setSnackbarOpen}
            disabled={false}
          />
          <ControlDivider/>

          {Object.values(jobs)
            .filter(job => job.metadata.display)
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings], index) => (
              Object.entries(settings)
                .filter(([setting_key, setting],_) => setting.display && setting.editable)
                .map(([setting_key, setting],_) =>
                        <React.Fragment key={setting_key}>
                          <Typography gutterBottom>
                            {setting.label}
                          </Typography>

                          <Typography variant="body2" component="p">
                            {setting.description}
                          </Typography>

                          {renderSettingComponent(setting, job_key, setting_key, state)}

                          <ControlDivider/>
                        </React.Fragment>
          )))}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Typography  gutterBottom>
            Cycle Media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle media in and out of your Pioreactor for a set duration (seconds) by running the media periodically and waste pump continuously.
          </Typography>

          <ActionCirculatingForm action="circulate_media" unit={unit} experiment={experiment} job={jobs.circulate_media} />

          <ControlDivider/>

          <Typography  gutterBottom>
            Cycle alternative media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle alternative media in and out of your Pioreactor for a set duration (seconds) by running the alt-media periodically and waste pump continuously.
          </Typography>

          <ActionCirculatingForm action="circulate_alt_media" unit={unit} experiment={experiment} job={jobs.circulate_alt_media} />

          <ControlDivider/>

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
          <ActionDosingForm action="add_media" unit={unit} experiment={experiment} job={jobs.add_media} />
          <ControlDivider/>
          <Typography  gutterBottom>
            Remove waste
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the waste pump for a set duration (s), moving a set volume (mL), or continuously remove until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to remove waste:
          </Typography>
          <ActionDosingForm action="remove_waste" unit={unit} experiment={experiment} job={jobs.remove_waste} />
          <ControlDivider/>
          <Typography gutterBottom>
            Add alternative media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the alt-media pump for a set duration (s), moving a set volume (mL), or continuously add until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add alt-media:
          </Typography>
          <ActionDosingForm action="add_alt_media" unit={unit} experiment={experiment} job={jobs.add_alt_media} />
          <ControlDivider/>
          <Typography gutterBottom>
            Manual adjustments
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Record adjustments before manually adding or removing from the vial. This is recorded in the database and will ensure accurate metrics. Dosing automation must be on.
          </Typography>
          <ActionManualDosingForm unit={unit} experiment={experiment}/>


        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['A']) ? (LEDMap['A'].replace("_", " ").replace("led", "LED")) : "Channel A" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['A']) ? "Channel A" : ""}
          </Typography>
          <ActionLEDForm experiment={experiment} channel="A" unit={unit} />
          <ControlDivider/>

          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['B']) ? (LEDMap['B'].replace("_", " ").replace("led", "LED")) : "Channel B" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['B']) ? "Channel B" : ""}
          </Typography>
          <ActionLEDForm experiment={experiment} channel="B" unit={unit} />
          <ControlDivider/>

          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['C']) ? (LEDMap['C'].replace("_", " ").replace("led", "LED")) : "Channel C" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['C']) ? "Channel C" : ""}
          </Typography>

          <ActionLEDForm experiment={experiment} channel="C" unit={unit} />
          <ControlDivider/>

          <Typography style={{textTransform: "capitalize"}}>
            {(LEDMap['D']) ? (LEDMap['D'].replace("_", " ").replace("led", "LED")) : "Channel D" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['D']) ? "Channel D" : ""}
          </Typography>
          <ActionLEDForm experiment={experiment} channel="D" unit={unit} />
          <ControlDivider/>
        </TabPanel>
        <TabPanel value={tabValue} index={4}>

          <Typography  gutterBottom>
            Addresses and hostname
          </Typography>

            <Typography variant="body2" component="p" gutterBottom>
              Learn about how to <a target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com/user-guide/accessing-raspberry-pi">access the Pioreactor's Raspberry Pi</a>.
            </Typography>

            <table style={{borderCollapse: "separate", borderSpacing: "5px", fontSize: "0.90rem"}}>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    IPv4
                </td>
                <td>
                  <StylizedCode>{ipInfo || "-"}</StylizedCode>
                </td>
              </tr>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    Hostname
                </td>
                <td>
                  <StylizedCode>{unit}.local</StylizedCode>
                </td>
              </tr>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    WLAN MAC
                </td>
                <td>
                  <StylizedCode>{macInfoWlan || "-"}</StylizedCode>
                </td>
              </tr>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    Ethernet MAC
                </td>
                <td>
                  <StylizedCode>{macInfoEth || "-"}</StylizedCode>
                </td>
              </tr>
            </table>


          <ControlDivider/>

          <Typography  gutterBottom>
            Version information
          </Typography>


            <table style={{borderCollapse: "separate", borderSpacing: "5px", fontSize: "0.90rem"}}>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    Software version
                </td>
                <td >
                  <StylizedCode>{versionInfo.app || "-"}</StylizedCode>
                </td>
              </tr>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    Raspberry Pi
                </td>
                <td >
                  <StylizedCode>{versionInfo.rpi_machine || "-"}</StylizedCode>
                </td>
              </tr>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    HAT version
                </td>
                <td >
                  <StylizedCode>{versionInfo.hat || "-"}</StylizedCode>
                </td>
              </tr>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    HAT serial number
                </td>
                <td >
                  <StylizedCode>{versionInfo.hat_serial || "-"}</StylizedCode>
                </td>
              </tr>
            </table>


          <ControlDivider/>

          <Typography  gutterBottom>
            Voltage on PWM rail
          </Typography>

            <table style={{borderCollapse: "separate", borderSpacing: "5px", fontSize: "0.90rem"}}>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    Voltage
                </td>
                <td >
                  <StylizedCode>{voltageInfo.voltage ? `${voltageInfo.voltage} V` : "-" }</StylizedCode>
                </td>
              </tr>
              <tr>
                <td style={{textAlign: "right", minWidth: "120px", color: ""}}>
                    Last updated at
                </td>
                <td >
                  <StylizedCode>{voltageInfo.timestamp ? dayjs.utc(voltageInfo.timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]').local().format('MMMM D, h:mm a') : "-"}</StylizedCode>
                </td>
              </tr>
            </table>


          <ControlDivider/>

          <Typography  gutterBottom>
            Reboot
          </Typography>
          <Typography variant="body2" component="p">
            Reboot the Raspberry Pi operating system. This will stop all jobs, and the Pioreactor will be inaccessible for a few minutes. It will blink its blue LED when back up, or press the onboard button to light up the blue LED.
          </Typography>

          <LoadingButton
            loadingIndicator="Rebooting"
            loading={rebooting}
            variant="text"
            color="primary"
            style={{marginTop: "15px", textTransform: 'none'}}
            onClick={rebootRaspberryPi()}
          >
            Reboot RPi
          </LoadingButton>

          <ControlDivider/>

          <Typography  gutterBottom>
            Shut down
          </Typography>
          <Typography variant="body2" component="p">
            After 20 seconds, shut down the Pioreactor. This will stop all jobs, and the Pioreactor will be inaccessible until it is restarted by unplugging and replugging the power supply.
          </Typography>
          <LoadingButton
            loadingIndicator="😵"
            loading={shuttingDown}
            variant="text"
            color="primary"
            style={{marginTop: "15px", textTransform: 'none'}}
            onClick={shutDownRaspberryPi()}
          >
            Shut down
          </LoadingButton>

          <ControlDivider/>



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
    </div>
  );
}


function SettingsActionsDialogAll({experiment, config}) {
  const unit = "$broadcast"
  const [open, setOpen] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [tabValue, setTabValue] = useState(0);
  const [jobs, setJobs] = useState({});
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = useState(false);
  const [openChangeDosingDialog, setOpenChangeDosingDialog] = useState(false);
  const [openChangeLEDDialog, setOpenChangeLEDDialog] = useState(false);
  const {client} = useMQTT();
  const contribJobsList = useContribJobsList();

  useEffect(() => {
    if (!Array.isArray(contribJobsList)) {
      return;
    }
    const jobsFromApi = {};
    for (const job of contribJobsList) {
      const metaData = {
        publishedSettings: {},
        metadata: {
          display_name: job.display_name,
          display: job.display,
          description: job.description,
          key: job.job_name,
          source: job.source,
        },
      };
      for (const field of job.published_settings) {
        metaData.publishedSettings[field.key] = {
          value: field.default || null,
          label: field.label,
          type: field.type,
          unit: field.unit || null,
          display: field.display,
          description: field.description,
          editable: field.editable || true,
        };
      }
      jobsFromApi[job.job_name] = metaData;
    }
    setJobs(jobsFromApi);
  }, [contribJobsList]);


  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  function setPioreactorJobState(job, state) {
    return function sendMessage() {
      try{
        setPioreactorJobAttr(job.metadata.key, "$state", state)
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
        setSnackbarMessage(`${verbs[state]} ${job.metadata.display_name.toLowerCase()} on all active & assigned Pioreactors`)
        setSnackbarOpen(true)
      }
    };
  }



  function setPioreactorJobAttr(job, setting, value) {
    fetch(`/api/workers/${unit}/jobs/update/job_name/${job}/experiments/${experiment}`, {
      method: "PATCH",
      body: JSON.stringify({settings: {[setting]: value}}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
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

  const handleRunPioreactorJobResponse = (name) => {
    setSnackbarMessage(`Starting ${name} on all active & assigned Pioreactors`)
    setSnackbarOpen(true)
    return;
  };

  function createUserButtonsBasedOnState(job){


    if (job.metadata.key === "temperature_automation"){
      var startAction = () => setOpenChangeTemperatureDialog(true)
    }
    else if (job.metadata.key === "dosing_automation"){
      startAction = () => setOpenChangeDosingDialog(true)
    }
    else if (job.metadata.key === "led_automation"){
      startAction = () => setOpenChangeLEDDialog(true)
    }
    else {
      startAction = () => {
        runPioreactorJob(unit, experiment, job.metadata.key, [], {})
        handleRunPioreactorJobResponse(job.metadata.display_name.toLowerCase())
      }
    }


    return (<div key={job.metadata.key}>
        <Button
          sx={{pr: 2, pl: 2}}
          disableElevation
          color="primary"
          onClick={startAction}
        >
          Start
        </Button>
        <Button
          sx={{pr: 2, pl: 2}}
          disableElevation
          color="primary"
          onClick={setPioreactorJobState(job, "sleeping")}
        >
          Pause
        </Button>
        <Button
          sx={{pr: 2, pl: 2}}
          disableElevation
          color="primary"
          onClick={setPioreactorJobState(job, "ready")}
        >
          Resume
        </Button>
        <Button
          sx={{pr: 2, pl: 2}}
          disableElevation
          color="secondary"
          onClick={setPioreactorJobState(job, "disconnected")}
        >
          Stop
        </Button>
      </div>
  )}


  // Define a function to determine which component to render based on the type of setting
  function renderSettingComponent(setting, job_key, setting_key, state) {
    const commonProps = {
      onUpdate: setPioreactorJobAttr,
      setSnackbarMessage: setSnackbarMessage,
      setSnackbarOpen: setSnackbarOpen,
      value: setting.value,
      units: setting.unit,
      job: job_key,
      setting: setting_key,
      disabled: state === "disconnected",
    };

    switch (setting.type) {
      case "boolean":
        return <SettingSwitchField {...commonProps} />;
      case "numeric":
        return <SettingNumericField {...commonProps} />;
      default:
        return <SettingTextField {...commonProps} />;
    }
  }


  const buttons = Object.fromEntries(Object.entries(jobs || {}).map( ([job_key, job], i) => [job_key, createUserButtonsBasedOnState(job)]))
  const isLargeScreen = useMediaQuery(theme => theme.breakpoints.down('xl'));
  var dosingControlJob = jobs.dosing_automation
  var ledControlJob = jobs.led_automation
  var temperatureControlJob = jobs.temperature_automation

  return (
    <React.Fragment>
    <Button style={{textTransform: 'none', float: "right" }} onClick={handleClickOpen} color="primary">
      <SettingsIcon fontSize="small" sx={textIcon}/> Control all Pioreactors
    </Button>
    <Dialog  maxWidth={isLargeScreen ? "sm" : "md"} fullWidth={true}  open={open} onClose={handleClose} aria-labelledby="form-dialog-title"  PaperProps={{
      sx: {
        height: "calc(100% - 64px)"
      }
    }}>
      <DialogTitle style={{backgroundImage: "linear-gradient(to bottom left, rgba(83, 49, 202, 0.4), rgba(0,0,0,0))"}}>
        <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}}>
          <PioreactorsIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/> <b>All assigned & active Pioreactors</b>
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
        <Tab sx={{textTransform: 'none'}} label="Activities"/>
        <Tab sx={{textTransform: 'none'}} label="Settings"/>
        <Tab sx={{textTransform: 'none'}} label="Dosing"/>
        <Tab sx={{textTransform: 'none'}} label="LEDs"/>
      </Tabs>
      </DialogTitle>
      <DialogContent>

        <TabPanel value={tabValue} index={0}>
          {Object.entries(jobs)
            .filter(([job_key, job]) => job.metadata.display)
            .filter(([job_key, job]) => !['dosing_automation', 'led_automation', 'temperature_automation'].includes(job_key))
            .map(([job_key, job]) =>
            <div key={job_key}>
              <Typography gutterBottom>
                {job.metadata.display_name}
              </Typography>
              <Typography variant="body2" component="p" gutterBottom>
                <span dangerouslySetInnerHTML={{__html: job.metadata.description}}/>
              </Typography>

              {buttons[job_key]}

              <ControlDivider/>
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
                <span dangerouslySetInnerHTML={{__html: temperatureControlJob.metadata.description}}/>
              </Typography>

              {buttons['temperature_automation']}
            </div>

            <ChangeAutomationsDialog
              open={openChangeTemperatureDialog}
              onFinished={() => setOpenChangeTemperatureDialog(false)}
              unit={unit}
              experiment={experiment}
              automationType="temperature"
              no_skip_first_run={true}
            />
          </React.Fragment>
          }

          <ControlDivider/>



          {dosingControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                Dosing automation
              </Typography>
            </div>
            <div>
              <Typography variant="body2" component="p" gutterBottom>
                <span dangerouslySetInnerHTML={{__html: dosingControlJob.metadata.description}}/>
              </Typography>

              {buttons['dosing_automation']}
            </div>

            <ChangeDosingAutomationsDialog
              automationType="dosing"
              open={openChangeDosingDialog}
              onFinished={() => setOpenChangeDosingDialog(false)}
              unit={unit}
              experiment={experiment}
              no_skip_first_run={false}
              maxVolume={config?.bioreactor?.max_working_volume_ml || 19}
              liquidVolume={config?.bioreactor?.initial_volume_ml || 10}
              threshold={39}
            />
          </React.Fragment>
          }

          <ControlDivider/>


          {ledControlJob &&
          <React.Fragment>
            <div style={{justifyContent: "space-between", display: "flex"}}>
              <Typography display="block">
                LED automation
              </Typography>
            </div>
            <div>
              <Typography variant="body2" component="p" gutterBottom>
                <span dangerouslySetInnerHTML={{__html: ledControlJob.metadata.description}}/>
              </Typography>

              {buttons['led_automation']}
            </div>

            <ChangeAutomationsDialog
              automationType="led"
              open={openChangeLEDDialog}
              onFinished={() => setOpenChangeLEDDialog(false)}
              unit={unit}
              experiment={experiment}
              no_skip_first_run={false}
            />
          </React.Fragment>
          }

          <ControlDivider/>

        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {Object.values(jobs)
            .filter(job => job.metadata.display)
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings], index) => (
              Object.entries(settings)
                .filter(([setting_key, setting],_) => setting.display && setting.editable)
                .map(([setting_key, setting],_) =>
              <React.Fragment key={job_key + setting_key}>
                <Typography  gutterBottom>
                  {setting.label}
                </Typography>
                <Typography variant="body2" component="p">
                  {setting.description}
                </Typography>
                {renderSettingComponent(setting, job_key, setting_key, state)}

                <ControlDivider/>
              </React.Fragment>

          )))}

        </TabPanel>
        <TabPanel value={tabValue} index={2}>
          <Typography  gutterBottom>
            Cycle Media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle media in and out of your Pioreactor for a set duration (seconds) by running the media pump periodically and waste pump continuously.
          </Typography>

          <ActionCirculatingForm action="circulate_media" unit={unit} experiment={experiment} />

          <ControlDivider/>

          <Typography  gutterBottom>
            Cycle alternative media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle alternative media in and out of your Pioreactor for a set duration (seconds)  by running the alt-media pump periodically and waste pump continuously.
          </Typography>

          <ActionCirculatingForm action="circulate_alt_media" unit={unit} experiment={experiment} />

          <ControlDivider/>

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
          <ActionDosingForm experiment={experiment} action="add_media" unit={unit} />
          <ControlDivider/>
          <Typography  gutterBottom>
            Remove waste
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the waste pumps for a set duration (seconds), moving a set volume (mL), or continuously add until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to remove media:
          </Typography>
          <ActionDosingForm  experiment={experiment} action="remove_waste" unit={unit} />
          <ControlDivider/>
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
          <ActionDosingForm  experiment={experiment} action="add_alt_media" unit={unit} />
          <ControlDivider/>
          <Typography gutterBottom>
            Manual adjustments
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Record adjustments before manually adding or removing from the vial. This is recorded in the database and will ensure accurate metrics. Dosing automation must be on.
          </Typography>
          <ActionManualDosingForm experiment={experiment}  unit={unit}/>

        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Typography style={{textTransform: "capitalize"}}>
            Channel A
          </Typography>
          <ActionLEDForm experiment={experiment} channel="A" unit={unit} />
          <ControlDivider/>

          <Typography style={{textTransform: "capitalize"}}>
            Channel B
          </Typography>
          <ActionLEDForm experiment={experiment} channel="B" unit={unit} />
          <ControlDivider/>

          <Typography style={{textTransform: "capitalize"}}>
            Channel C
          </Typography>
          <ActionLEDForm experiment={experiment} channel="C" unit={unit} />

          <ControlDivider/>
          <Typography style={{textTransform: "capitalize"}}>
            Channel D
          </Typography>
          <ActionLEDForm experiment={experiment} channel="D" unit={unit} />

          <ControlDivider/>
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


function SettingTextField({ value: initialValue, onUpdate, setSnackbarMessage, setSnackbarOpen, units, disabled, job, setting, id }){
  const [value, setValue] = useState(initialValue || "");
  const [activeSubmit, setActiveSumbit] = useState(false);

  useEffect(() => {
    if (initialValue !== value) {
      setValue(initialValue || "");
    }
  }, [initialValue]);


  const onChange = (e) => {
    setActiveSumbit(true);
    setValue(e.target.value);
  };

  const onKeyPress = (e) => {
    if (e.key === "Enter" && e.target.value) {
      onSubmit();
    }
  };

  const onSubmit = () => {
    onUpdate(job, setting, value);
    if (value !== "") {
      setSnackbarMessage(`Updating to ${value}${!units ? "" : ` ${units}`}.`);
    } else {
      setSnackbarMessage("Updating.");
    }
    setSnackbarOpen(true);
    setActiveSumbit(false);
  };

    return (
     <div style={{display: "flex"}}>
        <TextField
          id={id}
          size="small"
          autoComplete="off"
          disabled={disabled}
          value={value}
          InputProps={{
            endAdornment: <InputAdornment position="end">{units}</InputAdornment>,
            autoComplete: 'new-password',
          }}
          variant="outlined"
          onChange={onChange}
          onKeyPress={onKeyPress}
          sx={{mt: 2, maxWidth: "180px"}}
        />
        <Button
          size="small"
          color="primary"
          disabled={!activeSubmit}
          onClick={onSubmit}
          style={{textTransform: 'none', marginTop: "15px", marginLeft: "7px", display: (disabled ? "none" : undefined)}}
        >
          Update
        </Button>
     </div>
    )
}


function SettingSwitchField({ value: initialValue, onUpdate, setSnackbarMessage, setSnackbarOpen, job, setting, disabled, id }){
  const [value, setValue] = useState(initialValue || false);

  useEffect(() => {
    if (initialValue !== value) {
      setValue(initialValue || false);
    }
  }, [initialValue]);

  const onChange = (e) => {
    const checked = e.target.checked;
    setValue(checked);
    onUpdate(job, setting, checked ? 1 : 0);
    setSnackbarMessage(`Updating to ${checked ? "on" : "off"}.`);
    setSnackbarOpen(true);
  };

  return (
    <Switch
      checked={value}
      disabled={disabled}
      onChange={onChange}
      id={id}
    />
  );
}


function SettingNumericField({ value: initialValue, units, onUpdate, setSnackbarMessage, setSnackbarOpen, job, setting, disabled, id }){
  const [value, setValue] = useState(initialValue || "");
  const [error, setError] = useState(false);
  const [activeSubmit, setActiveSubmit] = useState(false);

  useEffect(() => {
    if (initialValue !== value) {
      setValue(initialValue || "");
    }
  }, [initialValue]);

  const validateNumericInput = (input) => {
    const numericPattern = /^-?\d*\.?\d*$/; // Allows negative and decimal numbers
    return numericPattern.test(input);
  };

  const onChange = (e) => {
    const input = e.target.value;
    const isValid = validateNumericInput(input);
    setError(!isValid);
    setActiveSubmit(isValid);
    setValue(input);
  };

  const onKeyPress = (e) => {
    if (e.key === "Enter" && e.target.value && !error) {
      onSubmit();
    }
  };

  const onSubmit = () => {
    if (!error) {
      onUpdate(job, setting, value);
      const message = value !== "" ? `Updating to ${value}${units ? ` ${units}` : ""}.` : "Updating.";
      setSnackbarMessage(message);
      setSnackbarOpen(true);
      setActiveSubmit(false);
    }
  };

  return (
    <div style={{ display: "flex" }}>
      <TextField
        id={id}
        type="number"
        size="small"
        autoComplete="off"
        disabled={disabled}
        value={value}
        error={error}
        InputProps={{
          endAdornment: <InputAdornment position="end">{units}</InputAdornment>,
          autoComplete: 'new-password',
        }}
        variant="outlined"
        onChange={onChange}
        onKeyPress={onKeyPress}
        sx={{mt: 2, maxWidth: "140px"}}
      />
      <Button
        size="small"
        color="primary"
        disabled={!activeSubmit || error}
        onClick={onSubmit}
        style={{ textTransform: 'none', marginTop: "15px", marginLeft: "7px", display: (disabled ? "none" : undefined) }}
      >
        Update
      </Button>
    </div>
  );
}



function ActiveUnits({experiment, config, units, availableModels}){
  const [relabelMap, setRelabelMap] = useState({})

  useEffect(() => {
    if (experiment){
      getRelabelMap(setRelabelMap, experiment)
    }
  }, [experiment])

  const renderCards = () => (units || []).map(unit =>{
    const modelDetails = availableModels.find(
      ({model_name, model_version}) => model_name === unit.model_name && unit.model_version === model_version
    );
    return <PioreactorCard key={unit.pioreactor_unit} isUnitActive={true} unit={unit.pioreactor_unit} modelDetails={modelDetails || {}} config={config} experiment={experiment} originalLabel={relabelMap[unit.pioreactor_unit]}/>
  })

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
      {renderCards()}

    </React.Fragment>
)}


function FlashLEDButton({ unit, disabled }){
  const [flashing, setFlashing] = useState(false)

  const onClick = () => {
    setFlashing(true)
    fetch(`/api/workers/${unit}/blink`, {method: "POST"})
  }
  return (
    <Button style={{textTransform: 'none', float: "right"}} className={flashing ? 'blinkled' : ''} disabled={disabled} onClick={onClick} color="primary">
      <FlareIcon color={disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon}/> <span> Identify </span>
    </Button>
)}


function PioreactorCard({unit, isUnitActive, experiment, config, originalLabel, modelDetails = {}}){
  const [jobFetchComplete, setJobFetchComplete] = useState(false)
  const [label, setLabel] = useState("")
  const {client, subscribeToTopic } = useMQTT();
  const contribJobsList = useContribJobsList();

  const [jobs, setJobs] = useState({
    monitor: {
      state : null,
      metadata: {display: false},
      publishedSettings: {
        versions: {
            value: null, label: null, type: "json", unit: null, display: false, description: null, editable: false,
        },
        voltage_on_pwm_rail: {
            value: null, label: null, type: "json", unit: null, display: false, description: null, editable: false,
        },
        ipv4: {
            value: null, label: null, type: "string", unit: null, display: false, description: null, editable: false,
        },
        wlan_mac_address: {
            value: null, label: null, type: "string", unit: null, display: false, description: null, editable: false,
        },
        eth_mac_address: {
            value: null, label: null, type: "string", unit: null, display: false, description: null, editable: false,
        },
      },
    },
  })

  useEffect(() => {
    setLabel(originalLabel)
  }, [originalLabel])


  useEffect(() => {
    if (!Array.isArray(contribJobsList)) {
      return;
    }
    const jobsFromApi = {};
    for (const job of contribJobsList) {
      const metaData = {
        state: "disconnected",
        publishedSettings: {},
        metadata: {
          display_name: job.display_name,
          subtext: job.subtext,
          display: job.display,
          description: job.description,
          key: job.job_name,
          source: job.source,
        },
      };
      for (const field of job.published_settings) {
        metaData.publishedSettings[field.key] = {
          value: field.default || null,
          label: field.label,
          type: field.type,
          unit: field.unit || null,
          display: field.display,
          description: field.description,
          editable: field.editable || true,
        };
      }
      jobsFromApi[job.job_name] = metaData;
    }
    setJobs((prev) => ({ ...prev, ...jobsFromApi }));
    setJobFetchComplete(true);
  }, [contribJobsList])

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

    if (!client){
      return
    }

    subscribeToTopic(`pioreactor/${unit}/$experiment/monitor/$state`, onMessage, "PioreactorCard");
    for (const job of Object.keys(jobs)) {

      subscribeToTopic(`pioreactor/${unit}/${experiment}/${job}/$state`, onMessage, "PioreactorCard");
      for (const setting of Object.keys(jobs[job].publishedSettings)){
          var topic = [
            "pioreactor",
            unit,
            (job === "monitor" ? "$experiment" : experiment),
            job,
            setting
          ].join("/")
          subscribeToTopic(topic, onMessage, "PioreactorCard");
      }
    }

  },[experiment, jobFetchComplete, isUnitActive, client])

  const onMessage = (topic, message, packet) => {
    if (!message || !topic) return;

    var [job, setting] = topic.toString().split('/').slice(-2)
    if (setting === "$state"){
      var payload = message.toString()
      setJobs((prev) => ({...prev, [job]: {...prev[job], state: payload}}))
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
      return "Online"
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

  const indicatorDotColor = getIndicatorDotColor(jobs.monitor.state)
  const indicatorDotShadow = 2
  const indicatorLabel = getInicatorLabel(jobs.monitor.state, isUnitActive)

  return (
    <Card sx={{mt: 0, mb: 3}} id={unit} aria-disabled={!isUnitActive}>
      <CardContent sx={{p: "10px 20px 20px 20px"}}>
        <Box className={"fixme"}>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(label) ? unit : ""}
          </Typography>
          <Box sx={(theme) => ({
            display: "flex",
            justifyContent: "space-between",
            [theme.breakpoints.down('md')]:{
              flexFlow: "nowrap",
              flexDirection: "column",
            }
          })}>
            <div style={{display: "flex", justifyContent: "left", marginTop: "3px"}}>
              <Tooltip title={indicatorLabel} placement="left">
                <div className="indicator-dot-beside-button" style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
              </Tooltip>
              <PioreactorIconWithModel badgeContent={modelDetails.reactor_capacity_ml} />
              <Typography sx={{
                  fontSize: 20,
                  color: "rgba(0, 0, 0, 0.87)",
                  fontWeight: 500,
                  ...(isUnitActive ? {} : { color: disabledColor }),
                }}
                gutterBottom>
                {(label ) ? label : unit }
              </Typography>
              <Button disabled={!isUnitActive} component={Link} to={`/pioreactors/${unit}`} sx={{padding: "0px 8px", marginBottom: "7px", ml: 1, textTransform: "none", ...(isUnitActive ? {} : { color: disabledColor }),}}>
                View details <ArrowForwardIcon sx={{ verticalAlign: "middle", ml: 0.5 }} fontSize="small"/>
              </Button>
            </div>
            <Box sx={{
              display: "flex",
              justifyContent: "flex-end",
              flexDirection: "row",
              flexWrap: "wrap",
              }}
            >
              <div>
                <SelfTestDialog
                  client={client}
                  disabled={!isUnitActive}
                  experiment={experiment}
                  unit={unit}
                  label={label}
                  selfTestState={jobs['self_test'] ? jobs['self_test'].state : null}
                  selfTestTests={jobs['self_test'] ? jobs['self_test'] : null}
                />
              </div>
              <div>
                <FlashLEDButton disabled={!isUnitActive} unit={unit}/>
              </div>
              <div>
                <CalibrateDialog
                  client={client}
                  odBlankReading={jobs['od_blank'] ? jobs['od_blank'].publishedSettings.means.value : null}
                  odBlankJobState={jobs['od_blank'] ? jobs['od_blank'].state : null}
                  growthRateJobState={jobs['growth_rate_calculating'] ? jobs['growth_rate_calculating'].state : null}
                  experiment={experiment}
                  unit={unit}
                  label={label}
                  disabled={!isUnitActive}
                />
              </div>
              <SettingsActionsDialog
                client={client}
                unit={unit}
                label={label}
                disabled={!isUnitActive}
                experiment={experiment}
                jobs={jobs}
                setLabel={setLabel}
                modelDetails={modelDetails}
              />
            </Box>
          </Box>
        </Box>


      <Box sx={{
          display: "flex",
          m: "15px 20px 20px 0px",
          flexDirection: "row",
        }}>
        <Box sx={{width: "100px", mt: "10px", mr: "5px"}}>
          <Typography variant="body2" component={'span'}>
            <Box fontWeight="fontWeightBold" sx={{ color: !isUnitActive ? disabledColor : 'inherit' }}>
              Activities:
            </Box>
          </Typography>
        </Box>
        <RowOfUnitSettingDisplayBox>
          {Object.values(jobs)
              .filter(job => job.metadata.display)
              .map(job => (
            <Box sx={{width: "130px", mt: "10px", mr: "2px", p: "0px 3px"}} key={job.metadata.key}>
              <Typography variant="body2" style={{fontSize: "0.84rem"}} sx={{ color: !isUnitActive ? disabledColor : 'inherit' }}>
                {job.metadata.display_name}
              </Typography>
              <UnitSettingDisplay
                value={job.state}
                isUnitActive={isUnitActive}
                default="disconnected"
                subtext={job.metadata.subtext ? job.publishedSettings[job.metadata.subtext].value : null}
                isStateSetting
              />
            </Box>
         ))}

        </RowOfUnitSettingDisplayBox>
      </Box>

      <Divider/>

      <Box style={{
          display: "flex",
          m: "15px 20px 20px 0px",
          flexDirection: "row",
        }}>
        <Box sx={{width: "100px", mt: "10px", mr: "5px"}}>
          <Typography variant="body2" component={'span'}>
            <Box fontWeight="fontWeightBold" sx={{ color: !isUnitActive ? disabledColor : 'inherit' }}>
              Settings:
            </Box>
          </Typography>
        </Box>
        <RowOfUnitSettingDisplayBox>
          {Object.values(jobs)
            //.filter(job => (job.state !== "disconnected") || (job.metadata.key === "leds"))
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings], index) => (
              Object.entries(settings)
                .filter(([setting_key, setting], _) => setting.display)
                .map(([setting_key, setting], _) =>
                  <Box sx={{width: "130px", mt: "10px", mr: "2px", p: "0px 3px"}} key={job_key + setting_key}>
                    <Typography variant="body2" style={{fontSize: "0.84rem"}} sx={{ color: !isUnitActive ? disabledColor : 'inherit' }}>
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
                  </Box>
            )))}
        </RowOfUnitSettingDisplayBox>
      </Box>


      </CardContent>
    </Card>
)}


function InactiveUnits({ units, config, experiment, availableModels }){
  return (
  <React.Fragment>
    <div style={{display: "flex", justifyContent: "space-between", marginBottom: "10px", marginTop: "15px"}}>
      <Typography variant="h5" component="h2">
        <Box fontWeight="fontWeightRegular">
          Inactive Pioreactors
        </Box>
      </Typography>
    </div>
    {(units || []).map((unit) => {
      const modelDetails = (availableModels || []).find(
        ({ model_name, model_version }) => model_name === unit.model_name && model_version === unit.model_version
      );
      return (
        <PioreactorCard
          key={unit.pioreactor_name}
          isUnitActive={false}
          unit={unit.pioreactor_name}
          modelDetails={modelDetails || {}}
          config={config}
          experiment={experiment}
        />
      );
    })}
    </React.Fragment>
)}

function Pioreactors({title}) {
  const { experimentMetadata } = useExperiment();
  const [workers, setWorkers] = useState([]);
  const [config, setConfig] = useState({})
  const [isLoading, setIsLoading] = useState(true);
  const [availableModels, setAvailableModels] = useState([]);
  const [modelCheckKey, setModelCheckKey] = useState(0);

  useEffect(() => {
    document.title = title;
    getConfig(setConfig)
  }, [title]);

  useEffect(() => {
    if (experimentMetadata.experiment) {
      fetchWorkers();
    }
  }, [experimentMetadata.experiment]);

  useEffect(() => {
    fetch('/api/models')
      .then((r) => r.json())
      .then((data) => setAvailableModels(data.models))
  }, []);

  const workersMissingModel = workers.some(workerMissingModelDetails);

  useEffect(() => {
    if (workersMissingModel) {
      setModelCheckKey((key) => key + 1);
    }
  }, [workersMissingModel]);


  const fetchWorkers = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`/api/experiments/${experimentMetadata.experiment}/workers`);
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


  const renderCards = () => {
      const activeUnits = workers.filter(worker => worker.is_active === 1);
      const inactiveUnits = workers.filter(worker => worker.is_active === 0);
      return (
      <>
      <ActiveUnits experiment={experimentMetadata.experiment} config={config} availableModels={availableModels} units={activeUnits} />
      { (inactiveUnits.length > 0) &&
      <InactiveUnits experiment={experimentMetadata.experiment} config={config} availableModels={availableModels} units={inactiveUnits}/>
      }
      </>
    )
  }
  const renderEmptyState = () => (
    <Box sx={{textAlign: "center"}}>
      {isLoading ? <CircularProgress /> : (
      <>
      <img alt="filler image for no pioreactor assigned" src={cloudImage} style={{width: "500px", opacity: 0.9, filter: "grayscale(50%)", marginLeft: "30px"}}/>
      <Typography component='div' variant='h6' sx={{mb: 2}}>
        No Pioreactors assigned to this experiment
      </Typography>
      <AssignPioreactors experiment={experimentMetadata.experiment} variant="contained"/>
      <Typography component='div' variant='body2'>
        <p>Learn more about <a href="https://docs.pioreactor.com/user-guide/create-cluster" target="_blank" rel="noopener noreferrer">assigning inventory</a>.</p>
      </Typography>
      </>
      )}
    </Box>
  )

  return (
    <MQTTProvider name="pioreactor" config={config} experiment={experimentMetadata.experiment}>
      {modelCheckKey > 0 && <MissingWorkerModelModal triggerCheckKey={modelCheckKey} />}
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <PioreactorHeader experiment={experimentMetadata.experiment} config={config}/>

          {(workers.length === 0 ? renderEmptyState() : renderCards())}

        </Grid>
      </Grid>
    </MQTTProvider>
  );
}

export default Pioreactors;
