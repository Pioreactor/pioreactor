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
import { Link } from 'react-router-dom';
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';
import RecordEventLogDialog from './RecordEventLogDialog';

import {ERROR_COLOR, WARNING_COLOR, NOTICE_COLOR} from "../utilities"

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
  "NOTSET",
  "DEBUG",
  "INFO",
  "NOTICE",
  "WARNING",
  "ERROR",
  "CRITICAL"
]

function LogTableByUnit({ experiment, unit, level="info" }) {
  const [listOfLogs, setListOfLogs] = useState([]);
  const { client, subscribeToTopic } = useMQTT();

  useEffect(() => {
    const getData = async () => {
      const response = await fetch(
        `/api/workers/${unit}/experiments/${experiment}/recent_logs?` +
          new URLSearchParams({ min_level: level })
      );
      const logs = await response.json();
      setListOfLogs(
        logs.map((log) => ({
          ...log,
          key: `${log.timestamp}-${log.pioreactor_unit}-${log.level}-${log.message}`,
        }))
      );
    };

    if (experiment) {
      getData();
    }
  }, [experiment, unit]);

  useEffect(() => {
    if (client) {
      const levelRequested = 'INFO';
      const ix = LEVELS.indexOf(levelRequested);
      subscribeToTopic(
        LEVELS.slice(ix).map(
          (level) => `pioreactor/${unit}/$experiment/logs/+/${level.toLowerCase()}`
        ),
        onMessage,
        'LogTableByUnit'
      );
    }
  }, [client, unit]);

  useEffect(() => {
    if (experiment && client) {
      const levelRequested = 'INFO';
      const ix = LEVELS.indexOf(levelRequested);
      subscribeToTopic(
        LEVELS.slice(ix).map(
          (level) => `pioreactor/${unit}/${experiment}/logs/+/${level.toLowerCase()}`
        ),
        onMessage,
        'LogTableByUnit'
      );
    }
  }, [client, experiment]);

  const toTimestampObject = (timestamp) => {
    return dayjs.utc(timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSS[Z]');
  };

  const timestampCell = (timestampStr) => {
    const ts = toTimestampObject(timestampStr);
    const localTs = ts.local();
    return <span title={localTs.format('YYYY-MM-DD HH:mm:ss')}>{localTs.format('HH:mm:ss')}</span>;
  };

  const onMessage = (topic, message, packet) => {
    if (!message || !topic) return;

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
      ].sort((a, b) => {
        return a.timestamp > b.timestamp;
      })
    );
  };


  const handleSubmitDialog = async (newLog) => {
    try {
      const response = await fetch(`/api/workers/${newLog.pioreactor_unit}/experiments/${newLog.experiment}/logs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newLog),
      });
      if (!response.ok) {
        throw new Error('Failed to submit new log entry.');
      }
    } catch (error) {
      console.error('Error adding new log entry:', error);
    }
  };

  return (
    <Card>
      <CardContent sx={{ '&:last-child': { pb: 0 } }}>
        <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">Recent logs for {unit}</Box>
        </Typography>
        <TableContainer sx={{ height: '700px', width: '100%', overflowY: 'auto' }}>
          <Table stickyHeader size="small" aria-label="log table">
            <TableHead>
              <TableRow>
                <StyledTableCell>Time</StyledTableCell>
                <StyledTableCell>Source</StyledTableCell>
                <StyledTableCell>Message</StyledTableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {listOfLogs.map((log, i) => (
                <React.Fragment key={log.key}>
                  <TableRow>
                    <StyledTimeTableCell level={log.level}>{timestampCell(log.timestamp)}</StyledTimeTableCell>
                    <StyledTableCell level={log.level}>{log.task.replace(/_/g, ' ')}</StyledTableCell>
                    <StyledTableCell level={log.level}>{log.message}</StyledTableCell>
                  </TableRow>
                  {listOfLogs[i + 1] &&
                    toTimestampObject(log.timestamp).diff(
                      toTimestampObject(listOfLogs[i + 1].timestamp),
                      'hours',
                      true
                    ) >= 2 && (
                      <TableRow key={`filler-${log.key}`}>
                        <StyledTableCellFiller colSpan="3">
                          {toTimestampObject(log.timestamp).diff(
                            toTimestampObject(listOfLogs[i + 1].timestamp),
                            'hours'
                          )}{' '}
                          hours earlier...
                        </StyledTableCellFiller>
                      </TableRow>
                    )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <Divider />
        <CardActions sx={{ justifyContent: 'right' }}>
          {(experiment !== "$experiment") &&
          <RecordEventLogDialog
            defaultPioreactor={unit}
            defaultExperiment={experiment || '<All experiments>'}
            availableUnits={[unit]}
            onSubmit={handleSubmitDialog}
          />}
          <Button
            to={(experiment == "$experiment") ? `/system-logs/${unit}` :  `/logs/${unit}`}
            component={Link}
            color="primary"
            style={{ textTransform: 'none', verticalAlign: 'middle', margin: '0px 3px' }}
          >
            <ListAltOutlinedIcon style={{ fontSize: 17, margin: '0px 3px' }} color="primary" /> View all logs
          </Button>
        </CardActions>
      </CardContent>
    </Card>
  );
}


export default LogTableByUnit;
