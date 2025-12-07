import dayjs from 'dayjs';

import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from "react-router";
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';
import {
  CircularProgress,
  FormControl,
  MenuItem,
  Select,
  Typography,
  Divider,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
} from '@mui/material';
import Grid from "@mui/material/Grid";
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import {checkTaskCallback, colors, ColorCycler} from "./utilities"
import CalibrationChart from "./components/CalibrationChart"
import FormLabel from '@mui/material/FormLabel';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import { Table, TableBody, TableCell, TableHead, TableRow, TableContainer } from '@mui/material';
import Chip from '@mui/material/Chip';
import Button from '@mui/material/Button';
import UploadIcon from '@mui/icons-material/Upload';
import DownloadIcon from '@mui/icons-material/Download';
import PioreactorIcon from "./components/PioreactorIcon"
import PioreactorsIcon from './components/PioreactorsIcon';
import TuneIcon from '@mui/icons-material/Tune';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import {readyGreen} from "./utilities"

import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import 'prismjs/components/prism-yaml';
import CheckIcon from '@mui/icons-material/Check';


export function sanitizeDeviceName(raw) {
  const cleaned = raw
    .replace(/\s+/g, "_")          // spaces, tabs, line‑breaks → “_”
    .replace(/[^A-Za-z0-9_-]/g, "") // drop everything else (only allow these chars)
    .replace(/^[_.]+/, "")           // no leading “.” or “_”
    .slice(0, 255);                // extra‑long names are sliced

  return cleaned;
}

