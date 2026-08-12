import React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TuneIcon from "@mui/icons-material/Tune";
import { Link } from "react-router";
import EstimatorIcon from "./EstimatorIcon";


export default function CalibrationSessionResultLinks({ result, protocolTargetDevice, unit }) {
  if (!result || !unit) {
    return null;
  }

  const completedCalibrationDevice =
    result.calibration?.device || result.device || protocolTargetDevice;
  const completedEstimatorDevice =
    result.device || result.calibration?.device || protocolTargetDevice;

  return (
    <>
      {Array.isArray(result.calibrations) && (
        <Stack direction="column" spacing={0} sx={{ flexWrap: "wrap" }}>
          {result.calibrations.map((calibration) => (
            <Box key={`${calibration.device}-${calibration.calibration_name}`}>
              View{" "}
              <Chip
                size="small"
                icon={<TuneIcon />}
                clickable
                component={Link}
                sx={{ my: 1 }}
                to={`/calibrations/${unit}/${calibration.device}/${calibration.calibration_name}`}
                label={calibration.calibration_name}
              />
            </Box>
          ))}
        </Stack>
      )}
      {result.calibration?.calibration_name &&
        !result.calibrations &&
        completedCalibrationDevice && (
          <Chip
            size="small"
            icon={<TuneIcon />}
            clickable
            component={Link}
            to={`/calibrations/${unit}/${completedCalibrationDevice}/${result.calibration.calibration_name}`}
            label={result.calibration.calibration_name}
          />
        )}
      {result.estimator_name && completedEstimatorDevice && (
        <Box sx={{ mt: 1 }}>
          View{" "}
          <Chip
            size="small"
            icon={<EstimatorIcon />}
            clickable
            component={Link}
            sx={{ my: 1 }}
            to={`/estimators/${unit}/${completedEstimatorDevice}/${result.estimator_name}`}
            label={result.estimator_name}
          />
        </Box>
      )}
    </>
  );
}
