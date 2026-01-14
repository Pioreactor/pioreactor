import React from "react";
import Alert from "@mui/material/Alert";

function RequirementsAlert(props) {
  const { sx, children, ...rest } = props;
  const baseSx = {
    backgroundColor: "grey.100",
    borderColor: "grey.300",
    borderStyle: "solid",
    borderWidth: "1px",
    color: "grey.700",
    mt: 1,
    mb: 1,
    "& .MuiAlert-icon": {
      color: "grey.600",
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
