import React from "react";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import Typography from "@mui/material/Typography";
import MenuItem from "@mui/material/MenuItem";

export function getAutomationFieldError(field, settings) {
  if (field.disabled || !field.required) {
    return "";
  }

  const hasExplicitValue = Object.prototype.hasOwnProperty.call(settings, field.key);
  const value = hasExplicitValue ? settings[field.key] : field.default;

  if (value == null || value === "" || Number.isNaN(value)) {
    return "Required";
  }

  return "";
}

export function hasAutomationFormErrors(fields, settings) {
  return (fields || []).some((field) => getAutomationFieldError(field, settings));
}


function AutomationForm(props){
  const [touchedFields, setTouchedFields] = React.useState({});

  React.useEffect(() => {
    setTouchedFields({});
  }, [props.name]);

  const onSettingsChange = (id, value) => {
    setTouchedFields((previous) => ({ ...previous, [id]: true }));
    props.updateParent({ [id]: value });
  };

  const markFieldTouched = (id) => {
    setTouchedFields((previous) => ({ ...previous, [id]: true }));
  };

  const listOfDisplayFields = props.fields.map(field => {
    const hasExplicitValue = Object.prototype.hasOwnProperty.call(props.settings, field.key);
    const value = hasExplicitValue ? (props.settings[field.key] ?? "") : (field.default ?? "");
    const error = touchedFields[field.key] ? getAutomationFieldError(field, props.settings) : "";
    const commonProps = {
      size: "small",
      autoComplete: "off",
      id: field.key,
      label: field.label,
      value,
      required: field.required,
      error: Boolean(error),
      helperText: error,
      disabled: field.disabled,
      variant: "outlined",
      onKeyPress: (e) => { e.key === 'Enter' && e.preventDefault(); },
      onBlur: (e) => markFieldTouched(e.target.id),
      sx: { mt: 3, mr: 2, mb: 0, width: "18ch" },
    };

    if (field.type === "select") {
      return (
        <TextField
          key={field.key + props.name}
          select
          onChange={(e) => onSettingsChange(e.target.id, e.target.value)}
          {...commonProps}
        >
          {(field.options || []).map((option) => (
            <MenuItem key={`${field.key}-${option}`} value={option}>
              {option}
            </MenuItem>
          ))}
        </TextField>
      );
    }

    const inputProps = field.unit ? {
      endAdornment: <InputAdornment position="end">{field.unit}</InputAdornment>,
    } : undefined;

    return (
      <TextField
        key={field.key + props.name}
        type={field.type === "numeric" ? "number" : "text"}
        onChange={
          field.type === "numeric"
            ? (e) => onSettingsChange(e.target.id, Number.isNaN(e.target.valueAsNumber) ? null : e.target.valueAsNumber)
            : (e) => onSettingsChange(e.target.id, e.target.value)
        }
        slotProps={{ input: inputProps }}
        {...commonProps}
      />
    );
  });


  return (
    <div>
      <Typography variant="body1"
        sx={{
          whiteSpace: "pre-line",
          mt: 3, mb: 1,
          padding: "6px 6px",
        }}> {props.description} </Typography>
      {listOfDisplayFields}

    </div>
)}


export default AutomationForm;
