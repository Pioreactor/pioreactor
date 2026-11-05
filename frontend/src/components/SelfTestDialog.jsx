import { uiColors } from "../theme/colors";
import React, {useState} from "react";
import { styled } from '@mui/material/styles';
import CheckIcon from '@mui/icons-material/Check';
import ErrorOutlineOutlinedIcon from '@mui/icons-material/ErrorOutlineOutlined';
import CircularProgress from '@mui/material/CircularProgress';
import Box from '@mui/material/Box';
import IndeterminateCheckBoxOutlinedIcon from '@mui/icons-material/IndeterminateCheckBoxOutlined';
import CheckBoxOutlinedIcon from '@mui/icons-material/CheckBoxOutlined';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListSubheader from '@mui/material/ListSubheader';
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import {Typography} from '@mui/material';
import Alert from '@mui/material/Alert';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import PlayArrowIcon from "@mui/icons-material/PlayArrow";


import PioreactorIcon from "./PioreactorIcon"
import RequirementsAlert from "./RequirementsAlert"
import { runPioreactorJob } from "../utils/jobs";
import { readyGreen, lostRed } from "../utils/color";
import DialogCloseButton from "./DialogCloseButton";
import { textIcon } from "../theme";
import { getAvailableSelfTestGroupsFromSettings } from "./PioreactorCardShared";
import useCameraResource from "../hooks/useCameraResource";
import { experimentPathSegment } from "../utils/url";


const ManageDivider = styled(Divider)(({ theme }) => ({
  marginTop: theme.spacing(2), // equivalent to 16px if the default spacing unit is 8px
  marginBottom: theme.spacing(1.25) // equivalent to 10px
}));

export default function SelfTestDialog({disabled, experiment, unit, label , selfTestState, selfTestTests}) {
  const [open, setOpen] = useState(false);
  const { data: cameraStatus, error: cameraStatusError } = useCameraResource({
    url: open
      ? `/api/workers/${encodeURIComponent(unit)}/camera/experiments/${experimentPathSegment(experiment)}/status`
      : null,
  });
  const cameraDetected = cameraStatus?.detection_status === "detected";
  const selfTestGroups = getAvailableSelfTestGroupsFromSettings(selfTestTests?.publishedSettings, cameraDetected);

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };


  function displayIcon(key, state){
    if (selfTestTests == null){
      return <IndeterminateCheckBoxOutlinedIcon />
    }
    else if (selfTestTests.publishedSettings[key]?.value === true){
      return <CheckIcon sx={{color: readyGreen}}/>
    }
    else if (selfTestTests.publishedSettings[key]?.value === false){
      return <ErrorOutlineOutlinedIcon sx={{color: lostRed}}/>
    }
    else if (state === "ready") {
      return <CircularProgress size={20} />
    }
    else {
      return <IndeterminateCheckBoxOutlinedIcon />
    }
  }


  function createUserButtonsBasedOnState(jobState){

    switch (jobState){
      case "init":
      case "ready":
      case "sleeping":
       return (
         <Box sx={{display: "inline-block"}}>
           <Button
            variant="contained"
            loading={true}
            loadingPosition="start"
            disabled={true}
            sx={{mt: "5px", height: "31px"}}
           >
            Running
           </Button>
         </Box>
       )
      default:
       return (
         <Box sx={{display: "inline-block"}}>
           <Button
            variant="contained"
            loading={false}
            loadingPosition="start"
            endIcon={<PlayArrowIcon />}
            onClick={() => runPioreactorJob(unit, experiment, "self_test")}
            sx={{mt: "5px", height: "31px"}}
           >
            Start
           </Button>
         </Box>
       )
    }
  }


  function colorOfIcon(){
    return disabled ? "disabled" : "primary"
  }

  function Icon(){
    if (selfTestTests == null){
      return <IndeterminateCheckBoxOutlinedIcon color={colorOfIcon()} fontSize="small" sx={textIcon}/>
    }
    else {
      return selfTestTests.publishedSettings["all_tests_passed"].value ? <CheckBoxOutlinedIcon color={colorOfIcon()} fontSize="small" sx={textIcon}/> : <IndeterminateCheckBoxOutlinedIcon color={colorOfIcon()} fontSize="small" sx={textIcon}/>
    }
  }

  const selfTestButton = createUserButtonsBasedOnState(selfTestState, "self_test")

  return (
    <React.Fragment>
      <Button color="primary" disabled={disabled} onClick={handleClickOpen}>
        {Icon()} Self-test
      </Button>
      <Dialog open={open} onClose={handleClose}>
        <DialogTitle>
          <Typography sx={{fontSize: "13px", color: uiColors.textSecondary,}} gutterBottom>
            <PioreactorIcon sx={{verticalAlign: "middle", fontSize: "1.2em"}}/> {label ? `${label} / ${unit}` : `${unit}`}
          </Typography>
           Self-test
          <DialogCloseButton onClick={handleClose} />
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" component="p" gutterBottom>
            Perform a check of the heating & temperature sensor, LEDs & photodiodes, and stirring{cameraDetected ? ", plus the camera" : ""}.
          </Typography>
          {cameraStatusError && (
            <Alert severity="warning">Could not check camera availability. Reopen this dialog to retry.</Alert>
          )}
          <RequirementsAlert sx={{mb: 2, pb: 0}}>
            Add a closed vial, half-filled with water or clear media, and stirbar into the Pioreactor.
            <Box
              component="img"
              src="/static/svgs/prepare-vial-arrow-pioreactor-compact.svg"
              alt="Prepare vial"
              sx={{width: "150px", display: "block", mb: 0, mx: "auto"}}
            />
          </RequirementsAlert>

            <Box>

              {selfTestButton}

              <Box sx={{display: "inline-block"}}>
               <Button
                sx={{mt: "5px", height: "31px", ml: '3px'}}
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

          {selfTestGroups.map((group) => (
            <List
              key={group.title}
              subheader={
                <ListSubheader sx={{lineHeight: "20px"}} component="div" disableSticky disableGutters>
                  {group.title}
                </ListSubheader>
              }
            >
              {group.tests.map((test) => (
                <ListItem key={test.key} sx={{pt: 0, pb: 0}}>
                  <ListItemIcon sx={{minWidth: "30px"}}>
                    {displayIcon(test.key, selfTestState)}
                  </ListItemIcon>
                  <ListItemText
                    primary={test.label}
                    secondary={test.secondaryKey && selfTestTests?.publishedSettings[test.secondaryKey]?.value
                      ? JSON.parse(selfTestTests.publishedSettings[test.secondaryKey].value)
                        .map((ledPd) => `${ledPd[0]} ⇝ ${ledPd[1]}`).join(",  ")
                      : ""}
                  />
                </ListItem>
              ))}
            </List>
          ))}

          <ManageDivider/>
          <Typography variant="body2" component="p" gutterBottom>
            Learn more about self-tests and <a rel="noopener noreferrer" target="_blank" href="https://docs.pioreactor.com/user-guide/self-test-reference">what to do if a test fails.</a>
          </Typography>
        </DialogContent>
      </Dialog>
  </React.Fragment>
  );
}
