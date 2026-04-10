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
import ExperimentMetadataDialog from "./ExperimentMetadataDialog";


export default function ManageExperimentMenu({experiment}){
  const [anchorEl, setAnchorEl] = React.useState(null);
  const [isEditDialogOpen, setIsEditDialogOpen] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState("");
  const open = Boolean(anchorEl);
  const confirm = useConfirm();
  const navigate = useNavigate();
  const {experimentMetadata, updateExperiment, allExperiments, setAllExperiments} = useExperiment()

  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };
  const handleClose = () => {
    setAnchorEl(null);
  };

  const currentExperiment = React.useMemo(() => {
    return (
      allExperiments.find((candidate) => candidate.experiment === experiment) ||
      (experimentMetadata.experiment === experiment ? experimentMetadata : null) ||
      { experiment, description: "", tags: [] }
    );
  }, [allExperiments, experiment, experimentMetadata]);

  const allTagOptions = React.useMemo(() => {
    return [...new Set(
      allExperiments.flatMap((candidate) => (Array.isArray(candidate.tags) ? candidate.tags : [])),
    )].sort((left, right) => left.localeCompare(right));
  }, [allExperiments]);

  const handleOpenEditDialog = () => {
    handleClose();
    setErrorMessage("");
    setIsEditDialogOpen(true);
  };

  const handleCloseEditDialog = () => {
    if (isSaving) {
      return;
    }

    setErrorMessage("");
    setIsEditDialogOpen(false);
  };

  const handleSaveExperimentMetadata = async (updatedExperiment) => {
    setIsSaving(true);
    setErrorMessage("");

    try {
      const response = await fetch(`/api/experiments/${encodeURIComponent(updatedExperiment.experiment)}`, {
        method: "PATCH",
        body: JSON.stringify({
          description: updatedExperiment.description,
          tags: updatedExperiment.tags,
        }),
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload?.error || "Failed to update experiment metadata.");
      }

      const savedExperiment = await response.json();
      updateExperiment(savedExperiment);
      setIsEditDialogOpen(false);
    } catch (error) {
      console.error("Failed to save experiment metadata:", error);
      setErrorMessage(error.message || "Failed to update experiment metadata.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleEndExperiment = () => {
    confirm({
      description: 'This will stop any running activities in assigned Pioreactors, and unassign all Pioreactors from this experiment. Do you wish to continue?',
      title: "End experiment?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", sx: {textTransform: 'none'}},
      cancellationButtonProps: {color: "secondary", sx: {textTransform: 'none'}},

      }).then(() =>
        fetch(`/api/experiments/${encodeURIComponent(experiment)}/workers`, {method: "DELETE"})
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
        fetch(`/api/experiments/${encodeURIComponent(experiment)}`, {method: "DELETE"}).then((res) => {
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
        slotProps={{
          list: {
            'aria-labelledby': 'basic-button',
          },
        }}
      >
        <MenuItem onClick={handleOpenEditDialog}>
          <ListItemText>Edit details</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleEndExperiment}>
          <ListItemText>End experiment</ListItemText>
        </MenuItem>
        <Divider />
        <MenuItem color="secondary" disabled={allExperiments.length <= 1} onClick={handleDeleteExperiment}>
          <ListItemText slotProps={{ primary: { sx: { color: 'secondary.main' } } }}>Delete experiment</ListItemText>
        </MenuItem>
      </Menu>
      <ExperimentMetadataDialog
        experiment={currentExperiment}
        open={isEditDialogOpen}
        onClose={handleCloseEditDialog}
        onSave={handleSaveExperimentMetadata}
        allTagOptions={allTagOptions}
        isSaving={isSaving}
        errorMessage={errorMessage}
      />
    </div>
  );
}
