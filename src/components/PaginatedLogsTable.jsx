import React, { useState, useEffect } from 'react';
import { useMQTT } from '../providers/MQTTContext'; // Import the useMQTT hook
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import Button from "@mui/material/Button";
import Card from '@mui/material/Card';
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
import {ERROR_COLOR, WARNING_COLOR, NOTICE_COLOR} from "../utilities"
import GetAppIcon from '@mui/icons-material/GetApp';
import { Link, useLocation} from 'react-router-dom';

// Activate the UTC plugin
dayjs.extend(utc);



const StyledTableCell = styled(TableCell)(({ theme, level }) => {
  return {
    padding: "6px 6px 6px 10px",
    fontSize: 13,
    backgroundColor: level === "ERROR" ? ERROR_COLOR :
                      level === "WARNING" ? WARNING_COLOR :
                      level === "NOTICE" ? NOTICE_COLOR : "white",
    whiteSpace: "normal"
  };
});

const StyledTableCellFiller = styled(TableCell)(({ theme, level }) => {
  return {
    paddingTop: "25px",
    paddingBottom: "15px",
    textAlign: "center"
  };
});

const StyledTimeTableCell = styled(TableCell)(({ theme, level }) => {
  return {
    padding: "6px 6px 6px 10px",
    fontSize: 13,
    backgroundColor: level === "ERROR" ? ERROR_COLOR :
                      level === "WARNING" ? WARNING_COLOR :
                      level === "NOTICE" ? NOTICE_COLOR : "white",
    whiteSpace: "pre"
  };
});

const LEVELS = [
  "DEBUG",
  "INFO",
  "NOTICE",
  "WARNING",
  "ERROR",
  "CRITICAL"
]

function PaginatedLogTable({unit, experiment, relabelMap }) {
  const [listOfLogs, setListOfLogs] = useState([]);
  const [skip, setSkip] = useState(0); // Tracks the number of logs already loaded
  const [loading, setLoading] = useState(false); // Tracks if the logs are currently loading
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const location = useLocation();

  useEffect(() => {
    const getData = async () => {
      if (!experiment) return;
      setLoading(true);
      try {
        var response
        if (unit){
          response = await fetch(`/api/units/${unit}/experiments/${experiment}/logs`);
        }
        else {
          response = await fetch(`/api/experiments/${experiment}/logs`);
        }
        const logs = await response.json();
        setListOfLogs(
          logs.map((log, index) => ({
            ...log,
            key: `${log.timestamp}-${log.pioreactor_unit}-${log.level}-${log.message}`,
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

  }, [experiment, location, unit]);

  const loadMoreLogs = async () => {
    setLoading(true);
    try {
      var response
      if (unit){
        response = await fetch(`/api/units/${unit}/experiments/${experiment}/logs?skip=${skip}`);
      }
      else {
        response = await fetch(`/api/experiments/${experiment}/logs?skip=${skip}`);
      }
      const logs = await response.json();
      if (logs.length > 0) {
        setListOfLogs((prevLogs) => [
          ...prevLogs,
          ...logs.map((log, index) => ({
            ...log,
            key: `${log.timestamp}-${log.pioreactor_unit}-${log.level}-${log.message}`,
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
    if (client) {
      subscribeToTopic(
        LEVELS.map((level) => `pioreactor/${unit || '+'}/$experiment/logs/+/${level.toLowerCase()}`),
        onMessage,
        'PagLogTable'
      );
    }
    return () => {
      LEVELS.map((level) => unsubscribeFromTopic(`pioreactor/${unit || '+'}/$experiment/logs/+/${level.toLowerCase()}`, 'PagLogTable'))
    };
  }, [client, unit]);

  useEffect(() => {
    if (experiment && client) {
      subscribeToTopic(
        LEVELS.map((level) => `pioreactor/${unit || '+'}/${experiment}/logs/+/${level.toLowerCase()}`),
        onMessage,
        'PagLogTable'
      );
    }
    return () => {
      LEVELS.map((level) => unsubscribeFromTopic(`pioreactor/${unit || '+'}/${experiment}/logs/+/${level.toLowerCase()}`, 'PagLogTable'))
    };
  }, [client, experiment, unit]);

  const onMessage = (topic, message, packet) => {
    const unit = topic.toString().split('/')[1];
    const payload = JSON.parse(message.toString());
    setListOfLogs((currentLogs) =>
      [
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

  return (
    <>
    <Card>
      <CardContent>
        <TableContainer sx={{ maxHeight: "500px", minHeight: "200px", width: "100%", overflowY: "auto" }}>
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
              {listOfLogs.map((log) => (
                <TableRow key={log.key}>
                  <StyledTimeTableCell level={log.level}>
                    {timestampCell(log.timestamp)}
                  </StyledTimeTableCell>
                  <StyledTableCell level={log.level}>{relabelUnit(log.pioreactor_unit)}</StyledTableCell>
                  <StyledTableCell level={log.level}>{log.task.replace(/_/g, ' ')}</StyledTableCell>
                  <StyledTableCell level={log.level}>{log.message}</StyledTableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <Box display="flex" justifyContent="center" mt={2}>
          <Button onClick={loadMoreLogs} disabled={loading || (skip % 50 !== 0) || (skip === 0) } style={{textTransform: 'none'}}>
            {loading ? "Loading..." : "More"}
          </Button>
        </Box>
      </CardContent>
    </Card>

  </>
  );
}


export default PaginatedLogTable;