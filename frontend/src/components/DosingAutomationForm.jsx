import React from "react";
import TextField from "@mui/material/TextField";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import InputAdornment from "@mui/material/InputAdornment";
import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import UnderlineSpan from "./UnderlineSpan";
import MenuItem from "@mui/material/MenuItem";
import VialVolumePreview from "./VialVolumePreview";

function DosingAutomationForm(props) {
  const threshold = props.threshold;
  const safetyBufferMl = 1;
  const capacity = Number.isFinite(props.capacity) ? props.capacity : null;
  const volumeInputBounds = capacity !== null ? { min: 0, max: capacity } : { min: 0 };

  const computeWarning = (currentVolume, maxWorkingVolume) => {
    if (currentVolume != null && currentVolume >= threshold) {
      return `Current volume exceeds safe maximum of ${threshold} mL.`;
    }

    if (maxWorkingVolume != null && maxWorkingVolume >= threshold) {
      return `Max working volume exceeds safe maximum of ${threshold} mL.`;
    }

    if (
      maxWorkingVolume != null &&
      maxWorkingVolume >= threshold - safetyBufferMl &&
      maxWorkingVolume < threshold
    ) {
      return `Max working volume is very close to the ${threshold} mL safety ceiling.`;
    }

    return "";
  };

  const parseNumericInput = (event) => (
    Number.isNaN(event.target.valueAsNumber) ? null : event.target.valueAsNumber
  );

  const onSettingsChange = (id, value) => {
    props.updateParent({ [id]: value });
  };

  const warning = computeWarning(
    props.algoSettings.current_volume_ml,
    props.algoSettings.max_working_volume_ml,
  );

  const dilutionRate = (
    Number.isFinite(props.algoSettings.exchange_volume_ml) &&
    Number.isFinite(props.algoSettings.duration) &&
    Number.isFinite(props.algoSettings.max_working_volume_ml) &&
    props.algoSettings.duration > 0 &&
    props.algoSettings.max_working_volume_ml > 0
  )
    ? props.algoSettings.exchange_volume_ml * (60 / props.algoSettings.duration) / props.algoSettings.max_working_volume_ml
    : null;

  const listOfDisplayFields = props.fields.map(field => {
    const hasExplicitValue = Object.prototype.hasOwnProperty.call(props.algoSettings, field.key);
    const value = hasExplicitValue ? (props.algoSettings[field.key] ?? "") : (field.default ?? "");
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
            ? (e) => onSettingsChange(e.target.id, parseNumericInput(e))
            : (e) => onSettingsChange((e.target.id, e.target.value))
        }
        InputProps={inputProps}
        {...commonProps}
      />
    );
  });

  return (
    <Box sx={{ width: "100%", minWidth: { md: 520 } }}>
      <Typography variant="body1" sx={{ whiteSpace: "pre-line", mt: 3, mb: 1, padding: "6px 6px" }}>
        {props.description}
      </Typography>
      {props.name === "chemostat" && dilutionRate !== null &&
        <Typography variant="body1" sx={{ whiteSpace: "pre-line", mt: 0, mb: 1, padding: "6px 6px" }}>
          The current computed <UnderlineSpan title="Exchange volume * (60 / Time between dosing) / (Max working volume)">dilution rate</UnderlineSpan> is <code style={{backgroundColor: "rgba(0, 0, 0, 0.07)", padding: "1px 4px"}}>{dilutionRate.toFixed(2)} h⁻¹</code>.
        </Typography>
      }

      {listOfDisplayFields}


      <Divider sx={{ mt: 2, mb: 0 }} />

      <Box
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "flex-start",
          gap: 2,
          flexWrap: { xs: "wrap", md: "nowrap" },
        }}
      >
        <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", flex: 1, minWidth: 0, mt: 1 }}>
          <TextField
            type="number"
            size="small"
            autoComplete="off"
            id="current_volume_ml"
            label="Current volume"
            value={props.algoSettings.current_volume_ml ?? ""}
            InputProps={{
              endAdornment: <InputAdornment position="end">ml</InputAdornment>,
            }}
            inputProps={volumeInputBounds}
            variant="outlined"
            onChange={(e) => onSettingsChange(e.target.id, parseNumericInput(e))}
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
            inputProps={volumeInputBounds}
            variant="outlined"
            value={props.algoSettings.max_working_volume_ml ?? ""}
            onChange={(e) => onSettingsChange(e.target.id, parseNumericInput(e))}
            onKeyPress={(e) => { e.key === 'Enter' && e.preventDefault(); }}
            sx={{ mt: 3, mr: 1, mb: 0, width: "18ch" }}
          />
        </Box>

        <Box
          sx={{
            flex: { xs: "1 0 100%", md: "0 0 120px" },
            width: { xs: "100%", md: 120 },
            display: "flex",
            justifyContent: { xs: "center", md: "center" },
            alignItems: "flex-start",
          }}
        >
          <VialVolumePreview
            initialVolumeMl={props.algoSettings.current_volume_ml}
            maxWorkingVolumeMl={props.algoSettings.max_working_volume_ml}
            maxVolumeMl={capacity}
          />
        </Box>
      </Box>

      {warning && (
        <Alert severity="warning" sx={{ mt: 0 }}>
          {warning}
        </Alert>
      )}
    </Box>
  );
}

export default DosingAutomationForm;
