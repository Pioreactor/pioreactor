import React from "react";

import MenuItem from "@mui/material/MenuItem";
import Menu from "@mui/material/Menu";
import Button from "@mui/material/Button";
import ListItemText from "@mui/material/ListItemText";
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import { useNavigate } from 'react-router';
import { useConfirm } from 'material-ui-confirm';
import { useExperiment } from '../providers/ExperimentContext';
import Divider from '@mui/material/Divider';


export default function ManageExperimentMenu({experiment}){
  const [anchorEl, setAnchorEl] = React.useState(null);
  const open = Boolean(anchorEl);
  const confirm = useConfirm();
  const navigate = useNavigate();
  const {updateExperiment, allExperiments, setAllExperiments} = useExperiment()

  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };
  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleEndExperiment = () => {
    confirm({
      description: 'This will stop any running activities in assigned Pioreactors, and unassign all Pioreactors from this experiment. Do you wish to continue?',
      title: "End experiment?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
      cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},

      }).then(() =>
        fetch(`/api/experiments/${experiment}/workers`, {method: "DELETE"})
        // DELETEing will also stop all activity.
    ).then(() => navigate(0)).catch(() => {});

  };

  const handleDeleteExperiment = () => {
    confirm({
      description: 'This will permanently delete experiment data, stop Pioreactor activity, and unassign Pioreactors. Do you wish to continue?',
      title: "Delete experiment?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
      cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},

      }).then(() =>
        fetch(`/api/experiments/${experiment}`, {method: "DELETE"}).then((res) => {
          if (res.ok){
            updateExperiment(allExperiments.find((em) => em.experiment !== experiment));
            setAllExperiments(allExperiments.filter((em) => em.experiment !== experiment));
          }
        })
      ).catch(() => {})
  };

  return (
    <div>
      <Button
        aria-controls={open ? 'basic-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        onClick={handleClick}
        style={{textTransform: "None"}}
      >
        Manage experiment <ArrowDropDownIcon/>
      </Button>
      <Menu
        id="manage-exp"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        MenuListProps={{
          'aria-labelledby': 'basic-button',
        }}
      >
        <MenuItem onClick={handleEndExperiment}>
          <ListItemText>End experiment</ListItemText>
        </MenuItem>
        <Divider />
        <MenuItem color="secondary" disabled={allExperiments.length <= 1} onClick={handleDeleteExperiment}>
          <ListItemText primaryTypographyProps={{color: 'secondary.main'}} >Delete experiment</ListItemText>
        </MenuItem>
      </Menu>
    </div>
  );
}
