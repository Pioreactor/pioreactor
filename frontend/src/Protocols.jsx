import React from "react";
import { useNavigate, useParams } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormLabel from "@mui/material/FormLabel";
import Grid from "@mui/material/Grid";
import AlertTitle from "@mui/material/AlertTitle";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from './components/Snackbar';
import Typography from "@mui/material/Typography";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import CalibrationSessionDialog from "./components/CalibrationSessionDialog";
import StirringCalibrationBatchDialog from "./components/StirringCalibrationBatchDialog";
import PioreactorsIcon from "./components/PioreactorsIcon";
import { fetchTaskResult } from "./utils/tasks";
import CircularProgress from "@mui/material/CircularProgress";
import RequirementsAlert from "./components/RequirementsAlert";

const CALIBRATION_SESSION_STORAGE_KEY = "activeCalibrationSession";
const ALL_PIOREACTORS = "$broadcast";

function getSharedProtocolsById(protocolsByUnit) {
  const units = Object.keys(protocolsByUnit || {});
  if (units.length === 0) {
    return [];
  }

  const protocolCounts = new Map();
  const protocolDetails = new Map();

  units.forEach((unit) => {
    const protocols = Array.isArray(protocolsByUnit[unit]) ? protocolsByUnit[unit] : [];
    protocols.forEach((protocol) => {
      const key = protocol.id;
      protocolCounts.set(key, (protocolCounts.get(key) || 0) + 1);
      if (!protocolDetails.has(key)) {
        protocolDetails.set(key, protocol);
      }
    });
  });

  return Array.from(protocolCounts.entries())
    .filter(([, count]) => count === units.length)
    .map(([key]) => protocolDetails.get(key));
}

function isAllPioreactorsStirringProtocol(protocol) {
  return (
    protocol?.target_device === "stirring" &&
    protocol?.protocol_name === "dc_based"
  );
}

