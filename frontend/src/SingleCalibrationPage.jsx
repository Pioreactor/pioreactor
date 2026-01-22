import React, { useEffect, useState } from "react";
import { useParams,  useNavigate,  Link } from "react-router";
import { useConfirm } from 'material-ui-confirm';
import { CircularProgress, Button, Typography, Box, Divider } from "@mui/material";
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import IconButton from '@mui/material/IconButton';
import {fetchTaskResult, colors, ColorCycler, readyGreen} from "./utilities"
import MuiLink from '@mui/material/Link';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CalibrationChart from "./components/CalibrationChart";
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import CodeIcon from '@mui/icons-material/Code';
import Grid from "@mui/material/Grid";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";
import PioreactorIcon from "./components/PioreactorIcon"
import yaml from "js-yaml";
import dayjs from 'dayjs';
import Snackbar from '@mui/material/Snackbar';
import TuneIcon from '@mui/icons-material/Tune';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import Chip from '@mui/material/Chip';
import DoNotDisturbOnOutlinedIcon from '@mui/icons-material/DoNotDisturbOnOutlined';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import DisplaySourceCode from "./components/DisplaySourceCode";
import CloseIcon from '@mui/icons-material/Close';


function formatPolynomial(coefficients) {
    const superscripts = {
        0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹'
    };

    const toSuperscript = (num) => {
        return String(num)
            .split('')
            .map(digit => superscripts[digit] || '')
            .join('');
    };

    // Define thresholds for extreme magnitudes.
    const LOWER_THRESHOLD = 1e-3;
    const UPPER_THRESHOLD = 1e5;

    let result = '';

    coefficients.forEach((coef, i) => {
        if (coef === 0) return;

        const power = coefficients.length - i - 1;
        const absCoef = Math.abs(coef);

        let term = '';

        // Add sign
        if (result) {
            term += coef > 0 ? ' + ' : ' - ';
        } else if (coef < 0) {
            term += '-';
        }

        // Only display the coefficient if it's not 1 (or -1) for non-constant terms.
        if (absCoef !== 1 || power === 0) {
            if (absCoef < LOWER_THRESHOLD || absCoef >= UPPER_THRESHOLD) {
                term += absCoef.toExponential(3);
            } else {
                term += absCoef.toFixed(3);
            }
        }

        // Add the variable and its exponent if needed.
        if (power > 0) {
            term += 'x';
            if (power > 1) term += toSuperscript(power);
        }

        result += term;
    });

    return result || '0';
}

function formatSpline(splineData) {
  if (!splineData || Array.isArray(splineData)) {
    return 'Invalid spline data';
  }
  const { knots } = splineData;
  if (!Array.isArray(knots)) {
    return 'Invalid spline data';
  }
  return `Natural cubic spline (${knots.length} knots)`;
}

function formatCurve(curveType, curveData) {
  if (curveType === "spline") {
    return formatSpline(curveData);
  }
  if (!curveData || Array.isArray(curveData) || !Array.isArray(curveData.coefficients)) {
    return "Invalid polynomial data";
  }
  return `y=${formatPolynomial(curveData.coefficients)}`;
}



function Delete({ pioreactorUnit, device, calibrationName }) {
  const navigate = useNavigate()
  const confirm = useConfirm();

  const deleteCalibration = async () => {
    try {
      await confirm({
        description: 'Deleting this calibration will remove it from disk. This is irreversible. Do you wish to continue?',
        title: `Delete calibration ${calibrationName}?`,
        confirmationText: "Confirm",
        confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
        cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},
      });

      const response = await fetch(`/api/workers/${pioreactorUnit}/calibrations/${device}/${calibrationName}`, {
        method: "DELETE",
      });

      if (response.ok){
         navigate(`/calibrations/${pioreactorUnit}/${device}`, {replace: true})
      }
    } catch (err) {
      // confirmation rejected or request failed; no further action needed
    }
  };

  return (
    <Button style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="secondary" onClick={deleteCalibration}>
       <DeleteOutlineIcon fontSize="small"/> Delete
    </Button>
)}


