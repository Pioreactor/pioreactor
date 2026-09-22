import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";

export default function PageHeader({ title, actions, navigation, sx }) {
  return (
    <Box component="header" sx={{ mb: 2, ...sx }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          flexWrap: "wrap",
          // Reserve the same space even when there are no action buttons.
          minHeight: 44,
          mb: 1,
        }}
      >
        {navigation || (
          <Typography variant="h5" component="h1" sx={{ fontWeight: "bold", overflowWrap: "anywhere" }}>
            {title}
          </Typography>
        )}
        {actions && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
            {actions}
          </Box>
        )}
      </Box>
      <Divider />
    </Box>
  );
}
