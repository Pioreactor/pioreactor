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

class LogTable extends React.Component {
  constructor(props) {
    super(props);
    this.state = {listOfLogs: this.props.listOfLogs};
    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
    console.log(this.state.isUnitActive)
  }

  componentDidMount() {
    // need to have unique clientIds
    this.client = new Client("leader.local", 9001, "webui-logtable");
    this.client.connect({'onSuccess': this.onConnect});
    this.client.onMessageArrived = this.onMessageArrived;
  }

  onConnect() {
      this.client.subscribe("morbidostat/+/" + "Trial-14-d29bfbaee0dd4fb28348c8cb3532cdd0" + "/log")
  }

  onMessageArrived(message) {
      this.state.listOfLogs.pop()
      const unit = message.topic.split("/")[1]
      this.state.listOfLogs.unshift({timestamp: "Oct 22 10:06:45.217", unit: unit, message: message.payloadString})
      this.setState({
        listOfLogs: this.state.listOfLogs
      });
  }

  render(){
    return (
      <Card>
        <TableContainer style={{ height: "500px", width: "100%", overflowY: "scroll"}}>
          <Table stickyHeader size="small" aria-label="log table">
             <TableHead>
              <TableRow>
                <TableCell align="center" colSpan={3} className=""> Event logs </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="">Timestamp</TableCell>
                <TableCell className="">Message</TableCell>
                <TableCell className="">Unit</TableCell>
              </TableRow>
            </TableHead>

            <TableBody>
              {this.state.listOfLogs.map((log, i) => (
                <TableRow key={i}>
                  <TableCell className=""> {moment(log.timestamp, 'MMM D HH:mm:ss.SSS').format('HH:mm:ss')} </TableCell>
                  <TableCell className=""> {log.message} </TableCell>
                  <TableCell className="">{log.unit}</TableCell>
                </TableRow>
                ))
              }
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
  )}
}



export default LogTable;
