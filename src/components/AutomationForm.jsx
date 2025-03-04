import React, {useEffect } from "react";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";


function AutomationForm(props){
  const defaults = Object.assign({}, ...props.fields.map(field => ({[field.key]: field.default})))
  useEffect(() => {
    props.updateParent(defaults)
  }, [props.fields])


  const onSettingsChange = (e) => {
    props.updateParent({[e.target.id]: e.target.value})
  }


  var listOfDisplayFields = props.fields.map(field => {
      switch (field.type) {
        case 'numeric':
          return <TextField
            type="number"
            size="small"
            autoComplete={"off"}
            id={field.key}
            key={field.key + props.name}
            label={field.label}
            defaultValue={field.default}
            disabled={field.disabled}
            InputProps={{
              endAdornment: <InputAdornment position="end">{field.unit}</InputAdornment>,
            }}
            variant="outlined"
            onChange={onSettingsChange}
            onKeyPress={(e) => {e.key === 'Enter' && e.preventDefault();}}
            sx={{
              mt: 3,
              mr: 2,
              mb: 0,
              width: "18ch"
            }}
          />
        case 'string':
        default:
          return <TextField
            size="small"
            autoComplete={"off"}
            id={field.key}
            key={field.key + props.name}
            label={field.label}
            defaultValue={field.default}
            disabled={field.disabled}
            InputProps={{
              endAdornment: <InputAdornment position="end">{field.unit}</InputAdornment>,
            }}
            variant="outlined"
            onChange={onSettingsChange}
            onKeyPress={(e) => {e.key === 'Enter' && e.preventDefault();}}
            sx={{
              mt: 3,
              mr: 2,
              mb: 0,
              width: "18ch"
            }}
          />
      }
    }
  )

  return (
    <div>
      <p style={{whiteSpace: "pre-line"}}> {props.description} </p>
      {listOfDisplayFields}
    </div>
)}


export default AutomationForm;