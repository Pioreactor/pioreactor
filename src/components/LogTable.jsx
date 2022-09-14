import React from 'react'

import clsx from 'clsx';
import {Client} from 'paho-mqtt';
import moment from 'moment';


import {withStyles} from '@mui/styles';
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

const useStyles = theme => ({
  tightCell: {
    padding: "6px 6px 6px 10px",
    fontSize: 13,
  },
  smallText: {
    fontSize: 12,
  },
  headerCell: {
    backgroundColor: "white",
    padding: "8px 6px 6px 6px",
  },
  tightRight: {
    textAlign: "right"
  },
  errorLog: {
    backgroundColor: "#ff7961"
  },
  warningLog: {
    backgroundColor: "#FFEA8A"
  },
  noticeLog: {
    backgroundColor: "#addcaf"
  },
});

const levelMappingToOrdinal = {
  NOTSET: 0,
  DEBUG: 1,
  INFO: 2,
  NOTICE: 2.5,
  WARNING: 3,
  ERROR: 4,
  CRITICAL: 5
}


class LogTable extends React.Component {
  constructor(props) {
    super(props);
    this.state = {listOfLogs: []};
    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
  }

  async getData() {
    await fetch("/api/recent_logs?" + new URLSearchParams({
        min_level: this.props.config.logging.ui_log_level
      }))
      .then(response => {
        return response.json();
      })
      .then(data => {
        this.setState({listOfLogs: data});
      }).catch((e) => {
        console.log(e)
      });
  }

  componentDidMount() {
    this.getData()
    if (this.props.config.remote && this.props.config.remote.ws_url) {
      this.client = new Client(
        `ws://${this.props.config.remote.ws_url}/`,
        "webui_LogTable" + Math.random()
      )}
    else {
      this.client = new Client(
        `${this.props.config['cluster.topology']['leader_address']}`, 9001,
        "webui_LogTable" + Math.random()
      );
    }
    this.client.connect({timeout: 180, 'onSuccess': this.onConnect, reconnect: true});
    this.client.onMessageArrived = this.onMessageArrived;
  }

  componentDidUpdate(prevProps) {
     if (prevProps.experiment !== this.props.experiment) {
      this.getData()
     }
  }

  onConnect() {
    this.client.subscribe(["pioreactor", "+", this.props.experiment, "logs", "+"].join("/"))
    this.client.subscribe(["pioreactor", "+", "$experiment",         "logs", "+"].join("/"))
  }

  onMessageArrived(message) {
    if (this.state.listOfLogs.length > 50){
      this.state.listOfLogs.pop()
    }
    const unit = message.topic.split("/")[1]
    const payload = JSON.parse(message.payloadString)

    if (levelMappingToOrdinal[payload.level] < levelMappingToOrdinal[this.props.config.logging.ui_log_level]){
      return
    }

    this.state.listOfLogs.unshift(
      {timestamp: moment.utc().format('YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]'), pioreactor_unit: unit, message: String(payload.message), task: payload.task, is_error: (payload.level === "ERROR"), is_warning: (payload.level === "WARNING"), is_notice: (payload.level === "NOTICE")}
    )
    this.setState({
      listOfLogs: this.state.listOfLogs
    });
  }

  relabelUnit(unit) {
    return (this.props.relabelMap && this.props.relabelMap[unit]) ? `${this.props.relabelMap[unit]} / ${unit}` : unit
  }

  render(){
    const { classes } = this.props;
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" component="h2">
            <Box fontWeight="fontWeightRegular">
              Recent event logs
            </Box>
          </Typography>
          <TableContainer style={{ height: "700px", width: "100%", overflowY: "scroll"}}>
            <Table stickyHeader size="small" aria-label="log table">
               <TableHead>
                <TableRow>
                  <TableCell className={clsx(classes.headerCell)}>Time</TableCell>
                  <TableCell className={clsx(classes.headerCell)}>Pioreactor</TableCell>
                  <TableCell className={clsx(classes.headerCell)}>Source</TableCell>
                  <TableCell className={clsx(classes.headerCell)}>Message</TableCell>
                </TableRow>
              </TableHead>

              <TableBody>
                {this.state.listOfLogs.map((log, i) => (
                  <TableRow key={i}>
                    <TableCell className={clsx(classes.tightCell, classes.smallText, {[classes.noticeLog]: log.is_notice, [classes.errorLog]: log.is_error, [classes.warningLog]: log.is_warning})}>
                      <span title={moment.utc(log.timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]').local().format('YYYY-MM-DD HH:mm:ss.SS')}>{moment.utc(log.timestamp, 'YYYY-MM-DD[T]HH:mm:ss.SSSSS[Z]').local().format('HH:mm:ss')} </span>
                    </TableCell>
                    <TableCell className={clsx(classes.tightCell, classes.smallText, {[classes.noticeLog]: log.is_notice, [classes.errorLog]: log.is_error, [classes.warningLog]: log.is_warning})}> {this.relabelUnit(log.pioreactor_unit)}</TableCell>
                    <TableCell className={clsx(classes.tightCell, classes.smallText, {[classes.noticeLog]: log.is_notice, [classes.errorLog]: log.is_error, [classes.warningLog]: log.is_warning})}>{log.task.replace(/_/g, ' ')}</TableCell>
                    <TableCell className={clsx(classes.tightCell, classes.smallText, {[classes.noticeLog]: log.is_notice, [classes.errorLog]: log.is_error, [classes.warningLog]: log.is_warning})}>{log.message}</TableCell>
                  </TableRow>
                  ))
                }
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    );}
}



export default withStyles(useStyles)(LogTable);
