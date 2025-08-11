import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import React, { useState, useEffect } from 'react';

import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Chip from '@mui/material/Chip';
import PioreactorIcon from "./PioreactorIcon"
import PioreactorsIcon from "./PioreactorsIcon"
import { useMQTT } from '../providers/MQTTContext';
import { Link } from 'react-router-dom';


function MediaCard({experiment, relabelMap, activeUnits}) {
  const [mediaThroughputPerUnit, setMediaThroughputPerUnit] = useState({});
  const [altMediaThroughputPerUnit, setAltMediaThroughputPerUnit] = useState({});
  const [mediaThroughput, setMediaThroughput] = useState(0);
  const [altMediaThroughput, setAltMediaThroughput] = useState(0);
  const [rates, setRates] = useState({ all: { mediaRate: 0, altMediaRate: 0 } });
  const {client, subscribeToTopic } = useMQTT();

  useEffect(() => {
    if (experiment && client) {
      subscribeToTopic(
          [`pioreactor/+/${experiment}/dosing_automation/alt_media_throughput`, `pioreactor/+/${experiment}/dosing_automation/media_throughput`],
          onMessage, "MediaCard")
    }

  }, [experiment, client]);

  useEffect(() => {
    async function getRecentRates() {
      const response = await fetch(`/api/experiments/${experiment}/media_rates`);
      const data = await response.json();
      setRates(data);
    }

    if (experiment) {
      getRecentRates();
    }
  }, [experiment]);




  function addOrUpdate(hash, object, value) {
    if (Object.hasOwnProperty(hash)) {
      object[hash] = value + object[hash];
    } else {
      object[hash] = value;
    }
    return object;
  }

  function onMessage(topic, message, packet) {
    if (!message || !topic) return;

    const topicParts = topic.toString().split('/');
    const payload = parseFloat(message.toString());
    const unit = topicParts[1];
    const objectRef =
      topicParts.slice(-1)[0] === 'alt_media_throughput' ? 'altMediaThroughputPerUnit' : 'mediaThroughputPerUnit';
    const totalRef =
      topicParts.slice(-1)[0] === 'alt_media_throughput' ? 'altMediaThroughput' : 'mediaThroughput';

    const updatedObject = addOrUpdate(unit, objectRef === 'altMediaThroughputPerUnit' ? altMediaThroughputPerUnit : mediaThroughputPerUnit, payload);

    if (objectRef === 'altMediaThroughputPerUnit') {
      setAltMediaThroughputPerUnit(updatedObject || 0);
    } else {
      setMediaThroughputPerUnit(updatedObject || 0);
    }

    var total = Object.values(updatedObject).reduce((a, b) => a + b, 0);

    if (totalRef === 'altMediaThroughput') {
      setAltMediaThroughput(total || 0);
    } else {
      setMediaThroughput(total || 0);
    }
  }

  function relabelUnit(unit) {
    return relabelMap && relabelMap[unit] ? `${relabelMap[unit]} / ${unit}` : unit;
  }

  return (
    <Card>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">Dosing</Box>
        </Typography>

        {activeUnits.length === 0 && (
            <Typography variant="body2" component="p">No Pioreactors are currently assigned.</Typography>
        )}

        {activeUnits.length > 0 && (
        <TableContainer sx={{ maxHeight: '300px', width: '100%', overflowY: 'auto' }}>
          <Table size="small" aria-label="media throughput">
            <TableHead>
              <TableRow>
                <TableCell style={{ padding: '6px 0px' }}>Pioreactor</TableCell>
                <TableCell style={{ padding: '6px 0px' }} align="right">
                  Media used
                </TableCell>
                <TableCell style={{ padding: '6px 0px' }} align="right">
                  Alt. Media used
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>

              {activeUnits.map((unit) => (
                <TableRow key={unit}>
                  <TableCell style={{ padding: '6px 0px' }} component="th" scope="row">
                    <Chip size="small" icon={<PioreactorIcon/>} label={relabelUnit(unit)} clickable component={Link} to={"/pioreactors/" + unit} data-pioreactor-unit={unit} />
                  </TableCell>
                  <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                    {(mediaThroughputPerUnit[unit] || 0).toFixed(1)}mL ({(rates[unit] ? rates[unit].mediaRate.toFixed(1) : '0.0')}mL/h)
                  </TableCell>
                  <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                    {(altMediaThroughputPerUnit[unit] || 0).toFixed(1)}mL ({(rates[unit] ? rates[unit].altMediaRate.toFixed(1) : '0.0')}mL/h)
                  </TableCell>
                </TableRow>
              ))}

              {activeUnits.length > 1 &&
              <TableRow key="all">
                <TableCell style={{ padding: '6px 0px' }} component="th" scope="row">
                  <Chip size="small" icon={<PioreactorsIcon/>} label="All assigned Pioreactors" sx={{backgroundColor: "white"}} />
                </TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                  {(mediaThroughput || 0).toFixed(1)}mL ({rates.all.mediaRate.toFixed(1)}mL/h)
                </TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                  {(altMediaThroughput || 0).toFixed(1)}mL ({rates.all.altMediaRate.toFixed(1)}mL/h)
                </TableCell>
              </TableRow>
            }

            </TableBody>
          </Table>
        </TableContainer>
        )}
      </CardContent>
    </Card>
  );
}

export default MediaCard;
