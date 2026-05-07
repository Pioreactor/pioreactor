import React, { useState, useEffect, useRef } from "react";

import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import DialogTitle from '@mui/material/DialogTitle';
import FormLabel from '@mui/material/FormLabel';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import Select from '@mui/material/Select';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';
import Snackbar from './Snackbar';
import {getAutomationDescriptors, runPioreactorJob} from "../utils/jobs"

import PioreactorIcon from "./PioreactorIcon"
import DosingAutomationForm from "./DosingAutomationForm"
import { hasAutomationFormErrors } from "./AutomationForm"

const getDefaultDosingSettings = (fields) => (
  Object.fromEntries(
    (fields || [])
      .filter((field) => field.key !== "current_volume_ml" && field.key !== "efflux_tube_volume_ml")
      .map((field) => [field.key, field.default])
  )
)

const getPreferredDosingAutomationName = (automations) => {
  if (automations.chemostat) {
    return "chemostat"
  }

  return Object.keys(automations)[0] || ""
}


function ChangeDosingAutomationsDialog(props) {
  const automationType = "dosing"
  const initializationCompletedForOpenRef = useRef(false);
  const [automationName, setAutomationName] = useState("chemostat")
  const [algoSettings, setAlgoSettings] = useState({
    efflux_tube_volume_ml: props.maxVolume,
    current_volume_ml: props.liquidVolume,
  })
  const [automations, setAutomations] = useState({})
  const [isLoading, setIsLoading] = useState(true)
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const selectedAutomation = automations[automationName]
  const hasValidationErrors = hasAutomationFormErrors(selectedAutomation?.fields, algoSettings)

  useEffect(() => {
    setIsLoading(true)
    getAutomationDescriptors(props.unit, automationType)
      .then((listOfAuto) => {
        setAutomations(Object.assign({}, ...listOfAuto.map(auto => ({ [auto.automation_name]: auto}))))
        setIsLoading(false)
      })
      .catch((_error) => {
        setIsLoading(false)
      })
  }, [automationType, props.unit])

  useEffect(() => {
    if (!props.open) {
      initializationCompletedForOpenRef.current = false;
      return;
    }

    if (initializationCompletedForOpenRef.current || Object.keys(automations).length === 0) {
      return;
    }

    const nextAutomationName = getPreferredDosingAutomationName(automations);
    setAutomationName(nextAutomationName);
    setAlgoSettings({
      ...getDefaultDosingSettings(automations[nextAutomationName]?.fields),
      efflux_tube_volume_ml: props.maxVolume,
      current_volume_ml: props.liquidVolume,
    });
    initializationCompletedForOpenRef.current = true;
  }, [props.liquidVolume, props.maxVolume, props.open, automations]);


  const removeEmpty = (obj) => {
    return Object.fromEntries(Object.entries(obj).filter(([_, v]) => v != null));
  }


  const handleClose = () => {
    props.onFinished();
  };

  const handleAlgoSelectionChange = (e) => {
    const newAlgoName = e.target.value;
    setAutomationName(newAlgoName);

    setAlgoSettings({
      ...getDefaultDosingSettings(automations[newAlgoName]?.fields),
      efflux_tube_volume_ml: algoSettings.efflux_tube_volume_ml ?? props.maxVolume,
      current_volume_ml: algoSettings.current_volume_ml ?? props.liquidVolume,
    });
  };

  const updateFromChild = (setting) => {
    setAlgoSettings(prevState => ({...prevState, ...setting}))
  }

  const startJob = (event) => {
    event.preventDefault()
    if (hasValidationErrors) {
      return
    }

    runPioreactorJob(
      props.unit,
      props.experiment,
      `${automationType}_automation`,
      [],
      {"automation_name": automationName, ...removeEmpty(algoSettings)},
      props.configOverrides || []
    )
    setOpenSnackbar(true);
    handleClose()
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  return (
    <React.Fragment>
    <Dialog open={props.open} onClose={handleClose} aria-labelledby="form-dialog-title" slotProps={{ paper: { sx: { height: "100%" } } }}>
      <DialogTitle>
        <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)"}}>
          <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/>
            {(props.unit === "$broadcast")
              ? <b>All active and assigned Pioreactors</b>
              :((props.title || props.label)
                  ? ` ${props.label} / ${props.unit}`
                  : `${props.unit}`
              )
            }
        </Typography>
        <Typography sx={{fontSize: 20, color: "rgba(0, 0, 0, 0.87)"}}>
          Select {automationType} automation
        </Typography>
        <IconButton
          aria-label="close"
          onClick={handleClose}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[500],
          }}
          size="large">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" component="span" gutterBottom>
          <span style={{textTransform: "capitalize"}}>{automationType}</span> automations control the {automationType} in the Pioreactor's vial. Learn more about <a target="_blank" rel="noopener noreferrer" href={"https://docs.pioreactor.com/user-guide/" + automationType + "-automations"}>{automationType} automations</a>.
        </Typography>

        {!isLoading && <form>
          <FormControl component="fieldset" sx={{mt: 2}}>
          <FormLabel component="legend">Automation</FormLabel>
            <Select
              variant="standard"
              value={automationName}
              onChange={handleAlgoSelectionChange}
              style={{maxWidth: "270px"}}
            >
              {Object.keys(automations).map((key) => <MenuItem id={key} value={key} key={"change-io" + key}>{automations[key].display_name}</MenuItem>)}

            </Select>
            {selectedAutomation &&
              <DosingAutomationForm
                fields={selectedAutomation.fields}
                description={selectedAutomation.description}
                updateParent={updateFromChild}
                name={automationName}
                maxVolume={props.maxVolume}
                liquidVolume={props.liquidVolume}
                capacity={props.capacity}
                threshold={props.threshold}
                algoSettings={algoSettings}
              />

            }

          </FormControl>
        </form>}
        {isLoading && <p>Loading...</p>}
      </DialogContent>
      <DialogActions>
        <Button
          color="secondary"
          onClick={handleClose}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          variant="contained"
          color="primary"
          onClick={startJob}
          disabled={isLoading || hasValidationErrors}
        >
          Start
        </Button>
      </DialogActions>
    </Dialog>
    <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={openSnackbar}
      onClose={handleSnackbarClose}
      message={`Starting ${automationType} automation ${automations[automationName]?.display_name}.`}
      autoHideDuration={7000}
      key={"snackbar-change-" + automationType}
    />
    </React.Fragment>
  );}


export default ChangeDosingAutomationsDialog;
