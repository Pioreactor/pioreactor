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
import HelpOutlineOutlinedIcon from "@mui/icons-material/HelpOutlineOutlined";
import ImageNotSupportedOutlinedIcon from "@mui/icons-material/ImageNotSupportedOutlined";
import LocalSeeIcon from "@mui/icons-material/LocalSee";
import PhotoLibraryOutlinedIcon from "@mui/icons-material/PhotoLibraryOutlined";
import ScheduleIcon from "@mui/icons-material/Schedule";

import PioreactorIcon from "./PioreactorIcon";
import UnderlineSpan from "./UnderlineSpan";
import useCameraResource from "../hooks/useCameraResource";
import { fetchTaskResult, getUnitTaskResult } from "../utils/tasks";
import { experimentPathSegment } from "../utils/url";

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

function CameraEmptyState({
  title,
  detail,
  icon = <ImageNotSupportedOutlinedIcon color="action" sx={{ fontSize: 40 }} />,
}) {
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
      {icon}
      <Typography variant="subtitle2">{title}</Typography>
      {detail && <Typography variant="body2">{detail}</Typography>}
    </Stack>
  );
}

function CameraMedia({ unit, status, imageUrl, onOpenViewer, onMissingImage }) {
  const latestStill = status?.latest_still;

  if (!latestStill) {
    if (status?.detection_status === "configured_camera_not_detected") {
      return (
        <CameraEmptyState
          title="No camera detected"
          detail="The configured camera was not detected on this Pioreactor."
        />
      );
    }

    if (status?.detection_status === "unknown") {
      return (
        <CameraEmptyState
          title="Camera status unavailable"
          detail="Camera detection did not complete."
          icon={<HelpOutlineOutlinedIcon color="action" sx={{ fontSize: 40 }} />}
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
  status: controlledStatus,
  onStatusChange,
  experiment,
  experimentStartTime = null,
}) {
  const ownsStatus = controlledStatus === undefined;
  const statusUrl = ownsStatus && unit && experiment
    ? workerCameraPath(unit, "status", experiment)
    : null;
  const {
    data: loadedStatus,
    error: statusError,
    loading,
    setData: setLoadedStatus,
  } = useCameraResource({
    mqttTopic: statusUrl ? `pioreactor/${unit}/${experiment}/camera/latest_still` : null,
    url: statusUrl,
  });
  const status = ownsStatus ? loadedStatus : controlledStatus;
  const [viewerOpen, setViewerOpen] = React.useState(false);
  const [actionError, setActionError] = React.useState(null);
  const [autoCaptureUpdatePending, setAutoCaptureUpdatePending] = React.useState(false);
  const [autoCaptureOverride, setAutoCaptureOverride] = React.useState(null);
  const autoCaptureUpdatePendingRef = React.useRef(false);

  const setStatus = React.useCallback((nextStatus) => {
    if (ownsStatus) {
      setLoadedStatus(nextStatus);
    } else {
      onStatusChange?.(nextStatus);
    }
  }, [onStatusChange, ownsStatus, setLoadedStatus]);

  const snapshotIntervalMinutes = status?.snapshot_interval_minutes;

  const hasLatestStill = Boolean(status?.latest_still);
  const latestStillIsScheduled = status?.latest_still?.capture_reason !== "manual";
  const latestStillCaptureReasonLabel = latestStillIsScheduled
    ? "Scheduled snapshot"
    : "Manual snapshot";
  const LatestStillCaptureReasonIcon = latestStillIsScheduled ? ScheduleIcon : LocalSeeIcon;
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
  }, [setStatus]);

  const handleAutoCaptureChange = React.useCallback(async (event) => {
    if (autoCaptureUpdatePendingRef.current) {
      return;
    }

    const autoCaptureEnabled = event.target.checked;
    autoCaptureUpdatePendingRef.current = true;
    setAutoCaptureUpdatePending(true);
    setAutoCaptureOverride(autoCaptureEnabled);
    setActionError(null);

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
      setActionError(
        `Could not update automatic snapshots. ${error.message || "Please try again."}`,
      );
    } finally {
      autoCaptureUpdatePendingRef.current = false;
      setAutoCaptureUpdatePending(false);
      setAutoCaptureOverride(null);
    }
  }, [setStatus, unit]);

  const automaticStillsDisabledInConfig = snapshotIntervalMinutes === 0;
  const automaticStillsEnabled = autoCaptureOverride ?? status?.auto_capture_enabled !== false;

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
                {status?.detection_status === "configured_camera_not_detected" && (
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

            {(statusError || actionError) && (
              <Alert severity="error">{statusError || actionError}</Alert>
            )}

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
          <Typography variant="h6" component="div">
            {unit}
          </Typography>
          {status?.latest_still && (
            <>
              <Typography variant="subtitle2" component="div" color="text.secondary">
                {formatCaptureTime(status.latest_still)}
              </Typography>
              <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", minWidth: 0 }}>
                <Typography
                  variant="subtitle2"
                  component="div"
                  color="text.secondary"
                  sx={{ overflowWrap: "anywhere" }}
                >
                  {status.latest_still.image_id}
                </Typography>
                <Tooltip title={latestStillCaptureReasonLabel}>
                  <LatestStillCaptureReasonIcon
                    role="img"
                    titleAccess={latestStillCaptureReasonLabel}
                    fontSize="small"
                    sx={{ color: "text.secondary", flexShrink: 0 }}
                  />
                </Tooltip>
              </Stack>
            </>
          )}
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
