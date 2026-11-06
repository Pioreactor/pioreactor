import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";

export default function LoadingState({ label = "Loading" }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "10vh", py: 2 }}>
      <CircularProgress size={33} aria-label={label} />
    </Box>
  );
}
