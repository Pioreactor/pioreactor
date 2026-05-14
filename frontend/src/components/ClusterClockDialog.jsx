import React from "react";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import CloseIcon from "@mui/icons-material/Close";
import { Link } from "react-router";
import PioreactorIcon from "./PioreactorIcon";
import { checkTaskCallback } from "../utils/tasks";

dayjs.extend(utc);

function ClusterClockDialog({open, onClose, leaderHostname}) {
  const [clockData, setClockData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [updatingClock, setUpdatingClock] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [timestampLocal, setTimestampLocal] = React.useState(dayjs().local().format("YYYY-MM-DD HH:mm:ss"));
  const hasUserEditedTimestamp = React.useRef(false);

  const normalizeClockData = React.useCallback((result) => Object.fromEntries(
    Object.entries(result || {}).map(([unitName, info]) => {
      const baseInfo = info || {};
      const clockTimeMs = baseInfo.clock_time
        ? dayjs.utc(baseInfo.clock_time, "YYYY-MM-DD[T]HH:mm:ss.SSS[Z]").local().valueOf()
        : null;
      return [unitName, { ...baseInfo, clock_time_ms: clockTimeMs }];
    })
  ), []);

  const fetchBroadcastData = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch("/api/units/$broadcast/system/utc_clock", {
        method: "GET",
      });

      if (!response.ok) {
        throw new Error(`Broadcast request failed with status ${response.status}`);
      }

      const broadcastData = await response.json();
      const finalResult = await checkTaskCallback(broadcastData.result_url_path);

      setClockData(normalizeClockData(finalResult.result));
    } catch (err) {
      setError(err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [normalizeClockData]);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    fetchBroadcastData();
  }, [fetchBroadcastData, open]);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    const intervalId = setInterval(() => {
      setClockData((prev) => {
        if (!prev) return prev;
        return Object.fromEntries(Object.entries(prev).map(([unitName, info]) => {
          if (info?.clock_time_ms == null) return [unitName, info];
          return [unitName, { ...info, clock_time_ms: info.clock_time_ms + 1000 }];
        }));
      });

      if (!hasUserEditedTimestamp.current) {
        setTimestampLocal((prev) => {
          const parsed = dayjs(prev, "YYYY-MM-DD HH:mm:ss", true);
          const baseMs = parsed.isValid() ? parsed.valueOf() : dayjs().local().valueOf();
          return dayjs(baseMs + 1000).format("YYYY-MM-DD HH:mm:ss");
        });
      }
    }, 1000);

    return () => clearInterval(intervalId);
  }, [open]);

  async function handlePostTimestamp() {
    setUpdatingClock(true);
    try {
      const response = await fetch("/api/system/utc_clock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ utc_clock_time: dayjs(timestampLocal, "YYYY-MM-DD HH:mm:ss").utc().format() }),
      });
      if (!response.ok) {
        throw new Error(`Request failed with status: ${response.status}`);
      }
      const broadcastData = await response.json();
      await checkTaskCallback(broadcastData.result_url_path);
      await new Promise((resolve) => setTimeout(resolve, 1000));

      fetchBroadcastData();
    } catch (err) {
      console.error("Error posting timestamp:", err);
    } finally {
      setUpdatingClock(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ pr: 6 }}>
        Cluster clocks
        <IconButton
          aria-label="close"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        {loading && (
          <Box sx={{textAlign: "center"}}>
            <CircularProgress size={33}/>
          </Box>
        )}

        {error && (
          <Alert severity="error">{error}</Alert>
        )}

        {!loading && !error && clockData && (
          <TableContainer sx={{ maxHeight: "400px", width: "100%", overflowY: "auto" }}>
            <Table size="small" sx={{mt: 1}}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{padding: "6px 0px"}}>Pioreactor</TableCell>
                  <TableCell align="right" sx={{padding: "6px 0px"}}>Clock time (localtime)</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.entries(clockData).map(([unitName, info]) => {
                  return (
                    <TableRow key={unitName}>
                      <TableCell sx={{padding: "6px 0px"}}>
                        <Chip
                          size="small"
                          icon={<PioreactorIcon/>}
                          label={unitName}
                          clickable
                          component={Link}
                          to={leaderHostname === unitName ? "/leader" : "/pioreactors/" + unitName}
                        />
                      </TableCell>
                      <TableCell align="right" sx={{padding: "6px 0px"}}>{info?.clock_time_ms ? dayjs(info.clock_time_ms).format("MMM D, YYYY HH:mm:ss") : "No data received"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        <Box sx={{ mt: 4 }}>
          <TextField
            size="small"
            variant="outlined"
            label="Timestamp (localtime)"
            value={timestampLocal}
            onChange={(e) => {
              setTimestampLocal(e.target.value);
              hasUserEditedTimestamp.current = true;
            }}
          />
          <Button
            variant="text"
            loading={updatingClock}
            sx={{ ml: 2, textTransform: "none" }}
            onClick={handlePostTimestamp}
          >
            Update clocks
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
}

export default ClusterClockDialog;
