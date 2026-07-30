import React from "react";
import dayjs from "dayjs";
import { Link } from "react-router";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import CloseIcon from "@mui/icons-material/Close";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import ImageNotSupportedOutlinedIcon from "@mui/icons-material/ImageNotSupportedOutlined";
import PhotoLibraryOutlinedIcon from "@mui/icons-material/PhotoLibraryOutlined";

import PioreactorIcon from "./PioreactorIcon";
import UnderlineSpan from "./UnderlineSpan";
import { fetchTaskResult, getUnitTaskResult } from "../utils/tasks";
import { experimentPathSegment } from "../utils/url";

const MIN_CAMERA_REFRESH_INTERVAL_MS = 5000;

function workerCameraPath(unit, suffix, experiment) {
  return `/api/workers/${encodeURIComponent(unit)}/camera/experiments/${experimentPathSegment(experiment)}/${suffix}`;
}

function workerCameraSettingsPath(unit) {
  return `/api/workers/${encodeURIComponent(unit)}/camera/settings`;
}

function experimentStillUrl(unit, experiment, imageId) {
  return workerCameraPath(unit, `stills/${encodeURIComponent(imageId)}.jpg`, experiment);
}

function formatCaptureTime(metadata) {
  if (!metadata?.captured_at) {
    return "";
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

function CameraEmptyState({ title, detail }) {
  return (
    <Stack
      spacing={1}
      sx={{
        alignItems: "center",
        justifyContent: "center",
        minHeight: 220,
        color: "text.secondary",
        textAlign: "center",
        px: 2,
      }}
    >
      <ImageNotSupportedOutlinedIcon color="action" sx={{ fontSize: 40 }} />
      <Typography variant="subtitle2">{title}</Typography>
      {detail && <Typography variant="body2">{detail}</Typography>}
    </Stack>
  );
}

function CameraMedia({ unit, status, imageUrl, onOpenViewer, onMissingImage }) {
  const latestStill = status?.latest_still;

  if (!latestStill) {
    if (!status?.available) {
      return (
        <CameraEmptyState
          title="No camera detected"
          detail="Camera capture tools are not available on this Pioreactor."
        />
      );
    }

    return (
      <CameraEmptyState
        title="No camera snapshot"
        detail="Waiting on image to become available."
      />
    );
  }

  return (
    <Box
      component="button"
      type="button"
      onClick={onOpenViewer}
      sx={{
        display: "block",
        width: "100%",
        p: 0,
        border: 0,
        bgcolor: "action.hover",
        cursor: "zoom-in",
      }}
    >
      <Box
        component="img"
        alt={`Latest camera snapshot for ${unit}`}
        src={imageUrl}
        onError={onMissingImage}
        sx={{ display: "block", width: "100%", aspectRatio: "4 / 3", objectFit: "contain" }}
      />
    </Box>
  );
}

export default function CameraPanel({
  unit,
  initialStatus = null,
  experiment,
  experimentStartTime = null,
}) {
  const [status, setStatus] = React.useState(initialStatus);
  const [loading, setLoading] = React.useState(!initialStatus);
  const [viewerOpen, setViewerOpen] = React.useState(false);
  const [actionError, setActionError] = React.useState(null);
  const [autoCaptureUpdatePending, setAutoCaptureUpdatePending] = React.useState(false);
  const autoCaptureUpdatePendingRef = React.useRef(false);
  const autoCaptureUpdateVersionRef = React.useRef(0);

  const refreshStatus = React.useCallback(async ({ signal, showLoading = true } = {}) => {
    const autoCaptureUpdateVersion = autoCaptureUpdateVersionRef.current;
    const autoCaptureWasUpdating = autoCaptureUpdatePendingRef.current;

    if (showLoading) {
      setLoading(true);
    }
    setActionError(null);

    try {
      const response = await fetch(workerCameraPath(unit, "status", experiment), { signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not fetch camera status.");
      }

      const data = await response.json();
      setStatus((previous) => ({
        ...data,
        auto_capture_enabled:
          autoCaptureWasUpdating || autoCaptureUpdateVersion !== autoCaptureUpdateVersionRef.current
            ? previous?.auto_capture_enabled
            : data.auto_capture_enabled,
      }));
    } catch (error) {
      if (error.name !== "AbortError") {
        setActionError(error.message);
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [experiment, unit]);

  React.useEffect(() => {
    setStatus(initialStatus);
    setLoading(!initialStatus);
  }, [initialStatus, unit]);

  React.useEffect(() => {
    if (initialStatus) {
      return undefined;
    }

    const controller = new AbortController();
    void refreshStatus({ signal: controller.signal });

    return () => {
      controller.abort();
    };
  }, [initialStatus, refreshStatus]);

  const snapshotIntervalMinutes = status?.snapshot_interval_minutes;
  const refreshIntervalMs = typeof snapshotIntervalMinutes === "number" && snapshotIntervalMinutes > 0
    ? Math.max(MIN_CAMERA_REFRESH_INTERVAL_MS, snapshotIntervalMinutes * 60 * 1000)
    : null;

  React.useEffect(() => {
    if (initialStatus || !refreshIntervalMs) {
      return undefined;
    }

    const controller = new AbortController();
    const interval = window.setInterval(() => {
      void refreshStatus({ signal: controller.signal, showLoading: false });
    }, refreshIntervalMs);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [initialStatus, refreshIntervalMs, refreshStatus]);

  const hasLatestStill = Boolean(status?.latest_still);
  const openMediaUrl = status?.latest_still
    ? experimentStillUrl(unit, experiment, status.latest_still.image_id)
    : null;
  const handleMissingImage = React.useCallback(() => {
    setStatus((previous) => (
      previous
        ? {
            ...previous,
            latest_still: null,
          }
        : previous
    ));
  }, []);

  const handleAutoCaptureChange = React.useCallback(async (event) => {
    if (autoCaptureUpdatePendingRef.current) {
      return;
    }

    const autoCaptureEnabled = event.target.checked;
    const previouslyEnabled = status?.auto_capture_enabled !== false;
    autoCaptureUpdateVersionRef.current += 1;
    autoCaptureUpdatePendingRef.current = true;
    setAutoCaptureUpdatePending(true);
    setActionError(null);
    setStatus((previous) => (
      previous
        ? { ...previous, auto_capture_enabled: autoCaptureEnabled }
        : previous
    ));

    try {
      const taskPayload = await fetchTaskResult(workerCameraSettingsPath(unit), {
        fetchOptions: {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auto_capture_enabled: autoCaptureEnabled }),
        },
      });
      const result = getUnitTaskResult(
        taskPayload,
        unit,
        "Could not update automatic snapshots on this Pioreactor.",
      );
      setStatus((previous) => (
        previous
          ? { ...previous, auto_capture_enabled: result.auto_capture_enabled }
          : previous
      ));
    } catch (error) {
      setStatus((previous) => (
        previous
          ? { ...previous, auto_capture_enabled: previouslyEnabled }
          : previous
      ));
      setActionError(
        `Could not update automatic snapshots. ${error.message || "Please try again."}`,
      );
    } finally {
      autoCaptureUpdatePendingRef.current = false;
      setAutoCaptureUpdatePending(false);
    }
  }, [status?.auto_capture_enabled, unit]);

  const automaticStillsDisabledInConfig = snapshotIntervalMinutes === 0;
  const automaticStillsEnabled = status?.auto_capture_enabled !== false;

  return (
    <>
      <Card sx={{ height: "100%" }}>
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", justifyContent: "space-between" }}>
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", minWidth: 0, flexWrap: "wrap" }}
              >
                <PioreactorIcon />
                <Typography variant="h6" noWrap>
                  <Box sx={{ fontWeight: "fontWeightRegular" }}>{unit}'s Camera</Box>
                </Typography>
                {status?.available === false && (
                  <Chip
                    size="small"
                    variant="outlined"
                    icon={<ImageNotSupportedOutlinedIcon />}
                    label="Camera unavailable"
                  />
                )}
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ textAlign: "right", whiteSpace: "nowrap"}}>
                {experimentStartTime ? (
                  <UnderlineSpan title={formatCaptureTime(status?.latest_still)}>
                    {formatCaptureDelta(status?.latest_still, experimentStartTime)}
                  </UnderlineSpan>
                ) : (
                  formatCaptureTime(status?.latest_still)
                )}
              </Typography>
            </Stack>

            <Box
              sx={{
                position: "relative",
                borderRadius: 1,
                overflow: "hidden",
                bgcolor: "action.hover",
                minHeight: 220,
              }}
            >
              {loading ? (
                <Stack sx={{ alignItems: "center", justifyContent: "center", minHeight: 220 }}>
                  <CircularProgress size={28} />
                </Stack>
              ) : (
                <CameraMedia
                  unit={unit}
                  status={status}
                  imageUrl={openMediaUrl}
                  onOpenViewer={() => setViewerOpen(true)}
                  onMissingImage={handleMissingImage}
                />
              )}
            </Box>

            {actionError && <Alert severity="error">{actionError}</Alert>}

            <Stack
              direction="row"
              spacing={1}
              sx={{ alignItems: "center", flexWrap: "wrap", justifyContent: "space-between", rowGap: 1 }}
            >
              <Box sx={{ display: "flex", alignItems: "center", flex: "1 1 240px", minHeight: 40, minWidth: 0 }}>
                {status && (
                  <FormControlLabel
                    control={
                      <Switch
                        checked={automaticStillsEnabled}
                        disabled={autoCaptureUpdatePending || automaticStillsDisabledInConfig}
                        onChange={handleAutoCaptureChange}
                      />
                    }
                    label={
                      automaticStillsDisabledInConfig
                        ? "Automatic snapshots disabled in configuration"
                        : "Capture snapshots automatically"
                    }
                    sx={{ m: 0 }}
                  />
                )}
                <Box sx={{ display: "flex", justifyContent: "center", width: 20 }}>
                  {autoCaptureUpdatePending && (
                    <CircularProgress aria-label="Saving automatic snapshot setting" size={16} />
                  )}
                </Box>
              </Box>
              <Stack direction="row" spacing={0.5} sx={{ flex: "0 0 auto", ml: "auto" }}>
                <Tooltip title="View snapshot history">
                  <IconButton
                    component={Link}
                    to={`/cameras/${encodeURIComponent(unit)}`}
                    aria-label="View snapshot history"
                    sx={{ minHeight: 44, minWidth: 44 }}
                  >
                    <PhotoLibraryOutlinedIcon />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Open image">
                  <span>
                    <IconButton
                      component="a"
                      href={openMediaUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      disabled={!hasLatestStill}
                      aria-label="Open image"
                      sx={{ minHeight: 44, minWidth: 44 }}
                    >
                      <FullscreenIcon />
                    </IconButton>
                  </span>
                </Tooltip>
              </Stack>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Dialog open={viewerOpen} onClose={() => setViewerOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle sx={{ pr: 6 }}>
          {unit}
          <IconButton
            aria-label="Close"
            onClick={() => setViewerOpen(false)}
            sx={{ position: "absolute", right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ bgcolor: "action.hover", borderRadius: 1, overflow: "hidden" }}>
            <CameraMedia
              unit={unit}
              status={status}
              imageUrl={openMediaUrl}
              onOpenViewer={() => {}}
              onMissingImage={handleMissingImage}
            />
          </Box>
        </DialogContent>
      </Dialog>

    </>
  );
}
