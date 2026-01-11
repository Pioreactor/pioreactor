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
import TuneIcon from "@mui/icons-material/Tune";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import CalibrationSessionDialog from "./components/CalibrationSessionDialog";
import { fetchTaskResult } from "./utilities";
import CircularProgress from "@mui/material/CircularProgress";

function ProtocolCard({
  protocol,
  selectedUnit,
  onRun,
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
          <Typography variant="subtitle2">Requirements</Typography>
          <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2 }}>
            {requirements.map((item) => (
              <li key={item}>
                <Typography variant="body2" >
                  {item}
                </Typography>
              </li>
            ))}
          </Box>
        </Box>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mt: 2,
          }}
        >
          <Button
            variant="contained"
            endIcon={<PlayArrowIcon />}
            onClick={() => onRun(protocol)}
            disabled={!selectedUnit}
            sx={{ textTransform: "none" }}
          >
            Run protocol
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}

function Protocols(props) {
  const { pioreactorUnit, device } = useParams();
  const [workers, setWorkers] = React.useState([]);
  const [selectedUnit, setSelectedUnit] = React.useState(pioreactorUnit || "");
  const [selectedDevice, setSelectedDevice] = React.useState(device || "");
  const [protocols, setProtocols] = React.useState([]);
  const [workersError, setWorkersError] = React.useState("");
  const [isLoadingWorkers, setIsLoadingWorkers] = React.useState(true);
  const [protocolsError, setProtocolsError] = React.useState("");
  const [isLoadingProtocols, setIsLoadingProtocols] = React.useState(false);
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");
  const [activeSessionProtocol, setActiveSessionProtocol] = React.useState(null);
  const navigate = useNavigate();

  const isSessionDialogOpen = Boolean(activeSessionProtocol);

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
          setSelectedUnit(units[0]);
        }
        if (pioreactorUnit === "$broadcast" && units.length > 0) {
          setSelectedUnit(units[0]);
        }
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
      if (!selectedUnit || selectedUnit === "$broadcast") {
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

  React.useEffect(() => {
    if (protocols.length === 0) {
      if (selectedDevice !== "") {
        setSelectedDevice("");
      }
      return;
    }
    if (device && protocols.some((protocol) => protocol.target_device === device)) {
      if (selectedDevice !== device) {
        setSelectedDevice(device);
      }
      return;
    }
    if (!protocols.some((protocol) => protocol.target_device === selectedDevice)) {
      setSelectedDevice(protocols[0].target_device);
    }
  }, [device, protocols, selectedDevice]);

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
    } else {
      navigate(`/protocols/${event.target.value}`);
    }
  };

  const closeSessionDialog = () => {
    setActiveSessionProtocol(null);
  };

  const handleRunProtocol = async (protocol) => {
    if (!selectedUnit) {
      return;
    }
    if (selectedUnit === "$broadcast") {
      setSnackbarMessage("Select a single Pioreactor to run a protocol.");
      setSnackbarOpen(true);
      return;
    }

    setActiveSessionProtocol(protocol);
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
              ? `/calibrations/${selectedUnit}/${
                  selectedDevice === "od" ? "od90" : selectedDevice
                }`
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
                  {Array.from(
                    new Set(protocols.map((protocol) => protocol.target_device))
                  ).map((targetDevice) => (
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
            />
          </Grid>
        ))}
      </Grid>
      <Box sx={{ textAlign: "center", mt: 3 }}>
        <Typography variant="body2">
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
      <CalibrationSessionDialog
        open={isSessionDialogOpen}
        protocol={activeSessionProtocol}
        unit={selectedUnit}
        onClose={closeSessionDialog}
        onAbortSuccess={() => {
          setSnackbarMessage("Calibration session aborted.");
          setSnackbarOpen(true);
        }}
        onAbortFailure={() => {
          setSnackbarMessage("Failed to abort calibration session.");
          setSnackbarOpen(true);
        }}
        onStartFailure={(message) => {
          setSnackbarMessage(message);
          setSnackbarOpen(true);
        }}
      />
    </React.Fragment>
  );
}

export default Protocols;
