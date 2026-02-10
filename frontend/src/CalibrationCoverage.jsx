import React from "react";
import { Link, useNavigate } from "react-router";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import TuneIcon from "@mui/icons-material/Tune";
import AddIcon from "@mui/icons-material/Add";
import PlaylistAddCheckIcon from '@mui/icons-material/PlaylistAddCheck';
import { fetchTaskResult } from "./utilities";
import PioreactorIcon from "./components/PioreactorIcon";
import {
  COVERAGE_STATUS,
  deriveCalibrationCoverageMatrix,
} from "./calibration_coverage_matrix";

function CoverageCell({ unit, device, cell, onNavigate }) {
  const hasLink = Boolean(cell?.detailPath);
  const hasCalibrationLink = Boolean(cell?.detailPath && cell?.calibrationName);
  const status = cell?.status;

  return (
    <TableCell align="left" sx={{ minWidth: 180 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minHeight: 32 }}>
        {status === COVERAGE_STATUS.ACTIVE && hasCalibrationLink && (
          <Chip
            size="small"
            icon={<TuneIcon />}
            label={cell.calibrationName}
            data-calibration-name={cell.calibrationName}
            clickable
            onClick={() => onNavigate(cell.detailPath)}
          />
        )}

        {status === COVERAGE_STATUS.AVAILABLE_NOT_ACTIVE && hasLink && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-start", width: "100%" }}>
            <Typography component="span" variant="body2" color="text.secondary">
              No active calibration
            </Typography>
          </Box>
        )}

        {status === COVERAGE_STATUS.MISSING && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-start", width: "100%" }}>
            <Typography component="span" variant="body2" color="text.secondary">
              Not calibrated
            </Typography>
          </Box>
        )}

        {status === COVERAGE_STATUS.UNKNOWN && (
          <Typography component="span" variant="caption" color="text.secondary">

          </Typography>
        )}
      </Box>
    </TableCell>
  );
}

function CalibrationCoverage(props) {
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [matrix, setMatrix] = React.useState({ units: [], devices: [], cells: {} });
  const navigate = useNavigate();

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  React.useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);

      try {
        const [activeResult, availableResult] = await Promise.all([
          fetchTaskResult("/api/workers/$broadcast/active_calibrations"),
          fetchTaskResult("/api/workers/$broadcast/calibrations"),
        ]);

        const activeByUnit = activeResult?.result || {};
        const availableByUnit = availableResult?.result || {};
        setMatrix(deriveCalibrationCoverageMatrix(availableByUnit, activeByUnit));
      } catch (err) {
        setError(err.message || "Failed to load calibration coverage matrix.");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  return (
    <React.Fragment>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1, alignItems: "center" }}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Calibration status
            </Box>
          </Typography>
          <Button
            color="primary"
            sx={{ textTransform: "none" }}
            onClick={() => navigate("/calibrations")}
            startIcon={<ArrowBackIcon />}
          >
            Back to calibrations
          </Button>
        </Box>
        <Divider sx={{ marginTop: "0px", marginBottom: "15px" }} />
      </Box>

      {loading && (
        <Box sx={{ textAlign: "center", marginTop: "2rem" }}>
          <CircularProgress />
        </Box>
      )}

      {!loading && error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      {!loading && !error && matrix.units.length === 0 && (
        <Typography color="text.secondary">
          No units were returned by the calibration APIs.
        </Typography>
      )}

      {!loading && !error && matrix.units.length > 0 && (
        <Paper sx={{ width: { xs: "100%", md: "100%" }, mx: "auto" }}>
          <TableContainer sx={{ maxHeight: "68vh" }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell
                    sx={{
                      minWidth: 180,
                      backgroundColor: (theme) => theme.palette.action.hover,
                    }}
                  >
                    Pioreactor
                  </TableCell>
                  {matrix.devices.map((device) => (
                    <TableCell key={device} align="left" sx={{ minWidth: 180 }}>
                      {device}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {matrix.units.map((unit) => (
                  <TableRow key={unit} hover>
                    <TableCell
                      component="th"
                      scope="row"
                      sx={{
                        backgroundColor: (theme) => theme.palette.action.hover,
                      }}
                    >
                      <Chip
                        size="small"
                        icon={<PioreactorIcon />}
                        label={unit}
                        data-pioreactor-unit={unit}
                        clickable
                        component={Link}
                        to={`/pioreactors/${unit}`}
                        sx={{ "& .MuiChip-label": { fontWeight: 600 } }}
                      />
                    </TableCell>
                    {matrix.devices.map((device) => (
                      <CoverageCell
                        key={`${unit}-${device}`}
                        unit={unit}
                        device={device}
                        cell={matrix.cells?.[unit]?.[device]}
                        onNavigate={(path) => navigate(path)}
                      />
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}
    </React.Fragment>
  );
}

export default CalibrationCoverage;
