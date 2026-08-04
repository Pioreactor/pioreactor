import React from "react";
import dayjs from "dayjs";
import { useConfirm } from "material-ui-confirm";
import { Link, useParams } from "react-router";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import DownloadIcon from "@mui/icons-material/Download";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import LocalSeeIcon from "@mui/icons-material/LocalSee";
import ScheduleIcon from "@mui/icons-material/Schedule";

import { useExperiment } from "./providers/ExperimentContext";
import UnderlineSpan from "./components/UnderlineSpan";
import useCameraResource from "./hooks/useCameraResource";
import { assertUnitTaskResultSucceeded, fetchTaskResult } from "./utils/tasks";
import { experimentPathSegment } from "./utils/url";

const CAMERA_STILLS_PAGE_SIZE = 24;
const textIcon = {verticalAlign: "middle", margin: "0px 3px"}

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


function normalizeCameraStills(payload) {
  return Array.isArray(payload?.stills) ? payload.stills : [];
}

export default function CameraStills({ title }) {
  const confirm = useConfirm();
  const { pioreactorUnit } = useParams();
  const { experimentMetadata } = useExperiment();
  const experiment = experimentMetadata?.experiment;
  const experimentStartTime = experimentMetadata?.created_at;
  const stillsUrl = pioreactorUnit && experiment
    ? workerExperimentCameraPath(pioreactorUnit, experiment, "stills")
    : null;
  const {
    data: stills = [],
    error,
    loading,
    refresh: loadStills,
    setData: setStills,
    setError,
  } = useCameraResource({
    mqttTopic: experiment && pioreactorUnit
      ? `pioreactor/${pioreactorUnit}/${experiment}/camera/latest_still`
      : null,
    normalize: normalizeCameraStills,
    url: stillsUrl,
  });
  const [deletingImageId, setDeletingImageId] = React.useState(null);
  const [takingSnapshot, setTakingSnapshot] = React.useState(false);
  const resourceKey = `${pioreactorUnit || ""}:${experiment || ""}`;
  const [pagination, setPagination] = React.useState({
    resourceKey,
    visibleStillCount: CAMERA_STILLS_PAGE_SIZE,
  });
  const visibleStillCount = pagination.resourceKey === resourceKey
    ? pagination.visibleStillCount
    : CAMERA_STILLS_PAGE_SIZE;
  const [selectedStillImageId, setSelectedStillImageId] = React.useState(null);

  React.useEffect(() => {
    document.title = title;
  }, [title]);

  const downloadHref = pioreactorUnit && experiment
    ? workerExperimentCameraPath(pioreactorUnit, experiment, "stills.zip")
    : "";
  const orderedStills = sortCameraStillsNewestFirst(stills);
  const visibleStills = orderedStills.slice(0, visibleStillCount);
  const hasEarlierStills = visibleStills.length < orderedStills.length;
  const selectedStillIndex = orderedStills.findIndex(
    (still) => still.image_id === selectedStillImageId,
  );
  const selectedStill = selectedStillIndex >= 0 ? orderedStills[selectedStillIndex] : null;

  const moveSelectedStill = (offset) => {
    setSelectedStillImageId((currentImageId) => {
      const currentIndex = orderedStills.findIndex((still) => still.image_id === currentImageId);
      return orderedStills[currentIndex + offset]?.image_id ?? currentImageId;
    });
  };

  const takeSnapshotAndRefreshTimeline = React.useCallback(async () => {
    if (!pioreactorUnit || !experiment || takingSnapshot) {
      return;
    }

    setTakingSnapshot(true);
    setError(null);

    try {
      const taskResult = await fetchTaskResult(
        workerExperimentCameraPath(pioreactorUnit, experiment, "stills"),
        {
          fetchOptions: { method: "POST" },
          maxRetries: 300,
          delayMs: 100,
        },
      );
      assertUnitTaskResultSucceeded(
        taskResult,
        pioreactorUnit,
        `Could not take a camera snapshot on ${pioreactorUnit}.`,
      );
      await loadStills();
    } catch (error) {
      setError(`Could not take a camera snapshot. ${error.message} Check that the camera is connected, then retry.`);
    } finally {
      setTakingSnapshot(false);
    }
  }, [experiment, loadStills, pioreactorUnit, setError, takingSnapshot]);

  const deleteStill = React.useCallback(async (still) => {
    if (!pioreactorUnit || !experiment || deletingImageId) {
      return;
    }

    try {
      await confirm({
        title: "Delete this camera snapshot?",
        description: `The image captured at ${formatCaptureTime(still)} will be permanently deleted.`,
        confirmationText: "Delete",
        confirmationButtonProps: { color: "primary", sx: { textTransform: "none"}, variant: 'contained'},
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
        throw new Error(payload.error || "Could not delete camera snapshot.");
      }

      setStills((currentStills) => (
        currentStills.filter((candidate) => candidate.image_id !== still.image_id)
      ));
    } catch (error) {
      setError(`${error.message} Refresh the timeline and retry.`);
    } finally {
      setDeletingImageId(null);
    }
  }, [confirm, deletingImageId, experiment, pioreactorUnit, setError, setStills]);

  return (
    <Stack spacing={2}>
      <Box component="header">
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 2,
            flexWrap: "wrap",
            mb: 1,
          }}
        >
          <Button component={Link} to="/cameras" startIcon={<ArrowBackIcon />} sx={{ textTransform: "none" }}>
            All cameras
          </Button>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Button
              onClick={takeSnapshotAndRefreshTimeline}
              disabled={loading || takingSnapshot || !experiment}
              sx={{ textTransform: "none", whiteSpace: "nowrap", float: "right"  }}
            >
              {takingSnapshot ? <CircularProgress  fontSize="small" color="inherit" size={18} sx={textIcon} /> : <LocalSeeIcon  fontSize="small" sx={textIcon} />}
              Capture snapshot
            </Button>

            <Button
              component="a"
              href={downloadHref}
              download={`${pioreactorUnit}_${experiment}_camera_snapshots.zip`}
              disabled={!experiment || stills.length === 0}
              startIcon={<DownloadIcon />}
              sx={{ textTransform: "none", whiteSpace: "nowrap" }}
            >
              Download all
            </Button>
          </Box>
        </Box>
        <Divider />
      </Box>

      <Box>
        <Typography variant="h5" component="h1" sx={{ fontWeight: "bold" }}>
          Camera snapshots on {pioreactorUnit}
        </Typography>
      </Box>

      {error && (
        <Alert severity="error">
          {error} {stills.length > 0 ? "Existing snapshots remain available below." : "Retry in a moment."}
        </Alert>
      )}

      {loading && stills.length === 0 ? (
        <Stack sx={{ alignItems: "center", py: 8 }}>
          <CircularProgress />
        </Stack>
      ) : stills.length === 0 ? (
        <Alert severity="info">No snapshots have been captured for this Pioreactor during this experiment.</Alert>
      ) : (
        <>
          <Grid container spacing={2}>
            {visibleStills.map((still) => {
              const isScheduled = still.capture_reason !== "manual";
              const captureReasonLabel = isScheduled ? "Scheduled snapshot" : "Manual snapshot";
              const CaptureReasonIcon = isScheduled ? ScheduleIcon : LocalSeeIcon;

              return (
                <Grid key={still.image_id} size={{ xs: 12, sm: 4, lg: 3, xl: 3 }}>
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
                      component="button"
                      type="button"
                      aria-label={`Enlarge camera snapshot captured at ${formatCaptureTime(still)}`}
                      onClick={() => setSelectedStillImageId(still.image_id)}
                      sx={{
                        display: "block",
                        width: "100%",
                        p: 0,
                        border: 0,
                        bgcolor: "action.hover",
                        cursor: "zoom-in",
                        "&:focus-visible": {
                          outline: "2px solid",
                          outlineColor: "primary.main",
                          outlineOffset: "-2px",
                        },
                      }}
                    >
                      <Box
                        component="img"
                        src={stillImageUrl(pioreactorUnit, experiment, still.image_id)}
                        alt={`Camera snapshot from ${pioreactorUnit} at ${formatCaptureTime(still)}`}
                        loading="lazy"
                        sx={{
                          display: "block",
                          width: "100%",
                          aspectRatio: "4 / 3",
                          objectFit: "contain",
                        }}
                      />
                    </Box>
                    <Stack
                      direction="row"
                      spacing={1}
                      sx={{ alignItems: "center", justifyContent: "space-between", px: 1.5, py: 1 }}
                    >
                      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", minWidth: 0 }}>
                        <Tooltip title={captureReasonLabel}>
                          <CaptureReasonIcon
                            role="img"
                            titleAccess={captureReasonLabel}
                            fontSize="small"
                            sx={{ color: "text.secondary", flexShrink: 0 }}
                          />
                        </Tooltip>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="body2" noWrap>
                            <UnderlineSpan title={formatCaptureTime(still)}>
                              {formatCaptureDelta(still, experimentStartTime)}
                            </UnderlineSpan>
                          </Typography>
                        </Box>
                      </Stack>
                      <Stack direction="row" spacing={0.5}>
                        <Tooltip title="Delete snapshot">
                          <span>
                            <IconButton
                              aria-label={`Delete camera snapshot captured at ${formatCaptureTime(still)}`}
                              color="secondary"
                              disabled={deletingImageId !== null}
                              onClick={() => deleteStill(still)}
                              sx={{ minHeight: 44, minWidth: 44 }}
                            >
                              {deletingImageId === still.image_id ? (
                                <CircularProgress color="inherit" size={18} />
                              ) : (
                                <DeleteOutlineIcon fontSize="small" />
                              )}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Open image">
                          <IconButton
                            aria-label="Open image"
                            component="a"
                            href={stillImageUrl(pioreactorUnit, experiment, still.image_id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            sx={{ minHeight: 44, minWidth: 44 }}
                          >
                            <FullscreenIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </Stack>
                  </Box>
                </Grid>
              );
            })}
          </Grid>
          {hasEarlierStills && (
            <Stack sx={{ alignItems: "center", pt: 1 }}>
              <Button
                onClick={() => setPagination({
                  resourceKey,
                  visibleStillCount: visibleStillCount + CAMERA_STILLS_PAGE_SIZE,
                })}
                sx={{ textTransform: "none" }}
              >
                Load earlier
              </Button>
              <Typography variant="caption" color="text.secondary">
                Showing {visibleStills.length} of {orderedStills.length} images. Older images may be automatically thinned to preserve the full experiment timeline.
              </Typography>
            </Stack>
          )}
        </>
      )}

      <Dialog
        open={selectedStill !== null}
        onClose={() => setSelectedStillImageId(null)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            moveSelectedStill(-1);
          } else if (event.key === "ArrowRight") {
            event.preventDefault();
            moveSelectedStill(1);
          }
        }}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle sx={{ pr: 6 }}>
          {selectedStill ? formatCaptureTime(selectedStill) : "Camera snapshot"}
          <IconButton
            aria-label="Close"
            onClick={() => setSelectedStillImageId(null)}
            sx={{ position: "absolute", right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          {selectedStill && (
            <Box
              sx={{
                bgcolor: "action.hover",
                borderRadius: 1,
                overflow: "hidden",
              }}
            >
              <Box
                component="img"
                src={stillImageUrl(pioreactorUnit, experiment, selectedStill.image_id)}
                alt={`Enlarged camera snapshot from ${pioreactorUnit} at ${formatCaptureTime(selectedStill)}`}
                sx={{
                  display: "block",
                  width: "100%",
                  aspectRatio: "4 / 3",
                  objectFit: "contain",
                }}
              />
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </Stack>
  );
}
