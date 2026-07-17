import React from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import CameraPanel from "./components/CameraPanel";
import { useExperiment } from "./providers/ExperimentContext";
import { experimentPathSegment } from "./utils/url";

const MIN_CAMERA_REFRESH_INTERVAL_MS = 5000;


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

function cameraRefreshIntervalMs(cameraResults) {
  const intervalMinutes = cameraResults
    .map((result) => result.status?.snapshot_interval_minutes)
    .filter((value) => typeof value === "number" && value > 0);

  if (intervalMinutes.length === 0) {
    return null;
  }

  return Math.max(MIN_CAMERA_REFRESH_INTERVAL_MS, Math.min(...intervalMinutes) * 60 * 1000);
}

export default function Cameras({ title }) {
  const { experimentMetadata } = useExperiment();
  const [cameraResults, setCameraResults] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const experiment = experimentMetadata?.experiment;

  const loadCameraStatuses = React.useCallback(async ({ signal, showLoading = true } = {}) => {
    if (!experiment) {
      setCameraResults([]);
      setLoading(false);
      return;
    }

    if (showLoading) {
      setLoading(true);
    }

    try {
      const response = await fetch(`/api/experiments/${experimentPathSegment(experiment)}/cameras`, { signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not fetch camera statuses.");
      }

      const payload = await response.json();
      setCameraResults(normalizeCameraResults(payload));
    } catch (error) {} finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [experiment]);

  React.useEffect(() => {
    document.title = title;
  }, [title]);

  React.useEffect(() => {
    const controller = new AbortController();
    void loadCameraStatuses({ signal: controller.signal });

    return () => {
      controller.abort();
    };
  }, [loadCameraStatuses]);

  const refreshIntervalMs = React.useMemo(
    () => cameraRefreshIntervalMs(cameraResults),
    [cameraResults],
  );

  React.useEffect(() => {
    if (!refreshIntervalMs) {
      return undefined;
    }

    const interval = window.setInterval(() => {
      void loadCameraStatuses({ showLoading: false });
    }, refreshIntervalMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadCameraStatuses, refreshIntervalMs]);

  const onlineCameraResults = cameraResults.filter((result) => result.status);
  const visibleCameraResults = onlineCameraResults.filter(
    (result) => result.status.available || result.status.latest_still,
  );

  return (
    <Stack spacing={2}>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h1">
            <Box sx={{ fontWeight: "fontWeightBold" }}>
              Cameras
            </Box>
          </Typography>
        </Box>
        <Divider sx={{mt: "12px", mb: "15px"}} />
      </Box>

      {loading && cameraResults.length === 0 ? (
        <Stack sx={{ alignItems: "center", py: 8 }}>
          <CircularProgress />
        </Stack>
      ) : cameraResults.length === 0 ? (
        <Alert severity="info">No assigned Pioreactors were found.</Alert>
      ) : visibleCameraResults.length === 0 ? (
        <Alert severity="info">
          No camera-capable Pioreactors or stored camera stills were found.
        </Alert>
      ) : null}


      <Grid container spacing={2}>
        {visibleCameraResults.map((result, _) => (
          <Grid key={result.unit} size={{ xs: 12, md: 6, xl: 4 }}>
            <CameraPanel
              unit={result.unit}
              initialStatus={result.status}
              detailsHref={`/cameras/${encodeURIComponent(result.unit)}`}
              experiment={experiment}
              experimentStartTime={experimentMetadata?.created_at}
            />
          </Grid>
        ))}
      </Grid>
    </Stack>
  );
}
