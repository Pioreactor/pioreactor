import React from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActions from "@mui/material/CardActions";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import RefreshIcon from "@mui/icons-material/Refresh";
import UsbIcon from "@mui/icons-material/Usb";

import Snackbar from "./Snackbar";
import { fetchTaskResult } from "../utils/tasks";

function unwrapUnitTaskResult(payload, unit) {
  const result = payload?.result;
  if (result && typeof result === "object" && !Array.isArray(result) && unit in result) {
    return result[unit];
  }
  return result;
}

function getUsbRows(status) {
  if (!status) {
    return [];
  }

  const partitions = Array.isArray(status.partitions) ? status.partitions : [];
  if (!status.active_mount) {
    return partitions;
  }

  return partitions.map((partition) => {
    if (partition.device !== status.active_mount.device) {
      return partition;
    }
    return {
      ...partition,
      ...status.active_mount,
      mounted: true,
    };
  });
}

function getPartitionStatus(partition) {
  if (partition.unsupported_reason) {
    return "Unsupported";
  }
  if (partition.mounted) {
    return partition.writable === false ? "Mounted read-only" : "Mounted";
  }
  return "Detected";
}

function UsbPartitionActionMenu({partition, isBusy, onMount, onEject}) {
  const [anchorEl, setAnchorEl] = React.useState(null);
  const menuOpen = Boolean(anchorEl);
  const canMount = !partition.mounted && !partition.unsupported_reason;
  const canEject = Boolean(partition.mounted);

  const handleClose = () => {
    setAnchorEl(null);
  };

  return (
    <React.Fragment>
      <span>
        <IconButton
          size="small"
          aria-label={`More actions for ${partition.display_name || partition.device}`}
          disabled={isBusy || (!canMount && !canEject)}
          onClick={(event) => setAnchorEl(event.currentTarget)}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
      </span>
      <Menu anchorEl={anchorEl} open={menuOpen} onClose={handleClose}>
        {canMount && (
          <MenuItem
            onClick={() => {
              handleClose();
              onMount(partition.device);
            }}
          >
            Mount
          </MenuItem>
        )}
        {canEject && (
          <MenuItem
            onClick={() => {
              handleClose();
              onEject(partition.device);
            }}
          >
            Eject
          </MenuItem>
        )}
      </Menu>
    </React.Fragment>
  );
}

export default function UsbDriveCard({unit}) {
  const [usbStatus, setUsbStatus] = React.useState(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [isBusy, setIsBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");
  const isMountedRef = React.useRef(false);

  const showSnackbar = (message) => {
    setSnackbarMessage(message);
    setSnackbarOpen(true);
  };

  const usbEndpoint = React.useCallback((suffix = "") => {
    if (unit) {
      return `/api/units/${encodeURIComponent(unit)}/usb${suffix}`;
    }
    return `/unit_api/usb${suffix}`;
  }, [unit]);

  const refreshUsbStatus = React.useCallback(async () => {
    if (isMountedRef.current) {
      setError("");
      setIsRefreshing(true);
    }
    try {
      let unitStatus;
      if (unit) {
        const payload = await fetchTaskResult(usbEndpoint(), {
          maxRetries: 80,
          delayMs: 100,
        });
        unitStatus = unwrapUnitTaskResult(payload, unit);
      } else {
        const response = await fetch(usbEndpoint());
        if (!response.ok) {
          throw new Error(`Failed to fetch USB status (HTTP ${response.status}).`);
        }
        unitStatus = await response.json();
      }

      if (!unitStatus) {
        throw new Error(unit ? `Could not reach ${unit}.` : "Could not read USB status.");
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
        setIsRefreshing(false);
      }
    }
  }, [unit, usbEndpoint]);

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
      const fetchOptions = {
        method: "POST",
        body: JSON.stringify(device ? {device} : {}),
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      };
      if (unit) {
        await fetchTaskResult(usbEndpoint("/mount"), {
          fetchOptions,
          maxRetries: 300,
          delayMs: 200,
        });
      } else {
        await fetchTaskResult("/unit_api/usb/mount", {
          fetchOptions,
          maxRetries: 300,
          delayMs: 200,
        });
      }
      showSnackbar("USB drive mounted.");
      await refreshUsbStatus();
    } catch (err) {
      console.error("Failed to mount USB:", err);
      setError(err instanceof Error ? err.message : "Failed to mount USB drive.");
    } finally {
      setIsBusy(false);
    }
  };

  const handleEject = async (device) => {
    setIsBusy(true);
    setError("");
    try {
      const fetchOptions = {
        method: "POST",
        body: JSON.stringify(device ? {device} : {}),
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      };
      if (unit) {
        await fetchTaskResult(usbEndpoint("/eject"), {
          fetchOptions,
          maxRetries: 300,
          delayMs: 200,
        });
      } else {
        await fetchTaskResult("/unit_api/usb/eject", {
          fetchOptions,
          maxRetries: 300,
          delayMs: 200,
        });
      }
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

  const usbRows = getUsbRows(usbStatus);

  return (
    <Card>
      <CardContent sx={{p: 2}} id="usb-card">
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
            {usbStatus.error && (
              <Alert severity="error" sx={{mt: 2}}>{usbStatus.error}</Alert>
            )}

            {usbRows.length === 0 && !usbStatus.error && (
              <Typography variant="body2" color="text.secondary" sx={{mt: 1}}>
                No USB drives detected.
              </Typography>
            )}

            {usbRows.length > 0 && (
              <Box sx={{mt: 1}}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{padding: "6px 0px"}}>Name</TableCell>
                      <TableCell>Device</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right" sx={{padding: "6px 0px", width: 36}} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {usbRows.map((partition) => (
                      <TableRow key={partition.device}>
                        <TableCell sx={{padding: "6px 0px"}}>
                          {partition.display_name || "-"}
                        </TableCell>
                        <TableCell>{partition.device}</TableCell>
                        <TableCell>{getPartitionStatus(partition)}</TableCell>
                        <TableCell align="right" sx={{padding: "6px 0px"}}>
                          <UsbPartitionActionMenu
                            partition={partition}
                            isBusy={isBusy}
                            onMount={handleMount}
                            onEject={handleEject}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}

            {usbRows.some((partition) => partition.unsupported_reason) && (
              <Alert severity="warning" sx={{mt: 2}}>
                {usbRows.find((partition) => partition.unsupported_reason).unsupported_reason}
              </Alert>
            )}
          </React.Fragment>
        )}
      </CardContent>

      <CardActions sx={{display: "flex", justifyContent: "flex-end"}}>
        <Button
          size="small"
          onClick={refreshUsbStatus}
          disabled={isBusy || isLoading}
          loading={isRefreshing}
          loadingPosition="start"
          startIcon={<RefreshIcon fontSize="small" />}
          sx={{textTransform: "none"}}
        >
          Refresh
        </Button>
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
