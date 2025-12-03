import React, { useEffect, useMemo, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Stack from "@mui/material/Stack";
import Snackbar from "@mui/material/Snackbar";
import { styled } from "@mui/material/styles";
import PioreactorIcon from "./PioreactorIcon";
import ListSubheader from '@mui/material/ListSubheader';


const fetchJSON = async (endpoint) => {
  const response = await fetch(endpoint);
  if (!response.ok) {
    throw new Error(`Request to ${endpoint} failed with status ${response.status}`);
  }
  return response.json();
};

const WorkerRow = styled("div")(({ theme }) => ({
  display: "flex",
  flexDirection: "column",
  padding: theme.spacing(1.5),

  marginBottom: theme.spacing(1.5),
}));

const MODELS_VERIFIED_STORAGE_KEY = "pioreactorModelsVerified";

const getModelsVerifiedFlag = () => {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return false;
    }
    return window.localStorage.getItem(MODELS_VERIFIED_STORAGE_KEY) === "true";
  } catch (_error) {
    return false;
  }
};

const setModelsVerifiedFlag = (value) => {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return;
    }
    window.localStorage.setItem(MODELS_VERIFIED_STORAGE_KEY, value ? "true" : "false");
  } catch (_error) {
    // ignore storage failures (e.g. private browsing)
  }
};

const hasMissingModelDetails = (worker) =>
  worker?.model_name == null || worker?.model_version == null;

