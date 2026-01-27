import React, { useState, useEffect } from 'react';
import { useMQTT } from '../providers/MQTTContext'; // Import the useMQTT hook
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import Button from "@mui/material/Button";
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Box from '@mui/material/Box';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import { styled } from '@mui/material/styles';
import { ERROR_COLOR, WARNING_COLOR, NOTICE_COLOR } from "../color";
import Chip from '@mui/material/Chip';
import PioreactorIcon from "./PioreactorIcon"
import { Link } from 'react-router';
import emptyStateIllustration from '../assets/undraw_clouds_bmtk.svg';

// Activate the UTC plugin
dayjs.extend(utc);



const StyledTableCell = styled(TableCell)(({ level }) => {
  return {
    padding: "6px 6px 6px 10px",
    fontSize: 13,
    backgroundColor: level === "ERROR" ? ERROR_COLOR :
                      level === "WARNING" ? WARNING_COLOR :
                      level === "NOTICE" ? NOTICE_COLOR : null,
    whiteSpace: "normal"
  };
});


const StyledTimeTableCell = styled(TableCell)(({ level }) => {
  return {
    padding: "6px 6px 6px 10px",
    fontSize: 13,
    backgroundColor: level === "ERROR" ? ERROR_COLOR :
                      level === "WARNING" ? WARNING_COLOR :
                      level === "NOTICE" ? NOTICE_COLOR : null,
    whiteSpace: "pre"
  };
});


const TableRowStyled = styled(TableRow)(() => ({
  '&:nth-of-type(odd)': {
    backgroundColor: "#F7F7F7",
  },
  '&:nth-of-type(even)': {
    backgroundColor: "white",
  },
}));

const LEVELS = [
  "DEBUG",
  "INFO",
  "NOTICE",
  "WARNING",
  "ERROR",
  "CRITICAL"
]

