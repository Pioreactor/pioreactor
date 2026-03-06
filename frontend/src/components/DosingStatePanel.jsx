import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import InputAdornment from "@mui/material/InputAdornment";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import UnderlineSpan from "./UnderlineSpan";
import { fetchTaskResult } from "../utilities";
import Divider from '@mui/material/Divider';
import { styled } from '@mui/material/styles';


const ControlDivider = styled(Divider)(({ theme }) => ({
  marginTop: theme.spacing(2), // equivalent to 16px if the default spacing unit is 8px
  marginBottom: theme.spacing(1.25) // equivalent to 10px
}));

function parseNumberOrNull(value) {
  if (value === "" || value == null) {
    return null;
  }

  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}


function getSingleUnitTaskResult(taskResult, unit) {
  return taskResult?.result?.[unit] || null;
}


const settingInputSx = { mt: 2, maxWidth: "160px" };
const settingActionSx = { textTransform: "none", mt: "15px", ml: "7px" };


export default function DosingStatePanel({
  unit,
  experiment,
  isRunning,
  liveState,
  threshold,
  onStateChange,
  setSnackbarMessage,
  setSnackbarOpen,
}) {
  const [persistedState, setPersistedState] = React.useState(null);
  const [currentVolumeDraft, setCurrentVolumeDraft] = React.useState("");
  const [maxWorkingVolumeDraft, setMaxWorkingVolumeDraft] = React.useState("");
  const [altMediaFractionDraft, setAltMediaFractionDraft] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(true);
  const [isSavingCurrentVolume, setIsSavingCurrentVolume] = React.useState(false);
  const [isSavingMaxWorkingVolume, setIsSavingMaxWorkingVolume] = React.useState(false);
  const [isSavingAltMediaFraction, setIsSavingAltMediaFraction] = React.useState(false);
  const [isResettingThroughputs, setIsResettingThroughputs] = React.useState(false);
  const [error, setError] = React.useState(null);

  const endpoint = `/api/workers/${unit}/dosing_state/experiments/${experiment}`;

  const displayedState = React.useMemo(() => {
    if (!persistedState) {
      return null;
    }

    if (!isRunning) {
      return persistedState;
    }

    return {
      current_volume_ml: liveState?.current_volume_ml ?? persistedState.current_volume_ml,
      max_working_volume_ml:
        liveState?.max_working_volume_ml ?? persistedState.max_working_volume_ml,
      alt_media_fraction: liveState?.alt_media_fraction ?? persistedState.alt_media_fraction,
      media_throughput: liveState?.media_throughput ?? persistedState.media_throughput,
      alt_media_throughput: liveState?.alt_media_throughput ?? persistedState.alt_media_throughput,
    };
  }, [isRunning, liveState, persistedState]);

  React.useEffect(() => {
    let cancelled = false;

    async function loadDosingState() {
      setIsLoading(true);
      setError(null);

      try {
        const taskResult = await fetchTaskResult(endpoint, { fetchOptions: { method: "GET" } });
        const nextState = getSingleUnitTaskResult(taskResult, unit);
        if (!cancelled && nextState) {
          setPersistedState(nextState);
          onStateChange?.(nextState);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    loadDosingState();

    return () => {
      cancelled = true;
    };
  }, [endpoint, onStateChange, unit]);

  React.useEffect(() => {
    if (!displayedState) {
      return;
    }

    setCurrentVolumeDraft(displayedState.current_volume_ml);
    setMaxWorkingVolumeDraft(displayedState.max_working_volume_ml);
    setAltMediaFractionDraft(displayedState.alt_media_fraction);
  }, [
    displayedState?.alt_media_fraction,
    displayedState?.current_volume_ml,
    displayedState?.max_working_volume_ml,
  ]);

  async function patchDosingState(patch, successMessage, setLoadingState) {
    setLoadingState(true);
    setError(null);

    try {
      const taskResult = await fetchTaskResult(endpoint, {
        fetchOptions: {
          method: "PATCH",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify(patch),
        },
      });

      const nextState = getSingleUnitTaskResult(taskResult, unit);
      if (!nextState) {
        throw new Error("Incorrect values submitted.");
      }

      setPersistedState(nextState);
      onStateChange?.(nextState);
      setSnackbarMessage(successMessage);
      setSnackbarOpen(true);
    } catch (patchError) {
      setError(patchError.message);
      setSnackbarMessage(`Failed to update: ${patchError.message}`);
      setSnackbarOpen(true);
    } finally {
      setLoadingState(false);
    }
  }

  if (isLoading) {
    return (
      <Box sx={{ mt: 2, display: "flex", alignItems: "center", gap: 1 }}>
        <CircularProgress size={16} />
        <Typography variant="body2" color="textSecondary">
          Loading...
        </Typography>
      </Box>
    );
  }

  if (!displayedState) {
    return null;
  }

  const nextCurrentVolume = parseNumberOrNull(currentVolumeDraft);
  const nextMaxWorkingVolume = parseNumberOrNull(maxWorkingVolumeDraft);
  const nextAltMediaFraction = parseNumberOrNull(altMediaFractionDraft);
  const canSaveCurrentVolume =
    nextCurrentVolume != null && nextCurrentVolume !== displayedState.current_volume_ml;
  const canSaveMaxWorkingVolume =
    nextMaxWorkingVolume != null &&
    nextMaxWorkingVolume !== displayedState.max_working_volume_ml;
  const canSaveAltMediaFraction =
    nextAltMediaFraction != null && nextAltMediaFraction !== displayedState.alt_media_fraction;

  return (
    <Box>


      <Typography gutterBottom sx={{ mt: 2 }}>
        Current volume
      </Typography>
      <Typography variant="body2" component="p">
        Adjust the volue of liquid in the vial.
      </Typography>
      <Box sx={{ display: "flex" }}>
        <TextField
          size="small"
          type="number"
          autoComplete="off"
          value={currentVolumeDraft}
          onChange={(event) => setCurrentVolumeDraft(event.target.value)}
          InputProps={{
            endAdornment: <InputAdornment position="end">mL</InputAdornment>,
            autoComplete: "new-password",
          }}
          sx={settingInputSx}
        />
        <Button
          size="small"
          disabled={!canSaveCurrentVolume || isSavingCurrentVolume}
          sx={settingActionSx}
          onClick={() =>
            patchDosingState(
              { current_volume_ml: nextCurrentVolume },
              `Updated current volume to ${nextCurrentVolume} mL.`,
              setIsSavingCurrentVolume,
            )
          }
        >
          Update
        </Button>
      </Box>

      <ControlDivider/>

      <Typography gutterBottom sx={{ mt: 2 }}>
        Max working volume
      </Typography>
      <Typography variant="body2" component="p">
        Set the max working volume. This is the volume at which the end of the waste tube touches the liquid surface.
      </Typography>
      <Box sx={{ display: "flex" }}>
        <TextField
          size="small"
          type="number"
          autoComplete="off"
          value={maxWorkingVolumeDraft}
          onChange={(event) => setMaxWorkingVolumeDraft(event.target.value)}
          InputProps={{
            endAdornment: <InputAdornment position="end">mL</InputAdornment>,
            autoComplete: "new-password",
          }}
          sx={settingInputSx}
        />
        <Button
          size="small"
          disabled={!canSaveMaxWorkingVolume || isSavingMaxWorkingVolume}
          sx={settingActionSx}
          onClick={() =>
            patchDosingState(
              { max_working_volume_ml: nextMaxWorkingVolume },
              `Updated max working volume to ${nextMaxWorkingVolume} mL.`,
              setIsSavingMaxWorkingVolume,
            )
          }
        >
          Update
        </Button>
      </Box>

      <ControlDivider/>

      <Typography gutterBottom sx={{ mt: 2 }}>
        Alt-media fraction
      </Typography>
      <Typography variant="body2" component="p">
        Fraction of the liquid that is alt-media. Set the proportion of alt-media currently in the liquid.
      </Typography>
      <Box sx={{ display: "flex" }}>
        <TextField
          size="small"
          type="number"
          autoComplete="off"
          value={altMediaFractionDraft}
          onChange={(event) => setAltMediaFractionDraft(event.target.value)}
          InputProps={{
            autoComplete: "new-password",
          }}
          sx={settingInputSx}
        />
        <Button
          size="small"
          disabled={!canSaveAltMediaFraction || isSavingAltMediaFraction}
          sx={settingActionSx}
          onClick={() =>
            patchDosingState(
              { alt_media_fraction: nextAltMediaFraction },
              `Updated alt-media fraction to ${nextAltMediaFraction}.`,
              setIsSavingAltMediaFraction,
            )
          }
        >
          Update
        </Button>
      </Box>

      <ControlDivider/>

      <Typography gutterBottom sx={{ mt: 2 }}>
        Throughput counters
      </Typography>
      <Typography variant="body2" component="p" gutterBottom>
        Reset the cumulative media totals if you need to correct the saved experiment state.
      </Typography>
      <Box>
        <table style={{ borderCollapse: "separate", borderSpacing: "5px", fontSize: "0.90rem", marginTop: "4px" }}>
          <tbody>
            <tr>
              <td style={{ textAlign: "left", minWidth: "140px" }}>
                Media throughput
              </td>
              <td>
                <code style={{ backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px" }}>
                  {displayedState.media_throughput.toFixed(2)} mL
                </code>
              </td>
            </tr>
            <tr>
              <td style={{ textAlign: "left", minWidth: "140px" }}>
                Alt-media throughput
              </td>
              <td>
                <code style={{ backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px" }}>
                  {displayedState.alt_media_throughput.toFixed(2)} mL
                </code>
              </td>
            </tr>
          </tbody>
        </table>
        <Button
          size="small"
          sx={{ textTransform: "none", mt: 1 }}
          disabled={isResettingThroughputs}
          onClick={() =>
            patchDosingState(
              { media_throughput: 0, alt_media_throughput: 0 },
              "Reset dosing throughput counters.",
              setIsResettingThroughputs,
            )
          }
        >
          Reset throughputs
        </Button>
      </Box>

      {displayedState.current_volume_ml > threshold && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          Current volume exceeds the model safety limit of {threshold} mL.
        </Alert>
      )}

    </Box>
  );
}
