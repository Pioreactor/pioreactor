import React, { useState, useEffect } from 'react';
import { useMQTT } from '../providers/MQTTContext'; // Import the useMQTT hook
import moment from 'moment';
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
  "NOTSET",
  "DEBUG",
  "INFO",
  "NOTICE",
  "WARNING",
  "ERROR",
  "CRITICAL"
]

function LogTable({byDuration, experimentStartTime, experiment, config, relabelMap}) {
  const [listOfLogs, setListOfLogs] = useState([]);
  const {client, subscribeToTopic } = useMQTT();

  useEffect(() => {
    const getData = async () => {
      const response = await fetch(`/api/experiments/${experiment}/logs?` + new URLSearchParams({
        min_level: config.logging.ui_log_level
      }));
      const logs = await response.json();
      setListOfLogs(logs.map((log, index) => ({
        ...log,
        key: index
      })));
    };
    if (experiment && Object.keys(config).length){
      getData();
    }
  }, [experiment, config]);

  useEffect(() => {
    if (client && (Object.keys(config).length)){

      // what level does the user request?
      const levelRequested = config.logging.ui_log_level.toUpperCase()|| "INFO"
      const ix = LEVELS.indexOf(levelRequested)

      subscribeToTopic(LEVELS.slice(ix).map(level => `pioreactor/+/$experiment/logs/+/${level.toLowerCase()}`), onMessage, "LogTable");

    }
  }, [client, config]);

  useEffect(() => {
    if (experiment && client && (Object.keys(config).length)){

      // what level does the user request?
      const levelRequested = config.logging.ui_log_level.toUpperCase() || "INFO"
      const ix = LEVELS.indexOf(levelRequested)

      subscribeToTopic(LEVELS.slice(ix).map(level => `pioreactor/+/${experiment}/logs/+/${level.toLowerCase()}`), onMessage, "LogTable");


    }
  }, [client, experiment, config]);

  const relabelUnit = (unit) => {
    return (relabelMap && relabelMap[unit]) ? `${relabelMap[unit]} / ${unit}` : unit;
  };

  const toTimestampObject = (timestamp) => {
    return moment.utc(timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]')
  }

  const timestampCell = (timestamp) => {
    const ts = toTimestampObject(timestamp);
    const localTs = ts.local();

    if (byDuration) {
      const deltaHours = Math.round(ts.diff(experimentStartTime, 'hours', true) * 1e2) / 1e2;
      return <span title={localTs.format('YYYY-MM-DD HH:mm:ss.SS')}>{deltaHours} h</span>;
    } else {
      return <span title={localTs.format('YYYY-MM-DD HH:mm:ss.SS')}>{localTs.format('HH:mm:ss')}</span>;
    }
  };

  const onMessage = (topic, message, packet) => {
    const unit = topic.toString().split("/")[1];
    const payload = JSON.parse(message.toString());


    setListOfLogs(currentLogs => [
      {
        timestamp: moment.utc().format('YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]'),
        pioreactor_unit: unit,
        message: String(payload.message),
        task: payload.task,
        level: payload.level.toUpperCase(),
        key: Math.random()
      },
      ...currentLogs.slice(0, 49)
    ]);
  };

  return (
    <Card>
      <CardContent>
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
              {listOfLogs.map( (log, i) => (
                <>
                <TableRow key={log.key}>
                  <StyledTimeTableCell level={log.level}>
                    {timestampCell(log.timestamp)}
                  </StyledTimeTableCell>
                  <StyledTableCell level={log.level}>{relabelUnit(log.pioreactor_unit)}</StyledTableCell>
                  <StyledTableCell level={log.level}>{log.task.replace(/_/g, ' ')}</StyledTableCell>
                  <StyledTableCell level={log.level}>{log.message}</StyledTableCell>
                </TableRow>
                {
                  listOfLogs[i+1] && (toTimestampObject(log.timestamp).diff(toTimestampObject(listOfLogs[i+1].timestamp), 'hours', true) >= 1) && (
                    <TableRow key={-log.key}>
                      <StyledTableCellFiller colspan="4">{toTimestampObject(log.timestamp).diff(toTimestampObject(listOfLogs[i+1].timestamp), 'hours')} hours earlier...</StyledTableCellFiller>
                    </TableRow>
                  )
                }
                </>

              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}

export default LogTable;