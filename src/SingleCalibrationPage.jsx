import React, { useEffect, useState } from "react";
import { useParams,  Link as RouterLink } from "react-router-dom";
import { CircularProgress, Button, Typography, Box } from "@mui/material";
import {checkTaskCallback, colors, DefaultDict} from "./utilities"
import Link from '@mui/material/Link';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import CalibrationChart from "./components/CalibrationChart"; // Reuse from your previous code
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@mui/material";
import PioreactorIcon from "./components/PioreactorIcon"
import dayjs from 'dayjs';
import Snackbar from '@mui/material/Snackbar';


function SingleCalibrationPage(props) {

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  return (
      <>
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
      </Box>
      <SingleCalibrationPageCard />
      </>
  )
}


function SingleCalibrationPageCard() {
  const { pioreactor_unit, device, calibration_name } = useParams();
  const unitsColorMap = new DefaultDict(colors)

  const [calibration, setCalibration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activateLoading, setActivateLoading] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  useEffect(() => {
    // 1. Build your API URL with the route parameters
    // Example: /api/calibrations/<pioreactor_unit>/<device>/<calibration_name>
    const apiUrl = `/api/workers/${pioreactor_unit}/calibrations/${device}/${calibration_name}`;
    
    const fetchSingleCalibration = async () => {
      try {
        const response = await fetch(apiUrl);
        const firstResponse = await response.json();
        const data = await checkTaskCallback(firstResponse.result_url_path)
        setCalibration(data.result[pioreactor_unit]);
      } catch (err) {
        console.error("Failed to fetch calibration:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchSingleCalibration();
  }, [pioreactor_unit, device, calibration_name]);

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  const handleSetActive = async () => {
    const apiUrl = `/api/workers/${pioreactor_unit}/calibrations/${device}/${calibration_name}/active`;
    setActivateLoading(true);
    try {
      const response = await fetch(apiUrl, { method: "PATCH" });
      if (!response.ok) {
        throw new Error("Failed to activate calibration");
      }
      setSnackbarOpen(true);
    } catch (err) {
      console.error("Error setting active calibration:", err);
    } finally {
      setActivateLoading(false);
    }
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

  // 3. We'll show relevant data in a simple way
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
            <Link component={RouterLink} to={`/calibrations/${pioreactor_unit}`} color="inherit"  underline="hover" sx={{cursor: "pointer"}} > <PioreactorIcon sx={{verticalAlign: "middle", marginRight: "1px"}} /> {pioreactor_unit} </Link>
              <NavigateNextIcon sx={{verticalAlign: "middle", marginRight: "3px"}}/>
            <Link component={RouterLink} to={`/calibrations/${pioreactor_unit}/${device}`} color="inherit"  underline="hover" sx={{cursor: "pointer"}} > {device} </Link>
              <NavigateNextIcon sx={{verticalAlign: "middle", marginRight: "3px"}}/>
            {calibration_name}
          </Typography>

          <CalibrationChart calibrations={[calibration]} deviceName={device} unitsColorMap={unitsColorMap} highlightedModel={{pioreactorUnit: null, calbrationName: null}} title={`Calibration curve for ${calibration_name}`} />

          <Box sx={{px: 5, mt: 1}} >
            <Table size="small">
                <TableBody>
                  <TableRow>
                    <TableCell><strong>Pioreactor Unit</strong></TableCell>
                    <TableCell>{pioreactor_unit}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Device</strong></TableCell>
                    <TableCell>{device}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Calibration Type</strong></TableCell>
                    <TableCell>{calibration_type ?? "n/a"}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Calibrated on</strong></TableCell>
                    <TableCell>{dayjs(created_at).format('YYYY-MM-DD') }</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Active</strong></TableCell>
                    <TableCell>{is_active ? "Active" : ""}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Coefficients</strong></TableCell>
                    <TableCell>
                      {Array.isArray(curve_data_)
                        ? JSON.stringify(curve_data_)
                        : "n/a"}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
          </Box>


          {/* 5. Button to set active */}
          <Box mt={2}>
            <Button
              variant="contained"
              color="primary"
              disabled={activateLoading || is_active}
              onClick={handleSetActive}
              sx={{ textTransform: "none", float: "right", }}
            >
              {activateLoading ? "Activating..." : "Set active"}
            </Button>
          </Box>

          <Snackbar
            anchorOrigin={{vertical: "bottom", horizontal: "center"}}
            open={snackbarOpen}
            onClose={handleSnackbarClose}
            message={"Calibration is now active."}
            autoHideDuration={7000}
            resumeHideDuration={2000}
            key={"snackbar" + pioreactor_unit + device + calibration_name}
          />
      </CardContent>
  </Card>
  );
}


export default SingleCalibrationPage;
