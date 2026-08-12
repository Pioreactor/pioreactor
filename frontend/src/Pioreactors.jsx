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
import DialogActions from '@mui/material/DialogActions';
import Checkbox from '@mui/material/Checkbox';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormGroup from '@mui/material/FormGroup';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import Snackbar from './components/Snackbar';
import Tooltip from '@mui/material/Tooltip';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Popover from '@mui/material/Popover';
import FormLabel from '@mui/material/FormLabel';
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
import FlareIcon from '@mui/icons-material/Flare';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import IndeterminateCheckBoxIcon from '@mui/icons-material/IndeterminateCheckBox';
import SettingsIcon from '@mui/icons-material/Settings';
import IconButton from '@mui/material/IconButton';
import Alert from '@mui/material/Alert';
import LibraryAddCheckOutlinedIcon from '@mui/icons-material/LibraryAddCheckOutlined';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import { useNavigate, Link } from 'react-router'

import AdvancedConfigButton from "./components/AdvancedConfigDialog"
import ChangeAutomationsDialog from "./components/ChangeAutomationsDialog"
import ChangeDosingAutomationsDialog from "./components/ChangeDosingAutomationsDialog"
import AutomationAdvancedConfigButton from "./components/AutomationAdvancedConfigDialog"
import ActionDosingForm from "./components/ActionDosingForm"
import ActionCirculatingForm from "./components/ActionCirculatingForm"
import ActionLEDForm from "./components/ActionLEDForm"
import PioreactorIcon from "./components/PioreactorIcon"
import PioreactorIconWithModel from "./components/PioreactorIconWithModel"
import PioreactorsIcon from "./components/PioreactorsIcon"
import RequirementsAlert from "./components/RequirementsAlert"
import ManageExperimentMenu from "./components/ManageExperimentMenu";
import { useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';
import PatientButton from './components/PatientButton';
import {
  buildBioreactorSettingsCollection,
  getBioreactorConfirmedValue,
  mergeSettingsCollections,
  parseNumericValue,
} from "./utils/bioreactor";
import { getConfig, getRelabelMap } from "./utils/config";
import {
  buildJobsStateFromDescriptors,
  buildSettingsCollectionsFromDescriptors,
  createMonitorJobState,
  getJobDescriptors,
  getPublishedSettingsSignature,
  getSettingsDescriptors,
  getWorkerJobDescriptors,
  getWorkerSettingsDescriptors,
  runPioreactorJob,
  updatePublishedSettingValue,
} from "./utils/jobs";
import { experimentPathSegment } from "./utils/url";
import {
  disconnectedGrey,
  lostRed,
  readyGreen,
  disabledColor,
} from "./utils/color";
import MissingWorkerModelModal from "./components/MissingWorkerModelModal";
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
  getAvailableSelfTestGroupsFromDefinition,
  getAvailableSelfTestGroupsFromSettings,
  getPioreactorCardBioreactorTopics,
  getPioreactorCardMonitorTopics,
  getPioreactorCardPublishedSettingsTopics,
  parsePayloadToType,
  textIcon,
  updateBioreactorSettingAndMirrorState,
} from "./components/PioreactorCardShared";

const workerMissingModelDetails = (worker) =>
  worker?.model_name == null || worker?.model_version == null;

const EMPTY_STATE_ILLUSTRATIONS = [
  "/static/svgs/yeast-cells.svg",
  "/static/svgs/bacteria-cells.svg",
  "/static/svgs/coccus-cells.svg",
  "/static/svgs/bacteria-two-bacillus-touching.svg",
  "/static/svgs/bacteria-three-bacillus-touching.svg",
];

