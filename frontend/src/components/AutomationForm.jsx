import React, {useEffect } from "react";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import Typography from "@mui/material/Typography";


function AutomationForm(props){
  const defaults = Object.assign({}, ...props.fields.map(field => ({[field.key]: field.default})))
  useEffect(() => {
    props.updateParent(defaults)
  }, [props.fields])


  const onSettingsChange = (id, value) => {
    props.updateParent({ [id]: value });
  };

  const listOfDisplayFields = props.fields.map(field => {
    const commonProps = {
      size: "small",
      autoComplete: "off",
      id: field.key,
      label: field.label,
      defaultValue: field.default,
      disabled: field.disabled,
      InputProps: {
        endAdornment: <InputAdornment position="end">{field.unit}</InputAdornment>,
      },
      variant: "outlined",
      onKeyPress: (e) => { e.key === 'Enter' && e.preventDefault(); },
      sx: { mt: 3, mr: 2, mb: 0, width: "18ch" },
    };

    return <TextField
      key={field.key + props.name}
      type={field.type === 'numeric' ? "number" : "text"}
      onChange={field.type === 'numeric' ? (e) => onSettingsChange(e.target.id, e.target.valueAsNumber || null) : (e) => onSettingsChange((e.target.id, e.target.value))}
      {...commonProps} />;
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
