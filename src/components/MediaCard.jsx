import React from 'react'
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import {Client} from 'paho-mqtt';
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import {withStyles} from '@mui/styles';

import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';

import PioreactorIcon from "./PioreactorIcon"



const useStyles = theme => ({
  tightCell: {
    padding: "8px 2px 6px 4px",
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
});



class MediaCard extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
        mediaThroughputPerUnit: {},
        altMediaThroughputPerUnit: {},
        mediaThroughput: 0,
        altMediaThroughput: 0,
        rates: {all: {mediaRate: 0, altMediaRate: 0}},
        activeUnits: []
      };
    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
  }

  async getRecentRates() {

     await fetch("/api/recent_media_rates")
    .then((response) => {
      return response.json();
    })
    .then((data) => {
      this.setState(prevState => ({...prevState, rates: data}))
    });
    return
  }

  componentDidUpdate(prevProps) {
     if (prevProps.experiment !== this.props.experiment) {
      this.getRecentRates()
     }
  }

  componentDidMount() {
    if (this.props.config.remote && this.props.config.remote.ws_url) {
      this.client = new Client(
        `ws://${this.props.config.remote.ws_url}/`,
        "webui_MediaCard" + Math.random()
      )}
    else {
      this.client = new Client(
        `${this.props.config['cluster.topology']['leader_address']}`, 9001,
        "webui_MediaCard" + Math.random()
      );
    }

    this.client.connect({timeout: 180, 'onSuccess': this.onConnect});
    this.client.onMessageArrived = this.onMessageArrived;
    this.setState({activeUnits: Object.entries(this.props.config['cluster.inventory']).filter((v) => v[1] === "1").map((v) => v[0])})
    this.getRecentRates()
  }


  onConnect() {
      this.client.subscribe(["pioreactor", "+", this.props.experiment, "dosing_automation", "alt_media_throughput"].join("/"))
      this.client.subscribe(["pioreactor", "+", this.props.experiment, "dosing_automation", "media_throughput"].join("/"))
  }

  addOrUpdate(hash, object, value) {
      if (Object.hasOwnProperty(hash)){
        object[hash] = value + object[hash]
      }
      else{
        object[hash] = value
      }
      return object
  }

  onMessageArrived(message) {
    const topic = message.destinationName
    const topicParts = topic.split("/")
    const payload = parseFloat(message.payloadString)
    const unit = topicParts[1]
    const objectRef = (topicParts.slice(-1)[0] === "alt_media_throughput")  ? "altMediaThroughputPerUnit"  : "mediaThroughputPerUnit"
    const totalRef = (topicParts.slice(-1)[0] === "alt_media_throughput")  ? "altMediaThroughput"  : "mediaThroughput"

    this.setState({
      [objectRef]: this.addOrUpdate(unit, this.state[objectRef], payload)
    });

    var total = Object.values(this.state[objectRef]).reduce((a, b) => a + b, 0)

    this.setState({
      [totalRef]: total
    })
  }

  relabelUnit(unit) {
    return (this.props.relabelMap && this.props.relabelMap[unit]) ? `${this.props.relabelMap[unit]} / ${unit}` : unit
  }

  render(){
    return (
    <Card>
      <CardContent>
        <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">
            Dosing
          </Box>
        </Typography>
       <TableContainer style={{ width: "100%"}}>
          <Table size="small" aria-label="media throughput">
            <TableHead>
              <TableRow>
                <TableCell style={{padding: "6px 0px"}}></TableCell>
                <TableCell style={{padding: "6px 0px"}} align="right">Media</TableCell>
                <TableCell style={{padding: "6px 0px"}} align="right">Alt. Media</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow key="all">
                <TableCell style={{padding: "6px 0px"}} component="th" scope="row">
                  All Pioreactors
                </TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: "6px 0px"}}>{this.state.mediaThroughput.toFixed(1)}mL (~{this.state.rates.all.mediaRate.toFixed(1)}mL/h)</TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: "6px 0px"}}>{this.state.altMediaThroughput.toFixed(1)}mL (~{this.state.rates.all.altMediaRate.toFixed(1)}mL/h)</TableCell>
              </TableRow>

              {this.state.activeUnits.map((unit) => (
                <TableRow key={unit}>
                  <TableCell style={{padding: "6px 0px"}} component="th" scope="row">
                      <PioreactorIcon style={{ fontSize: 14, verticalAlign: "middle" }} color="inherit"/>{this.relabelUnit(unit)}
                  </TableCell>
                  <TableCell align="right" style={{ fontSize: 13, padding: "6px 0px"}}>{(this.state.mediaThroughputPerUnit[unit] || 0).toFixed(1)}mL (~{this.state.rates[unit] ? this.state.rates[unit].mediaRate.toFixed(1) : "0.0"}mL/h)</TableCell>
                  <TableCell align="right" style={{ fontSize: 13, padding: "6px 0px"}}>{(this.state.altMediaThroughputPerUnit[unit] || 0).toFixed(1)}mL (~{this.state.rates[unit] ? this.state.rates[unit].altMediaRate.toFixed(1): "0.0"}mL/h)</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  )}
}

export default  withStyles(useStyles)(MediaCard);
