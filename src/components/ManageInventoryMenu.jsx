import React from "react";
import MenuItem from '@mui/material/MenuItem';
import Button from '@mui/material/Button';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RemoveCircleOutlineRoundedIcon from '@mui/icons-material/RemoveCircleOutlineRounded';
import { useConfirm } from 'material-ui-confirm';
import { useNavigate } from 'react-router-dom';
import Menu from "@mui/material/Menu";
import ListItemText from "@mui/material/ListItemText";
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import ListItemIcon from '@mui/material/ListItemIcon';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';

function ManageInventoryMenu(){
  const [anchorEl, setAnchorEl] = React.useState(null);
  const open = Boolean(anchorEl);
  const confirm = useConfirm();
  const navigate = useNavigate();


  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };
  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleReboot = () => {
    confirm({
      description: 'This will halt running activities in worker Pioreactors and reboot them. Do you wish to continue?',
      title: "Reboot all workers?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},

      }).then(() =>
        fetch('/api/units/$broadcast/system/reboot', {method: "POST"})
    );

  };

  const handleShutdown = () => {
    confirm({
      description: 'This will halt running activities in worker Pioreactors and shut them down. A physical power-cycle is required to restart them. Do you wish to continue?',
      title: "Shutdown all workers?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},

      }).then(() =>
        fetch('/api/units/$broadcast/system/shutdown', {method: "POST"})
      )
  };
  const handleUnassign = () => {
    confirm({
      description: 'Unassign all workers from active experiments. This will also halt all activities in worker Pioreactors. Do you wish to continue?',
      title: "Unassign all workers?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},

      }).then(() =>
        fetch('/api/workers/assignments', {method: "DELETE"})
      ).then(() => navigate(0)).catch(() => {});

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
        Manage inventory <ArrowDropDownIcon/>
      </Button>
      <Menu
        id="manage-inv"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        MenuListProps={{
          'aria-labelledby': 'basic-button',
        }}
      >
        <MenuItem onClick={handleUnassign}>
          <ListItemIcon>
            <RemoveCircleOutlineRoundedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Unassign all workers</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleReboot}>
          <ListItemIcon>
            <RestartAltIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Reboot all workers</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleShutdown}>
          <ListItemIcon>
            <PowerSettingsNewIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Shutdown all workers</ListItemText>
        </MenuItem>
      </Menu>
    </div>
  );
}

export default ManageInventoryMenu