import dayjs from 'dayjs';

import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from "react-router";
import {
  CircularProgress,
  FormControl,
  MenuItem,
  Select,
  Typography,
  Divider,
  Alert,
} from '@mui/material';
import Grid from "@mui/material/Grid";
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import { fetchTaskResult } from "./utilities";
import FormLabel from '@mui/material/FormLabel';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import { Table, TableBody, TableCell, TableHead, TableRow, TableContainer } from '@mui/material';
import Chip from '@mui/material/Chip';
import PioreactorIcon from "./components/PioreactorIcon";
import PioreactorsIcon from './components/PioreactorsIcon';
import EstimatorIcon from './components/EstimatorIcon';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import { readyGreen } from "./color";


const ActiveOrNotCheckBox = ({ onlyActive, setOnlyActive }) => {
  return (
    <FormControl sx={{ mt: 3, ml: 1 }}>
      <FormControlLabel
        checked={onlyActive}
        control={<Switch color="primary" onChange={setOnlyActive} size="small" />}
        label="Only Active estimators"
      />
    </FormControl>
  );
};


function EstimatorCard() {
  return (
    <Card>
      <CardContent sx={{ p: 2 }}>
        <EstimatorData />
      </CardContent>
    </Card>
  );
}


function EstimatorData() {
  const { pioreactorUnit, device } = useParams();

  const [loading, setLoading] = useState(true);
  const [rawData, setRawData] = useState(null);
  const [devices, setDevices] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [estimatorDataByDevice, setEstimatorDataByDevice] = useState({});
  const [selectedDevice, setSelectedDevice] = useState(device || '');
  const [selectedUnit, setSelectedUnit] = useState(pioreactorUnit || '$broadcast');
  const [onlyActive, setOnlyActive] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await fetchTaskResult('/api/workers/$broadcast/estimators');
        setRawData(data);
      } catch (err) {
        console.error('Error fetching estimator data', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  useEffect(() => {
    if (!rawData || rawData.status !== 'complete') {
      return;
    }

    const allMachines = rawData.result;
    const deviceSet = new Set();
    const deviceMap = {};

    setWorkers(Object.keys(allMachines));

    Object.values(allMachines).forEach((machine) => {
      Object.entries(machine ?? {}).forEach(([deviceName, estimators]) => {
        if (!Array.isArray(estimators)) return;

        deviceSet.add(deviceName);

        if (!deviceMap[deviceName]) {
          deviceMap[deviceName] = [];
        }

        const estimatorsWithDevice = estimators.map((estimator) => ({
          ...estimator,
          device: deviceName,
        }));
        deviceMap[deviceName].push(...estimatorsWithDevice);
      });
    });

    const deviceArray = Array.from(deviceSet).sort();

    setDevices(deviceArray);
    setEstimatorDataByDevice(deviceMap);

    if (selectedDevice === '') {
      setSelectedDevice(deviceArray[0]);
    }
  }, [rawData]);

  const handleSelectDeviceChange = (event) => {
    setSelectedDevice(event.target.value);
    navigate(`/estimators/${selectedUnit}/${event.target.value}`);
  };

  const handleSelectUnitChange = (event) => {
    setSelectedUnit(event.target.value);
    navigate(`/estimators/${event.target.value}/${selectedDevice}`);
  };

  const handleOnlyActiveChange = (event) => {
    setOnlyActive(event.target.checked);
  };

  const isDataComplete = rawData && rawData.status === 'complete';

  const filteredEstimators = React.useMemo(() => {
    if (!isDataComplete) {
      return [];
    }

    const estimatorsForDevice = estimatorDataByDevice[selectedDevice] || [];
    const allUnitsSelected = selectedUnit === '$broadcast';

    return estimatorsForDevice.filter((estimator) => {
      if (allUnitsSelected && onlyActive) {
        return estimator.is_active;
      }
      if (allUnitsSelected && !onlyActive) {
        return true;
      }
      if (!allUnitsSelected && onlyActive) {
        return estimator.pioreactor_unit === selectedUnit && estimator.is_active;
      }
      if (!allUnitsSelected && !onlyActive) {
        return estimator.pioreactor_unit === selectedUnit;
      }
      return false;
    }).sort((a, b) => {
      const aDate = dayjs(a.created_at);
      const bDate = dayjs(b.created_at);

      const aTime = aDate.isValid() ? aDate.valueOf() : 0;
      const bTime = bDate.isValid() ? bDate.valueOf() : 0;

      if (aTime !== bTime) {
        return bTime - aTime;
      }

      const unitCmp = a.pioreactor_unit.localeCompare(b.pioreactor_unit);
      if (unitCmp !== 0) return unitCmp;

      return a.estimator_name.localeCompare(b.estimator_name);
    });
  }, [isDataComplete, estimatorDataByDevice, selectedDevice, selectedUnit, onlyActive]);

  if (loading) {
    return (
      <Box sx={{ textAlign: 'center', marginTop: '2rem' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!isDataComplete) {
    return <Alert severity="error">Something went wrong or data is incomplete. Check web server logs.</Alert>;
  }

  return (
    <Box>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between" }}>
          <Box>
            <FormControl size="small" sx={{ marginBottom: '1rem', mr: 4 }}>
              <FormLabel component="legend">Pioreactor</FormLabel>
              <Select
                labelId="pioreactor-select-label"
                label="Pioreactor"
                variant="standard"
                value={selectedUnit}
                onChange={handleSelectUnitChange}
                sx={{ width: "200px" }}
              >
                {workers.map((worker) => (
                  <MenuItem key={worker} value={worker}>
                    {worker}
                  </MenuItem>
                ))}
                <MenuItem value={"$broadcast"}>
                  <PioreactorsIcon fontSize="small" sx={{ verticalAlign: "middle", margin: "0px 4px" }} /> All Pioreactors
                </MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ marginBottom: '1rem', mr: 4 }}>
              <FormLabel component="legend">Device</FormLabel>
              <Select
                labelId="device-select-label"
                label="Device"
                variant="standard"
                value={selectedDevice}
                onChange={handleSelectDeviceChange}
                sx={{ width: "200px" }}
              >
                {devices.map((deviceName) => (
                  <MenuItem key={deviceName} value={deviceName}>
                    {deviceName}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>
          <Box>
            <ActiveOrNotCheckBox onlyActive={onlyActive} setOnlyActive={handleOnlyActiveChange} />
          </Box>
        </Box>
      </Box>

      <TableContainer sx={{ px: 5, mt: 1, mb: 1, width: "100%", overflowY: "auto", overflowX: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ padding: "6px 0px" }}>Pioreactor</TableCell>
              <TableCell align="left" sx={{ padding: "6px 0px" }}>Device</TableCell>
              <TableCell align="left" sx={{ padding: "6px 0px" }}>Estimator name</TableCell>
              <TableCell align="left" sx={{ padding: "6px 0px" }}>Active</TableCell>
              <TableCell align="right" sx={{ padding: "6px 6px" }}>Created at</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredEstimators.map((estimator, i) => {
              const unitName = estimator.pioreactor_unit;
              const estimatorName = estimator.estimator_name;
              const deviceName = estimator.device || selectedDevice;

              return (
                <TableRow
                  sx={{
                    ':hover': {
                      bgcolor: '#F7F7F7',
                    },
                    cursor: "pointer",
                  }}
                  onClick={() => navigate(`/estimators/${unitName}/${deviceName}/${estimatorName}`)}
                  key={i}
                >
                  <TableCell sx={{ padding: "6px 6px", display: "flex" }}>
                    <Chip
                      size="small"
                      icon={<PioreactorIcon />}
                      label={unitName}
                      data-pioreactor-unit={unitName}
                    />
                  </TableCell>
                  <TableCell align="left" sx={{ padding: "6px 0px" }}>{deviceName}</TableCell>
                  <TableCell align="left" sx={{ padding: "6px 0px" }}>
                    <Chip
                      size="small"
                      icon={<EstimatorIcon />}
                      label={estimatorName}
                      data-estimator-name={estimatorName}
                    />
                  </TableCell>
                  <TableCell align="left" sx={{ padding: "6px 0px" }}>
                    {estimator.is_active ? (
                      <Chip
                        size="small"
                        label={"Active"}
                        icon={<CheckCircleOutlineOutlinedIcon />}
                        sx={{
                          color: readyGreen,
                          border: "none",
                          backgroundColor: "transparent",
                          "& .MuiChip-icon": { color: readyGreen },
                        }}
                      />
                    ) : ""}
                  </TableCell>
                  <TableCell align="right" sx={{ padding: "6px 6px" }}>
                    {dayjs(estimator.created_at).format('MMMM D, YYYY, h:mm a')}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}


function EstimatorsContainer() {
  return (
    <React.Fragment>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">Estimators</Box>
          </Typography>
        </Box>
        <Divider sx={{ marginTop: "0px", marginBottom: "15px" }} />
      </Box>
      <Grid container spacing={2}>
        <Grid
          size={{
            xs: 12,
            sm: 12,
          }}
        >
          <EstimatorCard />
        </Grid>
      </Grid>
    </React.Fragment>
  );
}


function Estimators(props) {
  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);
  return (
    <Grid container spacing={2}>
      <Grid
        size={{
          md: 12,
          xs: 12,
        }}
      >
        <EstimatorsContainer />
      </Grid>
    </Grid>
  );
}

export default Estimators;