function ViewYamlSource({ pioreactorUnit, device, calibrationName }) {
  const [open, setOpen] = useState(false);
  const [yamlText, setYamlText] = useState("");
  const [loading, setLoading] = useState(false);

  const openAndLoad = async () => {
    setOpen(true);
    setLoading(true);
    setYamlText("");
    try {
      const apiUrl = `/api/workers/${pioreactorUnit}/calibrations/${device}/${calibrationName}`;
      const data = await fetchTaskResult(apiUrl);
      const calibration = data.result[pioreactorUnit];

      const { calibration_type, created_at, curve_data_, x, y, recorded_data } = calibration;

      const yamlObj = {
        calibration_type,
        calibration_name: calibrationName,
        calibrated_on_pioreactor_unit: pioreactorUnit,
        created_at,
        curve_data_,
        x,
        y,
        recorded_data,
        ...calibration,
      };
      delete yamlObj["is_active"];

      const text = yaml.dump(yamlObj, { schema: yaml.JSON_SCHEMA }).replace(/^(\s*)'y':/gm, '$1y:');
      setYamlText(text);
    } catch (err) {
      console.error('Failed to load YAML', err);
      setYamlText('# Error loading YAML');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => setOpen(false);

  return (
    <>
      <Button
        style={{ textTransform: 'none', marginRight: '12px', float: 'right' }}
        onClick={openAndLoad}
      >
        <CodeIcon fontSize="small" sx={{ verticalAlign: "middle", margin: "0px 3px" }}/>
        View YAML
      </Button>
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>
          YAML description for calibration {calibrationName}
          <IconButton
            aria-label="close"
            onClick={handleClose}
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
          {loading ? (
            <Box textAlign="center" mt={2}><CircularProgress size={20} /></Box>
          ) : (
            <DisplaySourceCode sourceCode={yamlText} />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} sx={{ textTransform: 'none' }} autoFocus>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}


function SingleCalibrationPage(props) {
  const { pioreactorUnit, device, calibrationName } = useParams();
  const [calibration, setCalibration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  const fetchSingleCalibration = async () => {
    setLoading(true);
    const apiUrl = `/api/workers/${pioreactorUnit}/calibrations/${device}/${calibrationName}`;
    try {
      const data = await fetchTaskResult(apiUrl)
      setCalibration(data.result[pioreactorUnit]);
    } catch (err) {
      console.error("Failed to fetch calibration:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSingleCalibration();
  }, [pioreactorUnit, device, calibrationName]);

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  const showSnackbar = (message) => {
    setSnackbarMessage(message);
    setSnackbarOpen(true);
  }

  const handleSetActive = async () => {
    const apiUrl = `/api/workers/${pioreactorUnit}/active_calibrations/${device}/${calibrationName}`;
    try {
      const response = await fetch(apiUrl, { method: "PATCH" });
      if (!response.ok) {
        throw new Error("Failed to activate calibration");
      }
      showSnackbar("Calibration set as Active")
      await fetchSingleCalibration();
    } catch (err) {
      console.error("Error setting active calibration:", err);
    }
  };

  const handleRemoveActive = async () => {
    const apiUrl = `/api/workers/${pioreactorUnit}/active_calibrations/${device}`;
    try {
      const response = await fetch(apiUrl, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Failed to remove active calibration");
      }
      showSnackbar("Calibration removed as Active")
      await fetchSingleCalibration();
    } catch (err) {
      console.error("Error removing active calibration:", err);
    }
  };

  const isActive = calibration?.is_active ?? false;

  return (
      <>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>

          <Typography variant="h5" component="h1">
            <Box sx={{display:"inline"}}>
              <Button to={`/calibrations`} component={Link} sx={{ textTransform: 'none' }}>
                <ArrowBackIcon sx={{ verticalAlign: "middle", mr: 0.5 }} fontSize="small"/> All calibrations
              </Button>
            </Box>
          </Typography>

          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap", alignItems: "center"}}>
            <ViewYamlSource pioreactorUnit={pioreactorUnit} device={device} calibrationName={calibrationName} />
            <Delete pioreactorUnit={pioreactorUnit} device={device} calibrationName={calibrationName} />
            <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />
            <Button
              startIcon={isActive ? <DoNotDisturbOnOutlinedIcon/> : <CheckCircleOutlineOutlinedIcon />}
              variant={isActive ? "text" : "contained"}
              color="primary"
              disabled={loading || !calibration}
              onClick={isActive ? handleRemoveActive : handleSetActive}
              sx={{ textTransform: "none",  ml: 1, mr: 1 }}
            >
              {isActive ? "Set inactive" : "Set active"}
            </Button>
          </Box>
        </Box>
      </Box>
      <SingleCalibrationPageCard
        pioreactorUnit={pioreactorUnit}
        device={device}
        calibrationName={calibrationName}
        calibration={calibration}
        loading={loading}
      />

      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
        autoHideDuration={7000}
        resumeHideDuration={2000}
        key={"snackbar" + pioreactorUnit + device + calibrationName}
      />
      </>
  )
}


function SingleCalibrationPageCard({ pioreactorUnit, device, calibrationName, calibration, loading } ) {
  const unitsColorMap = new ColorCycler(colors)
  if (loading) {
    return (
      <Box textAlign="center" mt={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (!calibration) {
    return (
      <Box sx={{textAlign: "center", mb: '50px', mt: "50px"}}>
        <Typography  variant="body2" component="p" color="textSecondary">
           Unable to find calibration data.
        </Typography>
      </Box>
    );
  }

  const {
    calibration_type,
    created_at,
    curve_data_,
    curve_type,
    x,
    y,
    recorded_data,
    is_active,
  } = calibration;

  return (
    <Grid container spacing={0}>
      <Grid size={12} sx={{mb: 2}}>
        <Card>
          <CardContent sx={{p: 2}}>
              <Box sx={{ mb: 2 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <Typography variant="h6" component="h2">
                    Calibration: {calibrationName}
                  </Typography>
                  {is_active && (
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
                  )}
                </Box>
                <Typography variant="subtitle2" color="text.secondary">
                  <MuiLink
                    component={Link}
                    to={`/calibrations/${pioreactorUnit}`}
                    color="inherit"
                    underline="hover"
                    sx={{ fontWeight: 500 }}
                  >
                    {pioreactorUnit}
                  </MuiLink>
                  {" / "}
                  <MuiLink
                    component={Link}
                    to={`/calibrations/${pioreactorUnit}/${device}`}
                    color="inherit"
                    underline="hover"
                    sx={{ fontWeight: 500 }}
                  >
                    {device}
                  </MuiLink>
                </Typography>
              </Box>

              <CalibrationChart calibrations={[calibration]} deviceName={device} unitsColorMap={unitsColorMap} highlightedModel={{pioreactorUnit: null, calbrationName: null}} title={`Calibration curve for ${calibrationName}`} />

              <Box sx={{px: 5, mt: 1}}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="h6">Calibration data</Typography>
                  {/*<Button style={{textTransform: 'none', float: "right" }} onClick={copyCalibrationYamlToClipboard}>
                    <ContentCopyOutlinedIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/> Copy as YAML
                  </Button>*/}
                </Box>
                <Table size="small">
                  <TableBody>
                      <TableRow>
                        <TableCell><strong>Calibration name</strong></TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            icon={<TuneIcon/>}
                            label={calibrationName}
                            data-calibration-name={calibrationName}
                            />
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><strong>Pioreactor</strong></TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            icon={<PioreactorIcon/>}
                            label={pioreactorUnit}
                            clickable
                              component={Link}
                              to={`/calibrations/${pioreactorUnit}`}
                            data-pioreactor-unit={pioreactorUnit}
                            />
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><strong>Created at</strong></TableCell>
                        <TableCell>{dayjs(created_at).format('MMMM D, YYYY, h:mm a')}</TableCell>
                      </TableRow>
                      <TableRow>
                      <TableCell><strong>Active</strong></TableCell>
                      <TableCell>
                        {is_active && (
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
                        )}
                      </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><strong>Device</strong></TableCell>
                        <TableCell>{device}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><strong>Calibration type</strong></TableCell>
                        <TableCell>{calibration_type}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><strong>Fit curve</strong></TableCell>
                        <TableCell>
                          {formatCurve(curve_type, curve_data_)}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
              </Box>

              <Box sx={{ px: 5, mt: 5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="h6">Recorded data</Typography>
                  {/*<Button style={{textTransform: 'none', float: "right" }} onClick={copyRecordedDataCsvToClipboard}>
                    <ContentCopyOutlinedIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/> Copy as CSV
                  </Button>*/}
                </Box>
                <Box sx={{ maxHeight: 150, overflowY: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{x}</TableCell>
                        <TableCell>{y}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {recorded_data.x.map((xVal, idx) => (
                        <TableRow key={idx}>
                          <TableCell>{xVal}</TableCell>
                          <TableCell>{recorded_data.y[idx]}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              </Box>
          </CardContent>
      </Card>
    </Grid>
    <Grid size={12}>
      <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/hardware-calibrations" target="_blank" rel="noopener noreferrer">calibrations</a>.</p>
    </Grid>
  </Grid>
  );
}


export default SingleCalibrationPage;
