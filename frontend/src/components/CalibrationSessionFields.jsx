import React from "react";
import FormControl from "@mui/material/FormControl";
import FormLabel from "@mui/material/FormLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";


function shouldHideField(step, field) {
  if (field.field_type !== "bool") {
    return false;
  }
  return field.name === "confirmed" || (step.step_type === "action" && field.name === "confirm");
}


export default function CalibrationSessionFields({ step, values, onFieldChange }) {
  if (!Array.isArray(step?.fields) || step.fields.length === 0) {
    return null;
  }

  return (
    <Stack spacing={1}>
      {step.fields.map((field) => {
        if (shouldHideField(step, field)) {
          return null;
        }
        if (field.field_type === "bool") {
          const options = field.options?.length > 0 ? field.options : ["yes", "no"];
          return (
            <FormControl key={field.name} fullWidth size="small">
              <FormLabel>{field.label}</FormLabel>
              <Select
                value={values[field.name] ?? "no"}
                onChange={(event) => onFieldChange(field.name, event.target.value)}
              >
                {options.map((option) => (
                  <MenuItem key={option} value={option}>
                    {option}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          );
        }
        if (field.field_type === "choice") {
          return (
            <FormControl key={field.name} fullWidth size="small">
              <FormLabel>{field.label}</FormLabel>
              <Select
                value={values[field.name] ?? ""}
                onChange={(event) => onFieldChange(field.name, event.target.value)}
              >
                {(field.options || []).map((option) => (
                  <MenuItem key={option} value={option}>
                    {option}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          );
        }

        const helperText =
          field.field_type === "float_list" ? "Comma-separated values" : field.help_text;
        return (
          <TextField
            key={field.name}
            fullWidth
            size="small"
            label={field.label}
            value={values[field.name] ?? ""}
            helperText={helperText || " "}
            onChange={(event) => onFieldChange(field.name, event.target.value)}
          />
        );
      })}
    </Stack>
  );
}