function PaginatedLogTable({pioreactorUnit, experiment, relabelMap, logLevel }) {
  const [listOfLogs, setListOfLogs] = useState([]);
  const [skip, setSkip] = useState(0); // Tracks the number of logs already loaded
  const [loading, setLoading] = useState(false); // Tracks if the logs are currently loading
  const [onlyAssignedLogs, setOnlyAssignedLogs] = useState(true);
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();

  const getAPIURL = (unit, onlyAssignedLogs, experiment) => {
    if (unit && experiment === "$experiment"){
      return `/api/units/${unit}/system_logs`;
    } else if (unit && onlyAssignedLogs){
      return `/api/workers/${unit}/experiments/${experiment}/logs`;
    } else if (!unit && onlyAssignedLogs) {
      return `/api/experiments/${experiment}/logs`
    } else if (unit && !onlyAssignedLogs) {
      return `/api/units/${unit}/logs`;
    } else {
      return `/api/logs`
    }
  }

  useEffect(() => {
    const getData = async () => {
      if (!experiment) return;
      setLoading(true);
      try {
        const response = await fetch(getAPIURL(pioreactorUnit, onlyAssignedLogs, experiment) + "?min_level=" + logLevel);
        const logs = await response.json();
        setListOfLogs(
          logs.map((log, index) => ({
            ...log,
            key: `${log.timestamp}-${log.pioreactor_unit}-${log.level}-${log.message}-${index}`,
          }))
        );
        setSkip(logs.length); // Set the initial skip value
      } catch (error) {
        console.error("Failed to fetch logs:", error);
      } finally {
        setLoading(false);
      }
    };

    setSkip(0)
    getData();

  }, [experiment, pioreactorUnit, onlyAssignedLogs, logLevel]);

  const loadMoreLogs = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${getAPIURL(pioreactorUnit, onlyAssignedLogs, experiment)}?skip=${skip}&min_level=${logLevel}`);
      const logs = await response.json();
      if (logs.length > 0) {
        setListOfLogs((prevLogs) => [
          ...prevLogs,
          ...logs.map((log, index) => ({
            ...log,
            key: `${log.timestamp}-${log.pioreactor_unit}-${log.level}-${log.message}-${index}`,
          })),
        ]);
        setSkip((prevSkip) => prevSkip + logs.length);
      }
    } catch (error) {
      console.error("Failed to load more logs:", error);
    } finally {
      setLoading(false);
    }
  };



  useEffect(() => {
    if (experiment && client) {
      subscribeToTopic(
        LEVELS.map((level) => `pioreactor/${pioreactorUnit || '+'}/${experiment}/logs/+/${level.toLowerCase()}`),
        onMessage,
        'PagLogTable'
      );
    }
    return () => {
      LEVELS.map((level) => unsubscribeFromTopic(`pioreactor/${pioreactorUnit || '+'}/${experiment}/logs/+/${level.toLowerCase()}`, 'PagLogTable'))
    };
  }, [client, experiment, pioreactorUnit, logLevel]);


  const handleSwitchChange = (event) => {
    setOnlyAssignedLogs(!event.target.checked)
  }

  const onMessage = (topic, message, _packet) => {
    if (!message || !topic) return;

    const unit = topic.toString().split('/')[1];
    const payload = JSON.parse(message.toString());
    const levelOfMessage = payload.level.toUpperCase();

    if (LEVELS.indexOf(levelOfMessage) < LEVELS.indexOf(logLevel)){
      return
    }

    setListOfLogs((currentLogs) =>
      [
        {
          timestamp: toTimestampObject(payload.timestamp),
          pioreactor_unit: unit,
          message: String(payload.message),
          task: payload.task,
          level: payload.level.toUpperCase(),
          key: `${payload.timestamp}-${unit}-${payload.level.toUpperCase()}-${String(payload.message)}-00`,
        },
        ...currentLogs,
      ]);
  };

  const relabelUnit = (unit) => {
    return relabelMap && relabelMap[unit] ? `${relabelMap[unit]} / ${unit}` : unit;
  };

  const toTimestampObject = (timestamp) => {
    return dayjs.utc(timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSS[Z]');
  };

  const timestampCell = (timestamp) => {
    const ts = toTimestampObject(timestamp);
    const localTs = ts.local();
    return localTs.format('YYYY-MM-DD HH:mm:ss');
  };

  const hasLogs = listOfLogs.length > 0;
  const showEmptyState = !hasLogs && !loading;

  return (
    <>
      <Card sx={{ width: "100%" }}>
        <CardContent sx={{ width: "100%" }}>
          {hasLogs ? (
            <TableContainer sx={{ maxHeight: "500px", minHeight: "200px", width: "100%", overflowY: "auto", overflowX: 'auto', }}>
              <Table sx={{tableLayout: { xs: 'auto', lg: 'fixed' }, minWidth: 600}} stickyHeader size="small" aria-label="log table">
                <colgroup>
                  <col style={{width:'15%'}}/>
                  <col style={{width:'10%'}}/>
                  <col style={{width:'10%'}}/>
                  <col style={{width:'55%'}}/>
                </colgroup>
                <TableHead>
                  <TableRow >
                    <TableCell sx={{"backgroundColor": "white"}}>Time</TableCell>
                    <TableCell sx={{"backgroundColor": "white"}}>Pioreactor</TableCell>
                    <TableCell sx={{"backgroundColor": "white"}}>Source</TableCell>
                    <TableCell sx={{"backgroundColor": "white"}}>Message</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {listOfLogs.map((log) => (
                    <TableRowStyled key={log.key}>
                      <StyledTimeTableCell level={log.level}>
                        {timestampCell(log.timestamp)}
                      </StyledTimeTableCell>
                      <StyledTableCell level={log.level}><Chip size="small" icon={<PioreactorIcon/>} label={relabelUnit(log.pioreactor_unit)} clickable component={Link} to={"/pioreactors/" + log.pioreactor_unit} data-pioreactor-unit={log.pioreactor_unit} /></StyledTableCell>
                      <StyledTableCell level={log.level}>{log.task.replace(/_/g, ' ')}</StyledTableCell>
                      <StyledTableCell level={log.level}>{log.message}</StyledTableCell>
                    </TableRowStyled>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : showEmptyState ? (
            <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" sx={{ minHeight: "350px", gap: 2, textAlign: "center" }}>
              <Box component="img" src={emptyStateIllustration} alt="No logs illustration" sx={{ maxWidth: "320px", width: "100%", opacity: 0.9 }} />
              <Box sx={{ color: "#5f6a7d", fontSize: "14px" }}>
                No logs yet. They will appear here once your Pioreactor starts reporting activity.
              </Box>
            </Box>
          ) : (
            <Box sx={{ minHeight: "350px" }} />
          )}
          <Box display="flex" justifyContent="space-between" mt={2}>
            <Box sx={{width: 300}}/>
            <Button onClick={loadMoreLogs} disabled={loading || (skip % 50 !== 0) || (skip === 0) } style={{textTransform: 'none'}}>
              {loading ? "Loading..." : "More"}
            </Button>
            <FormControlLabel
              checked={!onlyAssignedLogs}
              control={<Switch color="primary"  onChange={handleSwitchChange}  size="small" />}
              label="Include logs from other experiments"
              labelPlacement="start"
            />
          </Box>
        </CardContent>
      </Card>
    </>
  );
}


export default PaginatedLogTable;
