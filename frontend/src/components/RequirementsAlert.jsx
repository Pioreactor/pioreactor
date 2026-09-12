import React from "react";
import { uiColors } from "../theme/colors";
import Alert from "@mui/material/Alert";

function RequirementsAlert(props) {
  const { sx, children, ...rest } = props;
  const baseSx = {
    backgroundColor: uiColors.subtleBackground,
    borderColor: uiColors.border,
    borderStyle: "solid",
    borderWidth: "1px",
    color: uiColors.textSecondary,
    mt: 1,
    mb: 1,
    "& .MuiAlert-icon": {
      color: uiColors.textSecondary,
    },
  };
  const combinedSx = Array.isArray(sx) ? [baseSx, ...sx] : [baseSx, sx];

  return (
    <Alert severity="info"  sx={combinedSx} {...rest}>
      {children}
    </Alert>
  );
}

export default RequirementsAlert;
