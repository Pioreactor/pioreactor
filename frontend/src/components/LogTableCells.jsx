import TableCell from "@mui/material/TableCell";
import { styled } from "@mui/material/styles";
import { ERROR_COLOR, WARNING_COLOR, NOTICE_COLOR } from "../utils/color";
import { uiColors } from "../theme/colors";

export const LogTableCell = styled(TableCell, {
  shouldForwardProp: (prop) => prop !== "level",
})(({ level }) => ({
  padding: "6px 6px 6px 10px",
  fontSize: 13,
  backgroundColor:
    level === "ERROR" ? ERROR_COLOR :
    level === "WARNING" ? WARNING_COLOR :
    level === "NOTICE" ? NOTICE_COLOR : "inherit",
  whiteSpace: "normal",
  "&.MuiTableCell-head": { backgroundColor: uiColors.surface },
}));

export const LogTimeTableCell = styled(LogTableCell)({ whiteSpace: "pre" });
