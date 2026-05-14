import React from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActions from "@mui/material/CardActions";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import EjectIcon from "@mui/icons-material/Eject";
import RefreshIcon from "@mui/icons-material/Refresh";
import UsbIcon from "@mui/icons-material/Usb";

import Snackbar from "./Snackbar";
import { fetchTaskResult } from "../utils/tasks";

function formatBytes(bytes) {
  if (bytes == null) {
    return "-";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const precision = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function unwrapUnitTaskResult(payload, unit) {
  const result = payload?.result;
  if (result && typeof result === "object" && !Array.isArray(result) && unit in result) {
    return result[unit];
  }
  return result;
}

function getStatusLabel(status) {
  switch (status) {
    case "absent":
      return "No USB drive detected.";
    case "present_unmounted":
      return "USB drive detected.";
    case "mounted":
      return "USB drive mounted.";
    case "mounted_readonly":
      return "USB drive mounted read-only.";
    case "multiple_present":
      return "Multiple USB partitions detected.";
    case "unsupported":
      return "USB filesystem is not supported.";
    case "error":
      return "Unable to read USB status.";
    default:
      return "USB status unavailable.";
  }
}

function getPrimaryPartition(status) {
  if (status?.active_mount) {
    return status.active_mount;
  }

  if (Array.isArray(status?.partitions) && status.partitions.length === 1) {
    return status.partitions[0];
  }

  return null;
}

function PartitionList({partitions, isBusy, onMount}) {
  if (!Array.isArray(partitions) || partitions.length === 0) {
    return null;
  }

  return (
    <List dense sx={{mt: 1}}>
      {partitions.map((partition) => (
        <ListItem
          key={partition.device}
          disableGutters
          secondaryAction={
            !partition.mounted && (
              <Button
                size="small"
                variant="text"
                disabled={isBusy || Boolean(partition.unsupported_reason)}
                onClick={() => onMount(partition.device)}
                sx={{textTransform: "none"}}
              >
                Mount
              </Button>
            )
          }
        >
          <ListItemText
            primary={partition.display_name || partition.device}
            secondary={`${partition.device} · ${partition.fstype || "unknown filesystem"}`}
          />
        </ListItem>
      ))}
    </List>
  );
}

export default function UsbDriveCard({unit}) {
  const [usbStatus, setUsbStatus] = React.useState(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isBusy, setIsBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");
  const isMountedRef = React.useRef(false);

  const showSnackbar = (message) => {
    setSnackbarMessage(message);
    setSnackbarOpen(true);
  };

  const refreshUsbStatus = React.useCallback(async () => {
    if (!unit) {
      if (isMountedRef.current) {
        setUsbStatus(null);
        setIsLoading(false);
      }
      return;
    }

    if (isMountedRef.current) {
      setError("");
    }
    try {
      const payload = await fetchTaskResult(`/api/units/${encodeURIComponent(unit)}/usb`, {
        maxRetries: 80,
        delayMs: 100,
      });
      const unitStatus = unwrapUnitTaskResult(payload, unit);
      if (!unitStatus) {
        throw new Error(`Could not reach ${unit}.`);
      }
      if (isMountedRef.current) {
        setUsbStatus(unitStatus);
      }
    } catch (err) {
      console.error("Failed to fetch USB status:", err);
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to fetch USB status.");
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [unit]);

  React.useEffect(() => {
    isMountedRef.current = true;
    setIsLoading(true);

    async function loadStatus() {
      await refreshUsbStatus();
    }

    loadStatus();

    return () => {
      isMountedRef.current = false;
    };
  }, [refreshUsbStatus]);

  const handleMount = async (device) => {
    setIsBusy(true);
    setError("");
    try {
      await fetchTaskResult(`/api/units/${encodeURIComponent(unit)}/usb/mount`, {
        fetchOptions: {
          method: "POST",
          body: JSON.stringify(device ? {device} : {}),
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
        },
        maxRetries: 300,
        delayMs: 200,
      });
      showSnackbar("USB drive mounted.");
      await refreshUsbStatus();
    } catch (err) {
      console.error("Failed to mount USB:", err);
      setError(err instanceof Error ? err.message : "Failed to mount USB drive.");
    } finally {
      setIsBusy(false);
    }
  };

  const handleEject = async () => {
    setIsBusy(true);
    setError("");
    try {
      await fetchTaskResult(`/api/units/${encodeURIComponent(unit)}/usb/eject`, {
        fetchOptions: {
          method: "POST",
          body: JSON.stringify({}),
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
        },
        maxRetries: 300,
        delayMs: 200,
      });
      showSnackbar("USB drive ejected.");
      await refreshUsbStatus();
    } catch (err) {
      console.error("Failed to eject USB:", err);
      setError(err instanceof Error ? err.message : "Failed to eject USB drive.");
    } finally {
      setIsBusy(false);
    }
  };

  const handleSnackbarClose = (_event, reason) => {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  };

  const primaryPartition = getPrimaryPartition(usbStatus);
  const isMounted = usbStatus?.status === "mounted" || usbStatus?.status === "mounted_readonly";
  const canMountSingle =
    usbStatus?.status === "present_unmounted" &&
    Array.isArray(usbStatus?.partitions) &&
    usbStatus.partitions.length === 1 &&
    !usbStatus.partitions[0].unsupported_reason;

  return (
    <Card>
      <CardContent sx={{p: 2}}>
        <Typography variant="h6" component="h2">
          <Box sx={{ fontWeight: "fontWeightRegular", display: "flex", alignItems: "center" }}>
            <UsbIcon fontSize="small" sx={{mr: 0.75}} />
            USB drive
          </Box>
        </Typography>

        {isLoading && (
          <Box sx={{textAlign: "center", mt: 2}}>
            <CircularProgress size={33}/>
          </Box>
        )}

        {!isLoading && error && (
          <Alert severity="error" sx={{mt: 2}}>{error}</Alert>
        )}

        {!isLoading && !error && usbStatus && (
          <React.Fragment>
            <Typography variant="body2" color="text.secondary" sx={{mt: 1}}>
              {getStatusLabel(usbStatus.status)}
            </Typography>

            {usbStatus.error && (
              <Alert severity="error" sx={{mt: 2}}>{usbStatus.error}</Alert>
            )}

            {primaryPartition && (
              <Box sx={{mt: 2}}>
                <Typography variant="body2">
                  {primaryPartition.display_name || primaryPartition.device}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {primaryPartition.device}
                  {primaryPartition.fstype ? ` · ${primaryPartition.fstype}` : ""}
                </Typography>
                {isMounted && (
                  <Typography variant="body2" color="text.secondary">
                    {formatBytes(primaryPartition.free_bytes)} available
                  </Typography>
                )}
                {primaryPartition.unsupported_reason && (
                  <Alert severity="warning" sx={{mt: 2}}>
                    {primaryPartition.unsupported_reason}
                  </Alert>
                )}
              </Box>
            )}

            {usbStatus.status === "multiple_present" && (
              <React.Fragment>
                <Divider sx={{mt: 2}} />
                <PartitionList
                  partitions={usbStatus.partitions}
                  isBusy={isBusy}
                  onMount={handleMount}
                />
              </React.Fragment>
            )}
          </React.Fragment>
        )}
      </CardContent>

      <CardActions sx={{display: "flex", justifyContent: "flex-end"}}>
        <Button
          size="small"
          onClick={refreshUsbStatus}
          disabled={isBusy || isLoading}
          sx={{textTransform: "none"}}
        >
          <RefreshIcon fontSize="small" sx={{mr: 0.5}} />
          Refresh
        </Button>
        {canMountSingle && (
          <Button
            size="small"
            variant="contained"
            onClick={() => handleMount(usbStatus.partitions[0].device)}
            disabled={isBusy}
            sx={{textTransform: "none"}}
          >
            Mount
          </Button>
        )}
        {isMounted && (
          <Button
            size="small"
            color="secondary"
            onClick={handleEject}
            disabled={isBusy}
            sx={{textTransform: "none"}}
          >
            <EjectIcon fontSize="small" sx={{mr: 0.5}} />
            Eject
          </Button>
        )}
      </CardActions>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
        autoHideDuration={2500}
        key={`snackbar-usb-drive-${unit}`}
      />
    </Card>
  );
}
