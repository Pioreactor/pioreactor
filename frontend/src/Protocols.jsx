import React from "react";
import { Link, useNavigate, useParams } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormLabel from "@mui/material/FormLabel";
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import LoadingButton from "@mui/lab/LoadingButton";
import PioreactorsIcon from "./components/PioreactorsIcon";
import TuneIcon from "@mui/icons-material/Tune";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { useMQTT } from "./providers/MQTTContext";

const PROTOCOLS = [
  {
    id: "stirring_dc_based",
    device: "stirring",
    protocolName: "dc_based",
    jobName: "stirring_calibration",
    title: "Stirring DC-based calibration",
    description:
      "Maps duty cycle to RPM for the current stirrer configuration.",
    requirements: [
      "Stirring must be off before starting.",
      "Insert a vial with a stir bar and the liquid volume you plan to use (water is fine).",
    ],
  },
  {
    id: "od_reference_standard",
    device: "od",
    protocolName: "od_reference_standard",
    jobName: "od_calibration",
    title: "Optics Calibration Jig",
    description:
      "Uses the Optics Calibration Jig to calibrate OD channels to a standard value (AU).",
    requirements: [
      "OD reading must be off before starting.",
      "Insert the Optics Calibration Jig.",
      "Set ir_led_intensity in [od_reading.config] to a numeric value.",
    ],
  },
];

const protocolRunEndpoint = (unit) =>
  `/api/workers/${unit}/calibrations/protocols/run`;

function ProtocolCard({
  protocol,
  selectedUnit,
  onRun,
  isSubmitting,
  isRunning,
  errorMessage,
}) {
  const buttonLabel = isRunning ? "Running" : isSubmitting ? "Starting" : "Run protocol";

  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Typography variant="h6" component="h3">
          {protocol.title}
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          {protocol.description}
        </Typography>

        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">Requirements</Typography>
          <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2 }}>
            {protocol.requirements.map((item) => (
              <li key={item}>
                <Typography variant="body2" color="text.secondary">
                  {item}
                </Typography>
              </li>
            ))}
          </Box>
        </Box>
        {errorMessage && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {errorMessage}
          </Alert>
        )}
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mt: 2,
          }}
        >
          <LoadingButton
            variant="contained"
            loading={isSubmitting || isRunning}
            loadingPosition="start"
            endIcon={<PlayArrowIcon />}
            onClick={() => onRun(protocol)}
            disabled={!selectedUnit || isRunning || isSubmitting}
            sx={{ textTransform: "none" }}
          >
            {buttonLabel}
          </LoadingButton>
        </Box>
      </CardContent>
    </Card>
  );
}

