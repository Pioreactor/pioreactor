import dayjs from "dayjs";
import React from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Switch from "@mui/material/Switch";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import { Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CancelIcon from "@mui/icons-material/Cancel";
import CloseIcon from "@mui/icons-material/Close";
import TuneIcon from "@mui/icons-material/Tune";
import { styled } from "@mui/material/styles";
import { useConfirm } from "material-ui-confirm";
import { Link } from "react-router";

import EstimatorIcon from "./EstimatorIcon";
import PatientButton from "./PatientButton";
import PioreactorIcon from "./PioreactorIcon";
import UnderlineSpan from "./UnderlineSpan";
import {
  getBioreactorSubscriptionTopics,
  parseNumericValue,
  updateBioreactorValues,
} from "../utils/bioreactor";
import {
  defaultStateDisplayBackground,
  disabledColor,
  disconnectedGrey,
  stateDisplay,
} from "../utils/color";
import {
  getPublishedSettingsTopicsFromSignature,
  runPioreactorJob,
} from "../utils/jobs";
import { fetchTaskResult, getUnitTaskResult } from "../utils/tasks";
import { experimentPathSegment } from "../utils/url";

export const TOPIC_SIGNATURE_SEPARATOR = "\u0000";
export const textIcon = { verticalAlign: "middle", margin: "0px 3px" };

export function getPioreactorCardMonitorTopics({
  unit,
  experiment,
  monitorSettingsSignature,
}) {
  if (!unit || !experiment) {
    return [];
  }

  const topics = [`pioreactor/${unit}/$experiment/monitor/$state`];
  const monitorSettings = monitorSettingsSignature
    ? monitorSettingsSignature.split(TOPIC_SIGNATURE_SEPARATOR)
    : [];

  for (const setting of monitorSettings) {
    if (setting) {
      topics.push(["pioreactor", unit, "$experiment", "monitor", setting].join("/"));
    }
  }
  return topics;
}

export function getPioreactorCardPublishedSettingsTopics(signature, {
  unit,
  experiment,
  includeState = false,
}) {
  return getPublishedSettingsTopicsFromSignature(signature, {
    unit,
    experiment,
    includeState,
    separator: TOPIC_SIGNATURE_SEPARATOR,
  });
}

export function getPioreactorCardBioreactorTopics({
  unit,
  experiment,
  bioreactorTopicsSignature,
}) {
  if (!unit || !experiment || !bioreactorTopicsSignature) {
    return [];
  }

  return getBioreactorSubscriptionTopics(
    unit,
    experiment,
    bioreactorTopicsSignature.split(TOPIC_SIGNATURE_SEPARATOR),
  );
}

export function ButtonStopProcess({ experiment, unit = "$broadcast", disabled = false }) {
  const confirm = useConfirm();
  const description = unit === "$broadcast"
    ? "This will immediately stop all running activities in assigned Pioreactor units, and any experiment profiles running for this experiment. Do you wish to continue?"
    : `This will immediately stop all running activities on ${unit}, and any experiment profiles running for this experiment on this Pioreactor. Do you wish to continue?`;

  const handleClick = () => {
    confirm({
      description,
      title: unit === "$broadcast" ? "Stop all activities in all assigned Pioreactors?" : `Stop all activities in ${unit}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: { autoFocus: true, variant: "contained", color: "primary", sx: { textTransform: "none" } },
      cancellationButtonProps: { color: "secondary", sx: { textTransform: "none" } },
    }).then(() =>
      fetch(`/api/workers/${unit}/jobs/stop/experiments/${experimentPathSegment(experiment)}`, { method: "POST" })
    ).catch(() => {});
  };

  return (
    <Button sx={{ textTransform: "none", float: "right" }} color="secondary" disabled={disabled} onClick={handleClick}>
      <CancelIcon fontSize="small" sx={textIcon} /> {unit === "$broadcast" ? "Stop all Pioreactors" : "Stop"}
    </Button>
  );
}

export function CalibrateDialog({
  unit,
  experiment,
  odBlankReading,
  odBlankJobState,
  growthRateJobState,
  disabled,
  label,
}) {
  const [open, setOpen] = React.useState(false);
  const [tabValue, setTabValue] = React.useState(0);
  const [activeCalibrations, setActiveCalibrations] = React.useState({});
  const [loadingCalibrations, setLoadingCalibrations] = React.useState(false);
  const [activeEstimators, setActiveEstimators] = React.useState({});
  const [loadingEstimators, setLoadingEstimators] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;

    setLoadingCalibrations(true);
    setLoadingEstimators(true);

    const apiUrl = `/api/workers/${unit}/active_calibrations`;
    const estimatorsUrl = `/api/workers/${unit}/active_estimators`;

    const fetchCalibrations = async () => {
      try {
        const data = await fetchTaskResult(apiUrl, { delayMs: 2000 });
        setActiveCalibrations(getUnitTaskResult(data, unit, "Failed to fetch calibration."));
        setLoadingCalibrations(false);
      } catch (err) {
        console.error("Failed to fetch calibration:", err);
        setLoadingCalibrations(false);
      }
    };

    const fetchEstimators = async () => {
      try {
        const data = await fetchTaskResult(estimatorsUrl, { delayMs: 2000 });
        setActiveEstimators(getUnitTaskResult(data, unit, "Failed to fetch estimators."));
        setLoadingEstimators(false);
      } catch (err) {
        console.error("Failed to fetch estimators:", err);
        setLoadingEstimators(false);
      }
    };

    fetchCalibrations();
    fetchEstimators();
  }, [open, unit]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setTimeout(() => setTabValue(0), 200);
  };

  function createUserButtonsBasedOnState(jobState, job, alwaysDisable = false) {
    switch (jobState) {
      case "ready":
      case "init":
      case "sleeping":
        return (
          <div>
            <PatientButton
              color="primary"
              variant="contained"
              buttonText="Running"
              disabled={true || alwaysDisable}
            />
          </div>
        );
      default:
        return (
          <div>
            <PatientButton
              color="primary"
              variant="contained"
              onClick={() => runPioreactorJob(unit, experiment, job)}
              buttonText="Start"
              disabled={alwaysDisable}
            />
          </div>
        );
    }
  }

  const isGrowRateJobRunning = growthRateJobState === "ready";
  const hasActiveODCalibration = Object.keys(activeCalibrations || {}).some((device) => device.startsWith("od"));
  const blankODButton = createUserButtonsBasedOnState(
    odBlankJobState,
    "od_blank",
    isGrowRateJobRunning || hasActiveODCalibration,
  );
  const activeEstimatorEntries = Object.entries(activeEstimators || {}).filter(([, estimator]) => estimator?.is_active);

  return (
    <React.Fragment>
      <Button sx={{ textTransform: "none", float: "right" }} color="primary" disabled={disabled} onClick={handleClickOpen}>
        <TuneIcon color={disabled ? "disabled" : "primary"} fontSize="small" sx={textIcon} /> Calibrate
      </Button>
      <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title">
        <DialogTitle>
          <Typography sx={{ fontSize: "13px", color: "rgba(0, 0, 0, 0.60)" }}>
            <PioreactorIcon sx={{ verticalAlign: "middle", fontSize: "1.2em" }} /> {label ? `${label} / ${unit}` : `${unit}`}
          </Typography>
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            indicatorColor="primary"
            textColor="primary"
          >
            <Tab sx={{ textTransform: "none" }} label="Calibrations" />
            <Tab sx={{ textTransform: "none" }} label="Estimators" />
            <Tab sx={{ textTransform: "none" }} label="Blanks" />
          </Tabs>
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
          <TabPanel value={tabValue} index={2}>
            <Typography gutterBottom>
              Record optical densities of blank (optional)
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
              For more accurate growth rate and biomass inferences, the Pioreactor can subtract out the
              media&apos;s <i>un-inoculated</i> optical density <i>per experiment</i>. Read more about <a href="https://docs.pioreactor.com/user-guide/od-normal-growth-rate#blanking">using blanks</a>. If your Pioreactor has an active OD calibration, this isn&apos;t required.
            </Typography>
            <Typography variant="body2" component="p" sx={{ m: "20px 0px" }}>
              Recorded optical densities of blank vial: <code>{odBlankReading ? Object.entries(JSON.parse(odBlankReading)).map(([k, v]) => `${k}:${v.toFixed(5)}`).join(", ") : "—"}</code>
            </Typography>

            <Box sx={{ display: "flex" }}>
              {hasActiveODCalibration ? (
                <UnderlineSpan title="If an active OD calibration is present, this isn't used.">
                  {blankODButton}
                </UnderlineSpan>
              ) : (
                <div>
                  {blankODButton}
                </div>
              )}
              <div>
                <Button
                  size="small"
                  sx={{ width: "70px", mt: "5px", height: "31px", mr: "3px" }}
                  color="secondary"
                  disabled={(odBlankReading === null) || isGrowRateJobRunning}
                  onClick={() => runPioreactorJob(unit, experiment, "od_blank", ["delete"])}
                >
                  Clear
                </Button>
              </div>
            </Box>
            <ControlDivider />
          </TabPanel>
          <TabPanel value={tabValue} index={1}>
            <Typography gutterBottom>
              Active estimators
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
              Below are the active estimators that will be used when interpreting measurements on this Pioreactor. Read more about{" "}
              <a href="https://docs.pioreactor.com/user-guide/estimators">estimators</a>.
            </Typography>
            {loadingEstimators ? (
              <Box sx={{ textAlign: "center", mt: "2rem" }}>
                <CircularProgress />
              </Box>
            ) : activeEstimatorEntries.length === 0 ? (
              <Typography variant="body2" component="p" color="textSecondary" sx={{ mt: 3 }}>
                There are no active estimators available.
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell align="left" sx={{ padding: "6px 0px" }}>Device</TableCell>
                    <TableCell align="left" sx={{ padding: "6px 0px" }}>Estimator name</TableCell>
                    <TableCell align="left" sx={{ padding: "6px 0px" }}>Created on</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {activeEstimatorEntries.map(([device, estimator]) => {
                    const estimatorName = estimator.estimator_name;
                    return (
                      <TableRow key={`${estimatorName}-${device}`}>
                        <TableCell align="left" sx={{ padding: "6px 0px" }}>
                          {device}
                        </TableCell>
                        <TableCell align="left" sx={{ padding: "6px 0px" }}>
                          <Chip
                            size="small"
                            icon={<EstimatorIcon />}
                            label={estimatorName}
                            data-estimator-name={estimatorName}
                            data-device={device}
                            sx={{ maxWidth: "300px" }}
                            clickable
                            component={Link}
                            to={`/estimators/${unit}/${device}/${estimatorName}`}
                          />
                        </TableCell>
                        <TableCell align="left" sx={{ padding: "6px 0px" }}>
                          {dayjs(estimator.created_at).format("YYYY-MM-DD")}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </TabPanel>
          <TabPanel value={tabValue} index={0}>
            <Typography gutterBottom>
              Active calibrations
            </Typography>
            <Typography variant="body2" component="p" gutterBottom>
              Below are the active calibrations that will be used when running devices like pumps, stirring, etc. Read more about{" "}
              <a href="https://docs.pioreactor.com/user-guide/hardware-calibrations">calibrations</a>.
            </Typography>
            {loadingCalibrations ? (
              <Box sx={{ textAlign: "center", mt: "2rem" }}>
                <CircularProgress />
              </Box>
            ) : Object.entries(activeCalibrations || {}).length === 0 ? (
              <Typography variant="body2" component="p" color="textSecondary" sx={{ mt: 3 }}>
                There are no active calibrations available.
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell align="left" sx={{ padding: "6px 0px" }}>Device</TableCell>
                    <TableCell align="left" sx={{ padding: "6px 0px" }}>Calibration name</TableCell>
                    <TableCell align="left" sx={{ padding: "6px 0px" }}>Calibrated on</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(activeCalibrations).map(([device, calibration]) => {
                    const calName = calibration.calibration_name;
                    return (
                      <TableRow key={`${calName}-${device}`}>
                        <TableCell align="left" sx={{ padding: "6px 0px" }}>
                          {device}
                        </TableCell>
                        <TableCell align="left" sx={{ padding: "6px 0px" }}>
                          <Chip
                            size="small"
                            icon={<TuneIcon />}
                            label={calName}
                            data-calibration-name={calName}
                            data-device={device}
                            clickable
                            component={Link}
                            sx={{ maxWidth: "300px" }}
                            to={`/calibrations/${unit}/${device}/${calName}`}
                          />
                        </TableCell>
                        <TableCell align="left" sx={{ padding: "6px 0px" }}>
                          {dayjs(calibration.created_at).format("YYYY-MM-DD")}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </TabPanel>
        </DialogContent>
      </Dialog>
    </React.Fragment>
  );
}

export const DisplaySettingsTable = styled("span")(() => ({
  width: "55px",
  display: "inline-block",
}));

export const ControlDivider = styled(Divider)(({ theme }) => ({
  marginTop: theme.spacing(2),
  marginBottom: theme.spacing(1.25),
}));

export const RowOfUnitSettingDisplayBox = styled(Box)(() => ({
  display: "flex",
  flexDirection: "row",
  flexWrap: "wrap",
  justifyContent: "flex-start",
  alignItems: "stretch",
  alignContent: "stretch",
}));

export const getFauxChipHoverSx = (isInteractive) => ({
  transition: (theme) => theme.transitions.create(["background-color", "box-shadow"], {
    duration: theme.transitions.duration.shortest,
  }),
  ...(isInteractive ? {
    "&:hover": {
      backgroundColor: (theme) =>
        theme.alpha(
          theme.palette.action.selected,
          `${theme.palette.action.selectedOpacity} + ${theme.palette.action.hoverOpacity}`,
        ),
    },
    "&:active": {
      boxShadow: (theme) => theme.shadows[1],
    },
  } : {}),
});

export function StateTypography({ state, isDisabled = false, isInteractive = false }) {
  const stateInfo = stateDisplay[state] || {
    display: state || "Unknown",
    color: disconnectedGrey,
    backgroundColor: defaultStateDisplayBackground,
  };

  const style = {
    color: isDisabled ? disabledColor : stateInfo.color,
    padding: "1px 9px",
    borderRadius: "16px",
    backgroundColor: stateInfo.backgroundColor,
    display: "inline-block",
    fontWeight: 500,
    ...getFauxChipHoverSx(isInteractive),
  };

  return (
    <Typography gutterBottom sx={{ ...style, display: "block" }}>
      {stateInfo.display}
    </Typography>
  );
}

export function DescriptorStatusMessage({ status, errorText = "Job controls unavailable." }) {
  if (status === "loading") {
    return (
      <Box sx={{ display: "flex", alignItems: "center", minHeight: "32px" }}>
        <CircularProgress size={18} />
      </Box>
    );
  }

  if (status === "error") {
    return (
      <Typography variant="body2" sx={{ color: disabledColor, mt: "10px" }}>
        {errorText}
      </Typography>
    );
  }

  return null;
}

export function TabPanel({ children, value, index, ...other }) {
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

export function parsePayloadToType(payloadString, typeOfSetting) {
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

export function updateBioreactorSettingAndMirrorState(
  unit,
  experiment,
  setting,
  value,
  setBioreactorValues,
) {
  return updateBioreactorValues(unit, experiment, { [setting]: value }).then(() => {
    const parsedValue = parseNumericValue(value);
    if (parsedValue !== null) {
      setBioreactorValues?.((previous) => ({
        ...previous,
        [setting]: parsedValue,
      }));
    }
  });
}

const SELF_TEST_GROUPS = [
  {
    title: "LEDs & photodiodes",
    tests: [
      { key: "test_pioreactor_HAT_present", label: "Pioreactor HAT is detected" },
      {
        key: "test_all_positive_correlations_between_pds_and_leds",
        label: "Photodiodes are responsive to IR LED",
        secondaryKey: "correlations_between_pds_and_leds",
      },
      { key: "test_ambient_light_interference", label: "No ambient IR light detected" },
      {
        key: "test_dark_offset_correction_is_effective",
        label: "Dark offset correction returns photodiodes to baseline",
      },
      { key: "test_REF_is_lower_than_0_dot_256_volts", label: "Reference photodiode is correct magnitude" },
      { key: "test_REF_is_in_correct_position", label: "Reference photodiode is in correct position" },
      { key: "test_PD_is_near_0_volts_for_blank", label: "Photodiode measures near zero signal for clear water" },
    ],
  },
  {
    title: "Heating & temperature",
    tests: [
      { key: "test_detect_heating_pcb", label: "Heating PCB is detected" },
      { key: "test_positive_correlation_between_temperature_and_heating", label: "Heating is responsive" },
    ],
  },
  {
    title: "Stirring",
    tests: [
      { key: "test_positive_correlation_between_rpm_and_stirring", label: "Stirring RPM is responsive" },
      { key: "test_aux_power_is_not_too_high", label: "AUX power supply is appropriate value" },
    ],
  },
];

function getAvailableSelfTestGroupsForKeys(keys) {
  const availableKeys = new Set(keys);
  return SELF_TEST_GROUPS
    .map((group) => ({
      ...group,
      tests: group.tests.filter((test) => availableKeys.has(test.key)),
    }))
    .filter((group) => group.tests.length > 0);
}

export function getAvailableSelfTestGroupsFromSettings(selfTestSettings) {
  if (!selfTestSettings) {
    return [];
  }
  return getAvailableSelfTestGroupsForKeys(Object.keys(selfTestSettings));
}

export function getAvailableSelfTestGroupsFromDefinition(selfTestDefinition) {
  if (!selfTestDefinition) {
    return [];
  }
  return getAvailableSelfTestGroupsForKeys(
    selfTestDefinition.published_settings.map((field) => field.key),
  );
}

export function UnitSettingDisplaySubtext({ subtext, emptyMinHeight = "24px" }) {
  if (subtext) {
    return (
      <Chip
        size="small"
        sx={{ fontSize: "11px", wordBreak: "break-word", padding: "5px 0px" }}
        label={subtext.replaceAll("_", " ")}
      />
    );
  }
  return <Box sx={{ minHeight: emptyMinHeight }} />;
}

export function UnitSettingDisplay(props) {
  const value = props.value === null ? "" : props.value;

  function prettyPrint(x) {
    if (x >= 10) {
      return x.toFixed(0);
    }
    if (x === 0) {
      return "0";
    }
    if (x < 1) {
      return "<1";
    }
    return (x).toFixed(1).replace(/[.,]0$/, "");
  }

  function formatForDisplay(displayValue) {
    if (typeof displayValue === "string") {
      return displayValue;
    }
    if (typeof displayValue === "boolean") {
      return displayValue ? "On" : "Off";
    }
    return +displayValue.toFixed(props.precision);
  }

  if (props.isStateSetting) {
    return (
      <React.Fragment>
        <StateTypography state={value} isDisabled={!props.isUnitActive} />
        <br />
        <UnitSettingDisplaySubtext subtext={props.subtext} emptyMinHeight={props.subtextMinHeight} />
      </React.Fragment>
    );
  }

  if (props.displayKind === "led_intensity") {
    if (!props.isUnitActive || value === "—" || value === "") {
      return <Box sx={{ color: disconnectedGrey, fontSize: "13px" }}> {props.default} </Box>;
    }

    const ledIntensities = JSON.parse(value);
    const LEDMap = props.config["leds"] || {};
    const renamedA = LEDMap["A"] ? LEDMap["A"].replace("_", " ") : null;
    const renamedB = LEDMap["B"] ? LEDMap["B"].replace("_", " ") : null;
    const renamedC = LEDMap["C"] ? LEDMap["C"].replace("_", " ") : null;
    const renamedD = LEDMap["D"] ? LEDMap["D"].replace("_", " ") : null;

    return (
      <React.Fragment>
        <Box sx={{ fontSize: "13px" }}>
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
        </Box>
        <UnitSettingDisplaySubtext subtext={props.subtext} emptyMinHeight={props.subtextMinHeight} />
      </React.Fragment>
    );
  }

  if (props.displayKind === "pwm_dc") {
    if (!props.isUnitActive || value === "—" || value === "") {
      return <Box sx={{ color: disconnectedGrey, fontSize: "13px" }}> {props.default} </Box>;
    }

    const pwmDcs = JSON.parse(value);
    const PWM_TO_PIN = { 1: "17", 2: "13", 3: "16", 4: "12" };
    const PWMMap = props.config["PWM"] || {};
    const renamed1 = PWMMap[1] ? PWMMap[1].replace("_", " ") : null;
    const renamed2 = PWMMap[2] ? PWMMap[2].replace("_", " ") : null;
    const renamed3 = PWMMap[3] ? PWMMap[3].replace("_", " ") : null;
    const renamed4 = PWMMap[4] ? PWMMap[4].replace("_", " ") : null;

    return (
      <React.Fragment>
        <Box sx={{ fontSize: "13px" }}>
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
        </Box>
        <UnitSettingDisplaySubtext subtext={props.subtext} emptyMinHeight={props.subtextMinHeight} />
      </React.Fragment>
    );
  }

  if (!props.isUnitActive || value === "—" || value === "") {
    return (
      <React.Fragment>
        <Box sx={{ color: disconnectedGrey, fontSize: "13px" }}> {props.default} </Box>
        <UnitSettingDisplaySubtext subtext={props.subtext} emptyMinHeight={props.subtextMinHeight} />
      </React.Fragment>
    );
  }

  return (
    <React.Fragment>
      <Typography
        display="block"
        gutterBottom
        sx={{
          color: "rgba(0, 0, 0, 0.87)",
          padding: "1px 9px",
          borderRadius: "16px",
          backgroundColor: defaultStateDisplayBackground,
          display: "inline-block",
          fontWeight: 400,
          fontSize: "14px",
          ...getFauxChipHoverSx(props.isInteractive),
        }}
      >
        {formatForDisplay(value)} {props.measurementUnit ? props.measurementUnit : ""}
      </Typography>
      <UnitSettingDisplaySubtext subtext={props.subtext} emptyMinHeight={props.subtextMinHeight} />
    </React.Fragment>
  );
}

export function SettingTextField({
  value: initialValue,
  onUpdate,
  setSnackbarMessage,
  setSnackbarOpen,
  units,
  disabled,
  job,
  setting,
  id,
}) {
  const committedValue = initialValue ?? "";
  const [draftValue, setDraftValue] = React.useState(committedValue);
  const [activeSubmit, setActiveSumbit] = React.useState(false);
  const [isPendingConfirmation, setIsPendingConfirmation] = React.useState(false);
  const unitSize = (units || "").length > 8 ? "large" : "normal";
  const textFieldMaxWidth = unitSize === "large" ? "240px" : "180px";

  if (isPendingConfirmation && draftValue === committedValue) {
    setIsPendingConfirmation(false);
  }

  const value = (activeSubmit || isPendingConfirmation) ? draftValue : committedValue;

  const onChange = (e) => {
    setActiveSumbit(true);
    setIsPendingConfirmation(false);
    setDraftValue(e.target.value);
  };

  const onKeyPress = (e) => {
    if (e.key === "Enter" && e.target.value) {
      onSubmit();
    }
  };

  const onSubmit = () => {
    onUpdate(job, setting, draftValue);
    if (value !== "") {
      setSnackbarMessage(`Updating to ${value}${!units ? "" : ` ${units}`}.`);
    } else {
      setSnackbarMessage("Updating.");
    }
    setSnackbarOpen(true);
    setActiveSumbit(false);
    setIsPendingConfirmation(true);
  };

  return (
    <Box sx={{ display: "flex" }}>
      <TextField
        id={id}
        size="small"
        autoComplete="off"
        disabled={disabled}
        value={value}
        slotProps={{
          input: {
            endAdornment: <InputAdornment position="end">{units}</InputAdornment>,
            autoComplete: "new-password",
          },
        }}
        variant="outlined"
        onChange={onChange}
        onKeyPress={onKeyPress}
        sx={{ mt: 2, maxWidth: textFieldMaxWidth }}
      />
      <Button
        size="small"
        color="primary"
        disabled={!activeSubmit}
        onClick={onSubmit}
        sx={{ textTransform: "none", mt: "15px", ml: "7px", display: disabled ? "none" : undefined }}
      >
        Update
      </Button>
    </Box>
  );
}

export function SettingSwitchField({
  value: initialValue,
  onUpdate,
  setSnackbarMessage,
  setSnackbarOpen,
  job,
  setting,
  disabled,
  id,
}) {
  const committedValue = Boolean(initialValue);
  const [draftValue, setDraftValue] = React.useState(committedValue);
  const [isPendingConfirmation, setIsPendingConfirmation] = React.useState(false);

  if (isPendingConfirmation && draftValue === committedValue) {
    setIsPendingConfirmation(false);
  }

  const value = isPendingConfirmation ? draftValue : committedValue;

  const onChange = (e) => {
    const checked = e.target.checked;
    setDraftValue(checked);
    setIsPendingConfirmation(true);
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

export function SettingNumericField({
  value: initialValue,
  units,
  min,
  max,
  onUpdate,
  setSnackbarMessage,
  setSnackbarOpen,
  job,
  setting,
  disabled,
  id,
}) {
  const committedValue = initialValue ?? "";
  const [draftValue, setDraftValue] = React.useState(committedValue);
  const [error, setError] = React.useState(false);
  const [hasLocalEdits, setHasLocalEdits] = React.useState(false);
  const [activeSubmit, setActiveSubmit] = React.useState(false);
  const [isPendingConfirmation, setIsPendingConfirmation] = React.useState(false);
  const unitSize = (units || "").length > 8 ? "large" : "normal";
  const textFieldMaxWidth = unitSize === "large" ? "220px" : "160px";

  if (isPendingConfirmation && draftValue === committedValue) {
    setIsPendingConfirmation(false);
  }

  const value = (hasLocalEdits || isPendingConfirmation) ? draftValue : committedValue;

  const validateNumericInput = (input) => {
    const numericPattern = /^-?\d*\.?\d*$/;
    if (!numericPattern.test(input)) {
      return false;
    }

    if (input === "" || input === "-" || input === "." || input === "-.") {
      return false;
    }

    const parsedValue = Number.parseFloat(input);
    if (!Number.isFinite(parsedValue)) {
      return false;
    }

    if (min != null && parsedValue < min) {
      return false;
    }

    if (max != null && parsedValue > max) {
      return false;
    }

    return true;
  };

  const onChange = (e) => {
    const input = e.target.value;
    const isValid = validateNumericInput(input);
    setError(!isValid);
    setHasLocalEdits(true);
    setActiveSubmit(isValid);
    setIsPendingConfirmation(false);
    setDraftValue(input);
  };

  const onKeyPress = (e) => {
    if (e.key === "Enter" && e.target.value && !error) {
      onSubmit();
    }
  };

  const onSubmit = () => {
    if (!error) {
      onUpdate(job, setting, draftValue);
      const message = value !== "" ? `Updating to ${value}${units ? ` ${units}` : ""}.` : "Updating.";
      setSnackbarMessage(message);
      setSnackbarOpen(true);
      setHasLocalEdits(false);
      setActiveSubmit(false);
      setIsPendingConfirmation(true);
    }
  };

  return (
    <Box sx={{ display: "flex" }}>
      <TextField
        id={id}
        type="number"
        size="small"
        autoComplete="off"
        disabled={disabled}
        value={value}
        error={error}
        slotProps={{
          input: {
            endAdornment: <InputAdornment position="end">{units}</InputAdornment>,
            autoComplete: "new-password",
          },
          htmlInput: {
            min,
            max,
            step: (min === 0 && max === 1) ? 0.01 : null,
          },
        }}
        variant="outlined"
        onChange={onChange}
        onKeyPress={onKeyPress}
        sx={{ mt: 2, minWidth: "180px", maxWidth: textFieldMaxWidth }}
      />
      <Button
        size="small"
        color="primary"
        disabled={!activeSubmit || error}
        onClick={onSubmit}
        sx={{ textTransform: "none", mt: "15px", ml: "7px", display: disabled ? "none" : undefined }}
      >
        Update
      </Button>
    </Box>
  );
}
