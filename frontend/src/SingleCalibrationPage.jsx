import React, { useEffect, useState } from "react";
import { useParams,  useNavigate,  Link } from "react-router-dom";
import { useConfirm } from 'material-ui-confirm';
import { CircularProgress, Button, Typography, Box } from "@mui/material";
import {checkTaskCallback, colors, ColorCycler} from "./utilities"
import MuiLink from '@mui/material/Link';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import CalibrationChart from "./components/CalibrationChart";
import ArrowBackIcon from '@mui/icons-material/ArrowBack';

import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@mui/material";
import PioreactorIcon from "./components/PioreactorIcon"
import dayjs from 'dayjs';
import Snackbar from '@mui/material/Snackbar';
import TuneIcon from '@mui/icons-material/Tune';
import DeleteIcon from '@mui/icons-material/Delete';
import Chip from '@mui/material/Chip';
import DoNotDisturbOnOutlinedIcon from '@mui/icons-material/DoNotDisturbOnOutlined';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';


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




function Delete({ pioreactorUnit, device, calibrationName }) {
  const navigate = useNavigate()
  const confirm = useConfirm();

  const deleteCalibration = () => {
    confirm({
      description: 'Deleting this calibration will remove it from disk. This is irreversible. Do you wish to continue?',
      title: `Delete calibration ${calibrationName}?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
    }).then(() => {
      fetch(`/api/workers/${pioreactorUnit}/calibrations/${device}/${calibrationName}`,
        {method: "DELETE"})
      .then((response) => {
        if (response.ok){
           navigate(`/calibrations/${pioreactorUnit}/${device}`, {replace: true})
        }
      })
    }).catch(() => {});
  };

  return (
    <Button style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="secondary" onClick={deleteCalibration}>
       <DeleteIcon fontSize="small"/> Delete
    </Button>
)}



function SingleCalibrationPage(props) {
  const { pioreactorUnit, device, calibrationName } = useParams();

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

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

          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <Delete pioreactorUnit={pioreactorUnit} device={device} calibrationName={calibrationName} />
          </Box>
        </Box>
      </Box>
      <SingleCalibrationPageCard pioreactorUnit={pioreactorUnit} device={device} calibrationName={calibrationName}  />
      </>
  )
}


function SingleCalibrationPageCard({ pioreactorUnit, device, calibrationName } ) {
  const unitsColorMap = new ColorCycler(colors)

  const [calibration, setCalibration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');

  useEffect(() => {
    fetchSingleCalibration();
  }, [pioreactorUnit, device, calibrationName]);

  const fetchSingleCalibration = async () => {
    const apiUrl = `/api/workers/${pioreactorUnit}/calibrations/${device}/${calibrationName}`;
    try {
      const response = await fetch(apiUrl);
      const firstResponse = await response.json();
      const data = await checkTaskCallback(firstResponse.result_url_path)
      setCalibration(data.result[pioreactorUnit]);
    } catch (err) {
      console.error("Failed to fetch calibration:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  const handleSetActive = async () => {
    const apiUrl = `/api/workers/${pioreactorUnit}/active_calibrations/${device}/${calibrationName}`;
    try {
      const response = await fetch(apiUrl, { method: "PATCH" });
      if (!response.ok) {
        throw new Error("Failed to activate calibration");
      }
      setSnackbarMessage("Calibration set as Active")
      setSnackbarOpen(true);
      setTimeout(fetchSingleCalibration, 300)
    } catch (err) {
      console.error("Error setting active calibration:", err);
    }
  };

  const handleRemoveActive = async () => {
    const apiUrl = `/api/workers/${pioreactorUnit}/active_calibrations/${device}`;
    const response = await fetch(apiUrl, { method: "DELETE" });
    if (!response.ok) {
      throw new Error("Failed to remove active calibration");
    }
    setSnackbarMessage("Calibration removed as Active")
    setSnackbarOpen(true);
    setTimeout(fetchSingleCalibration, 200);
  };

  if (loading) {
    return (
      <Box textAlign="center" mt={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (!calibration) {
    return (
      <Box mt={3}>
        <Typography variant="body1" color="error">
          Unable to find calibration data.
        </Typography>
      </Box>
    );
  }

  const {
    calibration_type,
    created_at,
    curve_data_,
    x,
    y,
    recorded_data,
    is_active,
  } = calibration;

  return (
    <Card>
      <CardContent sx={{p: 2}}>
          <Typography variant="h6" mb={2}>
            <MuiLink component={Link} to={`/calibrations/${pioreactorUnit}`} color="inherit" underline="hover" sx={{cursor: "pointer"}} > <PioreactorIcon sx={{verticalAlign: "middle", marginRight: "1px"}} /> {pioreactorUnit} </MuiLink>
              <NavigateNextIcon sx={{verticalAlign: "middle", marginRight: "3px"}}/>
            <MuiLink component={Link} to={`/calibrations/${pioreactorUnit}/${device}`} color="inherit" underline="hover" sx={{cursor: "pointer"}} >  {device} </MuiLink>
              <NavigateNextIcon sx={{verticalAlign: "middle", marginRight: "3px"}}/>
             {calibrationName}
          </Typography>

          <CalibrationChart calibrations={[calibration]} deviceName={device} unitsColorMap={unitsColorMap} highlightedModel={{pioreactorUnit: null, calbrationName: null}} title={`Calibration curve for ${calibrationName}`} />

          <Box sx={{px: 5, mt: 1}} >
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
                    <TableCell><strong>Active</strong></TableCell>
                    <TableCell>{is_active ? <><Chip size="small" label={"Active"} icon={<CheckCircleOutlineOutlinedIcon />} sx={{backgroundColor: "white"}}  /></>: ""}</TableCell>
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
                    <TableCell><strong>Calibrated on</strong></TableCell>
                    <TableCell>{dayjs(created_at).format('YYYY-MM-DD') }</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Fit polynomial</strong></TableCell>
                    <TableCell>
                      y={formatPolynomial(curve_data_)}
                    </TableCell>
                  </TableRow>
                  <TableRow >
                    <TableCell ><strong>Recorded data - {x}</strong></TableCell>
                    <TableCell sx={{maxWidth: "600px", whiteSpace: "pre-line", wordWrap: "break-word"}}>
                      <code>{JSON.stringify(recorded_data['x'])}</code><br/>
                    </TableCell>
                  </TableRow>
                  <TableRow >
                    <TableCell ><strong>Recorded data - {y}</strong></TableCell>
                    <TableCell sx={{maxWidth: "600px", whiteSpace: "pre-line", wordWrap: "break-word"}}>
                      <code>{JSON.stringify(recorded_data['y'])}</code><br/>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
          </Box>


          <Box mt={2}>
            <Button
              startIcon={<DoNotDisturbOnOutlinedIcon/>}
              variant="text"
              color="secondary"
              disabled={!is_active}
              onClick={handleRemoveActive}
              sx={{ textTransform: "none", float: "right", ml: 1 }}
            >
              Set inactive
            </Button>
            <Button
              startIcon={<CheckCircleOutlineOutlinedIcon />}
              variant="contained"
              color="primary"
              disabled={ is_active}
              onClick={handleSetActive}
              sx={{ textTransform: "none", float: "right", }}
            >
               Set active
            </Button>

          </Box>

          <Snackbar
            anchorOrigin={{vertical: "bottom", horizontal: "center"}}
            open={snackbarOpen}
            onClose={handleSnackbarClose}
            message={snackbarMessage}
            autoHideDuration={7000}
            resumeHideDuration={2000}
            key={"snackbar" + pioreactorUnit + device + calibrationName}
          />
      </CardContent>
  </Card>
  );
}


export default SingleCalibrationPage;
