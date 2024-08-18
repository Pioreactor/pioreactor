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

function LogTableByUnit({experiment, unit}) {
  const [listOfLogs, setListOfLogs] = useState([]);
  const {client, subscribeToTopic } = useMQTT();

  useEffect(() => {
    const getData = async () => {
      const response = await fetch(`/api/workers/${unit}/experiments/${experiment}/logs?` + new URLSearchParams({
        min_level: 'info'
      }));
      const logs = await response.json();
      setListOfLogs(logs.map((log, index) => ({
        ...log,
        key: index
      })));
    };

    if (experiment){
      getData();
    }
  }, [experiment, unit]);

  useEffect(() => {
    if (client){

      const levelRequested = "INFO"
      const ix = LEVELS.indexOf(levelRequested)

      subscribeToTopic(LEVELS.slice(ix).map(level => `pioreactor/${unit}/$experiment/logs/+/${level.toLowerCase()}`), onMessage, "LogTableByUnit");

    }
  }, [client, unit]);

  useEffect(() => {
    if (experiment && client){

      const levelRequested = "INFO"
      const ix = LEVELS.indexOf(levelRequested)

      subscribeToTopic(LEVELS.slice(ix).map(level => `pioreactor/${unit}/${experiment}/logs/+/${level.toLowerCase()}`), onMessage, "LogTableByUnit");


    }
  }, [client, experiment]);

  const toTimestampObject = (timestamp) => {
    return moment.utc(timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]')
  }

  const timestampCell = (timestampStr) => {
    const ts = toTimestampObject(timestampStr);
    const localTs = ts.local();
    return <span title={localTs.format('YYYY-MM-DD HH:mm:ss.SS')}>{localTs.format('HH:mm:ss')}</span>;
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
          <Box fontWeight="fontWeightRegular">Recent logs for {unit}</Box>
        </Typography>
        <TableContainer sx={{ height: "700px", width: "100%", overflowY: "auto"}}>
          <Table stickyHeader size="small" aria-label="log table">
            <TableHead>
              <TableRow>
                <StyledTableCell>Time</StyledTableCell>
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
                  <StyledTableCell level={log.level}>{log.task.replace(/_/g, ' ')}</StyledTableCell>
                  <StyledTableCell level={log.level}>{log.message}</StyledTableCell>
                </TableRow>
                {
                  listOfLogs[i+1] && (toTimestampObject(log.timestamp).diff(toTimestampObject(listOfLogs[i+1].timestamp), 'hours', true) >= 1) && (
                    <TableRow key={-log.key}>
                      <StyledTableCellFiller colspan="3">{toTimestampObject(log.timestamp).diff(toTimestampObject(listOfLogs[i+1].timestamp), 'hours')} hours earlier...</StyledTableCellFiller>
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

export default LogTableByUnit;