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

const StyledTableCell = styled(TableCell)(({ theme, level }) => ({
  padding: "6px 6px 6px 10px",
  fontSize: 13,
  backgroundColor: level === "ERROR" ? "#ff7961" :
                    level === "WARNING" ? "#FFEA8A" :
                    level === "NOTICE" ? "#addcaf" : "white",
  whiteSpace: "nowrap"
}));

const levelMappingToOrdinal = {
  NOTSET: 0,
  DEBUG: 1,
  INFO: 2,
  NOTICE: 2.5,
  WARNING: 3,
  ERROR: 4,
  CRITICAL: 5
}

function LogTable(props) {
  const [listOfLogs, setListOfLogs] = useState([]);
  const {client, subscribeToTopic } = useMQTT(); // Use the useMQTT hook

  useEffect(() => {
    const getData = async () => {
      const response = await fetch(`/api/experiments/${props.experiment}/logs?` + new URLSearchParams({
        min_level: props.config.logging.ui_log_level
      }));
      const logs = await response.json();
      setListOfLogs(logs.map((log, index) => ({
        ...log,
        key: index
      })));
    };

    getData();
  }, [props.experiment, props.config]);

  useEffect(() => {
    if (client){
      subscribeToTopic(`pioreactor/+/$experiment/logs/+`, onMessage, "LogTable");
    }
  }, [client]);

  useEffect(() => {
    if (props.experiment && client) {
      subscribeToTopic(`pioreactor/+/${props.experiment}/logs/+`, onMessage, "LogTable");
    }
  }, [props.experiment, client]);

  const onMessage = (topic, message, packet) => {
    const unit = topic.toString().split("/")[1];
    const payload = JSON.parse(message.toString());

    if (levelMappingToOrdinal[payload.level.toUpperCase()] < levelMappingToOrdinal[props.config.logging.ui_log_level.toUpperCase()]) {
      return;
    }

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
          Recent event logs
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
              {listOfLogs.map(log => (
                <TableRow key={log.key}>
                  <StyledTableCell level={log.level}>
                    {moment.utc(log.timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]').local().format('HH:mm:ss')}
                  </StyledTableCell>
                  <StyledTableCell level={log.level}>{log.pioreactor_unit}</StyledTableCell>
                  <StyledTableCell level={log.level}>{log.task.replace(/_/g, ' ')}</StyledTableCell>
                  <StyledTableCell level={log.level}>{log.message}</StyledTableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}

export default LogTable;