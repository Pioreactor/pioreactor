import React, { useEffect, useState } from "react";
import TextField from "@mui/material/TextField";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import InputAdornment from "@mui/material/InputAdornment";
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import IconButton from '@mui/material/IconButton';
import Alert from "@mui/material/Alert";
import UnderlineSpan from "./UnderlineSpan";

function DosingAutomationForm(props) {
  const threshold = props.threshold;
  const [warning, setWarning] = useState("");

  const defaults = Object.assign({}, ...props.fields.map(field => ({ [field.key]: field.default })));
  useEffect(() => {
    props.updateParent(defaults);
  }, [props.fields]);

  const checkForWarnings = (id, value) => {
    if (id === "initial_volume_ml" && value > threshold) {
      setWarning(`Initial volume exceeds safe maximum of ${threshold} mL.`);
    } else if (id === "max_working_volume_ml" && value > threshold) {
      setWarning(`Max working volume exceeds safe maximum of ${threshold} mL.`);
    } else {
      setWarning(""); // clear warning
    }
  };

  const onSettingsChange = (id, value) => {
    checkForWarnings(id, value);
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
      <Typography variant="body1" sx={{ whiteSpace: "pre-line", mt: 3, mb: 1, padding: "6px 6px" }}>
        {props.description}
      </Typography>
      {props.name === "chemostat" &&
        <Typography variant="body1" sx={{ whiteSpace: "pre-line", mt: 0, mb: 1, padding: "6px 6px" }}>
          The current computed <UnderlineSpan title="Exchange volume * (60 / Time between dosing) / (Max working volume)">dilution rate</UnderlineSpan> is <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{(props.algoSettings.exchange_volume_ml * (60/props.algoSettings.duration) / props.algoSettings.max_working_volume_ml).toFixed(2)} h⁻¹</code>.
        </Typography>
      }

      {listOfDisplayFields}


      <Divider sx={{ mt: 2, mb: 0 }} />

      <TextField
        type="number"
        size="small"
        autoComplete="off"
        id="initial_volume_ml"
        label="Initial volume"
        defaultValue={props.liquidVolume}
        InputProps={{
          endAdornment: <InputAdornment position="end">ml</InputAdornment>,
        }}
        variant="outlined"
        onChange={(e) => onSettingsChange(e.target.id, e.target.valueAsNumber || null)}
        onKeyPress={(e) => { e.key === 'Enter' && e.preventDefault(); }}
        sx={{ mt: 3, mr: 2, mb: 0, width: "18ch" }}
      />

      <TextField
        type="number"
        size="small"
        autoComplete="off"
        id="max_working_volume_ml"
        label={<UnderlineSpan title="Determined by the height of your waste/efflux tube.">Max working volume</UnderlineSpan>}
        InputProps={{
          endAdornment: <InputAdornment position="end">ml</InputAdornment>,
        }}
        variant="outlined"
        defaultValue={props.maxVolume}
        onChange={(e) => onSettingsChange(e.target.id, e.target.valueAsNumber || null)}
        onKeyPress={(e) => { e.key === 'Enter' && e.preventDefault(); }}
        sx={{ mt: 3, mr: 1, mb: 0, width: "18ch" }}
      />

      <IconButton
        sx={{ mt: 3 }}
        aria-label="Learn more about volume parameters"
        target="_blank"
        rel="noopener noreferrer"
        href="https://docs.pioreactor.com/user-guide/dosing-automations#volume-parameters"
      >
        <HelpOutlineIcon sx={{ fontSize: 17, verticalAlign: "middle", ml: 0 }} />
      </IconButton>

      {warning && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          {warning}
        </Alert>
      )}
    </div>
  );
}

export default DosingAutomationForm;
