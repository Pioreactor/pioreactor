import dayjs from 'dayjs';

import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from "react-router-dom";
import {
  CircularProgress,
  FormControl,
  MenuItem,
  Select,
  Typography,
  Divider,
} from '@mui/material';
import Grid from "@mui/material/Grid";
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {checkTaskCallback, colors, DefaultDict} from "./utilities"
import CalibrationChart from "./components/CalibrationChart"
import FormLabel from '@mui/material/FormLabel';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import { Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import Chip from '@mui/material/Chip';
import Button from '@mui/material/Button';
import GetAppIcon from '@mui/icons-material/GetApp';

import PioreactorIcon from "./components/PioreactorIcon"
import PioreactorsIcon from './components/PioreactorsIcon';
import TuneIcon from '@mui/icons-material/Tune';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';


function CalibrationCard(){
  return (

    <Card>
      <CardContent sx={{p: 2}}>
        <CalibrationData/>
      </CardContent>
    </Card>
  )
}


const ActiveOrNotCheckBox = ({onlyActive, setOnlyActive}) => {
  return (
      <FormControl sx={{mt: 3, ml: 1}}>
          <FormControlLabel
            checked={onlyActive}
            control={<Switch color="primary"  onChange={setOnlyActive}  size="small" />}
            label="Only Active calibrations"
          />
      </FormControl>
)}


function CalibrationData() {
  const { pioreactor_unit, device } = useParams();

  const [loading, setLoading] = useState(true);
  const [rawData, setRawData] = useState(null);
  const [devices, setDevices] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [calibrationDataByDevice, setCalibrationDataByDevice] = useState({});
  const [selectedDevice, setSelectedDevice] = useState(device || '');
  const [selectedUnit, setSelectedUnit] = useState(pioreactor_unit || '$broadcast');
  const [onlyActive, setOnlyActive] = useState(true);
  const [highlightedModel, setHighlightedModel] = useState({pioreactorUnit: null, calibrationName: null});
  const unitsColorMap = new DefaultDict(colors)
  const navigate = useNavigate()

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

      Object.entries(machine ?? {}).forEach(([deviceName, calibrations]) => {
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

    if (selectedDevice === '') {
      setSelectedDevice(deviceArray[0]);
    }
  }, [rawData]);

  const handleSelectDeviceChange = (event) => {
    setSelectedDevice(event.target.value);
  };

  const handleSelectUnitChange = (event) => {
    setSelectedUnit(event.target.value);
  };

  const handleOnlyActiveChange = (event) => {
    setOnlyActive(event.target.checked);
  };


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

  // filter calibrations to active if onlyActive is true, and by pioreactor_unit if selectedUnit is not $broadcast
  const filteredCalibrations = (calibrationDataByDevice[selectedDevice] || []).filter((cal) => {
    const allUnits = (selectedUnit === '$broadcast');

    if (allUnits && onlyActive) {
      // Case 1: All units and only active
      return cal.is_active;
    }
    if (allUnits && !onlyActive) {
      // Case 2: All units, regardless of activity
      return true;
    }
    if (!allUnits && onlyActive) {
      // Case 3: Selected unit and only active
      return cal.pioreactor_unit === selectedUnit && cal.is_active;
    }
    if (!allUnits && !onlyActive) {
      // Case 4: Selected unit, regardless of activity
      return cal.pioreactor_unit === selectedUnit;
    }
    return
  }).sort((a, b) => {
  // Compare `is_active` (true first, false later)
  if (a.is_active !== b.is_active) {
    return a.is_active ? -1 : 1; // true comes before false
  }
  // If `is_active` is the same, compare `pioreactor_unit`
  return a.pioreactor_unit.localeCompare(b.pioreactor_unit);
  });

  const onMouseOverRow = (_, cal) => {
    setHighlightedModel({pioreactorUnit: cal.pioreactor_unit, calibrationName: cal.calibration_name});
    // change background of row to light grey
  }
  const onMouseExitRow = (_) => {
    setHighlightedModel({pioreactorUnit: null, calibrationName: null});
  }

  return (
    <Box>
      <Box >
        <Box sx={{display: "flex", justifyContent: "space-between" }}>
          <Box>
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
                  <MenuItem  value={"$broadcast"}>
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
            <ActiveOrNotCheckBox onlyActive={onlyActive} setOnlyActive={handleOnlyActiveChange}/>
          </Box>
        </Box>

        <Box sx={{display: "flex", justifyContent: "center" }}>
          <CalibrationChart
            highlightedModel={highlightedModel}
            calibrations={filteredCalibrations}
            deviceName={selectedDevice}
            unitsColorMap={unitsColorMap}
            title={`Calibrations for ${selectedDevice}`}
          />

        </Box>
      </Box>

      <Box sx={{px: 5, mt: 1, mb: 1}}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{padding: "6px 0px"}}>
                Pioreactor
              </TableCell>
              <TableCell align="left" sx={{padding: "6px 0px"}}>Device</TableCell>
              <TableCell align="left" sx={{padding: "6px 0px"}}>Calibration name</TableCell>
              <TableCell align="left" sx={{padding: "6px 0px"}}>Active</TableCell>
              <TableCell align="right" sx={{padding: "6px 6px"}}>Calibrated on</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredCalibrations.map((cal, i) => {
              const unitName = cal.pioreactor_unit
              const calName = cal.calibration_name
              return (
                <TableRow
                  sx={{
                    ':hover': {
                      bgcolor: '#F7F7F7', // theme.palette.primary.main
                    },
                    cursor: "pointer",
                  }}
                  onMouseOver={(e) => onMouseOverRow(e, cal) }
                  onMouseOut={(e) => onMouseExitRow(e)}
                  onClick={() => navigate(`/calibrations/${unitName}/${selectedDevice}/${calName}`)}
                  key={i}
                  >
                  <TableCell sx={{padding: "6px 6px", display: "flex"}}>
                    <div className="indicator-dot-as-legend" style={{boxShadow: `0 0 0px, inset 0 0 100px  ${unitsColorMap[unitName + calName]}`}} />
                    <Chip
                      size="small"
                      icon={<PioreactorIcon/>}
                      label={unitName}
                      // clickable
                      // component={Link}
                      // to={leaderHostname === unitName ? "/leader" : "/pioreactors/" + unitName}
                      />
                  </TableCell>
                  <TableCell align="left" sx={{padding: "6px 0px"}}>{selectedDevice}</TableCell>
                  <TableCell align="left" sx={{padding: "6px 0px"}}>

                      <Chip
                        size="small"
                        icon={<TuneIcon/>}
                        label={calName}
                        />
                  </TableCell>
                  <TableCell align="left" sx={{padding: "6px 0px"}}>{cal.is_active ?  <><Chip size="small" label={"Active"} icon={<CheckCircleOutlineOutlinedIcon />} sx={{backgroundColor: "inherit"}}  /></> : ""}</TableCell>
                  <TableCell align="right" sx={{padding: "6px 6px"}}>{dayjs(cal.created_at).format('YYYY-MM-DD') }</TableCell>
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

  const handleDownloadCalibrations = async () => {
    try {
      // Request the ZIP as binary data
      const response = await fetch('/api/workers/$broadcast/zipped_calibrations');
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      const blob = await response.blob();

      // Create a temporary URL for the blob
      const url = window.URL.createObjectURL(blob);

      // Create a link to programmatically click
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'calibration_yamls.zip');
      document.body.appendChild(link);
      link.click();

      // Clean up
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };


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
            <Button style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary" onClick={handleDownloadCalibrations}>
              <GetAppIcon fontSize="15"/> Download all calibrations
            </Button>
          </Box>
        </Box>
        <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />

      </Box>

      <Grid container spacing={2} >
        <Grid item xs={12} sm={12}>
          <CalibrationCard/>
        </Grid>
      </Grid>
      <Grid item xs={12}>
        <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/hardware-calibrations" target="_blank" rel="noopener noreferrer">calibrations</a>.</p>
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
