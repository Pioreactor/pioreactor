import React from 'react'

import {Client, Message} from 'paho-mqtt';
import moment from 'moment';

import {makeStyles} from '@material-ui/styles';
import Card from '@material-ui/core/Card';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';

const useStyles = makeStyles({
  tightCell: {
    padding: "8px 8px 6px 6px"
  },
  headerCell: {
    fontWeight: "bold"
  }
});

function LogTable(props) {
    const classes = useStyles();
    return (
      <Card>
        <TableContainer style={{ height: "500px", width: "100%", overflowY: "scroll"}}>
          <Table stickyHeader size="small" aria-label="log table">
             <TableHead>
              <TableRow>
                <TableCell align="center" colSpan={3} className={classes.headerCell}> Event logs </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className={classes.tightCell, classes.headerCell}>Timestamp</TableCell>
                <TableCell className={classes.tightCell, classes.headerCell}>Message</TableCell>
                <TableCell className={classes.tightCell, classes.headerCell}>Unit</TableCell>
              </TableRow>
            </TableHead>

            <TableBody>
              {props.logs.map((log, i) => (
                <TableRow key={i}>
                  <TableCell className={classes.tightCell}> {moment(log['timestamp'], 'MMM D HH:mm:ss.SSS').format('HH:mm:ss')} </TableCell>
                  <TableCell className={classes.tightCell}> {log.message} </TableCell>
                  <TableCell className={classes.tightCell}>{log.unit}</TableCell>
                </TableRow>
                ))
              }
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
)}



export default LogTable;
