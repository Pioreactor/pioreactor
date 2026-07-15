import React from "react";
import dayjs from "dayjs";
import { Link } from "react-router";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

import CloseIcon from "@mui/icons-material/Close";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import ImageNotSupportedOutlinedIcon from "@mui/icons-material/ImageNotSupportedOutlined";
import PhotoLibraryOutlinedIcon from "@mui/icons-material/PhotoLibraryOutlined";

import PioreactorIcon from "./PioreactorIcon";
import UnderlineSpan from "./UnderlineSpan";
import { experimentPathSegment } from "../utils/url";

const textIcon = {verticalAlign: "middle", margin: "0px 3px"}
const MIN_CAMERA_REFRESH_INTERVAL_MS = 5000;

function workerCameraPath(unit, suffix, experiment) {
  return `/api/workers/${encodeURIComponent(unit)}/camera/experiments/${experimentPathSegment(experiment)}/${suffix}`;
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

  if (!status?.available) {
    return (
      <CameraEmptyState
        title="No camera detected"
        detail="Camera capture tools are not available on this Pioreactor."
      />
    );
  }

  if (!latestStill) {
    return (
      <CameraEmptyState
        title="No still image"
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
        alt={`Latest camera still for ${unit}`}
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
  detailsHref = null,
  experiment,
  experimentStartTime = null,
}) {
  const [status, setStatus] = React.useState(initialStatus);
  const [loading, setLoading] = React.useState(!initialStatus);
  const [viewerOpen, setViewerOpen] = React.useState(false);
  const [actionError, setActionError] = React.useState(null);

  const refreshStatus = React.useCallback(async ({ signal, showLoading = true } = {}) => {
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
      setStatus(data);
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

  return (
    <>
      <Card sx={{ height: "100%" }}>
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", justifyContent: "space-between" }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0 }}>
                <PioreactorIcon />
                <Typography variant="h6" noWrap>
                  <Box sx={{ fontWeight: "fontWeightRegular" }}>{unit}'s Camera</Box>
                </Typography>
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

            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "flex-end" }}>
              <Stack direction="row" spacing={0.5} sx={{ justifyContent: "flex-end" }}>
                {detailsHref && (
                    <Button
                      size="small"
                      component={Link}
                      to={detailsHref}
                      sx={{textTransform: 'none', float: "right" }}
                    >
                      <PhotoLibraryOutlinedIcon fontSize="small" sx={textIcon}/> View still history
                    </Button>
                )}
                    <Button
                      size="small"
                      component="a"
                      href={openMediaUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      disabled={!hasLatestStill}
                      sx={{textTransform: 'none', float: "right" }}
                    >
                      <FullscreenIcon fontSize="small" sx={textIcon}/> Open image
                    </Button>
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
