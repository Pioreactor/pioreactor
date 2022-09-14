import React, { useState, useEffect } from "react";

import { Client, Message } from "paho-mqtt";
import { makeStyles } from "@mui/styles";

import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import DialogTitle from '@mui/material/DialogTitle';
import FormLabel from '@mui/material/FormLabel';
import FormControl from '@mui/material/FormControl';
import Select from '@mui/material/Select';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';
import Snackbar from "@mui/material/Snackbar";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";

import PioreactorIcon from "./PioreactorIcon"
import AutomationForm from "./AutomationForm"

const useStyles = makeStyles((theme) => ({
  formControl: {
    marginTop: theme.spacing(2)
  },
  unitTitle: {
    fontSize: 17,
    color: "rgba(0, 0, 0, 0.87)",
  },
  unitTitleDialog :{
    fontSize: 20,
    color: "rgba(0, 0, 0, 0.87)",
  },
  suptitle: {
    fontSize: "13px",
    color: "rgba(0, 0, 0, 0.60)",
  },
}));


const defaultAutomations = {
  temperature: "stable",
  dosing: "chemostat",
  led: "light_dark_cycle"
}


function ChangeAutomationsDialog(props) {
  const classes = useStyles();
  const automationType = props.automationType
  const automationTypeForDisplay = (automationType === "led") ? "LED" : automationType
  const [automationName, setAutomationName] = useState(defaultAutomations[automationType])
  const [algoSettings, setAlgoSettings] = useState({
    skip_first_run: 0 //TODO: this should be not included if !props.no_skip_first_run
  })
  const [client, setClient] = useState(null)
  const [automations, setAutomations] = useState({})
  const [openSnackbar, setOpenSnackbar] = useState(false);


  useEffect(() => {
    function fetchAutomations() {
      fetch("/api/contrib/automations/" + automationType)
        .then((response) => {
            if (response.ok) {
              return response.json();
            } else {
              throw new Error('Something went wrong');
            }
          })
        .then((listOfAuto) => {
          setAutomations(Object.assign({}, ...listOfAuto.map(auto => ({ [auto.automation_name]: auto}))))
        })
        .catch((error) => {})
    }
    fetchAutomations();
  }, [automationType])


  useEffect(() => {
    // MQTT - client ids should be unique
    if (!props.config['cluster.topology']){
      return
    }

    var client
    if (props.config.remote && props.config.remote.ws_url) {
      client = new Client(
        `ws://${props.config.remote.ws_url}/`,
        "webui_ButtonChangeDialog" + Math.random()
      )}
    else {
      client = new Client(
        `${props.config['cluster.topology']['leader_address']}`, 9001,
        "webui_ButtonChangeDialog" + Math.random()
      );
    }

    client.connect({timeout: 180});
    setClient(client)
  },[props.config])


  const handleClose = () => {
    props.onFinished();
  };

  const handleSkipFirstRunChange = (e) => {
    setAlgoSettings({...algoSettings, skip_first_run: e.target.checked ? 1 : 0})
  }

  const handleAlgoSelectionChange = (e) => {
    setAutomationName(e.target.value)
    setAlgoSettings({
        ...( !props.no_skip_first_run && {skip_first_run: algoSettings.skip_first_run})
    })
  }

  const updateFromChild = (setting) => {
    setAlgoSettings(prevState => ({...prevState, ...setting}))
  }

  const startJob = (event) => {
    event.preventDefault()
    fetch(`/run/${automationType}_control/${props.unit}`, {
      method: "POST",
      body: JSON.stringify({"automation_name": automationName, ...algoSettings}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    setOpenSnackbar(true);
    handleClose()
  }

  const changeAutomation = (event) => {
    event.preventDefault()
    var message = new Message(JSON.stringify({"automation_name": automationName, "type": automationType, "args": algoSettings}),);
    message.destinationName = [
      "pioreactor",
      props.unit,
      props.experiment,
      `${automationType}_control`,
      "automation",
      "set",
    ].join("/");
    message.qos = 2;
    try{
      client.publish(message);
      setOpenSnackbar(true);
    }
    catch (e){
      console.log(e)
    }
    handleClose();
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  return (
    <React.Fragment>
    <Dialog open={props.open} onClose={handleClose} aria-labelledby="form-dialog-title" PaperProps={{style: {height: "100%"}}}>
      <DialogTitle>
        <Typography className={classes.suptitle}>
          <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/>
            {(props.unit === "$broadcast")
              ? <b>All active Pioreactors</b>
              :((props.title || props.label)
                  ? ` ${props.label} / ${props.unit}`
                  : `${props.unit}`
              )
            }
        </Typography>
        <Typography className={classes.unitTitleDialog}>
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
        <Typography variant="body2" component="p" gutterBottom>
          <span style={{textTransform: "capitalize"}}>{automationTypeForDisplay}</span> automations control the {automationTypeForDisplay} in the Pioreactor's vial. Learn more about <a target="_blank" rel="noopener noreferrer" href={"https://docs.pioreactor.com/user-guide/" + automationTypeForDisplay + "-automations"}>{automationTypeForDisplay} automations</a>.
        </Typography>

        <form>
          <FormControl component="fieldset" className={classes.formControl}>
          <FormLabel component="legend">Automation</FormLabel>
            <Select
              native
              variant="standard"
              value={automationName}
              onChange={handleAlgoSelectionChange}
              style={{maxWidth: "270px"}}
            >
              {Object.keys(automations).map((key) => <option id={key} value={key} key={"change-io" + key}>{automations[key].display_name}</option>)}

            </Select>
            {Object.keys(automations).length > 0 && <AutomationForm fields={automations[automationName].fields} description={automations[automationName].description} updateParent={updateFromChild} name={automationName}/>}

            {!props.no_skip_first_run ?
            <FormControlLabel
              control={<Checkbox checked={Boolean(algoSettings.skip_first_run)}
                                  color="primary"
                                  onChange={handleSkipFirstRunChange}
                                  size="small"/>
                      }
              label="Skip first run"
            />
            : <React.Fragment/> }

          </FormControl>
        </form>
      </DialogContent>
      <DialogActions>
        <Button
          type="submit"
          variant="contained"
          color="primary"
          onClick={props.isJobRunning ? changeAutomation :  startJob}
        >
          Start
        </Button>
        <Button
          color="secondary"
          onClick={handleClose}
        >
          Cancel
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
