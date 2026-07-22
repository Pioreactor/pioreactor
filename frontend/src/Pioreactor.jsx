import React, {useState, useEffect, useMemo, useCallback} from "react";

import Grid from '@mui/material/Grid';
import { useMediaQuery } from "@mui/material";

import Chip from '@mui/material/Chip';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import {Typography} from '@mui/material';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import Snackbar from './components/Snackbar';
import Tooltip from '@mui/material/Tooltip';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Popover from '@mui/material/Popover';
import SvgIcon from '@mui/material/SvgIcon';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import ListSubheader from '@mui/material/ListSubheader';
import Button from "@mui/material/Button";
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import ErrorOutlineOutlinedIcon from '@mui/icons-material/ErrorOutlineOutlined';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FlareIcon from '@mui/icons-material/Flare';
import IndeterminateCheckBoxIcon from '@mui/icons-material/IndeterminateCheckBox';
import SettingsIcon from '@mui/icons-material/Settings';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import {Link, useParams} from 'react-router'

import ChangeAutomationsDialog from "./components/ChangeAutomationsDialog"
import ChangeDosingAutomationsDialog from "./components/ChangeDosingAutomationsDialog"
import AdvancedConfigButton from "./components/AdvancedConfigDialog"
import AutomationAdvancedConfigButton from "./components/AutomationAdvancedConfigDialog"
import ActionDosingForm from "./components/ActionDosingForm"
import ActionCirculatingForm from "./components/ActionCirculatingForm"
import ActionLEDForm from "./components/ActionLEDForm"
import PioreactorIcon from "./components/PioreactorIcon"
import PioreactorIconWithModel from "./components/PioreactorIconWithModel"
import RequirementsAlert from "./components/RequirementsAlert";
import BioreactorDiagram from "./components/BioreactorDiagram";
import Chart from "./components/Chart";
import LogTableByUnit from "./components/LogTableByUnit";
import CameraPanel from "./components/CameraPanel";
import { useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';
import PatientButton from './components/PatientButton';
import {
  buildBioreactorSettingsCollection,
  getBioreactorConfirmedValue,
  getBioreactorSubscriptionTopics,
  mergeSettingsCollections,
  parseNumericValue,
} from "./utils/bioreactor";
import { getRelabelMap } from "./utils/config";
import {
  buildJobsStateFromDescriptors,
  buildSettingsCollectionsFromDescriptors,
  createMonitorJobState,
  getPublishedSettingsSignature,
  getWorkerJobDescriptors,
  getWorkerSettingsDescriptors,
  runPioreactorJob,
  updatePublishedSettingValue,
} from "./utils/jobs";
import { experimentPathSegment } from "./utils/url";
import {
  colors,
  disconnectedGrey,
  lostRed,
  readyGreen,
  disabledColor,
} from "./utils/color";
import { TimeFormatSwitch, TimeWindowSwitch } from "./components/TimeControls";
import {
  canQuickEditCardSetting,
  createPrimaryStateActionForState,
  createStateActionsForState,
  getCardSettingDisplayKind,
  isAutomationJob,
  shouldClearPendingStateAction,
} from "./components/pioreactorCardQuickControls";
import {
  ControlDivider,
  ButtonStopProcess,
  CalibrateDialog,
  DescriptorStatusMessage,
  RowOfUnitSettingDisplayBox,
  SettingNumericField,
  SettingSwitchField,
  SettingTextField,
  StateTypography,
  TOPIC_SIGNATURE_SEPARATOR,
  TabPanel,
  UnitSettingDisplay,
  UnitSettingDisplaySubtext,
  getAvailableSelfTestGroupsFromSettings,
  getPioreactorCardBioreactorTopics,
  getPioreactorCardMonitorTopics,
  getPioreactorCardPublishedSettingsTopics,
  parsePayloadToType,
  textIcon,
  updateBioreactorSettingAndMirrorState,
} from "./components/PioreactorCardShared";

const DIAGRAM_BIOREACTOR_KEYS = ["current_volume_ml", "efflux_tube_volume_ml"];

function BioreactorDiagramPanel({
  unit,
  experiment,
  config,
  modelDetails,
  values,
  onValuesChange,
}) {
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const bioreactorValues = values || {};

  const hasDiagram = Boolean(
    modelDetails.model_name?.startsWith("pioreactor_20ml") || modelDetails.model_name?.startsWith("pioreactor_40ml")
  );

  const pushBioreactorValues = useCallback((nextValuesOrUpdater) => {
    onValuesChange?.(nextValuesOrUpdater);
  }, [onValuesChange]);

  const onBioreactorMessage = useCallback((topic, message) => {
    if (!topic || !message) {
      return;
    }

    const parts = topic.toString().split("/");
    const variableName = parts[4];
    const parsedValue = parseNumericValue(message.toString());
    if (!variableName || parsedValue === null) {
      return;
    }

    pushBioreactorValues((previous) => ({
      ...previous,
      [variableName]: parsedValue,
    }));
  }, [pushBioreactorValues]);

  useEffect(() => {
    if (!client || !unit || !experiment) {
      return undefined;
    }

    const topics = getBioreactorSubscriptionTopics(unit, experiment, DIAGRAM_BIOREACTOR_KEYS);

    subscribeToTopic(topics, onBioreactorMessage, "BioreactorDiagramPanel");

    return () => {
      unsubscribeFromTopic(topics, "BioreactorDiagramPanel");
    };
  }, [client, experiment, onBioreactorMessage, subscribeToTopic, unsubscribeFromTopic, unit]);

  return (
    hasDiagram ? (
      <BioreactorDiagram
        experiment={experiment}
        unit={unit}
        config={config}
        size={modelDetails.reactor_capacity_ml}
        liquidVolume={getBioreactorConfirmedValue(bioreactorValues, config, "current_volume_ml")}
        maxVolume={getBioreactorConfirmedValue(bioreactorValues, config, "efflux_tube_volume_ml")}
      />
    ) : (
      <Box sx={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center" }}>
        <Typography variant="body2" component="p" color="textSecondary">
          No diagram available for this model
        </Typography>
      </Box>
    )
  );
}

function ShieldCheckOutlineIcon(props) {
  return (
    <SvgIcon {...props} viewBox="0 0 24 24">
      <path d="M21,11C21,16.55 17.16,21.74 12,23C6.84,21.74 3,16.55 3,11V5L12,1L21,5V11M12,21C15.75,20 19,15.54 19,11.22V6.3L12,3.18L5,6.3V11.22C5,15.54 8.25,20 12,21M10,17L6,13L7.41,11.59L10,14.17L16.59,7.58L18,9" />
    </SvgIcon>
  );
}

function ShieldAlertOutlineIcon(props) {
  return (
    <SvgIcon {...props} viewBox="0 0 24 24">
      <path d="M21,11C21,16.55 17.16,21.74 12,23C6.84,21.74 3,16.55 3,11V5L12,1L21,5V11M12,21C15.75,20 19,15.54 19,11.22V6.3L12,3.18L5,6.3V11.22C5,15.54 8.25,20 12,21M11,7H13V13H11V7M11,15H13V17H11V15Z" />
    </SvgIcon>
  );
}



function PioreactorHeader({assignedExperiment, isActive, selectExperiment, modelDisplayName}) {
  const onExperimentClick = () => {
    selectExperiment(assignedExperiment);
  }

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h1">
          <Box sx={{display:"inline"}}>
            <Button component={Link} to="/pioreactors" startIcon={<ArrowBackIcon />} sx={{ textTransform: 'none' }}>
              All assigned Pioreactors
            </Button>
          </Box>
        </Typography>
        <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
          {/* <ButtonStopProcess experiment={assignedExperiment} unit={unit}/> */}
          {/* <Divider orientation="vertical" flexItem variant="middle"/> */}
          {/* <ControlPioreactorMenu experiment={experiment} unit={unit}/> */}
        </Box>
      </Box>
     <Divider />

        <Box sx={{m: "10px 2px 0px 2px", display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
          <Typography variant="subtitle2" sx={{flexGrow: 1}}>
            <Box sx={{display:"inline"}}>
              <Box sx={{ fontWeight: "fontWeightBold", display:"inline-block" }}>
                <PlayCircleOutlinedIcon sx={{ fontSize: 14, verticalAlign: "-2px" }}/> Experiment assigned:&nbsp;
              </Box>
                <Box sx={{ fontWeight: "fontWeightRegular", mr: "1%", display:"inline-block" }}>
                <Chip icon={<PlayCircleOutlinedIcon/>} size="small" sx={{ mb: "2px" }} label={assignedExperiment} clickable component={Link} onClick={onExperimentClick} data-experiment-name={assignedExperiment} />
              </Box>
            </Box>
            <Box sx={{display:"inline"}}>
              <Box sx={{ fontWeight: "fontWeightBold", display:"inline-block" }}>
                {isActive
                  ? <ShieldCheckOutlineIcon sx={{ fontSize: 14, verticalAlign: "-2px" }}/>
                  : <ShieldAlertOutlineIcon sx={{ fontSize: 14, verticalAlign: "-2px" }}/>
                } Availability:&nbsp;
              </Box>
              <Box sx={{ fontWeight: "fontWeightRegular", mr: "1%", display:"inline-block" }}>
                {isActive ? "Active" : "Inactive"}
              </Box>
            </Box>
            <Box sx={{display:"inline"}}>
              <Box sx={{ fontWeight: "fontWeightBold", display:"inline-block" }}>
                <PioreactorIcon sx={{ fontSize: 14, verticalAlign: "-2px" }}/> Model:&nbsp;
              </Box>
              <Box sx={{ fontWeight: "fontWeightRegular", mr: "1%", display:"inline-block" }}>
                {modelDisplayName}
              </Box>
            </Box>

          </Typography>
        </Box>


    </Box>
  )
}



function SettingsActionsDialog(props) {
  const [open, setOpen] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [tabValue, setTabValue] = useState(0);
  const [openChangeDosingDialog, setOpenChangeDosingDialog] = useState(false);
  const [openChangeLEDDialog, setOpenChangeLEDDialog] = useState(false);
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = useState(false);
  const [selfTestResult, setSelfTestResult] = useState(null);
  const [selfTestStartPending, setSelfTestStartPending] = useState(false);
  const {client, subscribeToTopic, unsubscribeFromTopic} = useMQTT();
  const selfTestExperiment = "$experiment";
  const selfTestSettings = props.jobs?.self_test?.publishedSettings || null;
  const selfTestSettingTypes = useMemo(() => {
    if (!selfTestSettings) {
      return {};
    }
    return Object.entries(selfTestSettings).reduce((acc, [key, setting]) => {
      acc[key] = setting.type;
      return acc;
    }, {});
  }, [selfTestSettings]);
  const availableSelfTestGroups = useMemo(
    () => getAvailableSelfTestGroupsFromSettings(selfTestSettings),
    [selfTestSettings]
  );
  const editableSettingsGroups = useMemo(() => {
    return Object.values(props.settingsCollections || {}).filter(job => job.metadata.display)
  }, [props.settingsCollections])
  const buildSelfTestBaseline = useCallback(() => {
    const publishedSettings = {};
    if (!selfTestSettings) {
      return { state: null, publishedSettings };
    }
    for (const [key, setting] of Object.entries(selfTestSettings)) {
      publishedSettings[key] = {
        value: setting.value ?? null,
        type: setting.type,
        label: setting.label,
      };
    }
    return { state: null, publishedSettings };
  }, [selfTestSettings]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };


  function setPioreactorJobState(job, state) {
    return function() {
      setPioreactorJobAttr(job, "$state", state)
    };
  }


  function stopPioreactorJob(job){
    return setPioreactorJobState(job, "disconnected")
  }

  function setPioreactorJobAttr(job, setting, value) {
    if (job === "bioreactor") {
      // Mirror the confirmed save locally so the Settings dialog updates immediately.
      // The retained MQTT echo will still arrive, but it can lag the HTTP response.
      return updateBioreactorSettingAndMirrorState(
        props.unit,
        props.experiment,
        setting,
        value,
        props.setBioreactorValues,
      )
    }

    return fetch(`/api/workers/${props.unit}/jobs/update/job_name/${job}/experiments/${experimentPathSegment(props.experiment)}`, {
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
      fetch(`/api/experiments/${experimentPathSegment(props.experiment)}/unit_labels`,{
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

  useEffect(() => {
    if (!selfTestSettings) {
      return;
    }
    setSelfTestResult(buildSelfTestBaseline());
  }, [buildSelfTestBaseline, selfTestSettings]);

  const onSelfTestData = useCallback((topic, message) => {
    if (!topic || !message) {
      return;
    }
    const parts = topic.toString().split('/');
    if (parts.length < 5) {
      return;
    }
    const job = parts[3];
    const setting = parts[4];
    if (job !== "self_test") {
      return;
    }
    if (setting === "$state") {
      setSelfTestResult((prev) => {
        const current = prev || buildSelfTestBaseline();
        return { ...current, state: message.toString() };
      });
      return;
    }
    const payload = parsePayloadToType(message.toString(), selfTestSettingTypes[setting]);
    setSelfTestResult((prev) => {
      const current = prev || buildSelfTestBaseline();
      const previousSetting = current.publishedSettings[setting] || {
        type: selfTestSettingTypes[setting],
      };
      return {
        ...current,
        publishedSettings: {
          ...current.publishedSettings,
          [setting]: {
            ...previousSetting,
            value: payload,
          },
        },
      };
    });
  }, [buildSelfTestBaseline, selfTestSettingTypes]);

  useEffect(() => {
    if (!open || !client || !selfTestSettings) {
      return;
    }
    const baseTopic = `pioreactor/${props.unit}/${selfTestExperiment}/self_test`;
    const topics = [
      `${baseTopic}/$state`,
      ...Object.keys(selfTestSettings).map((key) => `${baseTopic}/${key}`),
    ];
    subscribeToTopic(topics, onSelfTestData, "ControlSelfTest");
    return () => {
      unsubscribeFromTopic(topics, "ControlSelfTest");
    };
  }, [client, onSelfTestData, open, props.unit, selfTestExperiment, selfTestSettings, subscribeToTopic, unsubscribeFromTopic]);

  function createUserButtonsBasedOnState(jobState, job){
    switch (jobState){
      case "lost":
        return (<div key={"patient_buttons_lost" + job}>
                  <PatientButton
                    color="primary"
                    variant="contained"
                    onClick={() => runPioreactorJob(props.unit, props.experiment, job)}
                    buttonText="Start"
                  />
        </div>)
      case "disconnected":
       return (<div key={"patient_buttons_disconnected" + job}>
                 <PatientButton
                  color="primary"
                  variant="contained"
                  onClick={() => runPioreactorJob(props.unit, props.experiment, job)}
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
              variant="contained"
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
    const componentKey = `${job_key}-${setting_key}`;
    const commonProps = {
      onUpdate: setPioreactorJobAttr,
      setSnackbarMessage: setSnackbarMessage,
      setSnackbarOpen: setSnackbarOpen,
      value: setting.value,
      units: setting.unit,
      min: setting.min,
      max: setting.max,
      job: job_key,
      setting: setting_key,
      disabled: state === "disconnected",
    };

    switch (setting.type) {
      case "boolean":
        return <SettingSwitchField key={componentKey} {...commonProps} />;
      case "numeric":
        return <SettingNumericField key={componentKey} {...commonProps} />;
      default:
        return <SettingTextField key={componentKey} {...commonProps} />;
    }
  }


  const LEDMap = props.config['leds'] || {}
  const buttons = Object.fromEntries(Object.entries(props.jobs).map(([job_key, job]) => [job_key, createUserButtonsBasedOnState(job.state, job_key)]))
  const isXrModel = Boolean(props.modelDetails?.model_name?.toLowerCase().includes("xr"));

  const isLargeScreen = useMediaQuery(theme => theme.breakpoints.down('xl'));
  const dosingControlJob = props.jobs.dosing_automation
  const ledControlJob = props.jobs.led_automation
  const temperatureControlJob = props.jobs.temperature_automation
  const dosingMaxVolume = getBioreactorConfirmedValue(
    props.bioreactorValues,
    props.config,
    "efflux_tube_volume_ml",
  );
  const dosingLiquidVolume = getBioreactorConfirmedValue(
    props.bioreactorValues,
    props.config,
    "current_volume_ml",
  );
  const isSelfTestRunningState = (state) =>
    ["init", "ready", "sleeping"].includes(state);

  const renderSelfTestIcon = (settingKey) => {
    const settingValue = selfTestResult?.publishedSettings?.[settingKey]?.value;
    if (settingValue === true) {
      return <CheckIcon sx={{color: readyGreen}} />;
    }
    if (settingValue === false) {
      return <ErrorOutlineOutlinedIcon sx={{color: lostRed}} />;
    }
    if (isSelfTestRunningState(selfTestResult?.state)) {
      return <CircularProgress size={18} />;
    }
    return <IndeterminateCheckBoxIcon sx={{color: disabledColor}} />;
  };

  const renderSelfTestSummaryIcon = () => {
    const overallStatus = selfTestResult?.publishedSettings?.all_tests_passed?.value;
    if (overallStatus === true) {
      return <CheckIcon sx={{color: readyGreen}} />;
    }
    if (overallStatus === false) {
      return <ErrorOutlineOutlinedIcon sx={{color: lostRed}} />;
    }
    if (isSelfTestRunningState(selfTestResult?.state)) {
      return <CircularProgress size={18} />;
    }
    return <IndeterminateCheckBoxIcon sx={{color: disabledColor}} />;
  };

  const renderSelfTestSecondary = (test) => {
    if (test.secondaryKey !== "correlations_between_pds_and_leds") {
      return test.description || null;
    }
    const rawValue = selfTestResult?.publishedSettings?.correlations_between_pds_and_leds?.value;
    if (!rawValue) {
      return null;
    }
    try {
      const parsed = typeof rawValue === "string" ? JSON.parse(rawValue) : rawValue;
      if (Array.isArray(parsed)) {
        return parsed.map((ledPd) => `${ledPd[0]} ⇝ ${ledPd[1]}`).join(",  ");
      }
    } catch (error) {
      return null;
    }
    return null;
  };

  const isSelfTestRunning = isSelfTestRunningState(selfTestResult?.state);

  const handleRunSelfTest = () => {
    setSelfTestStartPending(true);
    runPioreactorJob(props.unit, selfTestExperiment, "self_test")
      .then(() => {
        setSnackbarMessage(`Starting self test on ${props.unit}`);
        setSnackbarOpen(true);
      })
      .catch(() => {
        setSnackbarMessage(`Failed to start self test on ${props.unit}`);
        setSnackbarOpen(true);
      })
      .finally(() => {
        setSelfTestStartPending(false);
      });
  };

  return (
    <div>
    <Button sx={{textTransform: 'none', float: "right" }} disabled={props.disabled} onClick={handleClickOpen} color="primary">
      <SettingsIcon color={props.disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon}/> Control
    </Button>
    <Dialog maxWidth={isLargeScreen ? "sm" : "md"} fullWidth={true} open={open} onClose={handleClose} slotProps={{
      paper: {
        sx: {
          height: "calc(100% - 64px)"
        }
      }
    }}>
      <DialogTitle>
        <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}}>
          <PioreactorIcon sx={{verticalAlign: "middle", fontSize: "1.2em"}}/>
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
        <Tab sx={{textTransform: 'none'}} label="Activities"/>
        <Tab sx={{textTransform: 'none'}} label="Settings"/>
        <Tab sx={{textTransform: 'none'}} label="Dosing"/>
        <Tab sx={{textTransform: 'none'}} label="LEDs"/>
        <Tab sx={{textTransform: 'none'}} label="Self-test"/>
      </Tabs>
      </DialogTitle>
      <DialogContent>
        <TabPanel value={tabValue} index={0}>
          {/* Unit Specific Activites */}
          {Object.entries(props.jobs)
            .filter(([_, job]) => job.metadata.display)
            .filter(([job_key]) => !['dosing_automation', 'led_automation', 'temperature_automation'].includes(job_key)) //these are added later
            .map(([job_key, job]) =>
            <div key={job_key}>
              <Box sx={{justifyContent: "space-between", display: "flex"}}>
                <Typography sx={{ display: "block" }}>
                  {job.metadata.display_name}
                  {(job.metadata.display_name === "Optical density" && isXrModel) ? (
                    <Chip
                      component="span"
                      size="small"
                      variant="outlined"
                      label="XR"
                      sx={{ ml: 0.5, height: 18, fontSize: "0.65rem", "& .MuiChip-label": { px: "5px", pt: "1px" } }}
                    />
                  ) : null}
                </Typography>
                <StateTypography state={job.state}/>
              </Box>
              <Typography variant="caption" gutterBottom color="textSecondary" sx={{ display: "block" }}>
                {job.metadata.source !== "app" ? `Installed by ${job.metadata.source || "unknown"}` : ""}
              </Typography>
              <Typography variant="body2" component="p" gutterBottom>
                <div dangerouslySetInnerHTML={{__html: job.metadata.description}}/>
              </Typography>

              <Box sx={{justifyContent:"space-between", display:"flex"}}>
                {buttons[job_key]}

                <AdvancedConfigButton jobName={job_key} displayName={job.metadata.display_name} unit={props.unit} experiment={props.experiment} config={props.config[`${job_key}.config`]} disabled={job.state !== "disconnected"} />
              </Box>
              <ControlDivider/>
            </div>
          )}


          {/* Unit Specific Automations */}
          {temperatureControlJob &&
          <React.Fragment>
            <Box sx={{justifyContent: "space-between", display: "flex"}}>
              <Typography sx={{ display: "block" }}>
                Temperature automation
              </Typography>
              <StateTypography state={temperatureControlJob.state}/>
            </Box>

            <div key={temperatureControlJob.metadata.key}>
              {(temperatureControlJob.state === "ready") || (temperatureControlJob.state === "sleeping") || (temperatureControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="p" gutterBottom>
                Currently running temperature automation <Chip size="small" label={temperatureControlJob.publishedSettings.automation_name.value} />.
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
                  unit={props.unit}
                  experiment={props.experiment}
                  label={props.label}
                  configSections={props.config || {}}
                />

               </React.Fragment>
              }
            </div>

            <ChangeAutomationsDialog
              open={openChangeTemperatureDialog}
              onFinished={() => setOpenChangeTemperatureDialog(false)}
              unit={props.unit}
              label={props.label}
              experiment={props.experiment}
              automationType="temperature"
            />
          </React.Fragment>
          }

          <ControlDivider/>

          {dosingControlJob &&
          <React.Fragment>
            <Box sx={{justifyContent: "space-between", display: "flex"}}>
              <Typography sx={{ display: "block" }}>
                Dosing automation
              </Typography>
              <StateTypography state={dosingControlJob.state}/>
            </Box>
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
                  unit={props.unit}
                  experiment={props.experiment}
                  label={props.label}
                  configSections={props.config || {}}
                  maxVolume={dosingMaxVolume}
                  liquidVolume={dosingLiquidVolume}
                  capacity={props.modelDetails.reactor_capacity_ml}
                  threshold={props.modelDetails.reactor_max_fill_volume_ml}
                />
               </React.Fragment>
              }
            </div>


            <ChangeDosingAutomationsDialog
              automationType="dosing"
              open={openChangeDosingDialog}
              onFinished={() => setOpenChangeDosingDialog(false)}
              unit={props.unit}
              label={props.label}
              experiment={props.experiment}
              maxVolume={dosingMaxVolume}
              liquidVolume={dosingLiquidVolume}
              capacity={props.modelDetails.reactor_capacity_ml}
              threshold={props.modelDetails.reactor_max_fill_volume_ml}
            />
          </React.Fragment>
          }

          <ControlDivider/>


          {ledControlJob &&
          <React.Fragment>
            <Box sx={{justifyContent: "space-between", display: "flex"}}>
              <Typography sx={{ display: "block" }}>
                LED automation
              </Typography>
              <StateTypography state={ledControlJob.state}/>
            </Box>

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
                  unit={props.unit}
                  experiment={props.experiment}
                  label={props.label}
                  configSections={props.config || {}}
                />
               </React.Fragment>
              }
            </div>

            <ChangeAutomationsDialog
              automationType="led"
              open={openChangeLEDDialog}
              onFinished={() => setOpenChangeLEDDialog(false)}
              unit={props.unit}
              label={props.label}
              experiment={props.experiment}
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
            value={props.label}
            onUpdate={updateRenameUnit}
            setSnackbarMessage={setSnackbarMessage}
            setSnackbarOpen={setSnackbarOpen}
            disabled={false}
          />
          <ControlDivider/>

          {editableSettingsGroups
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings]) => (
              Object.entries(settings)
                .filter(([_, setting],__) => setting.display && setting.editable)
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

          <ActionCirculatingForm action="circulate_media" unit={props.unit} experiment={props.experiment} job={props.jobs.circulate_media} />

          <ControlDivider/>

          <Typography  gutterBottom>
            Cycle alternative media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle alternative media in and out of your Pioreactor for a set duration (seconds) by running the alt-media periodically and waste pump continuously.
          </Typography>

          <ActionCirculatingForm action="circulate_alt_media" unit={props.unit} experiment={props.experiment} job={props.jobs.circulate_alt_media} />

          <ControlDivider/>

          <Alert severity="warning" sx={{mb: '10px', mt: '10px'}}>It's easy to overflow your vial. Make sure you don't add too much media.</Alert>

          <Typography  gutterBottom>
            Add media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the media pump for a set duration (s), move a set volume (mL), or fill to the maximum safe volume.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add media:
          </Typography>
          <ActionDosingForm
            action="add_media"
            unit={props.unit}
            experiment={props.experiment}
            job={props.jobs.add_media}
            currentVolumeMl={dosingLiquidVolume}
            maxWorkingVolumeMl={dosingMaxVolume}
            thresholdMl={props.modelDetails.reactor_max_fill_volume_ml}
          />
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
          <ActionDosingForm
            action="remove_waste"
            unit={props.unit}
            experiment={props.experiment}
            job={props.jobs.remove_waste}
            currentVolumeMl={dosingLiquidVolume}
            maxWorkingVolumeMl={dosingMaxVolume}
            thresholdMl={props.modelDetails.reactor_max_fill_volume_ml}
          />
          <ControlDivider/>
          <Typography gutterBottom>
            Add alternative media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the alt-media pump for a set duration (s), move a set volume (mL), or fill to the maximum safe volume.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add alt-media:
          </Typography>
          <ActionDosingForm
            action="add_alt_media"
            unit={props.unit}
            experiment={props.experiment}
            job={props.jobs.add_alt_media}
            currentVolumeMl={dosingLiquidVolume}
            maxWorkingVolumeMl={dosingMaxVolume}
            thresholdMl={props.modelDetails.reactor_max_fill_volume_ml}
          />


        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['A']) ? (LEDMap['A'].replace("_", " ").replace("led", "LED")) : "Channel A" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['A']) ? "Channel A" : ""}
          </Typography>
          <ActionLEDForm experiment={props.experiment} channel="A" unit={props.unit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['B']) ? (LEDMap['B'].replace("_", " ").replace("led", "LED")) : "Channel B" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['B']) ? "Channel B" : ""}
          </Typography>
          <ActionLEDForm experiment={props.experiment} channel="B" unit={props.unit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['C']) ? (LEDMap['C'].replace("_", " ").replace("led", "LED")) : "Channel C" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['C']) ? "Channel C" : ""}
          </Typography>

          <ActionLEDForm experiment={props.experiment} channel="C" unit={props.unit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['D']) ? (LEDMap['D'].replace("_", " ").replace("led", "LED")) : "Channel D" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['D']) ? "Channel D" : ""}
          </Typography>
          <ActionLEDForm experiment={props.experiment} channel="D" unit={props.unit} />
          <ControlDivider/>
        </TabPanel>
        <TabPanel value={tabValue} index={4}>
          <Typography gutterBottom>
            Self-test
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run a hardware self-test on this Pioreactor. Results will update as the unit reports back.
          </Typography>
          <RequirementsAlert sx={{mb: 2, pb: 0}}>
            Add a closed vial, half-filled with water, and a stirbar into the Pioreactor.
            <Box
              component="img"
              src="/static/svgs/prepare-vial-arrow-pioreactor-compact.svg"
              alt="Prepare vial"
              sx={{width: "150px", display: "block", mb: 0, mx: "auto"}}
            />
          </RequirementsAlert>

          <Box sx={{display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap"}}>
            <Button
              variant="contained"
              loading={isSelfTestRunning || selfTestStartPending}
              loadingPosition="start"
              endIcon={<PlayArrowIcon />}
              disabled={isSelfTestRunning || selfTestStartPending }
              onClick={handleRunSelfTest}
              sx={{textTransform: "none"}}
            >
              {isSelfTestRunning ? "Running" : "Start"}
            </Button>
          </Box>

          <ControlDivider/>


          <Accordion disableGutters sx={{boxShadow: "none", "&:before": {display: "none"}}}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box sx={{display: "flex", alignItems: "center", gap: 1}}>
                {renderSelfTestSummaryIcon()}
                <Typography>{props.label ? `${props.label} / ${props.unit}` : props.unit}</Typography>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              {availableSelfTestGroups.length === 0 ? (
                <Typography variant="body2">No self-test checks available.</Typography>
              ) : (
                <>
                  {availableSelfTestGroups.map((group) => (
                    <List
                      key={`self-test-${props.unit}-${group.title}`}
                      dense
                      disablePadding
                      subheader={
                        <ListSubheader sx={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                          {group.title}
                        </ListSubheader>
                      }
                    >
                      {group.tests.map((test) => (
                        <ListItem key={`self-test-${props.unit}-${test.key}`} sx={{pt: 0, pb: 0}}>
                          <ListItemIcon sx={{minWidth: "30px"}}>
                            {renderSelfTestIcon(test.key)}
                          </ListItemIcon>
                          <ListItemText
                            primary={test.label}
                            secondary={renderSelfTestSecondary(test)}
                          />
                        </ListItem>
                      ))}
                    </List>
                  ))}
                </>
              )}
            </AccordionDetails>
          </Accordion>
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


function UnitCard({unit, experiment, config, isAssignedToExperiment, isActive, modelDetails, bioreactorValues, setBioreactorValues}){
  const [relabelMap, setRelabelMap] = useState({})
  useEffect(() => {

    if (experiment){
      getRelabelMap(setRelabelMap, experiment)
    }
  }, [experiment])

  return (
    <React.Fragment>
      <div>
         <PioreactorCard
           modelDetails={modelDetails}
           isUnitActive={isAssignedToExperiment && isActive}
           unit={unit}
           config={config}
           experiment={experiment}
           initialLabel={relabelMap[unit]}
           bioreactorValues={bioreactorValues}
           setBioreactorValues={setBioreactorValues}
         />
      </div>
    </React.Fragment>
)}


function FlashLEDButton(props){

  const [flashing, setFlashing] = useState(false)

  const onClick = () => {
    setFlashing(false)
    requestAnimationFrame(() => setFlashing(true))
    fetch(`/api/workers/${props.unit}/blink`, {method: "POST"})
  }

  return (
    <Button
      sx={{textTransform: 'none', float: "right"}}
      className={flashing ? 'blinkled' : ''}
      disabled={props.disabled}
      onClick={onClick}
      onAnimationEnd={() => setFlashing(false)}
      color="primary"
    >
      <FlareIcon color={props.disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon}/> <span > Identify </span>
    </Button>
)}


function PioreactorCard({ unit, modelDetails, isUnitActive, experiment, config, initialLabel, bioreactorValues, setBioreactorValues }){
  const [jobDescriptorsStatus, setJobDescriptorsStatus] = useState("loading")
  const [jobDescriptorsErrorText, setJobDescriptorsErrorText] = useState("Job controls unavailable.")
  const [label, setLabel] = useState(initialLabel || "")
  const [bioreactorDescriptors, setBioreactorDescriptors] = useState([])
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = useState(false)
  const [openChangeDosingDialog, setOpenChangeDosingDialog] = useState(false)
  const [openChangeLEDDialog, setOpenChangeLEDDialog] = useState(false)
  const [stateActionAnchorEl, setStateActionAnchorEl] = useState(null)
  const [stateActionJobKey, setStateActionJobKey] = useState(null)
  const [pendingStateActionsByJob, setPendingStateActionsByJob] = useState({})
  const [quickSettingAnchorEl, setQuickSettingAnchorEl] = useState(null)
  const [quickSettingSelection, setQuickSettingSelection] = useState(null)
  const {client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const isXrModel = Boolean(modelDetails.model_name?.toLowerCase().includes("xr"));
  const modelBadgeContent = modelDetails.model_name?.endsWith("XR") ? "XR" : modelDetails.reactor_capacity_ml;

  const [jobs, setJobs] = useState(() => ({ monitor: createMonitorJobState() }))
  const [passiveSettingsCollections, setPassiveSettingsCollections] = useState({})
  const [bioreactorUpdateFlashTokens, setBioreactorUpdateFlashTokens] = useState({})
  const seenCardTopics = React.useRef(new Set())
  const receivedBioreactorValues = React.useRef(new Map())

  useEffect(() => {
    setLabel(initialLabel || "")
  }, [initialLabel])

  const bioreactorSettingsGroup = useMemo(
    () => buildBioreactorSettingsCollection(bioreactorDescriptors, bioreactorValues, config, modelDetails),
    [bioreactorDescriptors, bioreactorValues, config, modelDetails]
  )
  const settingsCollections = useMemo(
    () => mergeSettingsCollections(jobs, passiveSettingsCollections, bioreactorSettingsGroup),
    [bioreactorSettingsGroup, jobs, passiveSettingsCollections],
  )


  useEffect(() => {
    let isCancelled = false

    setJobDescriptorsStatus("loading")
    setJobDescriptorsErrorText("Job controls unavailable.")
    setJobs({ monitor: createMonitorJobState() })
    setPassiveSettingsCollections({})
    setBioreactorDescriptors([])

    Promise.all([
      getWorkerJobDescriptors(unit),
      getWorkerSettingsDescriptors(unit),
    ])
      .then(([jobDescriptors, settingsCollectionDescriptors]) => {
        if (isCancelled) {
          return
        }
        setJobs((previous) =>
          buildJobsStateFromDescriptors(jobDescriptors, {
            includeMonitor: true,
            existingJobs: previous,
          }),
        )
        setBioreactorDescriptors(
          settingsCollectionDescriptors.find((descriptor) => descriptor.key === "bioreactor")?.published_settings || [],
        )
        setPassiveSettingsCollections((previous) =>
          buildSettingsCollectionsFromDescriptors(
            settingsCollectionDescriptors.filter((descriptor) => descriptor.key !== "bioreactor"),
            { existingCollections: previous },
          ),
        )
        setJobDescriptorsStatus("ready")
      })
      .catch((error) => {
        if (isCancelled) {
          return
        }
        setJobs({ monitor: createMonitorJobState() })
        setPassiveSettingsCollections({})
        setBioreactorDescriptors([])
        setJobDescriptorsErrorText(error.message || "Job controls unavailable.")
        setJobDescriptorsStatus("error")
      })

    return () => {
      isCancelled = true
    }
  }, [unit])

  const onMessage = useCallback((topic, message, packet) => {
    if (!message || !topic) return;

    const topicName = topic.toString()
    const payload = message.toString()
    const [job, setting] = topicName.split('/').slice(-2)
    const hasSeenTopic = seenCardTopics.current.has(topicName)
    seenCardTopics.current.add(topicName)
    const shouldFlash = hasSeenTopic && packet?.retain === false

    if (setting === "$state"){
      setJobs((prev) => {
        const currentJob = prev[job]
        if (!currentJob || Object.is(currentJob.state, payload)) {
          return prev
        }

        return {
          ...prev,
          [job]: {
            ...currentJob,
            state: payload,
            ...(shouldFlash && currentJob.metadata?.display
              ? {updateFlashToken: (currentJob.updateFlashToken || 0) + 1}
              : {}),
          },
        }
      })
      setPendingStateActionsByJob((previous) => {
        const pendingAction = previous[job]
        if (!pendingAction) {
          return previous
        }

        const shouldClearPending = shouldClearPendingStateAction(pendingAction, payload)

        if (!shouldClearPending) {
          return previous
        }

        const updated = {...previous}
        delete updated[job]
        return updated
      })
    } else {
      const updateSettingCollection = (previous) => {
        const typeOfSetting = previous[job]?.publishedSettings?.[setting]?.type
        if (!typeOfSetting) {
          return previous
        }
        const settingPayload = parsePayloadToType(payload, typeOfSetting)
        return updatePublishedSettingValue(previous, job, setting, settingPayload, {
          flash: shouldFlash,
        });
      }

      setJobs(updateSettingCollection);
      setPassiveSettingsCollections(updateSettingCollection);
    }
  }, []);

  const monitorSettingsSignature = Object.keys(jobs.monitor?.publishedSettings || {})
    .sort()
    .join(TOPIC_SIGNATURE_SEPARATOR);

  const monitorTopics = useMemo(() => {
    return getPioreactorCardMonitorTopics({
      unit,
      experiment,
      monitorSettingsSignature,
    });
  }, [experiment, monitorSettingsSignature, unit]);

  useEffect(() => {
    if (!isUnitActive) {
      return undefined;
    }

    if (!client || monitorTopics.length === 0) {
      return undefined;
    }

    subscribeToTopic(monitorTopics, onMessage, "PioreactorCardMonitor");

    return () => {
      unsubscribeFromTopic(monitorTopics, "PioreactorCardMonitor");
    };
  }, [client, isUnitActive, monitorTopics, onMessage, subscribeToTopic, unsubscribeFromTopic])

  const dynamicTopicsSignature = getPublishedSettingsSignature(jobs, {
    excludeKeys: ["monitor"],
    separator: TOPIC_SIGNATURE_SEPARATOR,
  });

  const passiveSettingsTopicsSignature = getPublishedSettingsSignature(passiveSettingsCollections, {
    separator: TOPIC_SIGNATURE_SEPARATOR,
  });
  const bioreactorTopicsSignature = bioreactorDescriptors
    .map((descriptor) => descriptor.key)
    .filter(Boolean)
    .sort()
    .join(TOPIC_SIGNATURE_SEPARATOR);

  const dynamicJobTopics = useMemo(() => {
    if (jobDescriptorsStatus !== "ready") {
      return [];
    }
    return getPioreactorCardPublishedSettingsTopics(dynamicTopicsSignature, {
      unit,
      experiment,
      includeState: true,
    });
  }, [dynamicTopicsSignature, experiment, jobDescriptorsStatus, unit]);

  const passiveSettingsTopics = useMemo(() => {
    if (jobDescriptorsStatus !== "ready") {
      return [];
    }
    return getPioreactorCardPublishedSettingsTopics(passiveSettingsTopicsSignature, {
      unit,
      experiment,
    });
  }, [experiment, jobDescriptorsStatus, passiveSettingsTopicsSignature, unit]);

  useEffect(() => {
    if (!isUnitActive) {
      return undefined;
    }

    if (!client || dynamicJobTopics.length === 0) {
      return undefined;
    }

    subscribeToTopic(dynamicJobTopics, onMessage, "PioreactorCardDynamic");

    return () => {
      unsubscribeFromTopic(dynamicJobTopics, "PioreactorCardDynamic");
    };
  }, [client, dynamicJobTopics, isUnitActive, onMessage, subscribeToTopic, unsubscribeFromTopic])

  useEffect(() => {
    if (!isUnitActive) {
      return undefined;
    }

    if (!client || passiveSettingsTopics.length === 0) {
      return undefined;
    }

    subscribeToTopic(passiveSettingsTopics, onMessage, "PioreactorCardSettings");

    return () => {
      unsubscribeFromTopic(passiveSettingsTopics, "PioreactorCardSettings");
    };
  }, [client, isUnitActive, onMessage, passiveSettingsTopics, subscribeToTopic, unsubscribeFromTopic])

  const onBioreactorMessage = useCallback((topic, message, packet) => {
    if (!topic || !message) {
      return;
    }

    const topicName = topic.toString()
    const parts = topicName.split("/");
    const variableName = parts[4];
    const parsedValue = parseNumericValue(message.toString());

    if (!variableName || parsedValue === null) {
      return;
    }

    const hasPreviousValue = receivedBioreactorValues.current.has(topicName)
    const previousValue = receivedBioreactorValues.current.get(topicName)
    receivedBioreactorValues.current.set(topicName, parsedValue)
    const descriptor = bioreactorDescriptors.find(({key}) => key === variableName)
    const isVisible = descriptor ? descriptor.display !== false : false
    if (
      hasPreviousValue
      && packet?.retain === false
      && isVisible
      && !Object.is(previousValue, parsedValue)
    ) {
      setBioreactorUpdateFlashTokens((previous) => ({
        ...previous,
        [variableName]: (previous[variableName] || 0) + 1,
      }))
    }

    setBioreactorValues((previous) => Object.is(previous[variableName], parsedValue)
      ? previous
      : {...previous, [variableName]: parsedValue});
  }, [bioreactorDescriptors, setBioreactorValues]);

  useEffect(() => {
    if (!isUnitActive) {
      return undefined;
    }

    const topics = getPioreactorCardBioreactorTopics({
      unit,
      experiment,
      bioreactorTopicsSignature,
    });

    if (!client || topics.length === 0) {
      return undefined;
    }

    subscribeToTopic(topics, onBioreactorMessage, "PioreactorCardBioreactor");

    return () => {
      unsubscribeFromTopic(topics, "PioreactorCardBioreactor");
    };
  }, [
    bioreactorTopicsSignature,
    client,
    experiment,
    isUnitActive,
    onBioreactorMessage,
    subscribeToTopic,
    unsubscribeFromTopic,
    unit,
  ])

  const setPioreactorJobAttr = (job, setting, value) => {
    if (job === "bioreactor") {
      return updateBioreactorSettingAndMirrorState(
        unit,
        experiment,
        setting,
        value,
        setBioreactorValues,
      )
    }

    return fetch(`/api/workers/${unit}/jobs/update/job_name/${job}/experiments/${experimentPathSegment(experiment)}`, {
      method: "PATCH",
      body: JSON.stringify({settings: {[setting]: value}}),
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      }
    }).then((response) => {
      if (response.ok) {
        return
      }
      throw new Error(`Error ${response.status}.`)
    })
  }

  const setPioreactorJobState = (job, state) => {
    return setPioreactorJobAttr(job, "$state", state)
  }

  const openAutomationSelectionDialog = (jobKey) => {
    if (jobKey === "temperature_automation") {
      setOpenChangeTemperatureDialog(true)
      return
    }
    if (jobKey === "dosing_automation") {
      setOpenChangeDosingDialog(true)
      return
    }
    if (jobKey === "led_automation") {
      setOpenChangeLEDDialog(true)
    }
  }

  const createStateActions = (jobKey, state) => {
    return createStateActionsForState(state, {
      onPause: () => setPioreactorJobState(jobKey, "sleeping"),
      onResume: () => setPioreactorJobState(jobKey, "ready"),
      onStop: () => setPioreactorJobState(jobKey, "disconnected"),
    })
  }

  const getPrimaryStateAction = (jobKey, state) => {
    const pendingStart = !isAutomationJob(jobKey)
    return createPrimaryStateActionForState(state, {
      onStart: pendingStart
        ? () => runPioreactorJob(unit, experiment, jobKey)
        : () => openAutomationSelectionDialog(jobKey),
      pendingStart,
    })
  }

  const runStateActionWithPending = (jobKey, action) => {
    if (!action?.onClick) {
      return
    }
    if (action.pendingAction) {
      setPendingStateActionsByJob((previous) => ({...previous, [jobKey]: action.pendingAction}))
    }
    return Promise.resolve(action.onClick()).catch(() => {
      setPendingStateActionsByJob((previous) => {
        if (!(jobKey in previous)) {
          return previous
        }
        const updated = {...previous}
        delete updated[jobKey]
        return updated
      })
    })
  }

  const handleStateMenuOpen = (event, jobKey) => {
    setStateActionAnchorEl(event.currentTarget)
    setStateActionJobKey(jobKey)
  }

  const handleStateMenuClose = () => {
    setStateActionAnchorEl(null)
    setStateActionJobKey(null)
  }

  const handleQuickSettingOpen = (event, jobKey, settingKey) => {
    setQuickSettingAnchorEl(event.currentTarget)
    setQuickSettingSelection({jobKey, settingKey})
  }

  const handleQuickSettingClose = () => {
    setQuickSettingAnchorEl(null)
    setQuickSettingSelection(null)
  }

  function renderQuickSettingComponent(setting, job_key, setting_key, state) {
    const onUpdateAndClose = (job, settingName, value) => {
      setPioreactorJobAttr(job, settingName, value)
      handleQuickSettingClose()
    }

    const componentKey = `${unit}-${job_key}-${setting_key}`;
    const commonProps = {
      setSnackbarMessage: () => {},
      setSnackbarOpen: () => {},
      value: setting.value,
      units: setting.unit,
      min: setting.min,
      max: setting.max,
      job: job_key,
      setting: setting_key,
      disabled: state === "disconnected" || !isUnitActive,
      id: `quick-edit-${unit}-${job_key}-${setting_key}`,
    }

    switch (setting.type) {
      case "boolean":
        return <SettingSwitchField key={componentKey} {...commonProps} onUpdate={setPioreactorJobAttr} />
      case "numeric":
        return <SettingNumericField key={componentKey} {...commonProps} onUpdate={onUpdateAndClose} />
      default:
        return <SettingTextField key={componentKey} {...commonProps} onUpdate={onUpdateAndClose} />
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
  const quickSettingEditorOpen = Boolean(quickSettingAnchorEl && quickSettingSelection)
  const quickSetting =
    quickSettingSelection &&
    settingsCollections[quickSettingSelection.jobKey] &&
    settingsCollections[quickSettingSelection.jobKey].publishedSettings[quickSettingSelection.settingKey]
      ? settingsCollections[quickSettingSelection.jobKey].publishedSettings[quickSettingSelection.settingKey]
      : null
  const quickSettingState = quickSettingSelection ? settingsCollections[quickSettingSelection.jobKey]?.state : null
  const stateActionMenuOpen = Boolean(stateActionAnchorEl && stateActionJobKey)
  const activeStateMenuActions =
    stateActionJobKey && jobs[stateActionJobKey]
      ? createStateActions(stateActionJobKey, jobs[stateActionJobKey].state)
      : []
  const dosingMaxVolume = getBioreactorConfirmedValue(
    bioreactorValues,
    config,
    "efflux_tube_volume_ml",
  )
  const dosingLiquidVolume = getBioreactorConfirmedValue(
    bioreactorValues,
    config,
    "current_volume_ml",
  )

  return (
    <Card aria-disabled={!isUnitActive}>
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
            <Box sx={{display: "flex", justifyContent: "left"}}>
              <PioreactorIconWithModel badgeContent={modelBadgeContent} />
              <Typography sx={{
                  fontSize: 20,
                  color: "rgba(0, 0, 0, 0.87)",
                  fontWeight: 500,
                  ...(isUnitActive ? {} : { color: disabledColor }),
                }}
                gutterBottom>
                {(label ) ? label : unit }
              </Typography>
              <Tooltip title={indicatorLabel} placement="right">
                <div>
                  <div className="indicator-dot" style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
                </div>
              </Tooltip>
            </Box>
            <Box sx={{
              display: "flex",
              justifyContent: "flex-end",
              flexDirection: "row",
              flexWrap: "wrap",
            }}
            >
              <div>
                <ButtonStopProcess
                  experiment={experiment}
                  unit={unit}
                  buttonText="Stop all"
                  disabled={!isUnitActive}
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
                disabled={!isUnitActive || jobDescriptorsStatus !== "ready"}
                experiment={experiment}
                jobs={jobs}
                settingsCollections={settingsCollections}
                setLabel={setLabel}
                modelDetails={modelDetails}
                bioreactorValues={bioreactorValues}
                setBioreactorValues={setBioreactorValues}
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
          <Typography variant="body2">
          <Box sx={{ fontWeight: "fontWeightBold", color: !isUnitActive ? disabledColor : 'inherit' }}>
              Activities:
            </Box>
          </Typography>
        </Box>
        <RowOfUnitSettingDisplayBox>
          {jobDescriptorsStatus !== "ready" ? (
            <DescriptorStatusMessage status={jobDescriptorsStatus} errorText={jobDescriptorsErrorText} />
          ) : null}
          {Object.entries(jobs)
            .filter(([, job]) => job.metadata.display)
            .map(([jobKey, job]) => {
              const primaryStateAction = getPrimaryStateAction(jobKey, job.state)
              const allStateActions = createStateActions(jobKey, job.state)
              const subtext = job.metadata.subtext ? job.publishedSettings[job.metadata.subtext]?.value : null
              const isPendingStateAction = Boolean(pendingStateActionsByJob[jobKey])
              const canUsePrimaryAction = isUnitActive && Boolean(primaryStateAction) && !isPendingStateAction
              const showStateActionMenu = isUnitActive && allStateActions.length > 0 && !isPendingStateAction
              return (
                <Box sx={{width: "132px", ml:"2px", mt: "10px", mr: "2px", px: "3px"}} key={job.metadata.key}>
                  <Typography variant="body2"  sx={{fontSize: "0.84rem",  color: !isUnitActive ? disabledColor : 'inherit' }}>
                    {job.metadata.display_name}
                    {(job.metadata.display_name === "Optical density" && isXrModel) ? (
                      <Chip
                        component="span"
                        size="small"
                        variant="outlined"
                        label="XR"
                        sx={{ ml: 0.5, height: 18, fontSize: "0.65rem", "& .MuiChip-label": { px: "5px" } }}
                      />
                    ) : null}
                  </Typography>
                  <Box sx={{display: "flex", alignItems: "center", minHeight: "32px"}}>
                    <Box
                      onClick={() => {
                        if (canUsePrimaryAction) {
                          runStateActionWithPending(jobKey, primaryStateAction)
                        }
                      }}
                      sx={{
                        cursor: canUsePrimaryAction ? "pointer" : "default",
                      }}
                    >
                      {isPendingStateAction ? (
                        <Box sx={{minHeight: "30px", display: "flex", alignItems: "center", ml: 1}}>
                          <CircularProgress size={18} />
                        </Box>
                      ) : (
                        <StateTypography
                          state={job.state}
                          isDisabled={!isUnitActive}
                          isInteractive={canUsePrimaryAction}
                          updateFlashToken={job.updateFlashToken}
                        />
                      )}
                    </Box>
                    {showStateActionMenu ? (
                      <span>
                        <IconButton
                          size="small"
                          onClick={(event) => handleStateMenuOpen(event, jobKey)}
                          sx={{ml: 0.25}}
                        >
                          <ExpandMoreIcon fontSize="small" />
                        </IconButton>
                      </span>
                    ) : null}
                  </Box>
                  <UnitSettingDisplaySubtext subtext={subtext}/>
                </Box>
              )
            })}

        </RowOfUnitSettingDisplayBox>
      </Box>

      <Divider/>

      <Box sx={{
          display: "flex",
          m: "15px 20px 20px 0px",
          flexDirection: "row",
        }}>
        <Box sx={{width: "100px", mt: "10px"}}>
          <Typography variant="body2">
            <Box sx={{ fontWeight: "fontWeightBold", color: !isUnitActive ? disabledColor : 'inherit' }}>
              Settings:
            </Box>
          </Typography>
        </Box>
        <RowOfUnitSettingDisplayBox>
          {Object.entries(settingsCollections)
            .map(([job_key, job]) =>
              Object.entries(job.publishedSettings)
                .filter(([, setting]) => setting.display)
                .map(([setting_key, setting]) => {
                  const canQuickEdit = canQuickEditCardSetting(setting, isUnitActive)
                  const displayKind = getCardSettingDisplayKind(job_key, setting_key)
                  return (
                    <Box sx={{width: "132px", ml:"2px", mt: "10px", mr: "2px", px: "3px"}} key={job_key + setting_key}>
                      <Typography variant="body2"  sx={{fontSize: "0.84rem",  color: !isUnitActive ? disabledColor : 'inherit' }}>
                        {setting.label}
                        {(setting.label === "Optical density" && isXrModel) ? (
                          <Chip
                            component="span"
                            size="small"
                            variant="outlined"
                            label="XR"
                            sx={{ ml: 0.5, height: 18, fontSize: "0.65rem", "& .MuiChip-label": { px: "5px" } }}
                          />
                        ) : null}
                      </Typography>
                      <Box
                        onClick={(event) => {
                          if (canQuickEdit) {
                            handleQuickSettingOpen(event, job_key, setting_key)
                          }
                        }}
                        sx={{
                          cursor: canQuickEdit ? "pointer" : "default",
                          display: "inline-flex",
                          borderRadius: "6px",
                          padding: canQuickEdit ? "1px 2px" : "0px",
                        }}
                      >
                        <UnitSettingDisplay
                          value={setting.value}
                          isUnitActive={isUnitActive}
                          measurementUnit={setting.unit}
                          precision={2}
                          default="—"
                          displayKind={displayKind}
                          config={config}
                          isInteractive={canQuickEdit}
                          updateFlashToken={job_key === "bioreactor"
                            ? bioreactorUpdateFlashTokens[setting_key]
                            : setting.updateFlashToken}
                        />
                      </Box>
                    </Box>
                  )
                })
            )}
        </RowOfUnitSettingDisplayBox>
      </Box>

      <Menu
        anchorEl={stateActionAnchorEl}
        open={stateActionMenuOpen}
        onClose={handleStateMenuClose}
      >
        {activeStateMenuActions.map((action) => (
          <MenuItem
            key={action.label}
            onClick={() => {
              if (stateActionJobKey) {
                runStateActionWithPending(stateActionJobKey, action)
              }
              handleStateMenuClose()
            }}
          >
            {action.label}
          </MenuItem>
        ))}
      </Menu>

      <ChangeAutomationsDialog
        open={openChangeTemperatureDialog}
        onFinished={() => setOpenChangeTemperatureDialog(false)}
        unit={unit}
        label={label}
        experiment={experiment}
        automationType="temperature"
      />

      <ChangeDosingAutomationsDialog
        automationType="dosing"
        open={openChangeDosingDialog}
        onFinished={() => setOpenChangeDosingDialog(false)}
        unit={unit}
        label={label}
        experiment={experiment}
        maxVolume={dosingMaxVolume}
        liquidVolume={dosingLiquidVolume}
        capacity={modelDetails.reactor_capacity_ml}
        threshold={modelDetails.reactor_max_fill_volume_ml}
      />

      <ChangeAutomationsDialog
        automationType="led"
        open={openChangeLEDDialog}
        onFinished={() => setOpenChangeLEDDialog(false)}
        unit={unit}
        label={label}
        experiment={experiment}
      />

      <Popover
        open={quickSettingEditorOpen && Boolean(quickSetting)}
        anchorEl={quickSettingAnchorEl}
        onClose={handleQuickSettingClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
      >
        <Box sx={{p: 2, width: "310px"}}>
          {quickSetting && quickSettingSelection ? (
            <React.Fragment>
              <Box sx={{display: "flex", justifyContent: "space-between", alignItems: "flex-start"}}>
                <Typography variant="subtitle2">
                  {quickSetting.label}
                </Typography>
                <IconButton size="small" onClick={handleQuickSettingClose} sx={{mt: -0.5, mr: -0.5}}>
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Box>
              <Typography variant="caption" color="text.secondary">
                {settingsCollections[quickSettingSelection.jobKey]?.metadata?.display_name}
              </Typography>
              {renderQuickSettingComponent(
                quickSetting,
                quickSettingSelection.jobKey,
                quickSettingSelection.settingKey,
                quickSettingState
              )}
            </React.Fragment>
          ) : null}
        </Box>
      </Popover>


      </CardContent>
    </Card>
)}


function evaluateChartLookback(timeWindow, lookbackExpression) {
  if (timeWindow >= 0) {
    return timeWindow;
  }
  if (!lookbackExpression) {
    return 10000;
  }
  // Chart descriptors provide legacy JavaScript expressions for lookback values.
  // eslint-disable-next-line no-eval
  return eval(lookbackExpression);
}

function evaluateChartTransformation(transformation) {
  // Chart descriptors provide legacy JavaScript functions for y-axis transformations.
  // eslint-disable-next-line no-eval
  return eval(transformation || "(y) => y");
}



function Charts(props) {
  const [charts, setCharts] = useState({})
  const config = props.config
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const experiment = props.experimentMetadata.experiment;

  useEffect(() => {
    fetch('/api/charts/descriptors')
      .then((response) => response.json())
      .then((data) => {
        setCharts(Object.fromEntries(data.map((chart) => [chart.chart_key, chart])));
      });
  }, []);


  return (
    <React.Fragment>
      {Object.entries(charts)
        .filter(([chart_key, _]) => config['ui.overview.charts'] && (config['ui.overview.charts'][chart_key] === "1"))
        .map(([chart_key, chart]) =>
          <React.Fragment key={`grid-chart-${chart_key}`}>
            <Grid size={12}>
              <Card sx={{ maxHeight: "100%"}}>
                <Chart
                  unit={props.unit}
                  key={`chart-${chart_key}-${experiment}-${props.unit || "all"}-${props.timeWindow}-${props.timeScale}`}
                  chartKey={chart_key}
                  config={config}
                  dataSource={chart.data_source}
                  title={chart.title}
                  topic={chart.mqtt_topic}
                  payloadKey={chart.payload_key}
                  yAxisLabel={chart.y_axis_label}
                  experiment={experiment}
                  deltaHours={props.experimentMetadata.delta_hours}
                  experimentStartTime={props.experimentMetadata.created_at}
                  downSample={chart.down_sample}
                  interpolation={chart.interpolation || "stepAfter"}
                  yAxisDomain={chart.y_axis_domain ? chart.y_axis_domain : null}
                  lookback={evaluateChartLookback(props.timeWindow, chart.lookback)}
                  fixedDecimals={chart.fixed_decimals}
                  relabelMap={props.relabelMap}
                  yTransformation={evaluateChartTransformation(chart.y_transformation)}
                  dataSourceColumn={chart.data_source_column}
                  isPartitionedBySensor={["raw_optical_density", 'optical_density'].includes(chart_key)}
                  isLiveChart={true}
                  byDuration={props.timeScale === "hours"}
                  client={client}
                  subscribeToTopic={subscribeToTopic}
                  unsubscribeFromTopic={unsubscribeFromTopic}
                  unitsColorMap={props.unitsColorMap}
                />
              </Card>
            </Grid>
          </React.Fragment>
     )}
    </React.Fragment>
  );}




function Pioreactor({title, cameraUIEnabled = false}) {
  const { experimentMetadata, selectExperiment } = useExperiment();
  const [unitConfig, setUnitConfig] = useState({})
  const initialTimeScale = localStorage.getItem('timeScale') || 'hours';
  const storedTimeWindow = parseInt(localStorage.getItem('timeWindow'), 10);
  const initialTimeWindow = storedTimeWindow >= 0 ? storedTimeWindow : 1000000;
  const [timeScale, setTimeScale] = useState(initialTimeScale);
  const [timeWindow, setTimeWindow] = useState(initialTimeWindow);

  const {pioreactorUnit} = useParams();
  const unit = pioreactorUnit
  const [assignedExperiment, setAssignedExperiment] = useState(null)
  const [bioreactorValues, setBioreactorValues] = useState({})
  const [isActive, setIsActive] = useState(true)
  const [modelDetails, setModelDetails] = useState({})
  const [error, setError] = useState(null)

  const onExperimentClick = () => {
    selectExperiment(assignedExperiment);
  }

  useEffect(() => {
    document.title = title;
  }, [title]);

  useEffect(() => {
    fetch(`/api/config/units/${unit}`).then((response) => {
      if (!response.ok) {
        return response.json().then((errorData) => {
          console.log(errorData)
          throw new Error(errorData.error);
        });
      }
      return response.json();
    })
    .then((data) => setUnitConfig(data.configs[unit]))
    .catch((error) => {
      console.error("Fetching configuration failed:", error);
    });
  }, [unit]);

  useEffect(() => {
    function getWorkerAssignment() {
      fetch(`/api/workers/${unit}/experiment`)
        .then((response) => {
          if (!response.ok) {
            return response.json().then((errorData) => {
              console.log(errorData)
              throw new Error(errorData.error);
            });
          }
          return response.json();
        })
        .then((json) => {
        setAssignedExperiment(json['experiment'])
        setIsActive(json['is_active'])
      })
      .catch((error) => {
        setError(error.message);
      });
    }

    if (experimentMetadata){
      getWorkerAssignment()
    }
  }, [experimentMetadata, unit])

  useEffect(() => {
    function getModelDetails() {
      fetch(`/api/workers/${unit}/model`)
        .then((response) => {
          if (!response.ok) {
            return response.json().then((errorData) => {
              console.log(errorData)
              throw new Error(errorData.error);
            });
          }
          return response.json();
        })
        .then((json) => {
        setModelDetails(json)
      })
      .catch((error) => {
        setError(error.message);
      });
    }
    getModelDetails()
  }, [unit])




  if (error) {
    return (
      <Box sx={{textAlign: "center", mb: '50px', mt: "50px"}}>
        <Alert severity="error" sx={{ display: "inline-flex", textAlign: "left" }}>
          {error}
        </Alert>
      </Box>
  )}
  else {
    return (
      <>
        <Grid container rowSpacing={1} columnSpacing={2} sx={{ justifyContent: "space-between" }}>
          <Grid
            size={{
              md: 12,
              xs: 12
            }}>
            <PioreactorHeader unit={unit} assignedExperiment={assignedExperiment} isActive={isActive} selectExperiment={selectExperiment} modelDisplayName={modelDetails.display_name} />
            {experimentMetadata.experiment && assignedExperiment && experimentMetadata.experiment !== assignedExperiment &&
            <Box>
            <Alert severity="info" sx={{mb: '10px', mt: '10px'}}>This worker is part of different experiment. Switch to experiment <Chip icon={<PlayCircleOutlinedIcon/>} size="small" label={assignedExperiment} clickable component={Link} onClick={onExperimentClick} data-experiment-name={assignedExperiment}/> to control this worker.</Alert>
            </Box>
          }
          </Grid>
          <Grid
            size={{
              lg: 8,
              md: 12,
              xs: 12
            }}>
            <UnitCard
              modelDetails={modelDetails}
              isActive={isActive}
              isAssignedToExperiment={experimentMetadata.experiment === assignedExperiment}
              unit={unit}
              experiment={experimentMetadata.experiment}
              config={unitConfig}
              bioreactorValues={bioreactorValues}
              setBioreactorValues={setBioreactorValues}
            />
          </Grid>
          <Grid
            size={{
              lg: 4,
              md: 12,
              xs: 12
            }}>
            <BioreactorDiagramPanel
              unit={unit}
              experiment={experimentMetadata.experiment}
              config={unitConfig}
              modelDetails={modelDetails}
              values={bioreactorValues}
              onValuesChange={setBioreactorValues}
            />
          </Grid>

          <Grid
            container
            spacing={2}
            justifyContent="flex-start"
            sx={{height: "100%"}}
            size={{
              xs: 12,
              md: 7
            }}>
            <Charts unit={unit} unitsColorMap={{[unit]: colors[0]}} config={unitConfig} timeScale={timeScale} timeWindow={timeWindow} experimentMetadata={experimentMetadata}/>
          </Grid>
          <Grid
            container
            spacing={2}
            justifyContent="flex-end"
            sx={{height: "100%"}}
            size={{
              xs: 12,
              md: 5
            }}>
            <Grid
              size={{
                xs: 7,
                md: 7
              }}>
              <Stack direction="row" sx={{ justifyContent: "start" }}>
                <TimeWindowSwitch setTimeWindow={setTimeWindow} timeWindow={timeWindow}/>
              </Stack>
            </Grid>
            <Grid
              size={{
                xs: 5,
                md: 5
              }}>
              <Stack direction="row" sx={{ justifyContent: "end" }}>
                <TimeFormatSwitch setTimeScale={setTimeScale} timeScale={timeScale}/>
              </Stack>
            </Grid>
            <Grid size={12}>
              <LogTableByUnit experiment={experimentMetadata.experiment} unit={unit} byDuration={timeScale === "hours"} experimentStartTime={experimentMetadata.created_at}/>
            </Grid>
            {cameraUIEnabled && (
              <Grid size={12}>
                <Box sx={{ mt: 1, mb: 1 }}>
                  <CameraPanel
                    key={`${unit}:${experimentMetadata.experiment}`}
                    unit={unit}
                    experiment={experimentMetadata.experiment}
                    experimentStartTime={experimentMetadata.created_at}
                  />
                </Box>
              </Grid>
            )}
          </Grid>
        </Grid>
      </>
    );
  }
}

export default Pioreactor;
