import React from "react";
import dayjs from "dayjs";
import { Link, useParams } from "react-router";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DownloadIcon from "@mui/icons-material/Download";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import RefreshIcon from "@mui/icons-material/Refresh";

import { useExperiment } from "./providers/ExperimentContext";
import { experimentPathSegment } from "./utils/url";

const MIN_CAMERA_REFRESH_INTERVAL_MS = 5000;

function workerExperimentCameraPath(unit, experiment, suffix) {
  return `/api/workers/${encodeURIComponent(unit)}/camera/experiments/${experimentPathSegment(experiment)}/${suffix}`;
}

function formatCaptureTime(metadata) {
  if (!metadata?.captured_at) {
    return "No capture";
  }

  return dayjs(metadata.captured_at).format("YYYY-MM-DD HH:mm:ss");
}

function stillImageUrl(unit, experiment, imageId) {
  return workerExperimentCameraPath(unit, experiment, `stills/${encodeURIComponent(imageId)}.jpg`);
}

export default function CameraStills({ title }) {
  const { pioreactorUnit } = useParams();
  const { experimentMetadata } = useExperiment();
  const experiment = experimentMetadata?.experiment;
  const [stills, setStills] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [downloading, setDownloading] = React.useState(false);
  const [refreshIntervalMs, setRefreshIntervalMs] = React.useState(null);

  const loadStills = React.useCallback(async ({ signal, showLoading = true } = {}) => {
    if (!pioreactorUnit || !experiment) {
      setStills([]);
      setRefreshIntervalMs(null);
      setLoading(false);
      return;
    }

    if (showLoading) {
      setLoading(true);
    }
    setError(null);

    try {
      const response = await fetch(workerExperimentCameraPath(pioreactorUnit, experiment, "stills"), {
        signal,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not fetch camera stills.");
      }

      const payload = await response.json();
      setStills(Array.isArray(payload?.stills) ? payload.stills : []);
      const intervalSeconds = payload?.snapshot_interval_seconds;
      setRefreshIntervalMs(
        typeof intervalSeconds === "number" && intervalSeconds > 0
          ? Math.max(MIN_CAMERA_REFRESH_INTERVAL_MS, intervalSeconds * 1000)
          : null,
      );
    } catch (error) {
      if (error.name !== "AbortError") {
        setError(error.message);
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [experiment, pioreactorUnit]);

  React.useEffect(() => {
    document.title = title;
  }, [title]);

  React.useEffect(() => {
    const controller = new AbortController();
    void loadStills({ signal: controller.signal });

    return () => {
      controller.abort();
    };
  }, [loadStills]);

  React.useEffect(() => {
    if (!refreshIntervalMs) {
      return undefined;
    }

    const interval = window.setInterval(() => {
      void loadStills({ showLoading: false });
    }, refreshIntervalMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadStills, refreshIntervalMs]);

  const downloadHref = pioreactorUnit && experiment
    ? workerExperimentCameraPath(pioreactorUnit, experiment, "stills.zip")
    : "";

  const downloadAllStills = React.useCallback(async () => {
    if (!downloadHref || !pioreactorUnit || !experiment) {
      return;
    }

    setDownloading(true);
    setError(null);

    try {
      const response = await fetch(downloadHref);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not download camera stills.");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${pioreactorUnit}_${experiment}_camera_stills.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setError(error.message);
    } finally {
      setDownloading(false);
    }
  }, [downloadHref, experiment, pioreactorUnit]);

  return (
    <Stack spacing={2}>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, mb: 1 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0 }}>
            <IconButton component={Link} to="/cameras" size="small">
              <ArrowBackIcon fontSize="small" />
            </IconButton>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h5" component="h1">
                <Box sx={{ fontWeight: "fontWeightBold" }}>
                  {pioreactorUnit} image timeline
                </Box>
              </Typography>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Button onClick={() => loadStills()} disabled={loading || !experiment} sx={{ textTransform: "none", whiteSpace: "nowrap" }} startIcon={<RefreshIcon/>}>
              Refresh
            </Button>

            <Button
              onClick={downloadAllStills}
              startIcon={<DownloadIcon />}
              disabled={!experiment || stills.length === 0 || downloading}
              sx={{ textTransform: "none", whiteSpace: "nowrap" }}
            >
              {downloading ? "Downloading..." : "Download All"}
            </Button>
          </Stack>
        </Box>
        <Divider sx={{ marginTop: "0px", marginBottom: "15px" }} />
      </Box>

      {error ? (
        <Alert severity="error">{error}</Alert>
      ) : loading && stills.length === 0 ? (
        <Stack sx={{ alignItems: "center", py: 8 }}>
          <CircularProgress />
        </Stack>
      ) : stills.length === 0 ? (
        <Alert severity="info">No still images were captured for this Pioreactor during this experiment.</Alert>
      ) : (
        <Grid container spacing={2}>
          {stills.map((still) => (
            <Grid key={still.image_id} size={{ xs: 12, sm: 6, lg: 4, xl: 3 }}>
              <Box
                sx={{
                  bgcolor: "background.paper",
                  borderRadius: 1,
                  overflow: "hidden",
                  border: 1,
                  borderColor: "divider",
                }}
              >
                <Box
                  component="img"
                  src={stillImageUrl(pioreactorUnit, experiment, still.image_id)}
                  alt={`Camera still from ${pioreactorUnit} at ${formatCaptureTime(still)}`}
                  loading="lazy"
                  sx={{
                    display: "block",
                    width: "100%",
                    aspectRatio: "4 / 3",
                    objectFit: "contain",
                    bgcolor: "action.hover",
                  }}
                />
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{ alignItems: "center", justifyContent: "space-between", px: 1.5, py: 1 }}
                >
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="body2" noWrap>
                      {formatCaptureTime(still)}
                    </Typography>
                  </Box>
                  <Tooltip title="Open image">
                    <IconButton
                      component="a"
                      href={stillImageUrl(pioreactorUnit, experiment, still.image_id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      size="small"
                    >
                      <FullscreenIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </Box>
            </Grid>
          ))}
        </Grid>
      )}
    </Stack>
  );
}
