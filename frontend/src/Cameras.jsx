import React from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import CameraPanel from "./components/CameraPanel";
import useCameraResource from "./hooks/useCameraResource";
import { useExperiment } from "./providers/ExperimentContext";
import { experimentPathSegment } from "./utils/url";


function normalizeCameraResults(payload) {
  const cameras = payload?.cameras;
  if (!cameras || typeof cameras !== "object" || Array.isArray(cameras)) {
    return [];
  }

  return Object.entries(cameras).map(([unit, result]) => {
    if (result?.ok === true) {
      return { unit, status: result.value, error: null };
    }

    return {
      unit,
      status: null,
      error: result?.error?.message || "Could not reach this Pioreactor.",
    };
  });
}

export default function Cameras({ title }) {
  const { experimentMetadata } = useExperiment();
  const experiment = experimentMetadata?.experiment;
  const cameraUrl = experiment
    ? `/api/experiments/${experimentPathSegment(experiment)}/cameras`
    : null;
  const {
    data: cameraResults = [],
    error,
    loading,
    setData: setCameraResults,
  } = useCameraResource({
    mqttTopic: experiment ? `pioreactor/+/${experiment}/camera/latest_still` : null,
    normalize: normalizeCameraResults,
    url: cameraUrl,
  });

  React.useEffect(() => {
    document.title = title;
  }, [title]);

  const updateCameraStatus = React.useCallback((unit, nextStatus) => {
    setCameraResults((currentResults = []) => currentResults.map((result) => (
      result.unit === unit
        ? {
            ...result,
            status: typeof nextStatus === "function" ? nextStatus(result.status) : nextStatus,
          }
        : result
    )));
  }, [setCameraResults]);

  const onlineCameraResults = cameraResults.filter((result) => result.status);
  const failedCameraResults = cameraResults.filter((result) => result.error);
  const visibleCameraResults = onlineCameraResults.filter(
    (result) => (
      result.status.detection_status !== "configured_camera_not_detected"
      || result.status.latest_still
    ),
  );

  return (
    <Stack spacing={2}>
      <Box component="header">
        <Typography variant="h5" component="h1" sx={{ fontWeight: "bold", mb: 1 }}>
          Cameras
        </Typography>
        <Divider sx={{mt: "12px", mb: "15px"}} />
      </Box>

      {error && <Alert severity="error">{error} Existing camera information may be out of date.</Alert>}
      {failedCameraResults.map((result) => (
        <Alert key={result.unit} severity="warning">
          {result.unit}: {result.error}
        </Alert>
      ))}

      {loading && cameraResults.length === 0 ? (
        <Stack sx={{ alignItems: "center", py: 8 }}>
          <CircularProgress />
        </Stack>
      ) : !error && cameraResults.length === 0 ? (
        <Alert severity="info">No assigned Pioreactors were found.</Alert>
      ) : !error && visibleCameraResults.length === 0 ? (
        <Alert severity="info">
          No camera-capable Pioreactors or stored camera snapshots were found.
        </Alert>
      ) : null}


      <Grid container spacing={2}>
        {visibleCameraResults.map((result, _) => (
          <Grid key={result.unit} size={{ xs: 12, md: 6, xl: 4 }}>
            <CameraPanel
              unit={result.unit}
              status={result.status}
              onStatusChange={(nextStatus) => updateCameraStatus(result.unit, nextStatus)}
              experiment={experiment}
              experimentStartTime={experimentMetadata?.created_at}
            />
          </Grid>
        ))}
      </Grid>
    </Stack>
  );
}
