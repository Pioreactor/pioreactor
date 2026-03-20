import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import React, { useState, useEffect, useCallback, useMemo } from 'react';

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
import { Link } from 'react-router';


function MediaCard({experiment, relabelMap, activeUnits}) {
  const [mediaThroughputPerUnit, setMediaThroughputPerUnit] = useState({});
  const [altMediaThroughputPerUnit, setAltMediaThroughputPerUnit] = useState({});
  const [rates, setRates] = useState({ all: { mediaRate: 0, altMediaRate: 0 } });
  const {client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();

  const onMessage = useCallback((topic, message, _packet) => {
    if (!message || !topic) return;

    const topicParts = topic.toString().split('/');
    const payload = parseFloat(message.toString());
    const unit = topicParts[1];
    const isAltMedia = topicParts.at(-1) === 'alt_media_throughput';

    if (Number.isNaN(payload)) {
      return;
    }

    if (isAltMedia) {
      setAltMediaThroughputPerUnit((previous) => ({
        ...previous,
        [unit]: payload,
      }));
      return;
    }

    setMediaThroughputPerUnit((previous) => ({
      ...previous,
      [unit]: payload,
    }));
  }, []);

  const mediaThroughput = useMemo(
    () => Object.values(mediaThroughputPerUnit).reduce((total, value) => total + value, 0),
    [mediaThroughputPerUnit]
  );
  const altMediaThroughput = useMemo(
    () => Object.values(altMediaThroughputPerUnit).reduce((total, value) => total + value, 0),
    [altMediaThroughputPerUnit]
  );

  useEffect(() => {
    setMediaThroughputPerUnit({});
    setAltMediaThroughputPerUnit({});
  }, [experiment]);

  useEffect(() => {
    if (!experiment || !client) {
      return undefined;
    }
    const topics = [
      `pioreactor/+/${experiment}/dosing_automation/alt_media_throughput`,
      `pioreactor/+/${experiment}/dosing_automation/media_throughput`,
    ];
    subscribeToTopic(topics, onMessage, "MediaCard");
    return () => {
      unsubscribeFromTopic(topics, "MediaCard");
    };
  }, [client, experiment, onMessage, subscribeToTopic, unsubscribeFromTopic]);

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

  function relabelUnit(unit) {
    return relabelMap && relabelMap[unit] ? `${relabelMap[unit]} / ${unit}` : unit;
  }

  return (
    <Card>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="h6" component="h2" gutterBottom>
          <Box fontWeight="fontWeightRegular">Dosing</Box>
        </Typography>

        {activeUnits.length === 0 && (
            <Typography variant="body2" component="p" color="textSecondary">No Pioreactors are currently assigned.</Typography>
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
