import dayjs from 'dayjs';

import React, { useEffect, useState } from 'react';
import {
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Typography,
  Divider,
} from '@mui/material';
import Grid from "@mui/material/Grid";
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {checkTaskCallback} from "./utilities"
import CalibrationChart from "./components/CalibrationChart"
import FormLabel from '@mui/material/FormLabel';
import { Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import Chip from '@mui/material/Chip';
import PioreactorIcon from "./components/PioreactorIcon"
import PioreactorsIcon from './components/PioreactorsIcon';


function ActiveCalibrationCard(){
  return (

    <Card>
      <CardContent sx={{p: 2}}>
       <Typography variant="h6" component="h2">
          <Box fontWeight="fontWeightRegular">Active calibrations</Box>
        </Typography>

        <ActiveCalibrationData/>
      </CardContent>
    </Card>
  )
}

function ActiveCalibrationData() {
  const [loading, setLoading] = useState(true);
  const [rawData, setRawData] = useState(null);
  const [devices, setDevices] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [calibrationDataByDevice, setCalibrationDataByDevice] = useState({});
  const [selectedDevice, setSelectedDevice] = useState('');
  const [selectedUnit, setSelectedUnit] = useState('_all');

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Replace the URL below with your actual endpoint or route
        const response = await fetch('/api/workers/$broadcast/calibrations');
        const firstResponse = await response.json();
        const data = await checkTaskCallback(firstResponse.result_url_path)
        setRawData(data);
      } catch (err) {
        console.error('Error fetching calibration data', err);
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

    const allMachines = rawData.result; // e.g. { worker: {...}, leader: {...}, ... }

    // temporary structures
    const deviceSet = new Set();
    const deviceMap = {}; // deviceName -> array of calibrations

    setWorkers(Object.keys(allMachines))
    //    Keys like media_pump, waste_pump, od, stirring, alt_media_pump, etc.
    Object.values(allMachines).forEach((machine) => {
      // machine is an object like:
      // { media_pump: [ ... ], od: [ ... ], stirring: [ ... ] }

      Object.entries(machine).forEach(([deviceName, calibrations]) => {
        // If calibrations is not an array, skip
        if (!Array.isArray(calibrations)) return;

        deviceSet.add(deviceName);

        // Keep building up the calibration data in deviceMap
        if (!deviceMap[deviceName]) {
          deviceMap[deviceName] = [];
        }
        deviceMap[deviceName].push(...calibrations);
      });
    });

    const deviceArray = Array.from(deviceSet).sort(); // sort for consistent dropdown order

    setDevices(deviceArray);
    setCalibrationDataByDevice(deviceMap);

    if (deviceArray.length > 0) {
      setSelectedDevice(deviceArray[0]);
    }
  }, [rawData]);

  const handleSelectDeviceChange = (event) => {
    setSelectedDevice(event.target.value);
  };

  const handleSelectUnitChange = (event) => {
    setSelectedUnit(event.target.value);
  };

  // This would be the calibrations associated with the currently selected device
  const calibrationsForSelectedDevice = calibrationDataByDevice[selectedDevice] || [];

  if (loading) {
    return (
      <Box sx={{ textAlign: 'center', marginTop: '2rem' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!rawData || rawData.status !== 'complete') {
    return <Typography>Something went wrong or data is incomplete. Check web server logs.</Typography>;
  }
  console.log(calibrationsForSelectedDevice.filter(cal => cal.pioreactor_unit === selectedUnit))
  return (
    <Box>
      <Box sx={{mt: 2}}>
        <Box sx={{display: "flex", justifyContent: "left" }}>
          <FormControl size="small" sx={{ marginBottom: '1rem', mr: 4}}>
            <FormLabel component="legend">Pioreactor</FormLabel>
            <Select
              labelId="pioreactor-select-label"
              label="Pioreactor"
              variant="standard"
              value={selectedUnit}
              onChange={handleSelectUnitChange}
              sx={{width: "200px"}}
            >
              {workers.map((worker) => (
                <MenuItem key={worker} value={worker}>
                  {worker}
                </MenuItem>
              ))}
                <MenuItem  value={"_all"}>
                  <PioreactorsIcon fontSize="15" sx={{verticalAlign: "middle", margin: "0px 4px"}} /> All Pioreactors
                </MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ marginBottom: '1rem', mr: 4}}>
            <FormLabel component="legend">Device</FormLabel>
            <Select
              labelId="device-select-label"
              label="Device"
              variant="standard"
              value={selectedDevice}
              onChange={handleSelectDeviceChange}
              sx={{width: "200px"}}
            >
              {devices.map((device) => (
                <MenuItem key={device} value={device}>
                  {device}
                </MenuItem>
                ))}
            </Select>
          </FormControl>
        </Box>
        <Box>
          <CalibrationChart
            calibrations={selectedUnit == "_all" ? calibrationsForSelectedDevice : calibrationsForSelectedDevice.filter(cal => cal.pioreactor_unit === selectedUnit)}
            deviceName={selectedDevice}
          />

        </Box>
      </Box>

      <Box>
        <Table size="small" sx={{mt: 2}}>
          <TableHead>
            <TableRow>
              <TableCell sx={{padding: "6px 0px"}}>Pioreactor</TableCell>
              <TableCell align="right" sx={{padding: "6px 0px"}}>Device</TableCell>
              <TableCell align="right" sx={{padding: "6px 0px"}}>Active calibration name</TableCell>
              <TableCell align="right" sx={{padding: "6px 0px"}}>Calibrated on</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {calibrationsForSelectedDevice.map((cal, i) => {
              const unitName = cal.pioreactor_unit
              return (
                <TableRow key={i}>
                  <TableCell sx={{padding: "6px 0px"}}>
                    <Chip
                      size="small"
                      icon={<PioreactorIcon/>}
                      label={unitName}
                      // clickable
                      // component={Link}
                      // to={leaderHostname === unitName ? "/leader" : "/pioreactors/" + unitName}
                      />
                  </TableCell>
                  <TableCell align="right" sx={{padding: "6px 0px"}}>{selectedDevice}</TableCell>
                  <TableCell align="right" sx={{padding: "6px 0px"}}>{cal.calibration_name}</TableCell>
                  <TableCell align="right" sx={{padding: "6px 0px"}}>{dayjs(cal.created_at).format('YYYY-MM-DD') }</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Box>
    </Box>
  );
}


function CalibrationsContainer(props) {

  const [config, setConfig] = React.useState({})
  const [calibrationData, setCalibrationData] = React.useState({})
  const [selectedDevice, setSelectedDevice] = React.useState(null)

  return (
    <React.Fragment>

      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Calibrations
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>

          </Box>

        </Box>
        <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />
      </Box>
      <Grid container spacing={2} >
        <Grid item xs={2} sm={2} />
        <Grid item xs={8} sm={8}>
          <ActiveCalibrationCard/>
        </Grid>
        <Grid item xs={2} sm={2} />

      </Grid>

    </React.Fragment>
  );
}

function Calibrations(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <CalibrationsContainer/>
          </Grid>
        </Grid>
    )
}

export default Calibrations;
