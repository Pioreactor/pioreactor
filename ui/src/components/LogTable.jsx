import React from 'react'

import {Client} from 'paho-mqtt';
import moment from 'moment';

import {withStyles} from '@material-ui/styles';
import Card from '@material-ui/core/Card';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';

const useStyles = theme => ({
  tightCell: {
    padding: "8px 8px 6px 6px",
    fontSize: 13,
  },
  headerCell: {
    fontWeight: "bold"
  },
  tightRight: {
    textAlign: "right"
  }
});

class LogTable extends React.Component {
  constructor(props) {
    super(props);
    this.state = {listOfLogs: []};
    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
    this.experiment = "Trial-22-a3cfb599c7ea4693a8e6c4b5f4f6e240"
  }

  async getData() {
    await fetch("./data/all_morbidostat.log.json")
      .then(response => {
        return response.json();
      })
      .then(data => {
        this.setState({listOfLogs: data});
      });
  }

  componentDidMount() {
      // Get shop data and update URL when selection changes
    this.getData()
    this.client = new Client("ws://morbidostatws.ngrok.io/", "client-log-table");
    this.client.connect({'onSuccess': this.onConnect});
    this.client.onMessageArrived = this.onMessageArrived;
  }

  onConnect() {
      this.client.subscribe(["morbidostat", "+", this.experiment, "log"].join("/"))
  }

  onMessageArrived(message) {
    this.state.listOfLogs.pop()
    const unit = message.topic.split("/")[1]
    // TODO: make the log table spit out unix timestamps
    this.state.listOfLogs.unshift({timestamp: moment().format("MMM D HH:mm:ss.SSS"), unit: unit, message: message.payloadString})
    this.setState({
      listOfLogs: this.state.listOfLogs
    });
  }

  render(){
    const { classes } = this.props;
    return (
      <Card>
        <TableContainer style={{ height: "500px", width: "100%", overflowY: "scroll"}}>
          <Table stickyHeader size="small" aria-label="log table">
             <TableHead>
              <TableRow>
                <TableCell align="center" colSpan={3} className={[classes.headerCell, classes.tightCell].join(" ")}> Event logs </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className={[classes.headerCell, classes.tightCell].join(" ")}>Timestamp</TableCell>
                <TableCell className={[classes.headerCell, classes.tightCell].join(" ")}>Message</TableCell>
                <TableCell className={[classes.headerCell, classes.tightCell].join(" ")}>Unit</TableCell>
              </TableRow>
            </TableHead>

            <TableBody>
              {this.state.listOfLogs.map((log, i) => (
                <TableRow key={i}>
                  <TableCell className={classes.tightCell}> {moment(log.timestamp, 'MMM D HH:mm:ss.SSS').format('HH:mm:ss')} </TableCell>
                  <TableCell className={classes.tightCell}> {log.message} </TableCell>
                  <TableCell className={[classes.tightCell, classes.tightRight].join(" ")}>{log.unit}</TableCell>
                </TableRow>
                ))
              }
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
  )}
}



export default withStyles(useStyles)(LogTable);
