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
  const [cameraResults, setCameraResults] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const experiment = experimentMetadata?.experiment;

  const loadCameraStatuses = React.useCallback(async ({ signal } = {}) => {
    if (!experiment) {
      setCameraResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/experiments/${experimentPathSegment(experiment)}/cameras`, { signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not fetch camera statuses.");
      }

      const payload = await response.json();
      setCameraResults(normalizeCameraResults(payload));
    } catch (error) {
      if (error.name !== "AbortError") {
        setError(error.message);
      }
    } finally {
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

  const onlineCameraResults = cameraResults.filter((result) => result.status);
  const cameraCapableResults = onlineCameraResults.filter((result) => result.status?.available);

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
        <Divider sx={{ marginTop: "0px", marginBottom: "15px" }} />
      </Box>

      {loading && cameraResults.length === 0 ? (
        <Stack sx={{ alignItems: "center", py: 8 }}>
          <CircularProgress />
        </Stack>
      ) : cameraResults.length === 0 ? (
        <Alert severity="info">No assigned Pioreactors were found.</Alert>
      ) : cameraCapableResults.length === 0 ? (
        <Alert severity="info">
          No camera-capable Pioreactors were detected. Camera tiles will appear here after a worker reports camera support.
        </Alert>
      ) : null}


      <Grid container spacing={2}>
        {cameraCapableResults.map((result, index) => (
          <Grid key={result.unit} size={{ xs: 12, md: 6, xl: 4 }}>
            <CameraPanel
              unit={result.unit}
              initialStatus={result.status}
              detailsHref={`/cameras/${encodeURIComponent(result.unit)}`}
            />
          </Grid>
        ))}
      </Grid>
    </Stack>
  );
}
