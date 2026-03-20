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
import { Link } from 'react-router';


function MediaCard({experiment, relabelMap, activeUnits}) {
  const [throughputByUnit, setThroughputByUnit] = useState({});
  const [rates, setRates] = useState({ all: { mediaRate: 0, altMediaRate: 0 } });
  const {client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();

  useEffect(() => {
    if (!experiment || !client) {
      return undefined;
    }

    const topics = [
      `pioreactor/+/${experiment}/dosing_automation/alt_media_throughput`,
      `pioreactor/+/${experiment}/dosing_automation/media_throughput`,
    ];
    const onMessage = (topic, message, _packet) => {
      if (!message || !topic) return;

      const topicParts = topic.toString().split('/');
      const payload = Number.parseFloat(message.toString());
      const unit = topicParts[1];
      const throughputKey = topicParts.at(-1) === 'alt_media_throughput' ? 'altMedia' : 'media';

      if (Number.isNaN(payload)) {
        return;
      }

      setThroughputByUnit((previous) => ({
        ...previous,
        [unit]: {
          media: previous[unit]?.media ?? 0,
          altMedia: previous[unit]?.altMedia ?? 0,
          [throughputKey]: payload,
        },
      }));
    };

    subscribeToTopic(topics, onMessage, "MediaCard");
    return () => {
      unsubscribeFromTopic(topics, "MediaCard");
    };
  }, [client, experiment, subscribeToTopic, unsubscribeFromTopic]);

  useEffect(() => {
    let isCancelled = false;

    async function getRecentRates() {
      const response = await fetch(`/api/experiments/${experiment}/media_rates`);
      const data = await response.json();

      if (!isCancelled) {
        setRates(data);
      }
    }

    if (experiment) {
      getRecentRates();
    }

    return () => {
      isCancelled = true;
    };
  }, [experiment]);

  function relabelUnit(unit) {
    return relabelMap && relabelMap[unit] ? `${relabelMap[unit]} / ${unit}` : unit;
  }

  const totals = Object.values(throughputByUnit).reduce(
    (aggregate, unitThroughput) => ({
      media: aggregate.media + (unitThroughput.media ?? 0),
      altMedia: aggregate.altMedia + (unitThroughput.altMedia ?? 0),
    }),
    { media: 0, altMedia: 0 }
  );

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
                    {(throughputByUnit[unit]?.media ?? 0).toFixed(1)}mL ({(rates[unit] ? rates[unit].mediaRate.toFixed(1) : '0.0')}mL/h)
                  </TableCell>
                  <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                    {(throughputByUnit[unit]?.altMedia ?? 0).toFixed(1)}mL ({(rates[unit] ? rates[unit].altMediaRate.toFixed(1) : '0.0')}mL/h)
                  </TableCell>
                </TableRow>
              ))}

              {activeUnits.length > 1 &&
              <TableRow key="all">
                <TableCell style={{ padding: '6px 0px' }} component="th" scope="row">
                  <Chip size="small" icon={<PioreactorsIcon/>} label="All assigned Pioreactors" sx={{backgroundColor: "white"}} />
                </TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                  {totals.media.toFixed(1)}mL ({rates.all.mediaRate.toFixed(1)}mL/h)
                </TableCell>
                <TableCell align="right" style={{ fontSize: 13, padding: '6px 0px' }}>
                  {totals.altMedia.toFixed(1)}mL ({rates.all.altMediaRate.toFixed(1)}mL/h)
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