function UploadCalibrationDialog({
  open,
  onClose,
}) {
  const { pioreactorUnit, device } = useParams();

  const [workers, setWorkers] = useState([])
  const [selectedWorker, setSelectedWorker] = useState(pioreactorUnit || '$broadcast');
  const [selectedDevice, setSelectedDevice] = useState(device || '');
  const [calibrationYaml, setCalibrationYaml] = useState('');
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const handleUploadCalibration = async () => {
    setError(null);
    setSuccess(null);
    try {
      const requestBody = {
        calibration_data: calibrationYaml
      };

      const response = await fetch(`/api/workers/${selectedWorker}/calibrations/${selectedDevice}`, {
        method: 'POST',
        headers: {
          // Note: "application/json" since endpoint only accepts JSON
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const error = await response.json();
        setError(error.error);
        return
      }

      // Optionally clear fields so user can enter another calibration easily:
      setCalibrationYaml('');
      setSuccess(
        <span>
          Calibration sent to Pioreactor(s). Add another calibration, or{' '}
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              color: 'inherit',
              textDecoration: 'underline',
              cursor: 'pointer',
            }}
          >
            refresh
          </button>{' '}
          the page to see updates.
        </span>
      );
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    const fetchWorkers = async () => {
      try {
        const response = await fetch('/api/workers');
        if (!response.ok) {
          throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
        setWorkers(data.map(worker => worker.pioreactor_unit));
      } catch (err) {
        console.error('Error fetching workers:', err);
      }
    };

    fetchWorkers();
  }, []);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth aria-labelledby="form-dialog-title">
      <DialogTitle>
      Upload calibration from a YAML description

        <IconButton
          aria-label="close"
          onClick={onClose}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[500],
          }}
          size="large">
          <CloseIcon />
        </IconButton>

      </DialogTitle>
      <DialogContent>
        <Box sx={{ mb: 2 }}>
          <FormControl variant="standard" sx={{ mr: 4, minWidth: 200 }}>
            <FormLabel component="legend">Pioreactor</FormLabel>
            <Select
              value={selectedWorker}
              onChange={(e) => setSelectedWorker(e.target.value)}
            >
              {workers.map((worker) => (
                <MenuItem key={worker} value={worker}>
                  {worker}
                </MenuItem>
              ))}
              {workers.length > 1 &&
              <MenuItem  value={"$broadcast"}>
                <PioreactorsIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 4px"}} /> All Pioreactors
              </MenuItem>
              }
            </Select>
          </FormControl>

          <FormControl variant="standard" sx={{ mr: 4, minWidth: 200 }}>
            <FormLabel component="legend">Device</FormLabel>
            <TextField
              variant="standard"
              fullWidth
              placeholder="e.g. od, media_pump"
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(sanitizeDeviceName(e.target.value))}
            />
          </FormControl>
        </Box>

        <FormLabel component="legend">YAML description</FormLabel>
        <Box sx={{
            tabSize: "4ch",
            border: "1px solid #ccc",
            margin: "5px 0px 10px 0px",
            position: "relative",
            width: "100%",
            height: "350px",
            overflow: "auto",
            borderRadius: "4px",
            flex: 1
          }}>
          <Editor
            value={calibrationYaml}
            onValueChange={setCalibrationYaml}
            highlight={_ => highlight(calibrationYaml, languages.yaml)}
            padding={10}
            style={{
              fontSize: "14px",
              fontFamily: 'monospace',
              backgroundColor: "hsla(0, 0%, 100%, .5)",
              borderRadius: "4px",
              minHeight: "100%"
            }}
          />
        </Box>


        <Box sx={{display: "flex", justifyContent: "space-between"}}>
          <Box>
          {error && <Box color="error.main">
          {error}
          </Box>
          }
          {success && <Box>
          <CheckIcon sx={{verticalAlign: "middle", margin: "0px 3px", color: readyGreen}}/> {success}
          </Box>
          }
          </Box>
          <Button onClick={handleUploadCalibration} variant="contained" sx={{marginTop: "10px", textTransform: 'none'}} disabled={!selectedDevice || !calibrationYaml || !selectedWorker}>
            Upload
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
}



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
  const { pioreactorUnit, device } = useParams();

  const [loading, setLoading] = useState(true);
  const [rawData, setRawData] = useState(null);
  const [devices, setDevices] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [calibrationDataByDevice, setCalibrationDataByDevice] = useState({});
  const [selectedDevice, setSelectedDevice] = useState(device || '');
  const [selectedUnit, setSelectedUnit] = useState(pioreactorUnit || '$broadcast');
  const [onlyActive, setOnlyActive] = useState(false);
  const [highlightedModel, setHighlightedModel] = useState({pioreactorUnit: null, calibrationName: null});
  const [hiddenCalibrationKeys, setHiddenCalibrationKeys] = useState({});
  const unitsColorMap = React.useMemo(
    () => new ColorCycler(colors),
    []
  );
  const getCalibrationKey = React.useCallback((unit, calibrationName) => `${unit}::${calibrationName}`, []);
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
    navigate(`/calibrations/${selectedUnit}/${event.target.value}`);
  };

  const handleSelectUnitChange = (event) => {
    setSelectedUnit(event.target.value);
    navigate(`/calibrations/${event.target.value}/${selectedDevice}`);
  };

  const handleOnlyActiveChange = (event) => {
    setOnlyActive(event.target.checked);
  };

  const toggleCalibrationVisibility = React.useCallback((calibration) => {
    const key = getCalibrationKey(calibration.pioreactor_unit, calibration.calibration_name);
    setHiddenCalibrationKeys((prev) => {
      const next = { ...prev };
      if (next[key]) {
        delete next[key];
      } else {
        next[key] = true;
      }
      return next;
    });
  }, [getCalibrationKey]);


  const isDataComplete = rawData && rawData.status === 'complete';

  const filteredCalibrations = React.useMemo(() => {
    if (!isDataComplete) {
      return [];
    }

    const calibrationsForDevice = calibrationDataByDevice[selectedDevice] || [];
    const allUnitsSelected = selectedUnit === '$broadcast';

    return calibrationsForDevice.filter((cal) => {
      if (allUnitsSelected && onlyActive) {
        return cal.is_active;
      }
      if (allUnitsSelected && !onlyActive) {
        return true;
      }
      if (!allUnitsSelected && onlyActive) {
        return cal.pioreactor_unit === selectedUnit && cal.is_active;
      }
      if (!allUnitsSelected && !onlyActive) {
        return cal.pioreactor_unit === selectedUnit;
      }
      return false;
    }).sort((a, b) => {
      const unitCmp = a.pioreactor_unit.localeCompare(b.pioreactor_unit);
      if (unitCmp !== 0) return unitCmp;

      const aDate = dayjs(a.created_at);
      const bDate = dayjs(b.created_at);

      const aTime = aDate.isValid() ? aDate.valueOf() : 0;
      const bTime = bDate.isValid() ? bDate.valueOf() : 0;

      if (aTime !== bTime) {
        return aTime - bTime; // oldest first within unit
      }

      return a.calibration_name.localeCompare(b.calibration_name);
    });
  }, [isDataComplete, calibrationDataByDevice, selectedDevice, selectedUnit, onlyActive]);

  const visibleCalibrations = React.useMemo(() => (
    filteredCalibrations.filter((cal) => {
      return !hiddenCalibrationKeys[getCalibrationKey(cal.pioreactor_unit, cal.calibration_name)];
    })
  ), [filteredCalibrations, hiddenCalibrationKeys, getCalibrationKey]);

  if (loading) {
    return (
      <Box sx={{ textAlign: 'center', marginTop: '2rem' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!isDataComplete) {
    return <Typography>Something went wrong or data is incomplete. Check web server logs.</Typography>;
  }

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
                    <PioreactorsIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 4px"}} /> All Pioreactors
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

          <CalibrationChart
            highlightedModel={highlightedModel}
            calibrations={visibleCalibrations}
            deviceName={selectedDevice}
            unitsColorMap={unitsColorMap}
            title={`Calibrations for ${selectedDevice}`}
          />

      </Box>

      <TableContainer sx={{px: 5, mt: 1, mb: 1,  width: "100%", overflowY: "auto", overflowX: 'auto',}}>
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
              const calibrationKey = getCalibrationKey(unitName, calName)
              const isHidden = Boolean(hiddenCalibrationKeys[calibrationKey])
              const dotColor = unitsColorMap[unitName + calName]

              const handleDotClick = (event) => {
                event.stopPropagation()
                event.preventDefault()
                toggleCalibrationVisibility(cal)
              }

              const handleDotKeyDown = (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  event.stopPropagation()
                  toggleCalibrationVisibility(cal)
                }
              }

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
                    <div
                      className="indicator-dot-as-legend"
                      role="button"
                      onClick={handleDotClick}
                      tabIndex={0}
                      aria-pressed={!isHidden}
                      aria-label={isHidden ? `Show ${unitName} calibration ${calName}` : `Hide ${unitName} calibration ${calName}`}
                      onKeyDown={handleDotKeyDown}
                      style={{
                        backgroundColor: isHidden ? 'transparent' : dotColor,
                        cursor: 'pointer',
                      }}
                    />
                    <Chip
                      size="small"
                      icon={<PioreactorIcon/>}
                      label={unitName}
                      data-pioreactor-unit={unitName}
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
                        data-calibration-name={calName}
                        />
                  </TableCell>
                  <TableCell align="left" sx={{padding: "6px 0px"}}>{cal.is_active ?  <><Chip size="small" label={"Active"} icon={<CheckCircleOutlineOutlinedIcon />} sx={{backgroundColor: "inherit"}}  /></> : ""}</TableCell>
                  <TableCell align="right" sx={{padding: "6px 6px"}}>{dayjs(cal.created_at).format('YYYY-MM-DD') }</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}


function CalibrationsContainer() {

  const [openUploadDialog, setOpenUploadDialog] = useState(false);

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
            <Button style={{textTransform: 'none', marginRight: "0px", float: "right"}}
                    color="primary"
                    onClick={() => setOpenUploadDialog(true)}
            >
              <UploadIcon fontSize="small"/> Upload calibration
            </Button>
            <Button style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary" onClick={handleDownloadCalibrations}>
              <DownloadIcon fontSize="small"/> Download all calibrations
            </Button>
          </Box>
        </Box>
        <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />

      </Box>
      <UploadCalibrationDialog
        open={openUploadDialog}
        onClose={() => setOpenUploadDialog(false)}
      />
      <Grid container spacing={2} >
        <Grid
          size={{
            xs: 12,
            sm: 12
          }}>
          <CalibrationCard/>
        </Grid>
      </Grid>
      <Grid size={12}>
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
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <CalibrationsContainer/>
        </Grid>
      </Grid>
    );
}

export default Calibrations;
