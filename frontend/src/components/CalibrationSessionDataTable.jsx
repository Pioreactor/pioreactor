import React from "react";
import Checkbox from "@mui/material/Checkbox";
import FormLabel from "@mui/material/FormLabel";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import { ZebraTableRow } from "./TableRows";


export function dataTableCellError(column, rawValue) {
  if (rawValue === "" || rawValue === null || rawValue === undefined) {
    return "Required";
  }
  const numeric = Number(rawValue);
  if (!Number.isFinite(numeric)) {
    return "Enter a number";
  }
  if (typeof column.minimum === "number" && numeric < column.minimum) {
    return `Must be ≥ ${column.minimum}`;
  }
  return "";
}


export function stepHasInvalidDataTable(step, values) {
  return (step?.fields || []).some((field) => {
    if (field.field_type !== "data_table") {
      return false;
    }
    const editableColumns = (field.columns || []).filter((column) => column.editable);
    const rows = Array.isArray(values[field.name]) ? values[field.name] : [];
    return rows.some((row) => editableColumns.some((column) => dataTableCellError(column, row[column.key])));
  });
}


function rowLabel(columns, row, rowIndex) {
  const firstColumn = columns[0];
  const value = firstColumn ? row[firstColumn.key] : null;
  return firstColumn ? `${firstColumn.label} ${value ?? rowIndex + 1}` : `Row ${rowIndex + 1}`;
}


// Rows carry an `include` flag when the step lets the user leave rows out of the fit.
export default function CalibrationSessionDataTable({ field, rows, onChange }) {
  const columns = Array.isArray(field.columns) ? field.columns : [];
  const tableRows = Array.isArray(rows) ? rows : [];
  const showInclude = tableRows.some((row) => Object.prototype.hasOwnProperty.call(row, "include"));

  const updateRow = (rowIndex, changes) => {
    onChange(tableRows.map((row, index) => (index === rowIndex ? { ...row, ...changes } : row)));
  };

  return (
    <>
      <FormLabel component="div" id={`${field.name}-label`} sx={{ mb: 0.5 }}>
        {field.label}
      </FormLabel>
      <TableContainer sx={{ overflowX: "auto", mb: 2 }}>
        <Table size="small" aria-labelledby={`${field.name}-label`}>
          <TableHead>
            <TableRow>
              {showInclude && <TableCell sx={{ whiteSpace: "nowrap" }}>Use in fit</TableCell>}
              {columns.map((column, columnIndex) => (
                <TableCell key={column.key} align={columnIndex === 0 ? "left" : "right"}>
                  {column.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {tableRows.map((row, rowIndex) => {
              const label = rowLabel(columns, row, rowIndex);
              const excluded = showInclude && row.include === false;
              return (
                <ZebraTableRow key={rowIndex}>
                  {showInclude && (
                    <TableCell padding="checkbox">
                      <Checkbox
                        size="small"
                        checked={row.include !== false}
                        onChange={(event) => updateRow(rowIndex, { include: event.target.checked })}
                        slotProps={{ input: { "aria-label": `Use ${label} in fit` } }}
                      />
                    </TableCell>
                  )}
                  {columns.map((column, columnIndex) => {
                    const value = row[column.key];
                    if (!column.editable) {
                      return (
                        <TableCell
                          key={column.key}
                          align={columnIndex === 0 ? "left" : "right"}
                          sx={{ color: excluded ? "text.disabled" : undefined }}
                        >
                          {value ?? "—"}
                        </TableCell>
                      );
                    }
                    const error = dataTableCellError(column, value);
                    return (
                      <TableCell key={column.key} align="right" sx={{ py: 0.5 }}>
                        <TextField
                          size="small"
                          variant="standard"
                          value={value ?? ""}
                          error={Boolean(error)}
                          helperText={error || undefined}
                          onChange={(event) => updateRow(rowIndex, { [column.key]: event.target.value })}
                          slotProps={{
                            htmlInput: {
                              inputMode: "decimal",
                              "aria-label": `${column.label} for ${label}`,
                              style: { textAlign: "right" },
                            },
                          }}
                          sx={{ maxWidth: 110 }}
                        />
                      </TableCell>
                    );
                  })}
                </ZebraTableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
