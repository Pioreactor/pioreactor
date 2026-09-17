import TableRow from "@mui/material/TableRow";
import { styled } from "@mui/material/styles";
import { useNavigate } from "react-router";
import { uiColors } from "../theme/colors";

export const ZebraTableRow = styled(TableRow)(() => ({
  "&:nth-of-type(odd)": { backgroundColor: uiColors.stripe },
  "&:nth-of-type(even)": { backgroundColor: uiColors.surface },
}));

export function NavigableTableRow({ to, children, ...props }) {
  const navigate = useNavigate();

  const isRowTarget = (event) =>
    !event.target.closest("a, button, input, select, textarea, [role='button']");

  return (
    <TableRow
      {...props}
      tabIndex={0}
      sx={{
        cursor: "pointer",
        backgroundColor: uiColors.surface,
        "&:hover": { backgroundColor: uiColors.stripe },
        "&:focus-visible": {
          outline: "2px solid",
          outlineColor: "primary.main",
          outlineOffset: "-2px",
        },
      }}
      onClick={(event) => {
        if (isRowTarget(event)) navigate(to);
      }}
      onKeyDown={(event) => {
        if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          navigate(to);
        }
      }}
    >
      {children}
    </TableRow>
  );
}
