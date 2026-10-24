import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export default function EmptyState({ children }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "10vh", py: 2, textAlign: "center" }}>
      <Typography variant="body2" component="p" color="text.secondary">
        {children}
      </Typography>
    </Box>
  );
}