function loadStoredCalibrationSession() {
  try {
    const raw = window.sessionStorage.getItem(CALIBRATION_SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (
      !parsed ||
      typeof parsed.sessionId !== "string" ||
      typeof parsed.unit !== "string" ||
      typeof parsed.protocolId !== "string" ||
      typeof parsed.targetDevice !== "string"
    ) {
      return null;
    }
    return parsed;
  } catch (_error) {
    return null;
  }
}

function saveStoredCalibrationSession(handle) {
  try {
    window.sessionStorage.setItem(CALIBRATION_SESSION_STORAGE_KEY, JSON.stringify(handle));
  } catch (_error) {
    // Best effort only.
  }
}

function clearStoredCalibrationSession() {
  try {
    window.sessionStorage.removeItem(CALIBRATION_SESSION_STORAGE_KEY);
  } catch (_error) {
    // Best effort only.
  }
}

function ProtocolCard({
  protocol,
  selectedUnit,
  onRun,
  showResume,
  onAbort,
  isAborting,
  runLabel,
}) {
  const requirements = Array.isArray(protocol.requirements) ? protocol.requirements : [];
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Typography
          variant="subtitle1"
          component="h3"
          sx={{ fontWeight: 600, letterSpacing: "0.01em" }}
        >
          {protocol.title}
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          {protocol.description}
        </Typography>

        <Box sx={{ mt: 2 }}>
          <RequirementsAlert>
            <AlertTitle>
              Requirements:
            </AlertTitle>
            <Box>
              <Box component="ul" sx={{ mt: 0, mb: 0, pl: 2 }}>
              {requirements.map((item) => (
                <li key={item}>
                  <Typography variant="body2">
                    {item}
                  </Typography>
                </li>
              ))}
              </Box>
            </Box>
          </RequirementsAlert>
        </Box>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mt: 2,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Button
              variant="contained"
              endIcon={<PlayArrowIcon />}
              onClick={() => onRun(protocol)}
              disabled={!selectedUnit}
              sx={{ textTransform: "none" }}
            >
              {showResume ? "Resume protocol" : runLabel || "Run protocol"}
            </Button>
            {showResume && (
              <Button
                variant="text"
                onClick={() => onAbort(protocol)}
                disabled={!selectedUnit || isAborting}
                sx={{ textTransform: "none", color: "error.main" }}
              >
                Abort protocol
              </Button>
            )}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

function Protocols(props) {
  const { pioreactorUnit, device } = useParams();
  const [workers, setWorkers] = React.useState([]);
  const [protocols, setProtocols] = React.useState([]);
  const [workersError, setWorkersError] = React.useState("");
  const [isLoadingWorkers, setIsLoadingWorkers] = React.useState(true);
  const [protocolsError, setProtocolsError] = React.useState("");
  const [isLoadingProtocols, setIsLoadingProtocols] = React.useState(false);
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");
  const [activeSessionProtocol, setActiveSessionProtocol] = React.useState(null);
  const [activeSessionId, setActiveSessionId] = React.useState(null);
  const [activeSessionProtocolId, setActiveSessionProtocolId] = React.useState(null);
  const [activeSessionUnit, setActiveSessionUnit] = React.useState(null);
  const [isAbortingProtocol, setIsAbortingProtocol] = React.useState(false);
  const [activeBatchProtocol, setActiveBatchProtocol] = React.useState(null);
  const restoreAttemptedRef = React.useRef(false);
  const navigate = useNavigate();

  const isSessionDialogOpen = Boolean(activeSessionProtocol);
  const isBatchDialogOpen = Boolean(activeBatchProtocol);
  const selectedUnit =
    pioreactorUnit || workers[0] || "";
  const displayedSelectedUnit =
    (selectedUnit === ALL_PIOREACTORS && workers.length > 0) || workers.includes(selectedUnit)
      ? selectedUnit
      : "";
  const deviceOptions = React.useMemo(
    () => Array.from(new Set(protocols.map((protocol) => protocol.target_device))),
    [protocols],
  );
  const selectedDevice = React.useMemo(() => {
    if (deviceOptions.length === 0) {
      return "";
    }

    if (device && deviceOptions.includes(device)) {
      return device;
    }

    return deviceOptions[0];
  }, [device, deviceOptions]);

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
      } catch (err) {
        setWorkersError(err.message || "Failed to load workers.");
      } finally {
        setIsLoadingWorkers(false);
      }
    };

    fetchWorkers();
  }, []);

  React.useEffect(() => {
    const fetchProtocols = async () => {
      if (!selectedUnit) {
        setProtocols([]);
        setProtocolsError("");
        setIsLoadingProtocols(false);
        return;
      }
      setIsLoadingProtocols(true);
      setProtocolsError("");
      try {
        const finalPayload = await fetchTaskResult(
          `/api/workers/${selectedUnit}/calibration_protocols`
        );
        if (selectedUnit === ALL_PIOREACTORS) {
          const sharedProtocols = getSharedProtocolsById(finalPayload?.result || {}).filter(
            isAllPioreactorsStirringProtocol,
          );
          setProtocols(sharedProtocols);
          return;
        }
        const result = finalPayload?.result?.[selectedUnit];
        if (!Array.isArray(result)) {
          throw new Error("Protocol payload is not a list.");
        }
        setProtocols(result);
      } catch (err) {
        setProtocolsError(err.message || "Failed to load protocols.");
        setProtocols([]);
      } finally {
        setIsLoadingProtocols(false);
      }
    };

    fetchProtocols();
  }, [selectedUnit]);

  const handleSnackbarClose = (_event, reason) => {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  };

  const handleSelectDeviceChange = (event) => {
    if (selectedUnit) {
      navigate(`/protocols/${selectedUnit}/${event.target.value}`);
    }
  };

  const handleSelectUnitChange = (event) => {
    setActiveSessionProtocol(null);
    setActiveBatchProtocol(null);
    if (selectedDevice) {
      navigate(`/protocols/${event.target.value}/${selectedDevice}`);
    } else {
      navigate(`/protocols/${event.target.value}`);
    }
  };

  const closeSessionDialog = () => {
    setActiveSessionProtocol(null);
  };

  const closeBatchDialog = () => {
    setActiveBatchProtocol(null);
  };

  const handleRunProtocol = async (protocol) => {
    if (!selectedUnit) {
      return;
    }
    if (selectedUnit === ALL_PIOREACTORS && isAllPioreactorsStirringProtocol(protocol)) {
      setActiveBatchProtocol(protocol);
      return;
    }
    if (
      activeSessionId &&
      activeSessionProtocolId === protocol.id &&
      activeSessionUnit === selectedUnit
    ) {
      setActiveSessionProtocol(protocol);
      return;
    }
    setActiveSessionId(null);
    setActiveSessionProtocolId(protocol.id);
    setActiveSessionUnit(selectedUnit);
    clearStoredCalibrationSession();
    setActiveSessionProtocol(protocol);
  };

  const handleAbortProtocol = async (protocol) => {
    if (!selectedUnit) {
      return;
    }
    if (
      !activeSessionId ||
      activeSessionProtocolId !== protocol.id ||
      activeSessionUnit !== selectedUnit
    ) {
      return;
    }
    setIsAbortingProtocol(true);
    try {
      const response = await fetch(
        `/api/workers/${selectedUnit}/calibrations/sessions/${activeSessionId}/abort`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
        }
      );
      if (!response.ok) {
        let errorMessage = `Failed to abort calibration session (${response.status}).`;
        try {
          const payload = await response.json();
          errorMessage = payload.error || JSON.stringify(payload);
        } catch (_error) {
          // Keep the fallback message.
        }
        throw new Error(errorMessage);
      }
      setActiveSessionId(null);
      setActiveSessionProtocolId(null);
      setActiveSessionUnit(null);
      clearStoredCalibrationSession();
      setSnackbarMessage("Calibration session aborted.");
      setSnackbarOpen(true);
    } catch (err) {
      setSnackbarMessage(err.message || "Failed to abort calibration session.");
      setSnackbarOpen(true);
    } finally {
      setIsAbortingProtocol(false);
    }
  };

  React.useEffect(() => {
    if (restoreAttemptedRef.current) {
      return;
    }
    restoreAttemptedRef.current = true;

    const restoreSession = async () => {
      const storedSession = loadStoredCalibrationSession();
      if (!storedSession) {
        return;
      }

      try {
        const response = await fetch(
          `/api/workers/${storedSession.unit}/calibrations/sessions/${storedSession.sessionId}`,
        );
        if (!response.ok) {
          clearStoredCalibrationSession();
          return;
        }
        const payload = await response.json();
        if (payload?.session?.status !== "in_progress") {
          clearStoredCalibrationSession();
          return;
        }

        setActiveSessionId(storedSession.sessionId);
        setActiveSessionProtocolId(storedSession.protocolId);
        setActiveSessionUnit(storedSession.unit);
      } catch (_error) {
        clearStoredCalibrationSession();
      }
    };

    restoreSession();
  }, []);

  return (
    <React.Fragment>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2">
          <Box sx={{ fontWeight: "fontWeightBold" }}>Protocols</Box>
        </Typography>

      </Box>
      <Divider sx={{ marginTop: "0px", marginBottom: "15px" }} />
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h6" component="h2" gutterBottom>
            <Box sx={{ fontWeight: "fontWeightRegular" }}>Available protocols</Box>
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
                  value={displayedSelectedUnit}
                  onChange={handleSelectUnitChange}
                  disabled={isLoadingWorkers || workers.length === 0}
                >
                  {workers.length > 0 && (
                    <MenuItem value={ALL_PIOREACTORS}>
                      <PioreactorsIcon fontSize="small" sx={{ verticalAlign: "middle", margin: "0px 4px" }} />
                      All Pioreactors
                    </MenuItem>
                  )}
                  {workers.map((worker) => (
                    <MenuItem key={worker} value={worker}>
                      {worker}
                    </MenuItem>
                  ))}
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
                  disabled={isLoadingProtocols || protocols.length === 0}
                >
                  {deviceOptions.map((targetDevice) => (
                    <MenuItem key={targetDevice} value={targetDevice}>
                      {targetDevice}
                    </MenuItem>
                  ))}
                  {!isLoadingProtocols && protocols.length === 0 && (
                    <MenuItem value="" disabled>
                      No protocols found
                    </MenuItem>
                  )}
                </Select>
              </FormControl>
            </Box>
          </Box>
          {workersError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {workersError}
            </Alert>
          )}
          {protocolsError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {protocolsError}
            </Alert>
          )}
          {isLoadingProtocols && (
            <Box sx={{ textAlign: "center", mt: 2 }}>
              <CircularProgress size={28} />
            </Box>
          )}
        </CardContent>
      </Card>
      <Grid container spacing={2}>
        {protocols
          .filter((protocol) => protocol.target_device === selectedDevice)
          .map((protocol) => (
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
              onAbort={handleAbortProtocol}
              isAborting={isAbortingProtocol}
              runLabel={
                selectedUnit === ALL_PIOREACTORS && isAllPioreactorsStirringProtocol(protocol)
                  ? "Run on all Pioreactors"
                  : "Run protocol"
              }
              showResume={
                Boolean(activeSessionId) &&
                activeSessionProtocolId === protocol.id &&
                activeSessionUnit === selectedUnit
              }
            />
          </Grid>
        ))}
      </Grid>
      <Box sx={{ textAlign: "center", mt: 3 }}>
        <Typography variant="body2">
          Learn more about{" "}
          <a
            href="https://docs.pioreactor.com/user-guide/protocols"
            target="_blank"
            rel="noopener noreferrer"
          >
            protocols
          </a>
          .
        </Typography>
      </Box>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
        autoHideDuration={2500}
        key="snackbar-protocols"
      />
      <CalibrationSessionDialog
        open={isSessionDialogOpen}
        protocol={activeSessionProtocol}
        unit={selectedUnit}
        sessionId={activeSessionId}
        onSessionId={(sessionId) => {
          setActiveSessionId(sessionId);
          setActiveSessionProtocolId(activeSessionProtocol?.id ?? null);
          setActiveSessionUnit(selectedUnit);
          if (activeSessionProtocol?.id && activeSessionProtocol?.target_device && selectedUnit) {
            saveStoredCalibrationSession({
              sessionId,
              unit: selectedUnit,
              protocolId: activeSessionProtocol.id,
              targetDevice: activeSessionProtocol.target_device,
            });
          }
        }}
        onComplete={() => {
          setActiveSessionId(null);
          setActiveSessionProtocolId(null);
          setActiveSessionUnit(null);
          clearStoredCalibrationSession();
          setSnackbarMessage("Calibration session completed.");
          setSnackbarOpen(true);
        }}
        onPause={() => {
          setSnackbarMessage("Protocol paused.");
          setSnackbarOpen(true);
        }}
        onClose={closeSessionDialog}
        onAbortSuccess={() => {
          setActiveSessionId(null);
          setActiveSessionProtocolId(null);
          setActiveSessionUnit(null);
          clearStoredCalibrationSession();
          setSnackbarMessage("Calibration session aborted.");
          setSnackbarOpen(true);
        }}
        onAbortFailure={(message) => {
          setSnackbarMessage(message || "Failed to abort calibration session.");
          setSnackbarOpen(true);
        }}
      />
      <StirringCalibrationBatchDialog
        open={isBatchDialogOpen}
        protocol={activeBatchProtocol}
        units={workers}
        onClose={closeBatchDialog}
      />
    </React.Fragment>
  );
}

export default Protocols;
