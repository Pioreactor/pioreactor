import CloseIcon from "@mui/icons-material/Close";
import IconButton from "@mui/material/IconButton";

export default function DialogCloseButton({ onClick, disabled }) {
  return (
    <IconButton
      aria-label="Close"
      onClick={onClick}
      disabled={disabled}
      sx={{ position: "absolute", right: 8, top: 8, color: "text.secondary" }}
    >
      <CloseIcon />
    </IconButton>
  );
}
