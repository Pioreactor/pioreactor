import { Badge } from "@mui/material";
import PioreactorIcon from "./PioreactorIcon"; // Adjust the import path as needed

const PioreactorIconWithModel = ({ badgeContent, color }) => {

  return (
    <Badge
      anchorOrigin={{
        vertical: "top",
        horizontal: "right",
      }}
      sx={{
        display: { xs: "none", sm: "none", md: "inline" },
        marginRight: "8px",
        "& .MuiBadge-badge": {
          color: "inherit",
          backgroundColor: "rgba(235,235,235)",
          padding: "0px",
          fontSize: "10px",
          fontWeight: "900",
          height: "16px",
          minWidth: "16px",
          top: "10%",
          right: "20%",
        },
      }}
      max={9999}
      badgeContent={badgeContent}
      overlap="circular"
      color="primary"
    >
      <PioreactorIcon
        style={{ verticalAlign: "middle" }}
        sx={{ display: { xs: "none", sm: "none", md: "inline" }, color: color}}
      />
    </Badge>
  );
};

export default PioreactorIconWithModel;
