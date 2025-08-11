import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Typography,
  Box,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import PioreactorsIcon from './PioreactorsIcon';
import dayjs from 'dayjs';

function RecordEventLogDialog({
  defaultPioreactor = "",
  defaultExperiment = "",
  availableUnits = [],
  onSubmit,
}) {
  const [selectedPioreactor, setSelectedPioreactor] = useState(defaultPioreactor);
  const [selectedExperiment, setSelectedExperiment] = useState(defaultExperiment);
  const [message, setMessage] = useState("");
  const [timestampLocal, setTimestampLocal] = useState(dayjs().local().format('YYYY-MM-DD HH:mm:ss'));
  const [task, setTask] = useState("");
  const [openDialog, setOpenDialog] = useState(false);

  const handleSubmit = () => {
    if (onSubmit) {
      const timestampUTC = dayjs(timestampLocal, 'YYYY-MM-DD HH:mm:ss', true)
        .utc()
        .format('YYYY-MM-DD[T]HH:mm:ss.000[Z]');
      onSubmit({
        pioreactor_unit: selectedPioreactor,
        experiment: selectedExperiment,
        message: message,
        timestamp: timestampUTC,
        task: task,
        source: "UI",
        level: "INFO",
      });
      setMessage("")
      setTask("")
      onClose()
    }
  };


  const handleOpenDialog = () => {
    setTimestampLocal(dayjs().local().format('YYYY-MM-DD HH:mm:ss'))
    setOpenDialog(true);
  };

  const onClose = () => {
    setOpenDialog(false);
  };

  return (
    <>
    <Button
      style={{textTransform: 'none', marginRight: "0px", float: "right"}}
      color="primary"
      onClick={handleOpenDialog}
    >
      <AddIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}} /> Record new event
    </Button>
    <Dialog open={openDialog} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ mb: 2 }}>
        Record a new event log
        <IconButton
          aria-label="close"
          onClick={onClose}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[500],
          }}
          size="large"
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 3 }}>
          Add a new event log manually.
        </Typography>
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <FormControl required size="small" variant="outlined" sx={{ flex: 1 }}>
            <InputLabel id="select-pioreactor-label">Pioreactor</InputLabel>
            <Select
              labelId="select-pioreactor-label"
              key="Confirmation Code"
              label="Pioreactor"
              value={selectedPioreactor}
              onChange={(e) => setSelectedPioreactor(e.target.value)}
            >
              {availableUnits.map((unit) => (
                <MenuItem key={unit} value={unit}>{unit}</MenuItem>
              ))}
              <MenuItem value="$broadcast"><PioreactorsIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 4px"}} /> All assigned Pioreactors </MenuItem>
            </Select>
          </FormControl>
          <FormControl required size="small" variant="outlined" sx={{ flex: 1 }}>
            <InputLabel id="select-experiment-label">Experiment</InputLabel>
            <Select
              labelId="select-experiment-label"
              value={selectedExperiment}
              label="Experiment"
              onChange={(e) => setSelectedExperiment(e.target.value)}
            >
              <MenuItem value={defaultExperiment}>{defaultExperiment}</MenuItem>
            </Select>
          </FormControl>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <TextField
            required
            size="small"
            variant="outlined"
            label="Message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            multiline
            minRows={2}
            sx={{ flex: 1 }}
          />
        </Box>
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <TextField
            required
            size="small"
            variant="outlined"
            label="Timestamp"
            value={timestampLocal}
            helperText="Localtime"
            onChange={(e) => setTimestampLocal(e.target.value)}
          />
          <TextField
            variant="outlined"
            size="small"
            label="Source (optional)"
            value={task}
            onChange={(e) => setTask(e.target.value)}
          />
        </Box>
      </DialogContent>
      <DialogActions sx={{ p: 2 }}>
        <Button onClick={onClose} sx={{ textTransform: "none" }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          style={{ textTransform: "none" }}
          disabled={message === "" || selectedExperiment === "" || selectedPioreactor === ""}
        >
          Submit
        </Button>
      </DialogActions>
    </Dialog>
    </>
  );
}

export default RecordEventLogDialog;
