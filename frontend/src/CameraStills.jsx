import React from "react";
import dayjs from "dayjs";
import { useConfirm } from "material-ui-confirm";
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
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import DownloadIcon from "@mui/icons-material/Download";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import RefreshIcon from "@mui/icons-material/Refresh";

import { useExperiment } from "./providers/ExperimentContext";
import UnderlineSpan from "./components/UnderlineSpan";
import { runPioreactorJob } from "./utils/jobs";
import { experimentPathSegment } from "./utils/url";

const MIN_CAMERA_REFRESH_INTERVAL_MS = 5000;
const CAMERA_STILLS_PAGE_SIZE = 24;

function workerExperimentCameraPath(unit, experiment, suffix) {
  return `/api/workers/${encodeURIComponent(unit)}/camera/experiments/${experimentPathSegment(experiment)}/${suffix}`;
}

function formatCaptureTime(metadata) {
  if (!metadata?.captured_at) {
    return "No capture";
  }

  return dayjs(metadata.captured_at).format("YYYY-MM-DD HH:mm:ss");
}

function formatCaptureDelta(metadata, experimentStartTime) {
  if (!metadata?.captured_at || !experimentStartTime) {
    return "";
  }

  const deltaHours = Math.round(
    dayjs(metadata.captured_at).diff(dayjs(experimentStartTime), "hours", true) * 1e2,
  ) / 1e2;
  return `${deltaHours} h`;
}

function stillImageUrl(unit, experiment, imageId) {
  return workerExperimentCameraPath(unit, experiment, `stills/${encodeURIComponent(imageId)}.jpg`);
}

function sortCameraStillsNewestFirst(stills) {
  return [...stills].sort((left, right) => {
    const capturedAtDifference = dayjs(right.captured_at).valueOf() - dayjs(left.captured_at).valueOf();
    return capturedAtDifference || right.image_id.localeCompare(left.image_id);
  });
}

export default function CameraStills({ title }) {
  const confirm = useConfirm();
  const { pioreactorUnit } = useParams();
  const { experimentMetadata } = useExperiment();
  const experiment = experimentMetadata?.experiment;
  const experimentStartTime = experimentMetadata?.created_at;
  const [stills, setStills] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [deletingImageId, setDeletingImageId] = React.useState(null);
  const [takingSnapshot, setTakingSnapshot] = React.useState(false);
  const [refreshIntervalMs, setRefreshIntervalMs] = React.useState(null);
  const [visibleStillCount, setVisibleStillCount] = React.useState(CAMERA_STILLS_PAGE_SIZE);

  const loadStills = React.useCallback(async ({
    signal,
    showLoading = true,
    resetVisibleStillCount = false,
  } = {}) => {
    if (!pioreactorUnit || !experiment) {
      setStills([]);
      setRefreshIntervalMs(null);
      setLoading(false);
      return;
    }

    if (showLoading) {
      setLoading(true);
    }
    if (resetVisibleStillCount) {
      setVisibleStillCount(CAMERA_STILLS_PAGE_SIZE);
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
      const intervalMinutes = payload?.snapshot_interval_minutes;
      setRefreshIntervalMs(
        typeof intervalMinutes === "number" && intervalMinutes > 0
          ? Math.max(MIN_CAMERA_REFRESH_INTERVAL_MS, intervalMinutes * 60 * 1000)
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
    void loadStills({
      signal: controller.signal,
      resetVisibleStillCount: true,
    });

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
  const orderedStills = sortCameraStillsNewestFirst(stills);
  const visibleStills = orderedStills.slice(0, visibleStillCount);
  const hasEarlierStills = visibleStills.length < orderedStills.length;

  const takeSnapshotAndRefreshTimeline = React.useCallback(async () => {
    if (!pioreactorUnit || !experiment || takingSnapshot) {
      return;
    }

    setTakingSnapshot(true);
    setError(null);

    try {
      await runPioreactorJob(pioreactorUnit, experiment, "camera_snapshot");
      await loadStills();
    } catch (error) {
      setError(`Could not take a camera snapshot. ${error.message} Check that the camera is connected, then retry.`);
    } finally {
      setTakingSnapshot(false);
    }
  }, [experiment, loadStills, pioreactorUnit, takingSnapshot]);

  const deleteStill = React.useCallback(async (still) => {
    if (!pioreactorUnit || !experiment || deletingImageId) {
      return;
    }

    try {
      await confirm({
        title: "Delete this camera still?",
        description: `The image captured at ${formatCaptureTime(still)} will be permanently deleted.`,
        confirmationText: "Delete",
        confirmationButtonProps: { color: "primary", sx: { textTransform: "none" } },
        cancellationButtonProps: { color: "secondary", sx: { textTransform: "none" } },
      });
    } catch (_error) {
      return;
    }

    setDeletingImageId(still.image_id);
    setError(null);

    try {
      const response = await fetch(
        workerExperimentCameraPath(
          pioreactorUnit,
          experiment,
          `stills/${encodeURIComponent(still.image_id)}.jpg`,
        ),
        { method: "DELETE" },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not delete camera still.");
      }

      setStills((currentStills) => (
        currentStills.filter((candidate) => candidate.image_id !== still.image_id)
      ));
    } catch (error) {
      setError(`${error.message} Refresh the timeline and retry.`);
    } finally {
      setDeletingImageId(null);
    }
  }, [confirm, deletingImageId, experiment, pioreactorUnit]);

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
            <Button
              onClick={takeSnapshotAndRefreshTimeline}
              disabled={loading || takingSnapshot || !experiment}
              sx={{ textTransform: "none", whiteSpace: "nowrap" }}
              startIcon={takingSnapshot ? <CircularProgress color="inherit" size={18} /> : <RefreshIcon />}
            >
              Refresh
            </Button>

            <Button
              href={downloadHref}
              startIcon={<DownloadIcon />}
              disabled={!experiment || stills.length === 0}
              sx={{ textTransform: "none", whiteSpace: "nowrap" }}
            >
              Download All
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
        <Alert severity="info">No still images have been captured for this Pioreactor during this experiment.</Alert>
      ) : (
        <>
          <Grid container spacing={2}>
            {visibleStills.map((still) => (
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
                        <UnderlineSpan title={formatCaptureTime(still)}>
                          {formatCaptureDelta(still, experimentStartTime)}
                        </UnderlineSpan>
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
                    <Tooltip title="Delete image">
                      <span>
                        <IconButton
                          aria-label={`Delete camera still captured at ${formatCaptureTime(still)}`}
                          color="secondary"
                          disabled={deletingImageId !== null}
                          onClick={() => deleteStill(still)}
                          size="small"
                        >
                          {deletingImageId === still.image_id ? (
                            <CircularProgress color="inherit" size={18} />
                          ) : (
                            <DeleteOutlineIcon fontSize="small" />
                          )}
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                </Box>
              </Grid>
            ))}
          </Grid>
          {hasEarlierStills && (
            <Stack sx={{ alignItems: "center", pt: 1 }}>
              <Button
                onClick={() => setVisibleStillCount((count) => count + CAMERA_STILLS_PAGE_SIZE)}
                sx={{ textTransform: "none" }}
              >
                Load earlier
              </Button>
              <Typography variant="caption" color="text.secondary">
                Showing {visibleStills.length} of {orderedStills.length} images
              </Typography>
            </Stack>
          )}
        </>
      )}
    </Stack>
  );
}