function useContribJobsList() {
  const [jobs, setJobs] = useState(null);

  useEffect(() => {
    let isActive = true;
    getJobDescriptors()
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

export function AssignPioreactors({ experiment, variant="text" }) {
  const [workers, setWorkers] = React.useState([]);
  const [assigned, setAssigned] = React.useState({});
  const [initialAssigned, setInitialAssigned] = React.useState({});
  const [selectAll, setSelectAll] = React.useState(false);
  const [open, setOpen] = React.useState(false);
  const [assignmentError, setAssignmentError] = React.useState(null);
  const [isSubmittingAssignments, setIsSubmittingAssignments] = React.useState(false);
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

  function getAssignmentDeltaCounts(delta) {
    let assignedCount = 0;
    let unassignedCount = 0;

    for (const worker in delta) {
      if (delta[worker].current && !delta[worker].initial) {
        assignedCount += 1;
      } else {
        unassignedCount += 1;
      }
    }

    return { assignedCount, unassignedCount };
  }

  function getAssignmentDeltaLabel(delta) {
    const { assignedCount, unassignedCount } = getAssignmentDeltaCounts(delta);
    const labelParts = [];
    const totalCount = assignedCount + unassignedCount;

    if (unassignedCount > 0) {
      labelParts.push(`Unassign ${unassignedCount}`);
    }

    if (assignedCount > 0) {
      labelParts.push(`Assign ${assignedCount}`);
    }

    if (labelParts.length === 0) {
      return "No changes";
    }

    if (assignedCount > 0 && unassignedCount > 0) {
      return `Update ${totalCount}`;
    }

    return labelParts.join(", ");
  }

  const workersSelectableByBulkAction = useMemo(
    () => workers.filter((worker) => worker.experiment === null || worker.experiment === experiment),
    [experiment, workers]
  );

  const updateAssignments = async () => {
    const delta = compareObjects(assigned, initialAssigned);
    const requests = [];
    setAssignmentError(null);
    setIsSubmittingAssignments(true);

    for (const worker in delta) {
      if (delta[worker].current && !delta[worker].initial) {
        requests.push(fetch(`/api/experiments/${experimentPathSegment(experiment)}/workers`, {
          method: "PUT",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ pioreactor_unit: worker }),
        }));
      } else {
        requests.push(fetch(`/api/experiments/${experimentPathSegment(experiment)}/workers/${worker}`, {
          method: "DELETE",
        }));
      }
    }

    try {
      const responses = await Promise.all(requests);
      if (responses.some((response) => !response.ok)) {
        setAssignmentError("Some Pioreactor assignments could not be updated. Please refresh and try again.");
        return;
      }

      setOpen(false);
      navigate(0);
    } catch (_error) {
      setAssignmentError("Some Pioreactor assignments could not be updated. Please refresh and try again.");
    } finally {
      setIsSubmittingAssignments(false);
    }
  };

  const handleClickOpen = () => {
    setAssignmentError(null);
    setOpen(true);
  };

  const handleClose = () => {
    setAssignmentError(null);
    setOpen(false);
  };

  const handleChange = (event) => {
    setAssignmentError(null);
    setAssigned({
      ...assigned,
      [event.target.name]: event.target.checked,
    });
  };

  const handleSelectAllChange = (event) => {
    const newValue = event.target.checked;
    const newAssigned = { ...assigned };
    setAssignmentError(null);

    workersSelectableByBulkAction.forEach((worker) => {
      newAssigned[worker.pioreactor_unit] = newValue;
    });
    setAssigned(newAssigned);
    setSelectAll(newValue);
  };

  useEffect(() => {
    if (workersSelectableByBulkAction.length === 0) {
      setSelectAll(false);
      return;
    }

    const allSelected = workersSelectableByBulkAction.every((worker) => Boolean(assigned[worker.pioreactor_unit]));
    const noneSelected = workersSelectableByBulkAction.every((worker) => !Boolean(assigned[worker.pioreactor_unit]));
    setSelectAll(allSelected ? true : (noneSelected ? false : null));
  }, [assigned, workersSelectableByBulkAction]);

  const assignmentDelta = compareObjects(assigned, initialAssigned);
  const assignmentDeltaCount = Object.keys(assignmentDelta).length;
  const assignmentDeltaLabel = getAssignmentDeltaLabel(assignmentDelta);
  return (
    <React.Fragment>
      <Button variant={variant} sx={{ textTransform: "none" }} onClick={handleClickOpen}>
        <LibraryAddCheckOutlinedIcon
          fontSize="small"
          sx={{ verticalAlign: "middle", m: "0px 3px" }}
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
          <Typography component="div" gutterBottom>
            Assign and unassign Pioreactors to experiment{" "}
            <Chip icon={<PlayCircleOutlinedIcon/>} size="small" label={experiment} />.
          </Typography>
          {assignmentError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {assignmentError}
            </Alert>
          )}
          <FormControl sx={{ m: "auto" }} component="fieldset" variant="standard">
            <FormLabel component="legend">Pioreactors</FormLabel>
            {workersSelectableByBulkAction.length > 1 &&
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
                const worker_exp = worker.experiment;
                const assignedToAnotherExperiment = worker_exp !== null && worker_exp !== experiment;
                const isSelectedForAssignment = Boolean(assigned[unit]);
                const sublabel = assignedToAnotherExperiment
                  ? (
                    isSelectedForAssignment ? <>
                        Will be unassigned from{" "}
                        <Chip
                          icon={<PlayCircleOutlinedIcon/>}
                          size="small"
                          label={worker_exp}
                          clickable
                          component={Link}
                          onClick={() => selectExperiment(worker_exp)}
                          data-experiment-name={worker_exp}
                        />
                         {" "}and re-assigned to{" "}
                        <Chip
                          icon={<PlayCircleOutlinedIcon/>}
                          size="small"
                          label={experiment}
                          clickable
                          component={Link}
                          onClick={() => selectExperiment(experiment)}
                          data-experiment-name={experiment}
                        />
                      </>
                  : <>
                    Currently assigned to{" "}
                      <Chip
                        icon={<PlayCircleOutlinedIcon/>}
                        size="small"
                        label={worker_exp}
                        clickable
                        component={Link}
                        onClick={() => selectExperiment(worker_exp)}
                        data-experiment-name={worker_exp}
                      />
                  </>
                  )


                  : null;

                return (
                  <CustomFormControlLabel
                    key={unit}
                    control={
                      <Checkbox
                        onChange={handleChange}
                        checked={isSelectedForAssignment}
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
            disabled={assignmentDeltaCount === 0 || isSubmittingAssignments}
            sx={{ textTransform: "none" }}
          >
            {assignmentDeltaLabel}
          </Button>
        </DialogActions>
      </Dialog>
    </React.Fragment>
  );
}

function PioreactorHeader({experiment, config, units}) {
  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h1">
          <Box sx={{ fontWeight: "fontWeightBold" }}>
            Pioreactors
          </Box>
        </Typography>
        <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
          <ButtonStopProcess experiment={experiment}/>
          <AssignPioreactors experiment={experiment}/>
          <SettingsActionsDialogAll experiment={experiment} config={config} units={units}/>
          <Divider orientation="vertical" flexItem variant="middle"/>
          <ManageExperimentMenu experiment={experiment}/>
        </Box>
      </Box>
      <Divider sx={{mt: "0px", mb: "15px"}} />
    </Box>
  )
}



function SettingsActionsDialog({
  unit,
  experiment,
  jobs,
  setLabel,
  label,
  disabled,
  modelDetails,
  bioreactorValues,
  setBioreactorValues,
  settingsCollections,
}) {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState({})
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
  const selfTestSettings = jobs?.self_test?.publishedSettings || null;

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
    return Object.values(settingsCollections || {}).filter(job => job.metadata.display)
  }, [settingsCollections]);

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
    const baseTopic = `pioreactor/${unit}/${selfTestExperiment}/self_test`;
    const topics = [
      `${baseTopic}/$state`,
      ...Object.keys(selfTestSettings).map((key) => `${baseTopic}/${key}`),
    ];
    subscribeToTopic(topics, onSelfTestData, "ControlSelfTest");
    return () => {
      unsubscribeFromTopic(topics, "ControlSelfTest");
    };
  }, [client, onSelfTestData, open, selfTestSettings, selfTestExperiment, subscribeToTopic, unsubscribeFromTopic, unit]);
  useEffect(() => {
    if (!open){
      return
    }

    fetch(`/api/config/units/${unit}`).then((response) => {
      if (!response.ok) {
        return response.json().then((errorData) => {
          console.log(errorData)
          throw new Error(errorData.error);
        });
      }
      return response.json();
    })
    .then((data) => setConfig(data.configs[unit]))
    .catch((error) => {
      console.error("Fetching configuration failed:", error);
    });


  }, [open, unit]);

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
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
  }


  function updateRenameUnit(_, __, value) {
      const relabeledTo = value
      setSnackbarMessage(`Updating to ${relabeledTo}`)
      setSnackbarOpen(true)
      fetch(`/api/experiments/${experimentPathSegment(experiment)}/unit_labels`,{
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


  const LEDMap = config['leds'] || {}
  const buttons = Object.fromEntries(Object.entries(jobs || {}).map(([job_key, job]) => [job_key, createUserButtonsBasedOnState(job.state, job_key)]));
  const isXrModel = Boolean(modelDetails?.model_name?.toLowerCase().includes("xr"));

  const isLargeScreen = useMediaQuery(theme => theme.breakpoints.down('xl'));
  const dosingControlJob = jobs.dosing_automation;
  const ledControlJob = jobs.led_automation;
  const temperatureControlJob = jobs.temperature_automation;
  const dosingMaxVolume = getBioreactorConfirmedValue(
    bioreactorValues,
    config,
    "efflux_tube_volume_ml",
  );
  const dosingLiquidVolume = getBioreactorConfirmedValue(
    bioreactorValues,
    config,
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
    runPioreactorJob(unit, selfTestExperiment, "self_test")
      .then(() => {
        setSnackbarMessage(`Starting self test on ${unit}`);
        setSnackbarOpen(true);
      })
      .catch(() => {
        setSnackbarMessage(`Failed to start self test on ${unit}`);
        setSnackbarOpen(true);
      })
      .finally(() => {
        setSelfTestStartPending(false);
      });
  };

  return (
    <div>
    <Button sx={{textTransform: 'none', float: "right" }} disabled={disabled} onClick={handleClickOpen} color="primary">
      <SettingsIcon color={disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon}/> Control
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
        <Tab sx={{textTransform: 'none'}} label="Self-test"/>
      </Tabs>
      </DialogTitle>
      <DialogContent>
        <TabPanel value={tabValue} index={0}>
          {/* Unit Specific Activites */}
          {Object.entries(jobs)
            .filter(([_, job]) => job.metadata.display)
            .filter(([job_key]) => !['dosing_automation', 'led_automation', 'temperature_automation'].includes(job_key)) // added later
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
                      sx={{ ml: 0.5, height: 18, fontSize: "0.65rem", "& .MuiChip-label": { px: "5px" } }}
                    />
                  ) : null}
                </Typography>
                <StateTypography state={job.state}/>
              </Box>
              <Typography variant="caption" gutterBottom color="textSecondary" sx={{ display: "block" }}>
                {job.metadata.source !== "app" ? `Installed by ${job.metadata.source || "unknown"}` : ""}
              </Typography>
              <Typography variant="body2" component="div" gutterBottom>
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
            <Box sx={{justifyContent: "space-between", display: "flex"}}>
              <Typography sx={{ display: "block" }}>
                Temperature automation
              </Typography>
              <StateTypography state={temperatureControlJob.state}/>
            </Box>

            <div key={temperatureControlJob.metadata.key}>
              {(temperatureControlJob.state === "ready") || (temperatureControlJob.state === "sleeping") || (temperatureControlJob.state === "init")
              ?<React.Fragment>
                <Typography variant="body2" component="div" gutterBottom>
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
                  configSections={config || {}}
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
                <Typography variant="body2" component="div" gutterBottom>
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
                  configSections={config || {}}
                  maxVolume={dosingMaxVolume}
                  liquidVolume={dosingLiquidVolume}
                  capacity={modelDetails.reactor_capacity_ml}
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
              maxVolume={dosingMaxVolume}
              liquidVolume={dosingLiquidVolume}
              capacity={modelDetails.reactor_capacity_ml}
              threshold={modelDetails.reactor_max_fill_volume_ml}
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
                <Typography variant="body2" component="div" gutterBottom>
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
                  configSections={config || {}}
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

          {editableSettingsGroups
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings]) => (
              Object.entries(settings)
                .filter(([_, setting]) => setting.display && setting.editable)
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
            unit={unit}
            experiment={experiment}
            job={jobs.add_media}
            currentVolumeMl={dosingLiquidVolume}
            maxWorkingVolumeMl={dosingMaxVolume}
            thresholdMl={modelDetails.reactor_max_fill_volume_ml}
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
            unit={unit}
            experiment={experiment}
            job={jobs.remove_waste}
            currentVolumeMl={dosingLiquidVolume}
            maxWorkingVolumeMl={dosingMaxVolume}
            thresholdMl={modelDetails.reactor_max_fill_volume_ml}
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
            unit={unit}
            experiment={experiment}
            job={jobs.add_alt_media}
            currentVolumeMl={dosingLiquidVolume}
            maxWorkingVolumeMl={dosingMaxVolume}
            thresholdMl={modelDetails.reactor_max_fill_volume_ml}
          />


        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['A']) ? (LEDMap['A'].replace("_", " ").replace("led", "LED")) : "Channel A" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['A']) ? "Channel A" : ""}
          </Typography>
          <ActionLEDForm experiment={experiment} channel="A" unit={unit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['B']) ? (LEDMap['B'].replace("_", " ").replace("led", "LED")) : "Channel B" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['B']) ? "Channel B" : ""}
          </Typography>
          <ActionLEDForm experiment={experiment} channel="B" unit={unit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['C']) ? (LEDMap['C'].replace("_", " ").replace("led", "LED")) : "Channel C" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['C']) ? "Channel C" : ""}
          </Typography>

          <ActionLEDForm experiment={experiment} channel="C" unit={unit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            {(LEDMap['D']) ? (LEDMap['D'].replace("_", " ").replace("led", "LED")) : "Channel D" }
          </Typography>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} color="textSecondary">
            {(LEDMap['D']) ? "Channel D" : ""}
          </Typography>
          <ActionLEDForm experiment={experiment} channel="D" unit={unit} />
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
              disabled={isSelfTestRunning || selfTestStartPending || !selfTestSettings}
              onClick={handleRunSelfTest}
              sx={{textTransform: "none"}}
            >
              {isSelfTestRunning ? "Running" : "Start"}
            </Button>

          </Box>

          <ControlDivider/>

          {!selfTestSettings && (
            <Alert severity="warning">
              Self-test is unavailable on this Pioreactor.
            </Alert>
          )}

          {selfTestSettings && (
            <Accordion defaultExpanded disableGutters sx={{boxShadow: "none", "&:before": {display: "none"}}}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{display: "flex", alignItems: "center", gap: 1}}>
                  {renderSelfTestSummaryIcon()}
                  <Typography>{label ? `${label} / ${unit}` : unit}</Typography>
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                {availableSelfTestGroups.length === 0 ? (
                  <Typography variant="body2">No self-test checks available.</Typography>
                ) : (
                  <>
                    {availableSelfTestGroups.map((group) => (
                      <List
                        key={`self-test-${unit}-${group.title}`}
                        dense
                        disablePadding
                        subheader={
                          <ListSubheader sx={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                            {group.title}
                          </ListSubheader>
                        }
                      >
                        {group.tests.map((test) => (
                          <ListItem key={`self-test-${unit}-${test.key}`} sx={{pt: 0, pb: 0}}>
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
          )}
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


function SettingsActionsDialogAll({experiment, config, units = []}) {
  const broadcastUnit = "$broadcast"
  const [open, setOpen] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [tabValue, setTabValue] = useState(0);
  const [jobs, setJobs] = useState({});
  const [settingsDescriptors, setSettingsDescriptors] = useState([]);
  const [bioreactorValues, setBioreactorValues] = useState({});
  const [selfTestResults, setSelfTestResults] = useState({});
  const [selfTestStartPending, setSelfTestStartPending] = useState(false);
  const [relabelMap, setRelabelMap] = useState({});
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = useState(false);
  const [openChangeDosingDialog, setOpenChangeDosingDialog] = useState(false);
  const [openChangeLEDDialog, setOpenChangeLEDDialog] = useState(false);
  const {client, subscribeToTopic, unsubscribeFromTopic} = useMQTT();
  const contribJobsList = useContribJobsList();
  const selfTestExperiment = "$experiment";
  const assignedUnits = useMemo(() => units || [], [units]);
  const assignedUnitNames = useMemo(
    () => assignedUnits.map((worker) => worker?.pioreactor_unit).filter(Boolean),
    [assignedUnits]
  );
  const assignedUnitSet = useMemo(
    () => new Set(assignedUnitNames),
    [assignedUnitNames]
  );

  useEffect(() => {
    if (!Array.isArray(contribJobsList)) {
      return;
    }
    setJobs(buildJobsStateFromDescriptors(contribJobsList, { initialState: null }));
  }, [contribJobsList]);

  useEffect(() => {
    let isCancelled = false

    getSettingsDescriptors()
      .then((descriptors) => {
        if (!isCancelled) {
          setSettingsDescriptors(descriptors)
        }
      })
      .catch(() => {})

    return () => {
      isCancelled = true
    }
  }, [])

  useEffect(() => {
    if (experiment) {
      getRelabelMap(setRelabelMap, experiment);
    }
  }, [experiment]);

  const selfTestDefinition = useMemo(() => {
    if (!Array.isArray(contribJobsList)) {
      return null;
    }
    return contribJobsList.find((job) => job.job_name === "self_test") || null;
  }, [contribJobsList]);

  const selfTestSettingTypes = useMemo(() => {
    if (!selfTestDefinition) {
      return {};
    }
    return selfTestDefinition.published_settings.reduce((acc, field) => {
      acc[field.key] = field.type;
      return acc;
    }, {});
  }, [selfTestDefinition]);

  const availableSelfTestGroups = useMemo(
    () => getAvailableSelfTestGroupsFromDefinition(selfTestDefinition),
    [selfTestDefinition]
  );
  const bioreactorSettingsGroup = useMemo(
    () => buildBioreactorSettingsCollection(
      settingsDescriptors.find((descriptor) => descriptor.key === "bioreactor")?.published_settings || [],
      bioreactorValues,
      config,
      null,
      { valueMode: "blank" },
    ),
    [settingsDescriptors, bioreactorValues, config]
  );
  const passiveSettingsCollections = useMemo(
    () => buildSettingsCollectionsFromDescriptors(
      settingsDescriptors.filter((descriptor) => descriptor.key !== "bioreactor"),
    ),
    [settingsDescriptors],
  );
  const settingsCollections = useMemo(
    () => mergeSettingsCollections(jobs, passiveSettingsCollections, bioreactorSettingsGroup),
    [bioreactorSettingsGroup, jobs, passiveSettingsCollections],
  );
  const editableSettingsGroups = useMemo(() => {
    return Object.values(settingsCollections).filter(job => job.metadata.display)
  }, [settingsCollections]);

  const buildSelfTestBaseline = useCallback(() => {
    const publishedSettings = {};
    if (!selfTestDefinition) {
      return { state: null, publishedSettings };
    }
    for (const field of selfTestDefinition.published_settings) {
      publishedSettings[field.key] = {
        value: field.default ?? null,
        type: field.type,
        label: field.label,
      };
    }
    return { state: null, publishedSettings };
  }, [selfTestDefinition]);

  useEffect(() => {
    if (!selfTestDefinition) {
      return;
    }
    setSelfTestResults((prev) => {
      const next = { ...prev };
      const unitSet = new Set(assignedUnitNames);

      for (const existingUnit of Object.keys(next)) {
        if (!unitSet.has(existingUnit)) {
          delete next[existingUnit];
        }
      }

      for (const unitName of assignedUnitNames) {
        if (!next[unitName]) {
          next[unitName] = buildSelfTestBaseline();
          continue;
        }
        const currentSettings = { ...next[unitName].publishedSettings };
        for (const field of selfTestDefinition.published_settings) {
          if (!(field.key in currentSettings)) {
            currentSettings[field.key] = {
              value: field.default ?? null,
              type: field.type,
              label: field.label,
            };
          }
        }
        next[unitName] = {
          ...next[unitName],
          publishedSettings: currentSettings,
        };
      }
      return next;
    });
  }, [assignedUnitNames, buildSelfTestBaseline, selfTestDefinition]);

  const onSelfTestData = useCallback((topic, message) => {
    if (!topic || !message) {
      return;
    }
    const parts = topic.toString().split('/');
    if (parts.length < 5) {
      return;
    }
    const unitName = parts[1];
    const job = parts[3];
    const setting = parts[4];
    if (job !== "self_test" || !assignedUnitSet.has(unitName)) {
      return;
    }
    if (setting === "$state") {
      setSelfTestResults((prev) => {
        const current = prev[unitName] || buildSelfTestBaseline();
        return { ...prev, [unitName]: { ...current, state: message.toString() } };
      });
      return;
    }
    const payload = parsePayloadToType(message.toString(), selfTestSettingTypes[setting]);
    setSelfTestResults((prev) => {
      const current = prev[unitName] || buildSelfTestBaseline();
      const previousSetting = current.publishedSettings[setting] || {
        type: selfTestSettingTypes[setting],
      };
      return {
        ...prev,
        [unitName]: {
          ...current,
          publishedSettings: {
            ...current.publishedSettings,
            [setting]: {
              ...previousSetting,
              value: payload,
            },
          },
        },
      };
    });
  }, [assignedUnitSet, buildSelfTestBaseline, selfTestSettingTypes]);

  useEffect(() => {
    if (!open || !client || !selfTestDefinition || assignedUnitNames.length === 0) {
      return;
    }
    const topics = [];
    for (const unitName of assignedUnitNames) {
      const baseTopic = `pioreactor/${unitName}/${selfTestExperiment}/self_test`;
      topics.push(`${baseTopic}/$state`);
      for (const field of selfTestDefinition.published_settings) {
        topics.push(`${baseTopic}/${field.key}`);
      }
    }
    subscribeToTopic(topics, onSelfTestData, "ControlAllSelfTest");
    return () => {
      unsubscribeFromTopic(topics, "ControlAllSelfTest");
    };
  }, [assignedUnitNames, client, onSelfTestData, open, selfTestDefinition, selfTestExperiment, subscribeToTopic, unsubscribeFromTopic]);


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
    if (job === "bioreactor") {
      return updateBioreactorSettingAndMirrorState(
        broadcastUnit,
        experiment,
        setting,
        value,
        setBioreactorValues,
      )
    }

    fetch(`/api/workers/${broadcastUnit}/jobs/update/job_name/${job}/experiments/${experimentPathSegment(experiment)}`, {
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
        runPioreactorJob(broadcastUnit, experiment, job.metadata.key, [], {})
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


  const buttons = Object.fromEntries(Object.entries(jobs || {}).map(([job_key, job]) => [job_key, createUserButtonsBasedOnState(job)]))
  const isLargeScreen = useMediaQuery(theme => theme.breakpoints.down('xl'));
  var dosingControlJob = jobs.dosing_automation
  var ledControlJob = jobs.led_automation
  var temperatureControlJob = jobs.temperature_automation
  const sortedAssignedUnits = useMemo(() => {
    return [...assignedUnits]
      .filter((worker) => worker?.pioreactor_unit)
      .sort((a, b) => a.pioreactor_unit.localeCompare(b.pioreactor_unit));
  }, [assignedUnits]);

  const formatUnitLabel = (unitName) => {
    const customLabel = relabelMap[unitName];
    return customLabel ? `${customLabel} / ${unitName}` : unitName;
  };

  const isSelfTestRunningState = (state) =>
    ["init", "ready", "sleeping"].includes(state);

  const renderSelfTestIcon = (unitName, settingKey) => {
    const unitState = selfTestResults[unitName];
    const settingValue = unitState?.publishedSettings?.[settingKey]?.value;
    if (settingValue === true) {
      return <CheckIcon sx={{color: readyGreen}} />;
    }
    if (settingValue === false) {
      return <ErrorOutlineOutlinedIcon sx={{color: lostRed}} />;
    }
    if (isSelfTestRunningState(unitState?.state)) {
      return <CircularProgress size={18} />;
    }
    return <IndeterminateCheckBoxIcon sx={{color: disabledColor}} />;
  };

  const renderSelfTestSecondary = (unitName, test) => {
    if (test.secondaryKey !== "correlations_between_pds_and_leds") {
      return test.description || null;
    }
    const rawValue = selfTestResults[unitName]?.publishedSettings?.correlations_between_pds_and_leds?.value;
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

  const renderSelfTestSummaryIcon = (unitName) => {
    const unitState = selfTestResults[unitName];
    const overallStatus = unitState?.publishedSettings?.all_tests_passed?.value;
    if (overallStatus === true) {
      return <CheckIcon sx={{color: readyGreen}} />;
    }
    if (overallStatus === false) {
      return <ErrorOutlineOutlinedIcon sx={{color: lostRed}} />;
    }
    if (isSelfTestRunningState(unitState?.state)) {
      return <CircularProgress size={18} />;
    }
    return <IndeterminateCheckBoxIcon sx={{color: disabledColor}} />;
  };

  const isSelfTestRunning = useMemo(() => {
    if (assignedUnitNames.length === 0) {
      return false;
    }
    return assignedUnitNames.some((unitName) =>
      isSelfTestRunningState(selfTestResults[unitName]?.state)
    );
  }, [assignedUnitNames, selfTestResults]);

  const handleRunSelfTestAll = () => {
    setSelfTestStartPending(true);
    runPioreactorJob(broadcastUnit, experiment, "self_test")
      .then(() => {
        handleRunPioreactorJobResponse("self test");
      })
      .catch(() => {
        setSnackbarMessage("Failed to start self test on all assigned Pioreactors");
        setSnackbarOpen(true);
      })
      .finally(() => {
        setSelfTestStartPending(false);
      });
  };

  return (
    <React.Fragment>
    <Button sx={{textTransform: 'none', float: "right" }} onClick={handleClickOpen} color="primary">
      <SettingsIcon fontSize="small" sx={textIcon}/> Control all Pioreactors
    </Button>
    <Dialog  maxWidth={isLargeScreen ? "sm" : "md"} fullWidth={true}  open={open} onClose={handleClose} aria-labelledby="form-dialog-title" slotProps={{
      paper: {
        sx: {
          height: "calc(100% - 64px)"
        }
      }
    }}>
      <DialogTitle sx={{backgroundImage: "linear-gradient(to bottom left, rgba(83, 49, 202, 0.4), rgba(0,0,0,0))"}}>
        <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}}>
          <PioreactorsIcon sx={{verticalAlign: "middle", fontSize: "1.2em"}}/> <b>All assigned & active Pioreactors</b>
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
        <Tab sx={{textTransform: 'none'}} label="Self-test"/>
      </Tabs>
      </DialogTitle>
      <DialogContent>

        <TabPanel value={tabValue} index={0}>
          {Object.entries(jobs)
            .filter(([_, job]) => job.metadata.display)
            .filter(([job_key]) => !['dosing_automation', 'led_automation', 'temperature_automation'].includes(job_key))
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
            <Box sx={{justifyContent: "space-between", display: "flex"}}>
                <Typography sx={{ display: "block" }}>
                Temperature automation
              </Typography>
            </Box>
            <div>
              <Typography variant="body2" component="p" gutterBottom>
                <span dangerouslySetInnerHTML={{__html: temperatureControlJob.metadata.description}}/>
              </Typography>

              {buttons['temperature_automation']}
            </div>

            <ChangeAutomationsDialog
              open={openChangeTemperatureDialog}
              onFinished={() => setOpenChangeTemperatureDialog(false)}
              unit={broadcastUnit}
              experiment={experiment}
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
            </Box>
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
              unit={broadcastUnit}
              experiment={experiment}
              maxVolume={config?.bioreactor?.efflux_tube_volume_ml || 19}
              liquidVolume={config?.bioreactor?.initial_volume_ml || 10}
              threshold={39}
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
            </Box>
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
              unit={broadcastUnit}
              experiment={experiment}
            />
          </React.Fragment>
          }

          <ControlDivider/>

        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {editableSettingsGroups
            .map(job => [job.state, job.metadata.key, job.publishedSettings])
            .map(([state, job_key, settings]) => (
              Object.entries(settings)
                .filter(([_, setting]) => setting.display && setting.editable)
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

          <ActionCirculatingForm action="circulate_media" unit={broadcastUnit} experiment={experiment} />

          <ControlDivider/>

          <Typography  gutterBottom>
            Cycle alternative media
          </Typography>
          <Typography variant="body2" component="p">
            Safely cycle alternative media in and out of your Pioreactor for a set duration (seconds)  by running the alt-media pump periodically and waste pump continuously.
          </Typography>

          <ActionCirculatingForm action="circulate_alt_media" unit={broadcastUnit} experiment={experiment} />

          <ControlDivider/>

          <Alert severity="warning" sx={{mb: '10px', mt: '10px'}}>It's easy to overflow your vial. Make sure you don't add too much media.</Alert>

          <Typography  gutterBottom>
            Add media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the media pumps for a set duration (seconds), move a set volume (mL), or fill to each vial's maximum safe volume.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add media:
          </Typography>
          <ActionDosingForm experiment={experiment} action="add_media" unit={broadcastUnit} />
          <ControlDivider/>
          <Typography  gutterBottom>
            Remove waste
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the waste pumps for a set duration (seconds), moving a set volume (mL), or continuously remove until stopped.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to remove media:
          </Typography>
          <ActionDosingForm  experiment={experiment} action="remove_waste" unit={broadcastUnit} />
          <ControlDivider/>
          <Typography gutterBottom>
            Add alternative media
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run the alternative media pumps for a set duration (seconds), moving a set
            volume (mL), or fill to each vial's maximum safe volume.
          </Typography>
          <Typography variant="body2" component="p">
            Specify how you’d like to add alt-media:
          </Typography>
          <ActionDosingForm  experiment={experiment} action="add_alt_media" unit={broadcastUnit} />

        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Typography sx={{textTransform: "capitalize"}}>
            Channel A
          </Typography>
          <ActionLEDForm experiment={experiment} channel="A" unit={broadcastUnit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            Channel B
          </Typography>
          <ActionLEDForm experiment={experiment} channel="B" unit={broadcastUnit} />
          <ControlDivider/>

          <Typography sx={{textTransform: "capitalize"}}>
            Channel C
          </Typography>
          <ActionLEDForm experiment={experiment} channel="C" unit={broadcastUnit} />

          <ControlDivider/>
          <Typography sx={{textTransform: "capitalize"}}>
            Channel D
          </Typography>
          <ActionLEDForm experiment={experiment} channel="D" unit={broadcastUnit} />

          <ControlDivider/>
        </TabPanel>

        <TabPanel value={tabValue} index={4}>
          <Typography gutterBottom>
            Self-test
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Run a hardware self-test on all assigned Pioreactors. Results will update as each unit reports back.
          </Typography>
          <RequirementsAlert sx={{mb: 2, pb: 0}}>
            Add a closed vial, half-filled with water or media, and a stirbar into each Pioreactor.
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
              disabled={isSelfTestRunning || selfTestStartPending || assignedUnitNames.length === 0 || !selfTestDefinition}
              onClick={handleRunSelfTestAll}
              sx={{textTransform: "none"}}
            >
              {isSelfTestRunning ? "Running" : "Start"}
            </Button>
          </Box>

          <ControlDivider/>

          {!selfTestDefinition && Array.isArray(contribJobsList) && (
            <Alert severity="warning">
              Self-test is unavailable on this cluster.
            </Alert>
          )}

          {!selfTestDefinition && !Array.isArray(contribJobsList) && (
            <Box sx={{display: "flex", justifyContent: "center", mt: 2}}>
              <CircularProgress size={24} />
            </Box>
          )}

          {selfTestDefinition && assignedUnitNames.length === 0 && (
            <Typography variant="body2">
              No assigned Pioreactors to run a self-test.
            </Typography>
          )}

          {selfTestDefinition && assignedUnitNames.length > 0 && (
            <Box>
              {sortedAssignedUnits.map((worker) => {
                const unitName = worker.pioreactor_unit;
                return (
                  <Accordion
                    key={`self-test-${unitName}`}
                    disableGutters
                    sx={{boxShadow: "none", "&:before": {display: "none"}}}
                  >
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Box sx={{display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%"}}>
                        <Box sx={{display: "flex", alignItems: "center", gap: 1}}>
                          {renderSelfTestSummaryIcon(unitName)}
                          <Typography>{formatUnitLabel(unitName)}</Typography>
                        </Box>
                        {!worker.is_active && (
                          <Typography variant="body2" sx={{color: disabledColor}}>
                            Inactive
                          </Typography>
                        )}
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      {availableSelfTestGroups.length === 0 ? (
                        <Typography variant="body2">No self-test checks available.</Typography>
                      ) : (
                        <>
                          {availableSelfTestGroups.map((group) => (
                            <List
                              key={`${unitName}-${group.title}`}
                              dense
                              disablePadding
                              subheader={
                                <ListSubheader sx={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                                  {group.title}
                                </ListSubheader>
                              }
                            >
                              {group.tests.map((test) => (
                                <ListItem key={`${unitName}-${test.key}`} sx={{pt: 0, pb: 0}}>
                                  <ListItemIcon sx={{minWidth: "30px"}}>
                                    {renderSelfTestIcon(unitName, test.key)}
                                  </ListItemIcon>
                                  <ListItemText
                                    primary={test.label}
                                    secondary={renderSelfTestSecondary(unitName, test)}
                                  />
                                </ListItem>
                              ))}
                            </List>
                          ))}
                        </>
                      )}
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Box>
          )}
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
      key={"snackbar" + broadcastUnit + "settings"}
    />
    </React.Fragment>
  );
}


function ActiveUnits({experiment, sharedConfig, unitConfigs, units, availableModels}){
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
    const unitName = unit.pioreactor_unit;
    return <PioreactorCard key={unitName} isUnitActive={true} unit={unitName} modelDetails={modelDetails || {}} config={unitConfigs[unitName] || sharedConfig} experiment={experiment} initialLabel={relabelMap[unitName]}/>
  })

  return (
    <React.Fragment>
      <Box sx={{display: "flex", justifyContent: "space-between", mb: "10px", mt: "15px"}}>
        <Typography variant="h5" component="h2">
          <Box sx={{ fontWeight: "fontWeightRegular" }}>
            Active Pioreactors
          </Box>
        </Typography>
      </Box>
      {renderCards()}

    </React.Fragment>
)}


function FlashLEDButton({ unit, disabled }){
  const [flashing, setFlashing] = useState(false)

  const onClick = () => {
    setFlashing(false)
    requestAnimationFrame(() => setFlashing(true))
    fetch(`/api/workers/${unit}/blink`, {method: "POST"})
  }
  return (
    <Button
      sx={{textTransform: 'none', float: "right"}}
      className={flashing ? 'blinkled' : ''}
      disabled={disabled}
      onClick={onClick}
      onAnimationEnd={() => setFlashing(false)}
      color="primary"
    >
      <FlareIcon color={disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon}/> <span> Identify </span>
    </Button>
)}


export function PioreactorCard({unit, isUnitActive, experiment, config, initialLabel, modelDetails = {}}){
  const [jobDescriptorsStatus, setJobDescriptorsStatus] = useState("loading")
  const [jobDescriptorsErrorText, setJobDescriptorsErrorText] = useState("Job controls unavailable.")
  const [label, setLabel] = useState("")
  const [bioreactorValues, setBioreactorValues] = useState({})
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

  const monitorTopics = useMemo(() => {
    return getPioreactorCardMonitorTopics({
      unit,
      experiment,
    });
  }, [experiment, unit]);

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
    const parts = topicName.split('/');
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
      return "Inactive, change status in Inventory"
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
  const bioreactorSettingsGroup = useMemo(
    () => buildBioreactorSettingsCollection(bioreactorDescriptors, bioreactorValues, config, modelDetails),
    [bioreactorDescriptors, bioreactorValues, config, modelDetails]
  )
  const settingsCollections = useMemo(
    () => mergeSettingsCollections(jobs, passiveSettingsCollections, bioreactorSettingsGroup),
    [bioreactorSettingsGroup, jobs, passiveSettingsCollections],
  )
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
            <Box sx={{display: "flex", justifyContent: "left", mt: "3px"}}>
              <Tooltip title={indicatorLabel} placement="left">
                <div className="indicator-dot-beside-button" style={{boxShadow: `0 0 ${indicatorDotShadow}px ${indicatorDotColor}, inset 0 0 12px  ${indicatorDotColor}`}}/>
              </Tooltip>
              <PioreactorIconWithModel badgeContent={modelBadgeContent} color={isUnitActive ? undefined : disabledColor} />
              <Typography sx={{
                  fontSize: 20,
                  color: "rgba(0, 0, 0, 0.87)",
                  fontWeight: 500,
                  ...(isUnitActive ? {} : { color: disabledColor }),
                }}
                gutterBottom>
                {(label ) ? label : unit }
              </Typography>
              <Button disabled={!isUnitActive} component={Link} to={`/pioreactors/${unit}`} sx={{padding: "0px 8px", mb: "7px", ml: 1, textTransform: "none", ...(isUnitActive ? {} : { color: disabledColor }),}}>
                View details <ArrowForwardIcon sx={{ verticalAlign: "middle", ml: 0.5 }} fontSize="small"/>
              </Button>
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
          <Typography variant="body2" component={'span'}>
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
                <Box sx={{width: "132px", ml: "2px", mt: "10px", mr: "2px", p: "0px 3px"}} key={job.metadata.key}>
                  <Typography variant="body2"  sx={{fontSize: "0.84rem",  color: !isUnitActive ? disabledColor : 'inherit' }}>
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
        <Box sx={{width: "100px", mt: "10px", mr: "5px"}}>
          <Typography variant="body2" component={'span'}>
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
                    <Box sx={{width: "132px", ml: "2px", mt: "10px", mr: "2px", p: "0px 3px"}} key={job_key + setting_key}>
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


function InactiveUnits({ units, sharedConfig, unitConfigs, experiment, availableModels }){
  const [relabelMap, setRelabelMap] = useState({})

  useEffect(() => {
    if (experiment) {
      getRelabelMap(setRelabelMap, experiment)
    }
  }, [experiment])

  return (
  <React.Fragment>
    <Box sx={{display: "flex", justifyContent: "space-between", mb: "10px", mt: "15px"}}>
      <Typography variant="h5" component="h2">
        <Box sx={{ fontWeight: "fontWeightRegular" }}>
          Inactive Pioreactors
        </Box>
      </Typography>
    </Box>
    {(units || []).map((unit) => {
      const modelDetails = (availableModels || []).find(
        ({ model_name, model_version }) => model_name === unit.model_name && model_version === unit.model_version
      );
      const unitName = unit.pioreactor_unit || unit.pioreactor_name;
      return (
        <PioreactorCard
          key={unitName}
          isUnitActive={false}
          unit={unitName}
          initialLabel={relabelMap[unitName]}
          modelDetails={modelDetails || {}}
          config={unitConfigs[unitName] || sharedConfig}
          experiment={experiment}
        />
      );
    })}
    </React.Fragment>
)}

function Pioreactors({title}) {
  const { experimentMetadata } = useExperiment();
  const [workers, setWorkers] = useState([]);
  const [sharedConfig, setSharedConfig] = useState({})
  const [unitConfigs, setUnitConfigs] = useState({})
  const [isLoading, setIsLoading] = useState(true);
  const [availableModels, setAvailableModels] = useState([]);
  const [modelCheckKey, setModelCheckKey] = useState(0);
  const emptyStateIllustration = useMemo(() => {
    const randomIndex = Math.floor(Math.random() * EMPTY_STATE_ILLUSTRATIONS.length);
    return EMPTY_STATE_ILLUSTRATIONS[randomIndex];
  }, []);

  useEffect(() => {
    document.title = title;
    getConfig(setSharedConfig)
  }, [title]);

  useEffect(() => {
    let isCancelled = false;

    if (!experimentMetadata.experiment) {
      setWorkers([]);
      setIsLoading(false);
      return () => {
        isCancelled = true;
      };
    }

    setIsLoading(true);
    setWorkers([]);
    fetch(`/api/experiments/${experimentPathSegment(experimentMetadata.experiment)}/workers`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to fetch workers: ${response.statusText}`);
        }
        return response.json();
      })
      .then((data) => {
        if (!isCancelled) {
          setWorkers(data);
        }
      })
      .catch((error) => {
        if (!isCancelled) {
          console.error("Fetching workers failed:", error);
        }
      })
      .finally(() => {
        if (!isCancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [experimentMetadata.experiment]);

  useEffect(() => {
    fetch('/api/models')
      .then((r) => r.json())
      .then((data) => setAvailableModels(data.models))
  }, []);

  useEffect(() => {
    let isCancelled = false;

    if (workers.length === 0) {
      setUnitConfigs({});
      return () => {
        isCancelled = true;
      };
    }

    const unitNames = [...new Set(workers
      .map((worker) => worker.pioreactor_unit || worker.pioreactor_name)
      .filter(Boolean))];
    const query = new URLSearchParams(unitNames.map((unitName) => ["unit", unitName]));

    fetch(`/api/config/units/$broadcast?${query}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to fetch unit configurations: ${response.statusText}`);
        }
        return response.json();
      })
      .then((data) => {
        if (isCancelled) {
          return;
        }

        const nextUnitConfigs = {};
        for (const unitName of unitNames) {
          if (data.configs?.[unitName]) {
            nextUnitConfigs[unitName] = data.configs[unitName];
          }
          if (data.errors?.[unitName]) {
            console.error(`Fetching unit configuration failed for ${unitName}:`, data.errors[unitName]);
          }
        }

        setUnitConfigs(nextUnitConfigs);
      })
      .catch((error) => {
        if (isCancelled) {
          return;
        }

        setUnitConfigs({});
        console.error("Fetching unit configurations failed:", error);
      });

    return () => {
      isCancelled = true;
    };
  }, [workers]);

  const workersMissingModel = workers.some(workerMissingModelDetails);

  useEffect(() => {
    if (workersMissingModel) {
      setModelCheckKey((key) => key + 1);
    }
  }, [workersMissingModel]);

  const renderCards = () => {
      const activeUnits = workers.filter(worker => worker.is_active === 1);
      const inactiveUnits = workers.filter(worker => worker.is_active === 0);
      return (
      <>
      <ActiveUnits experiment={experimentMetadata.experiment} sharedConfig={sharedConfig} unitConfigs={unitConfigs} availableModels={availableModels} units={activeUnits} />
      { (inactiveUnits.length > 0) &&
      <InactiveUnits experiment={experimentMetadata.experiment} sharedConfig={sharedConfig} unitConfigs={unitConfigs} availableModels={availableModels} units={inactiveUnits}/>
      }
      </>
    )
  }
  const renderEmptyState = () => (
    <Box sx={{textAlign: "center"}}>
      {isLoading ? <CircularProgress /> : (
      <>
      <Box component="img"
        alt="filler illustration for no pioreactor assigned"
        src={emptyStateIllustration}
        sx={{width: "420px", opacity: 0.8, mb: "8px"}}
      />
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
    <>
      {modelCheckKey > 0 && <MissingWorkerModelModal triggerCheckKey={modelCheckKey} />}
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <PioreactorHeader experiment={experimentMetadata.experiment} config={sharedConfig} units={workers}/>

          {(workers.length === 0 ? renderEmptyState() : renderCards())}

        </Grid>
      </Grid>
    </>
  );
}

export default Pioreactors;
