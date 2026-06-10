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
import { alpha } from "@mui/material/styles";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import CloseIcon from "@mui/icons-material/Close";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import ImageNotSupportedOutlinedIcon from "@mui/icons-material/ImageNotSupportedOutlined";
import PhotoLibraryOutlinedIcon from "@mui/icons-material/PhotoLibraryOutlined";

import PioreactorIcon from "./PioreactorIcon";
import { fetchTaskResult } from "../utils/tasks";

function workerCameraPath(unit, suffix) {
  return `/api/workers/${encodeURIComponent(unit)}/camera/${suffix}`;
}

function latestStillUrl(unit, imageVersion) {
  return `${workerCameraPath(unit, "latest.jpg")}?v=${imageVersion}`;
}

function formatCaptureTime(metadata) {
  if (!metadata?.captured_at) {
    return "No capture";
  }

  return dayjs(metadata.captured_at).format("YYYY-MM-DD HH:mm:ss");
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

function CameraMedia({ unit, status, imageVersion, onOpenViewer }) {
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
        detail="Capture a still image to create the latest view."
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
        src={latestStillUrl(unit, imageVersion)}
        sx={{ display: "block", width: "100%", aspectRatio: "4 / 3", objectFit: "contain" }}
      />
    </Box>
  );
}

export default function CameraPanel({
  unit,
  initialStatus = null,
  detailsHref = null,
}) {
  const [status, setStatus] = React.useState(initialStatus);
  const [loading, setLoading] = React.useState(!initialStatus);
  const [imageVersion, setImageVersion] = React.useState(Date.now());
  const [viewerOpen, setViewerOpen] = React.useState(false);
  const [actionError, setActionError] = React.useState(null);
  const [hasFreshStill, setHasFreshStill] = React.useState(false);
  const capturingRef = React.useRef(false);

  const refreshStatus = React.useCallback(async ({ signal } = {}) => {
    setLoading(true);
    setActionError(null);

    try {
      const response = await fetch(workerCameraPath(unit, "status"), { signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not fetch camera status.");
      }

      const data = await response.json();
      setStatus(data);
      setImageVersion(Date.now());
      setHasFreshStill(false);
    } catch (error) {
      if (error.name !== "AbortError") {
        setActionError(error.message);
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [unit]);

  React.useEffect(() => {
    setStatus(initialStatus);
    setLoading(!initialStatus);
    setHasFreshStill(false);
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

  const captureStill = React.useCallback(async () => {
    if (capturingRef.current) {
      return;
    }

    capturingRef.current = true;
    setActionError(null);

    try {
      const taskPayload = await fetchTaskResult(workerCameraPath(unit, "capture"), {
        fetchOptions: {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ capture_reason: "manual" }),
        },
        delayMs: 250,
      });
      const metadata = taskPayload.result;

      setStatus((previous) => ({
        ...(previous || {}),
        available: true,
        capture_available: true,
        latest_still: metadata,
      }));
      setImageVersion(Date.now());
      setHasFreshStill(true);
    } catch (error) {
      setActionError(error.message);
    } finally {
      capturingRef.current = false;
    }
  }, [unit]);

  const hasLatestStill = Boolean(status?.latest_still);
  const staleStillIsVisible = hasLatestStill && !hasFreshStill;
  const openMediaUrl = latestStillUrl(unit, imageVersion);

  return (
    <>
      <Card sx={{ height: "100%" }}>
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", justifyContent: "space-between" }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0 }}>
                <PioreactorIcon fontSize="small" />
                <Typography variant="h6" noWrap>{unit}</Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ textAlign: "right", whiteSpace: "nowrap" }}>
                {formatCaptureTime(status?.latest_still)}
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
                  imageVersion={imageVersion}
                  onOpenViewer={() => setViewerOpen(true)}
                />
              )}
              {staleStillIsVisible && (
                <Stack
                  spacing={1}
                  sx={{
                    position: "absolute",
                    inset: 0,
                    alignItems: "center",
                    justifyContent: "center",
                    bgcolor: (theme) => alpha(theme.palette.background.paper, 0.9),
                    color: "text.primary",
                    textAlign: "center",
                    px: 3,
                    zIndex: 1,
                  }}
                >
                  <CircularProgress size={30} />
                  <Typography variant="subtitle1" sx={{ fontWeight: "fontWeightBold" }}>
                    Updating camera image
                  </Typography>
                </Stack>
              )}
            </Box>

            {actionError && <Alert severity="error">{actionError}</Alert>}

            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
              <Stack direction="row" spacing={0.5} sx={{ justifyContent: "flex-end" }}>
                {detailsHref && (
                  <Tooltip title="View still history">
                    <IconButton
                      size="small"
                      component={Link}
                      to={detailsHref}
                    >
                      <PhotoLibraryOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip title="Open media">
                  <span>
                    <IconButton
                      size="small"
                      component="a"
                      href={openMediaUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      disabled={!hasLatestStill}
                    >
                      <FullscreenIcon fontSize="small" />
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
              imageVersion={imageVersion}
              onOpenViewer={() => {}}
            />
          </Box>
        </DialogContent>
      </Dialog>

    </>
  );
}
