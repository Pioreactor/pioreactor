import React, { useState, useEffect } from "react";

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
import AutomationForm, { hasAutomationFormErrors } from "./AutomationForm"


const defaultAutomations = {
  temperature: "thermostat",
  dosing: "chemostat",
  led: "light_dark_cycle"
}

const getDefaultSettingsForAutomation = (fields) => (
  Object.fromEntries((fields || []).map((field) => [field.key, field.default]))
)

const getPreferredAutomationName = (automationType, automations) => {
  const defaultAutomationName = defaultAutomations[automationType]
  if (defaultAutomationName && automations[defaultAutomationName]) {
    return defaultAutomationName
  }

  return Object.keys(automations)[0] || ""
}


function ChangeAutomationsDialog(props) {
  const automationType = props.automationType
  const automationTypeForDisplay = (automationType === "led") ? "LED" : automationType
  const [automationName, setAutomationName] = useState(defaultAutomations[automationType])
  const [algoSettings, setAlgoSettings] = useState({})
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
    if (!props.open || Object.keys(automations).length === 0) {
      return
    }

    const nextAutomationName = getPreferredAutomationName(automationType, automations)
    setAutomationName(nextAutomationName)
    setAlgoSettings({
      ...getDefaultSettingsForAutomation(automations[nextAutomationName]?.fields),
    })
  }, [props.open, automations, automationType])


  const removeEmpty = (obj) => {
    return Object.fromEntries(Object.entries(obj).filter(([_, v]) => v != null));
  }


  const handleClose = () => {
    props.onFinished();
  };

  const handleAlgoSelectionChange = (e) => {
    const nextAutomationName = e.target.value
    setAutomationName(nextAutomationName)
    setAlgoSettings({
        ...getDefaultSettingsForAutomation(automations[nextAutomationName]?.fields),
    })
  }

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
          Select {automationTypeForDisplay} automation
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
          <span style={{textTransform: "capitalize"}}>{automationTypeForDisplay}</span> automations control the {automationTypeForDisplay} in the Pioreactor's vial. Learn more about <a target="_blank" rel="noopener noreferrer" href={"https://docs.pioreactor.com/user-guide/" + automationTypeForDisplay + "-automations"}>{automationTypeForDisplay} automations</a>.
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
            {selectedAutomation && <AutomationForm fields={selectedAutomation.fields} description={selectedAutomation.description} updateParent={updateFromChild} name={automationName} settings={algoSettings}/>}

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
      message={`Starting ${automationTypeForDisplay} automation ${automations[automationName]?.display_name}.`}
      autoHideDuration={7000}
      key={"snackbar-change-" + automationType}
    />
    </React.Fragment>
  );}


export default ChangeAutomationsDialog;
