import React, {useState} from "react";
import { styled } from '@mui/material/styles';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import CircularProgress from '@mui/material/CircularProgress';
import IndeterminateCheckBoxIcon from '@mui/icons-material/IndeterminateCheckBox';
import Box from '@mui/material/Box';
import IndeterminateCheckBoxOutlinedIcon from '@mui/icons-material/IndeterminateCheckBoxOutlined';
import CheckBoxOutlinedIcon from '@mui/icons-material/CheckBoxOutlined';
import List from '@mui/material/List';
import IconButton from '@mui/material/IconButton';
import ListItem from '@mui/material/ListItem';
import ListSubheader from '@mui/material/ListSubheader';
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import {Typography} from '@mui/material';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';


import PioreactorIcon from "./PioreactorIcon"
import PatientButton from "./PatientButton"
import {runPioreactorJob} from "../utilities"


const ManageDivider = styled(Divider)(({ theme }) => ({
  marginTop: theme.spacing(2), // equivalent to 16px if the default spacing unit is 8px
  marginBottom: theme.spacing(1.25) // equivalent to 10px
}));

const readyGreen = "#176114"
const lostRed = "#DE3618"


export default function SelfTestDialog({client, disabled, experiment, unit, label , selfTestState, selfTestTests}) {
  const [open, setOpen] = useState(false);

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };


  function displayIcon(key, state){
    if (selfTestTests == null){
      return <IndeterminateCheckBoxIcon />
    }
    else if (selfTestTests.publishedSettings[key]?.value === true){
      return <CheckIcon sx={{color: readyGreen}}/>
    }
    else if (selfTestTests.publishedSettings[key]?.value === false){
      return <ErrorOutlineIcon sx={{color: lostRed}}/>
    }
    else if (state === "ready") {
      return <CircularProgress size={20} />
    }
    else {
      return <IndeterminateCheckBoxIcon />
    }
  }


  function createUserButtonsBasedOnState(jobState){

    switch (jobState){
      case "init":
      case "ready":
      case "sleeping":
       return (<Box  sx={{display: "inline-block"}}>
               <PatientButton
                color="primary"
                variant="contained"
                disabled={true}
                buttonText="Running"
               />
              </Box>)
      default:
       return (<Box  sx={{display: "inline-block"}}>
               <PatientButton
                color="primary"
                variant="contained"
                onClick={() => runPioreactorJob(unit, experiment, "self_test")}
                buttonText="Start"
               />
              </Box>)
    }
  }


  function colorOfIcon(){
    return disabled ? "disabled" : "primary"
  }

  function Icon(){
    if (selfTestTests == null){
      return <IndeterminateCheckBoxOutlinedIcon color={colorOfIcon()} fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/>
    }
    else {
      return selfTestTests.publishedSettings["all_tests_passed"].value ? <CheckBoxOutlinedIcon color={colorOfIcon()} fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/> : <IndeterminateCheckBoxOutlinedIcon color={colorOfIcon()} fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/>
    }
  }

  const selfTestButton = createUserButtonsBasedOnState(selfTestState, "self_test")

  return (
    <React.Fragment>
      <Button style={{textTransform: 'none'}} color="primary" disabled={disabled} onClick={handleClickOpen}>
        {Icon()} Self test
      </Button>
      <Dialog open={open} onClose={handleClose}>
        <DialogTitle>
          <Typography sx={{fontSize: "13px", color: "rgba(0, 0, 0, 0.60)",}} gutterBottom>
            <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.2em"}}/> {label ? `${label} / ${unit}` : `${unit}`}
          </Typography>
           Self test
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
            Perform a check of the heating & temperature sensor, LEDs & photodiodes, and stirring.
          </Typography>
          <Typography variant="body2" component="p" gutterBottom>
            Add a closed vial, half-filled with water, and stirbar into the Pioreactor.
          </Typography>

            <Box>

              {selfTestButton}

              <Box sx={{display: "inline-block"}}>
               <Button
                sx={{mt: "5px", height: "31px", ml: '3px', textTransform: "None"}}
                color="primary"
                variant="text"
                disabled={!(selfTestTests?.publishedSettings.all_tests_passed.value === false) || ["init", "ready"].includes(selfTestState)}
                onClick={() => runPioreactorJob(unit, experiment, "self_test", [], {"retry-failed": null})}
               >
               Retry failed tests
               </Button>
              </Box>
            </Box>

            <ManageDivider/>

            <List component="nav"
              subheader={
                <ListSubheader style={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                  LEDs & photodiodes
                </ListSubheader>
              }
            >
              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_pioreactor_HAT_present", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Pioreactor HAT is detected" />
              </ListItem>
              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_all_positive_correlations_between_pds_and_leds", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Photodiodes are responsive to IR LED" secondary={
                    (selfTestTests && selfTestTests?.publishedSettings["correlations_between_pds_and_leds"]?.value) ?
                      JSON.parse(selfTestTests.publishedSettings["correlations_between_pds_and_leds"].value).map(led_pd => `${led_pd[0]} ⇝ ${led_pd[1]}`).join(",  ") :
                      ""
                    }/>
              </ListItem>

              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_ambient_light_interference", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="No ambient IR light detected" />
              </ListItem>

              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_REF_is_lower_than_0_dot_256_volts", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Reference photodiode is correct magnitude" />
              </ListItem>

              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_REF_is_in_correct_position", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Reference photodiode is in correct position" />
              </ListItem>

              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_PD_is_near_0_volts_for_blank", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Photodiode measures near zero signal for clear water" />
              </ListItem>

            </List>

            <List component="nav"
              subheader={
                <ListSubheader style={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                  Heating & temperature
                </ListSubheader>
              }
            >
              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_detect_heating_pcb", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Heating PCB is detected" />
              </ListItem>

              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_positive_correlation_between_temperature_and_heating", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Heating is responsive" />
              </ListItem>
            </List>


            <List component="nav"
              subheader={
                <ListSubheader style={{lineHeight: "20px"}} component="div" disableSticky={true} disableGutters={true}>
                  Stirring
                </ListSubheader>
              }
            >
              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_positive_correlation_between_rpm_and_stirring", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Stirring RPM is responsive" />
              </ListItem>

              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_run_stirring_calibration", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="Create stirring calibration" />
              </ListItem>

              <ListItem sx={{pt: 0, pb: 0}}>
                <ListItemIcon sx={{minWidth: "30px"}}>
                  {displayIcon("test_aux_power_is_not_too_high", selfTestState)}
                </ListItemIcon>
                <ListItemText primary="AUX power supply is appropriate value" />
              </ListItem>


            </List>

          <ManageDivider/>
          <Typography variant="body2" component="p" gutterBottom>
            Learn more about self tests and <a rel="noopener noreferrer" target="_blank" href="https://docs.pioreactor.com/user-guide/running-self-test#explanation-of-each-test">what to do if a test fails.</a>
          </Typography>
        </DialogContent>
      </Dialog>
  </React.Fragment>
  );
}
