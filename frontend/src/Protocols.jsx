import React from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";

function Protocols(props) {
  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  return (
    <React.Fragment>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2" sx={{ fontWeight: "bold" }}>
          Protocols
        </Typography>
      </Box>
      <Card>
        <CardContent>
          <Typography variant="body1" gutterBottom>
            Protocol library and execution tools will live here.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            This is a placeholder skeleton page.
          </Typography>
        </CardContent>
      </Card>
    </React.Fragment>
  );
}

export default Protocols;