function Protocols(props) {
  const { pioreactorUnit, device } = useParams();
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const [workers, setWorkers] = React.useState([]);
  const [selectedUnit, setSelectedUnit] = React.useState(pioreactorUnit || "");
  const [selectedDevice, setSelectedDevice] = React.useState(
    device || PROTOCOLS[0]?.device || ""
  );
  const [workersError, setWorkersError] = React.useState("");
  const [isLoadingWorkers, setIsLoadingWorkers] = React.useState(true);
  const [runStateByProtocol, setRunStateByProtocol] = React.useState({});
  const [protocolStates, setProtocolStates] = React.useState({});
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");
  const navigate = useNavigate();

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  React.useEffect(() => {
    const fetchWorkers = async () => {
      setIsLoadingWorkers(true);
      setWorkersError("");
      try {
        const response = await fetch("/api/workers");
        if (!response.ok) {
          throw new Error(`Failed to load workers (${response.status}).`);
        }
        const data = await response.json();
        const units = data.map((worker) => worker.pioreactor_unit);
        setWorkers(units);
        if (!pioreactorUnit && units.length > 0) {
          setSelectedUnit(units.length > 1 ? "$broadcast" : units[0]);
        }
      } catch (err) {
        setWorkersError(err.message || "Failed to load workers.");
      } finally {
        setIsLoadingWorkers(false);
      }
    };

    fetchWorkers();
  }, []);

  const handleSnackbarClose = (_event, reason) => {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  };

  const handleSelectDeviceChange = (event) => {
    setSelectedDevice(event.target.value);
    if (selectedUnit) {
      navigate(`/protocols/${selectedUnit}/${event.target.value}`);
    }
  };

  const handleSelectUnitChange = (event) => {
    setSelectedUnit(event.target.value);
    if (selectedDevice) {
      navigate(`/protocols/${event.target.value}/${selectedDevice}`);
    }
  };

  const jobNameToProtocolId = React.useMemo(() => {
    return PROTOCOLS.reduce((acc, protocol) => {
      acc[protocol.jobName] = protocol.id;
      return acc;
    }, {});
  }, []);

  const protocolById = React.useMemo(() => {
    return PROTOCOLS.reduce((acc, protocol) => {
      acc[protocol.id] = protocol;
      return acc;
    }, {});
  }, []);

  const protocolStateTopics = React.useMemo(() => {
    const topics = new Set(
      PROTOCOLS.map(
        (protocol) => `pioreactor/+/+/${protocol.jobName}/$state`
      )
    );
    return Array.from(topics);
  }, []);

  const handleProtocolStateMessage = React.useCallback(
    (topic, message) => {
      const parts = topic.split("/");
      if (parts.length < 5) {
        return;
      }
      const unit = parts[1];
      const jobName = parts[3];
      const setting = parts[4];
      if (setting !== "$state") {
        return;
      }
      const protocolId = jobNameToProtocolId[jobName];
      if (!protocolId) {
        return;
      }

      const nextState = message.toString();
      let shouldHandleCompletion = false;
      let shouldHandleLost = false;
      let isSelectedUnit = false;
      let protocolTitle = "Calibration";

      setProtocolStates((prev) => {
        const prevState = prev?.[protocolId]?.[unit];
        const next = {
          ...prev,
          [protocolId]: {
            ...(prev[protocolId] || {}),
            [unit]: nextState,
          },
        };

        isSelectedUnit = selectedUnit === unit;
        const hasStateTransition = prevState && prevState !== nextState;
        if (isSelectedUnit && hasStateTransition) {
          protocolTitle = protocolById?.[protocolId]?.title || "Calibration";
          shouldHandleCompletion = nextState === "disconnected";
          shouldHandleLost = nextState === "lost";
        }

        return next;
      });

      if (shouldHandleLost) {
        setSnackbarMessage(`${protocolTitle} lost connection on ${unit}.`);
        setSnackbarOpen(true);
        return;
      }

      if (shouldHandleCompletion) {
        setSnackbarMessage(`${protocolTitle} completed on ${unit}.`);
        setSnackbarOpen(true);
      }

      setRunStateByProtocol((prev) => {
        const current = prev[protocolId];
        if (!current || !current.isSubmitting) {
          return prev;
        }
        const pendingUnit = current.pendingUnit;
        if (!pendingUnit) {
          return prev;
        }
        if (pendingUnit !== "$broadcast" && pendingUnit !== unit) {
          return prev;
        }
        return {
          ...prev,
          [protocolId]: {
            ...current,
            isSubmitting: false,
            pendingUnit: null,
          },
        };
      });
    },
    [
      jobNameToProtocolId,
      protocolById,
      selectedUnit,
    ]
  );

  React.useEffect(() => {
    if (!client || protocolStateTopics.length === 0) {
      return;
    }

    subscribeToTopic(
      protocolStateTopics,
      handleProtocolStateMessage,
      "protocols-calibration-states"
    );

    return () => {
      protocolStateTopics.forEach((topic) => {
        unsubscribeFromTopic(topic, "protocols-calibration-states");
      });
    };
  }, [
    client,
    handleProtocolStateMessage,
    protocolStateTopics,
    subscribeToTopic,
    unsubscribeFromTopic,
  ]);

  const isProtocolRunningForSelection = React.useCallback(
    (protocolId) => {
      const statesByUnit = protocolStates[protocolId] || {};
      const runningUnits = Object.entries(statesByUnit)
        .filter(([, state]) => state === "init" || state === "ready")
        .map(([unit]) => unit);

      if (selectedUnit === "$broadcast") {
        return runningUnits.length > 0;
      }

      return selectedUnit ? runningUnits.includes(selectedUnit) : false;
    },
    [protocolStates, selectedUnit]
  );

  const handleRunProtocol = async (protocol) => {
    if (!selectedUnit) {
      return;
    }

    setRunStateByProtocol((prev) => ({
      ...prev,
      [protocol.id]: {
        isSubmitting: true,
        pendingUnit: selectedUnit,
        errorMessage: "",
      },
    }));

    try {
      const response = await fetch(protocolRunEndpoint(selectedUnit), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          device: protocol.device,
          protocol_name: protocol.protocolName,
          set_active: true,
        }),
      });

      if (!response.ok) {
        let errorMessage = `Failed to start protocol (${response.status}).`;
        try {
          const payload = await response.json();
          errorMessage =
            payload.error || payload.message || JSON.stringify(payload);
        } catch (_error) {
          // Keep the fallback message.
        }
        throw new Error(errorMessage);
      }

      const targetLabel =
        selectedUnit === "$broadcast" ? "all Pioreactors" : selectedUnit;
      setSnackbarMessage(`Started ${protocol.title} on ${targetLabel}.`);
      setSnackbarOpen(true);
    } catch (err) {
      const message = err.message || "Failed to start protocol.";
      setRunStateByProtocol((prev) => ({
        ...prev,
        [protocol.id]: {
          ...prev[protocol.id],
          isSubmitting: false,
          pendingUnit: null,
          errorMessage: message,
        },
      }));
      setSnackbarMessage(message);
      setSnackbarOpen(true);
    }
  };

  return (
    <React.Fragment>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2">
          <Box fontWeight="fontWeightBold">Protocols</Box>
        </Typography>
        <Button
          component={Link}
          to={
            selectedUnit && selectedDevice
              ? `/calibrations/${selectedUnit}/${selectedDevice}`
              : "/calibrations"
          }
          startIcon={<TuneIcon />}
          sx={{ textTransform: "none" }}
        >
          {`View ${selectedDevice || "device"} calibrations`}
        </Button>
      </Box>
      <Divider sx={{ marginTop: "0px", marginBottom: "15px" }} />
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h6" component="h2" gutterBottom>
            <Box fontWeight="fontWeightRegular">Available protocols</Box>
          </Typography>
          <Typography variant="body2" sx={{ mb: 2 }} gutterBottom>
            Create calibrations by running device-specific protocols.
          </Typography>
          <Box
            sx={{
              display: "flex",
              alignItems: "flex-end",
              flexWrap: "wrap",
              gap: 3,
            }}
          >
            <Box>
              <FormControl variant="standard" sx={{ minWidth: 220 }}>
                <FormLabel component="legend">Pioreactor</FormLabel>
                <Select
                  value={selectedUnit}
                  onChange={handleSelectUnitChange}
                  disabled={isLoadingWorkers || workers.length === 0}
                >
                  {workers.map((worker) => (
                    <MenuItem key={worker} value={worker}>
                      {worker}
                    </MenuItem>
                  ))}
                  {workers.length > 0 && (
                    <MenuItem value="$broadcast">
                      <PioreactorsIcon
                        fontSize="small"
                        sx={{ verticalAlign: "middle", margin: "0px 4px" }}
                      />
                      All Pioreactors
                    </MenuItem>
                  )}
                  {workers.length === 0 && !isLoadingWorkers && (
                    <MenuItem value="" disabled>
                      No Pioreactors found
                    </MenuItem>
                  )}
                </Select>
              </FormControl>
            </Box>
            <Box>
              <FormControl variant="standard" sx={{ minWidth: 220 }}>
                <FormLabel component="legend">Device</FormLabel>
                <Select
                  value={selectedDevice}
                  onChange={handleSelectDeviceChange}
                >
                  {Array.from(
                    new Set(PROTOCOLS.map((protocol) => protocol.device))
                  ).map((device) => (
                    <MenuItem key={device} value={device}>
                      {device}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
          </Box>
          {workersError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {workersError}
            </Alert>
          )}
        </CardContent>
      </Card>
        <Box>
        <Alert severity="info" style={{marginBottom: '10px', marginTop: '10px'}}>Heads up! This isn't <i>all</i> the available calibrations - only the ones that can be run from the UI. See more here </Alert>
        </Box>
      <Grid container spacing={2}>
        {PROTOCOLS.filter(
          (protocol) => protocol.device === selectedDevice
        ).map((protocol) => {
          const runState = runStateByProtocol[protocol.id] || {};
          const isRunning = isProtocolRunningForSelection(protocol.id);
          return (
            <Grid
              key={protocol.id}
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <ProtocolCard
                protocol={protocol}
                selectedUnit={selectedUnit}
                onRun={handleRunProtocol}
                isSubmitting={Boolean(runState.isSubmitting)}
                isRunning={isRunning}
                errorMessage={runState.errorMessage}
              />
            </Grid>
          );
        })}
      </Grid>
      <Box sx={{ textAlign: "center", mt: 3 }}>
        <Typography variant="body2" color="text.secondary">
          Learn more about{" "}
          <a
            href="https://docs.pioreactor.com/user-guide/hardware-calibrations"
            target="_blank"
            rel="noopener noreferrer"
          >
            calibrations
          </a>
          .
        </Typography>
      </Box>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
        autoHideDuration={7000}
        key="snackbar-protocols"
      />
    </React.Fragment>
  );
}

export default Protocols;
