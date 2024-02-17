import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import {Client} from 'paho-mqtt';
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import React, { useState, useEffect } from 'react';

import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';

import PioreactorIcon from "./PioreactorIcon"


function MediaCard(props) {
  const [mediaThroughputPerUnit, setMediaThroughputPerUnit] = useState({});
  const [altMediaThroughputPerUnit, setAltMediaThroughputPerUnit] = useState({});
  const [mediaThroughput, setMediaThroughput] = useState(0);
  const [altMediaThroughput, setAltMediaThroughput] = useState(0);
  const [rates, setRates] = useState({ all: { mediaRate: 0, altMediaRate: 0 } });
  const [activeUnits, setActiveUnits] = useState([]);

  useEffect(() => {
    getRecentRates();

    const userName = props.config.mqtt.username || "pioreactor"
    const password = props.config.mqtt.password || "raspberry"
    const client = new Client(
        props.config.mqtt.broker_address,
        parseInt(props.config.mqtt.broker_ws_port || 9001),
        'webui_MediaCard' + Math.floor(Math.random() * 10000)
      );

    client.connect({
      userName: userName,
      password: password,
      keepAliveInterval: 60 * 15,
      timeout: 180,
      onSuccess: onConnect,
      reconnect: true
    });
    client.onMessageArrived = onMessageArrived;

    setActiveUnits(
      Object.entries(props.config['cluster.inventory'])
        .filter((v) => v[1] === '1')
        .map((v) => v[0])
    );

  }, [props.config, props.experiment]);

  async function getRecentRates() {
    const response = await fetch(`/api/media_rates/current`);
    const data = await response.json();
    setRates(data);
  }

  function onConnect() {
    this.client.subscribe(
      ['pioreactor', '+', props.experiment, 'dosing_automation', 'alt_media_throughput'].join('/')
    );
    this.client.subscribe(
      ['pioreactor', '+', props.experiment, 'dosing_automation', 'media_throughput'].join('/')
    );
  }

  function addOrUpdate(hash, object, value) {
    if (Object.hasOwnProperty(hash)) {
      object[hash] = value + object[hash];
    } else {
      object[hash] = value;
    }
    return object;
  }

  function onMessageArrived(message) {
    const topic = message.destinationName;
    const topicParts = topic.split('/');
    const payload = parseFloat(message.payloadString);
    const unit = topicParts[1];
    const objectRef =
      topicParts.slice(-1)[0] === 'alt_media_throughput' ? 'altMediaThroughputPerUnit' : 'mediaThroughputPerUnit';
    const totalRef =
      topicParts.slice(-1)[0] === 'alt_media_throughput' ? 'altMediaThroughput' : 'mediaThroughput';

    const updatedObject = addOrUpdate(unit, objectRef === 'altMediaThroughputPerUnit' ? altMediaThroughputPerUnit : mediaThroughputPerUnit, payload);

    if (objectRef === 'altMediaThroughputPerUnit') {
      setAltMediaThroughputPerUnit(updatedObject);
    } else {
      setMediaThroughputPerUnit(updatedObject);
    }

    var total = Object.values(updatedObject).reduce((a, b) => a + b, 0);

    if (totalRef === 'altMediaThroughput') {
      setAltMediaThroughput(total);
    } else {
      setMediaThroughput(total);
    }
  }

  function relabelUnit(unit) {
    return props.relabelMap && props.relabelMap[unit] ? `${props.relabelMap[unit]} / ${unit}` : unit;
  }

  return (
    <Card style={{ marginBottom: '6px' }}>
      <CardContent>
        <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">Dosing</Box>
        </Typography>
        <TableContainer style={{ width: '100%' }}>
          <Table size="small" aria-label="media throughput">
            <TableHead>
              <TableRow>
                <TableCell style={{ padding: '6px 0px' }}></TableCell>
                <TableCell style={{ padding: '6px 0px' }} align="right">
                  Media
                </TableCell>
                <TableCell style={{ padding: '6px 0px' }} align="right">
                  Alt. Media
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow key="all">
                <TableCell style={{ padding: '6px 0px' }} component="th" scope="row">
                  All Pioreactors
                </TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                  {mediaThroughput.toFixed(1)}mL (~{rates.all.mediaRate.toFixed(1)}mL/h)
                </TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                  {altMediaThroughput.toFixed(1)}mL (~{rates.all.altMediaRate.toFixed(1)}mL/h)
                </TableCell>
              </TableRow>

              {activeUnits.map((unit) => (
                <TableRow key={unit}>
                  <TableCell style={{ padding: '6px 0px' }} component="th" scope="row">
                    <PioreactorIcon style={{ fontSize: 14, verticalAlign: 'middle' }} color="inherit" />
                    {relabelUnit(unit)}
                  </TableCell>
                  <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                    {(mediaThroughputPerUnit[unit] || 0).toFixed(1)}mL (~{(rates[unit] ? rates[unit].mediaRate.toFixed(1) : '0.0')}mL/h)
                  </TableCell>
                  <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                    {(altMediaThroughputPerUnit[unit] || 0).toFixed(1)}mL (~{(rates[unit] ? rates[unit].altMediaRate.toFixed(1) : '0.0')}mL/h)
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}

export default MediaCard;
