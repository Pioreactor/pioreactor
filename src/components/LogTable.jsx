import React, { useState, useEffect } from 'react';
import { useMQTT } from '../providers/MQTTContext';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import Button from '@mui/material/Button';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import { styled } from '@mui/material/styles';
import Divider from '@mui/material/Divider';
import AddIcon from '@mui/icons-material/Add';
import { Link } from 'react-router-dom';
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';

import { ERROR_COLOR, WARNING_COLOR, NOTICE_COLOR } from "../utilities";

// Activate the UTC plugin
dayjs.extend(utc);

const textIcon = { verticalAlign: "middle", margin: "0px 3px" };

const StyledTableCell = styled(TableCell)(({ level }) => ({
  padding: "6px 6px 6px 10px",
  fontSize: 13,
  backgroundColor:
    level === "ERROR"   ? ERROR_COLOR   :
    level === "WARNING" ? WARNING_COLOR :
    level === "NOTICE"  ? NOTICE_COLOR  : "white",
  whiteSpace: "normal"
}));

const StyledTableCellFiller = styled(TableCell)(({ level }) => ({
  paddingTop: "25px",
  paddingBottom: "15px",
  textAlign: "center"
}));

const StyledTimeTableCell = styled(TableCell)(({ level }) => ({
  padding: "6px 6px 6px 10px",
  fontSize: 13,
  backgroundColor:
    level === "ERROR"   ? ERROR_COLOR   :
    level === "WARNING" ? WARNING_COLOR :
    level === "NOTICE"  ? NOTICE_COLOR  : "white",
  whiteSpace: "pre"
}));

const LEVELS = ["NOTSET", "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL"];

