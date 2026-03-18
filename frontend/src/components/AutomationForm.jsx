import React from "react";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import Typography from "@mui/material/Typography";
import MenuItem from "@mui/material/MenuItem";


function AutomationForm(props){
  const onSettingsChange = (id, value) => {
    props.updateParent({ [id]: value });
  };

  const listOfDisplayFields = props.fields.map(field => {
    const value = props.settings[field.key] ?? field.default ?? "";
    const commonProps = {
      size: "small",
      autoComplete: "off",
      id: field.key,
      label: field.label,
      value,
      disabled: field.disabled,
      variant: "outlined",
      onKeyPress: (e) => { e.key === 'Enter' && e.preventDefault(); },
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
        InputProps={inputProps}
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