const MissingWorkerModelModal = ({ triggerCheckKey = 0 }) => {
  const [isLoaded, setIsLoaded] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [workersNeedingInfo, setWorkersNeedingInfo] = useState([]);
  const [selections, setSelections] = useState({});
  const [availableModels, setAvailableModels] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");

  useEffect(() => {
    const shouldForceCheck = triggerCheckKey !== 0;

    if (getModelsVerifiedFlag() && !shouldForceCheck) {
      setIsLoaded(true);
      return;
    }

    const loadData = async () => {
      try {
        const [workersPayload, modelsPayload] = await Promise.all([
          fetchJSON("/api/workers"),
          fetchJSON("/api/models"),
        ]);

        const missing = (workersPayload || []).filter(hasMissingModelDetails);

        if (missing.length > 0) {
          const initialSelections = missing.reduce(
            (acc, worker) => ({
              ...acc,
              [worker.pioreactor_unit]: "",
            }),
            {}
          );
          setSelections(initialSelections);
          setWorkersNeedingInfo(missing);
          setIsOpen(true);
          setModelsVerifiedFlag(false);
        } else {
          setWorkersNeedingInfo([]);
          setIsOpen(false);
          setModelsVerifiedFlag(true);
        }

        setAvailableModels(modelsPayload?.models ?? []);
      } catch (error) {
        setErrorMessage(error.message);
      } finally {
        setIsLoaded(true);
      }
    };

    loadData();
  }, [triggerCheckKey]);

  const groupedModels = useMemo(() => {
    const safeModels = availableModels ?? [];
    return {
      standard: safeModels.filter((model) => !model.is_contrib && !model.is_legacy),
      contrib: safeModels.filter((model) => model.is_contrib),
      legacy: safeModels.filter((model) => model.is_legacy && !model.is_contrib),
    };
  }, [availableModels]);

  const anyMissingSelection = useMemo(
    () =>
      workersNeedingInfo.some(
        (worker) => !selections[worker.pioreactor_unit]
      ),
    [workersNeedingInfo, selections]
  );

  const handleSelectionChange = (unit) => (event) => {
    setSelections((current) => ({
      ...current,
      [unit]: event.target.value,
    }));
  };

  const handleSubmit = async () => {
    if (anyMissingSelection) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage("");

    try {
      const updatedUnits = workersNeedingInfo.map((worker) => worker.pioreactor_unit);

      await Promise.all(
        workersNeedingInfo.map((worker) => {
          const [model_name, model_version] = (selections[worker.pioreactor_unit] || "").split(
            "::"
          );
          return fetch(`/api/workers/${worker.pioreactor_unit}/model`, {
            method: "PUT",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ model_name, model_version }),
          }).then((response) => {
            if (!response.ok) {
              return response
                .json()
                .catch(() => response.text())
                .then((payload) => {
                  const detail =
                    typeof payload === "string"
                      ? payload
                      : payload?.error || payload?.message || JSON.stringify(payload);
                  throw new Error(
                    `Unable to update ${worker.pioreactor_unit}: ${detail || response.status}`
                  );
                });
            }
            return response;
          });
        })
      );
      setIsOpen(false);
      setWorkersNeedingInfo([]);
      setModelsVerifiedFlag(true);
      setSnackbarMessage(
        updatedUnits.length === 1
          ? `Assigned model to ${updatedUnits[0]}.`
          : "Model assignments updated"
      );
      setSnackbarOpen(true);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSnackbarClose = (_event, reason) => {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  };

  const shouldDisplayDialog = isOpen && workersNeedingInfo.length > 0;

  if (!isLoaded) {
    return null;
  }

  if (!shouldDisplayDialog && !snackbarOpen) {
    return null;
  }

  return (
    <>
      <Dialog open={shouldDisplayDialog} onClose={() => {}} maxWidth="sm" fullWidth>
        <DialogTitle>Update Pioreactor model</DialogTitle>
        <DialogContent>
          {shouldDisplayDialog && (
            <Stack spacing={2}>
              <Typography variant="body1">
                We need the model name and version for the following Pioreactors before continuing. Please select the correct for each unit. Note: you can change this later.
              </Typography>
              {errorMessage && (
                <Alert severity="error" onClose={() => setErrorMessage("")}>
                  {errorMessage}
                </Alert>
              )}
              {workersNeedingInfo.map((worker) => (
                <WorkerRow key={worker.pioreactor_unit}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 400 }}>
                     <PioreactorIcon fontSize="small" sx={{verticalAlign: "middle"}}/> {worker.pioreactor_unit}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Model information missing. Choose a model to proceed.
                  </Typography>
                  <FormControl required sx={{minWidth: "195px", maxWidth: "400px"}} variant="outlined" size="small">
                    <InputLabel id={`model-select-${worker.pioreactor_unit}`}>Model</InputLabel>
                    <Select
                      labelId={`model-select-${worker.pioreactor_unit}`}
                      value={selections[worker.pioreactor_unit] || ""}
                      label="Model"
                      onChange={handleSelectionChange(worker.pioreactor_unit)}
                      disabled={isSubmitting}
                    >
                      {groupedModels.standard.length > 0 && (
                        <ListSubheader disableSticky>Latest</ListSubheader>
                      )}
                      {groupedModels.standard.map((model) => (
                        <MenuItem
                          key={`${model.model_name}-${model.model_version}`}
                          value={`${model.model_name}::${model.model_version}`}
                        >
                          {model.display_name || `${model.model_name} v${model.model_version}`}
                        </MenuItem>
                      ))}
                      {groupedModels.contrib.length > 0 && (
                        <ListSubheader disableSticky>Custom</ListSubheader>
                      )}
                      {groupedModels.contrib.map((model) => (
                        <MenuItem
                          key={`${model.model_name}-${model.model_version}`}
                          value={`${model.model_name}::${model.model_version}`}
                        >
                          {model.display_name || `${model.model_name} v${model.model_version}`}
                        </MenuItem>
                      ))}
                      {groupedModels.legacy.length > 0 && (
                        <ListSubheader disableSticky>Legacy</ListSubheader>
                      )}
                      {groupedModels.legacy.map((model) => (
                        <MenuItem
                          key={`${model.model_name}-${model.model_version}`}
                          value={`${model.model_name}::${model.model_version}`}
                        >
                          {model.display_name || `${model.model_name} v${model.model_version}`}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </WorkerRow>
              ))}
            </Stack>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Box sx={{ flexGrow: 1, display: "flex", justifyContent: "right", alignItems: "center" }}>
            <Box sx={{ display: "flex", alignItems: "center" }}>
              {isSubmitting && <CircularProgress size={24} sx={{ mr: 2 }} />}
              <Button
                sx={{textTransform: 'none', }}
                color="primary"
                variant="contained"
                onClick={handleSubmit}
                disabled={isSubmitting || anyMissingSelection}
              >
                Save
              </Button>
            </Box>
          </Box>
        </DialogActions>
      </Dialog>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        autoHideDuration={6000}
        message={snackbarMessage}
      />
    </>
  );
};

export default MissingWorkerModelModal;