function LogTable({ activeUnits, byDuration, experimentStartTime, experiment, config, relabelMap }) {
  const [listOfLogs, setListOfLogs] = useState([]);
  const { client, subscribeToTopic } = useMQTT();

  // Dialog states
  const [openDialog, setOpenDialog] = useState(false);
  const [selectedPioreactor, setSelectedPioreactor] = useState("");
  const [selectedExperiment, setSelectedExperiment] = useState(experiment || "");
  const [message, setMessage] = useState("");
  const [timestampLocal, setTimestampLocal] = useState(dayjs().local().format('YYYY-MM-DD HH:mm:ss'));
  const [source, setSource] = useState("");

  useEffect(() => {
    const getData = async () => {
      const response = await fetch(
        `/api/experiments/${experiment}/logs?` + new URLSearchParams({
          min_level: config.logging.ui_log_level
        })
      );
      const logs = await response.json();
      setListOfLogs(logs.map((log) => ({
        ...log,
        key: `${log.timestamp}-${log.pioreactor_unit}-${log.level}-${log.message}`,
      })));
    };
    if (experiment && Object.keys(config).length) {
      getData();
    }
  }, [experiment, config]);

  useEffect(() => {
    if (client && Object.keys(config).length) {
      const levelRequested = config.logging.ui_log_level.toUpperCase() || "INFO";
      const ix = LEVELS.indexOf(levelRequested);
      subscribeToTopic(
        LEVELS.slice(ix).map(level => `pioreactor/+/$experiment/logs/+/${level.toLowerCase()}`),
        onMessage,
        "LogTable"
      );
    }
  }, [client, config]);

  useEffect(() => {
    if (experiment && client && Object.keys(config).length) {
      const levelRequested = config.logging.ui_log_level.toUpperCase() || "INFO";
      const ix = LEVELS.indexOf(levelRequested);
      subscribeToTopic(
        LEVELS.slice(ix).map(level => `pioreactor/+/${experiment}/logs/+/${level.toLowerCase()}`),
        onMessage,
        "LogTable"
      );
    }
  }, [client, experiment, config]);

  const relabelUnit = (unit) =>
    (relabelMap && relabelMap[unit]) ? `${relabelMap[unit]} / ${unit}` : unit;

  const toTimestampObject = (timestamp) => {
    return dayjs.utc(timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSS[Z]');
  };

  const timestampCell = (timestamp) => {
    const ts = toTimestampObject(timestamp);
    const localTs = ts.local();
    if (byDuration) {
      const deltaHours = Math.round(ts.diff(experimentStartTime, 'hours', true) * 1e2) / 1e2;
      return <span title={localTs.format('YYYY-MM-DD HH:mm:ss')}>{deltaHours} h</span>;
    } else {
      return <span title={localTs.format('YYYY-MM-DD HH:mm:ss')}>{localTs.format('HH:mm:ss')}</span>;
    }
  };

  const onMessage = (topic, message, packet) => {
    const unit = topic.toString().split("/")[1];
    const payload = JSON.parse(message.toString());
    setListOfLogs((currentLogs) => [
      {
        timestamp: toTimestampObject(payload.timestamp),
        pioreactor_unit: unit,
        message: String(payload.message),
        task: payload.task,
        level: payload.level.toUpperCase(),
        key: `${dayjs.utc().format()}-${unit}-${payload.level.toUpperCase()}-${String(payload.message)}`,
      },
      ...currentLogs.slice(0, 49),
    ]);
  };

  // Dialog handlers
  const handleOpenDialog = () => {
    setTimestampLocal(dayjs().local().format("YYYY-MM-DD HH:mm:ss"));
    setSelectedPioreactor(activeUnits.length > 0 ? activeUnits[0] : "");
    setSelectedExperiment(experiment || "<All experiments>");
    setMessage(message);
    setSource("");
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
  };

  const handleSubmitDialog = async () => {

    const timestampUTC = dayjs(timestampLocal, 'YYYY-MM-DD HH:mm:ss', true)
      .utc()
      .format('YYYY-MM-DD[T]HH:mm:ss[Z]');
    try {
      const body = {
        pioreactor_unit: selectedPioreactor,
        experiment: selectedExperiment,
        message: message,
        timestamp: timestampUTC,
        source: source
      };
      // Made-up API endpoint
      const response = await fetch(`/api/experiments/${selectedExperiment}/logs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (!response.ok) {
        throw new Error("Failed to submit new log entry.");
      }
      setOpenDialog(false);
      setMessage("")
    } catch (error) {
      console.error("Error adding new log entry:", error);
    }
  };

  return (
    <Card>
      <CardContent sx={{  '&:last-child': { pb: 0 }}}>
        <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">Recent event logs</Box>
        </Typography>
        <TableContainer sx={{ height: "660px", width: "100%", overflowY: "auto"}}>
          <Table stickyHeader size="small" aria-label="log table">
            <TableHead>
              <TableRow>
                <StyledTableCell>Time</StyledTableCell>
                <StyledTableCell>Pioreactor</StyledTableCell>
                <StyledTableCell>Source</StyledTableCell>
                <StyledTableCell>Message</StyledTableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {listOfLogs.map((log, i) => (
                <React.Fragment key={log.key}>
                  <TableRow>
                    <StyledTimeTableCell level={log.level}>
                      {timestampCell(log.timestamp)}
                    </StyledTimeTableCell>
                    <StyledTableCell level={log.level}>
                      {relabelUnit(log.pioreactor_unit)}
                    </StyledTableCell>
                    <StyledTableCell level={log.level}>
                      {log.task.replace(/_/g, ' ')}
                    </StyledTableCell>
                    <StyledTableCell level={log.level}>
                      {log.message}
                    </StyledTableCell>
                  </TableRow>
                  {listOfLogs[i+1] &&
                    toTimestampObject(log.timestamp).diff(toTimestampObject(listOfLogs[i+1].timestamp), 'hours', true) >= 1 && (
                      <TableRow key={`filler-${log.key}`}>
                        <StyledTableCellFiller colSpan="4">
                          {toTimestampObject(log.timestamp).diff(toTimestampObject(listOfLogs[i+1].timestamp), 'hours')} hours earlier...
                        </StyledTableCellFiller>
                      </TableRow>
                  )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <Divider/>
        <CardActions sx={{justifyContent:"right"}}>
          <Button
            style={{textTransform: 'none', float: "right", marginRight: "0px"}}
            color="primary"
            onClick={handleOpenDialog}
          >
            <AddIcon fontSize="15" sx={textIcon}/> Record a new log
          </Button>
          <Button
            to={`/export-data`}
            component={Link}
            color="primary"
            style={{textTransform: "none", verticalAlign: "middle", margin: "0px 3px"}}
          >
            <ListAltOutlinedIcon style={{ fontSize: 17, margin: "0px 3px"}} color="primary"/> Export all logs
          </Button>
        </CardActions>
      </CardContent>

      <Dialog open={openDialog} onClose={handleCloseDialog} aria-labelledby="form-dialog-title" fullWidth maxWidth="sm">
        <DialogTitle sx={{ mb: 2 }}>
          Record a new log
          <IconButton
            aria-label="close"
            onClick={handleCloseDialog}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
              color: (theme) => theme.palette.grey[500],
            }}
            size="large"
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent >
          <Typography variant="body2" sx={{ mb: 3 }}>
            Fill out the form below to add a new log entry to Pioreactor logs. You can select
            which Pioreactor or experiment the entry applies to, or choose "&lt;All experiments&gt;".
          </Typography>

          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <FormControl required size="small" variant="outlined" sx={{ flex: 1 }}>
              <InputLabel id="select-pioreactor-label">Select a Pioreactor</InputLabel>
              <Select
                labelId="select-pioreactor-label"
                label="Select a Pioreactor"
                value={selectedPioreactor}
                onChange={(e) => setSelectedPioreactor(e.target.value)}
              >
                {activeUnits.map((unit) => (
                  <MenuItem key={unit} value={unit}>{unit}</MenuItem>
                ))}
                <MenuItem value="$broadcast">&lt;All Pioreactors&gt;</MenuItem>

              </Select>
            </FormControl>

            <FormControl required size="small" variant="outlined" sx={{ flex: 1 }}>
              <InputLabel id="select-experiment-label">Which experiment?</InputLabel>
              <Select
                labelId="select-experiment-label"
                label="Which experiment?"
                value={selectedExperiment}
                onChange={(e) => setSelectedExperiment(e.target.value)}
              >
                <MenuItem value={experiment}>{experiment}</MenuItem>
                <MenuItem value="$experiment">&lt;All experiments&gt;</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              required
              size="small"
              variant="outlined"
              label="Message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              multiline
              minRows={2}
              sx={{ flex: 1 }}
            />

          </Box>
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              required
              size="small"
              variant="outlined"
              label="Timestamp"
              value={timestampLocal}
              onChange={(e) => setTimestampLocal(e.target.value)}
            />
            <TextField
              variant="outlined"
              size="small"
              label="Source (optional)"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            />
          </Box>
        </DialogContent>

        <DialogActions sx={{ p: 2 }}>
          <Button onClick={handleCloseDialog} style={{textTransform: "none"}}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleSubmitDialog} style={{textTransform: "none"}} disabled={message===""}>
            Submit
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}

export default LogTable;
