import React from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import SettingsIcon from '@mui/icons-material/Settings';
import Snackbar from "./Snackbar";
import Chip from '@mui/material/Chip';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';


const CustomFormControlLabel = ({ label, sublabel, control, ...props }) => (
  <FormControlLabel
    control={control}
    label={
      <Box>
        <Typography variant="body1">{label}</Typography>
        {sublabel && <Typography variant="body2" color="textSecondary">{sublabel}</Typography>}
      </Box>
    }
    {...props}
  />
);

function ChartPreferencesDialog({
  defaultChartKeys,
  descriptors,
  experiment,
  initialChartKeys,
  initialUseDefaults,
  onClose,
  onSave,
}) {
  const [selectedChartKeys, setSelectedChartKeys] = React.useState(initialChartKeys);
  const [useDefaults, setUseDefaults] = React.useState(initialUseDefaults);
  const [isSaving, setIsSaving] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [draggedChartKey, setDraggedChartKey] = React.useState(null);
  const [dragOverChartKey, setDragOverChartKey] = React.useState(null);

  const handleChartChange = (event) => {
    const chartKey = event.target.name;
    setUseDefaults(false);
    setSelectedChartKeys((currentKeys) => (
      event.target.checked
        ? [...currentKeys, chartKey]
        : currentKeys.filter((currentKey) => currentKey !== chartKey)
    ));
  };

  const moveChartToIndex = (chartKey, nextIndex) => {
    setUseDefaults(false);
    setSelectedChartKeys((currentKeys) => {
      const currentIndex = currentKeys.indexOf(chartKey);
      if (currentIndex < 0 || nextIndex < 0 || nextIndex >= currentKeys.length) {
        return currentKeys;
      }

      const nextKeys = [...currentKeys];
      nextKeys.splice(currentIndex, 1);
      nextKeys.splice(nextIndex, 0, chartKey);
      return nextKeys;
    });
  };

  const handleDrop = (targetChartKey) => {
    if (draggedChartKey && draggedChartKey !== targetChartKey) {
      moveChartToIndex(draggedChartKey, selectedChartKeys.indexOf(targetChartKey));
    }
    setDraggedChartKey(null);
    setDragOverChartKey(null);
  };

  const handleReset = () => {
    setSelectedChartKeys(defaultChartKeys);
    setUseDefaults(true);
    setError(null);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await onSave(useDefaults ? null : selectedChartKeys);
      onClose();
    } catch (saveError) {
      setError(saveError.message || "Could not save chart preferences. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  const descriptorsByKey = new Map(
    descriptors.map((descriptor) => [descriptor.chart_key, descriptor]),
  );
  const selectedDescriptors = selectedChartKeys
    .map((chartKey) => descriptorsByKey.get(chartKey))
    .filter(Boolean);
  const selectedChartKeySet = new Set(selectedChartKeys);
  const availableDescriptors = descriptors.filter(
    (descriptor) => !selectedChartKeySet.has(descriptor.chart_key),
  );

  const chartLabel = (descriptor) => descriptor.title
  const sublabel = (descriptor) => {
    if (descriptor.source !== "app"){
      return `Provided by ${descriptor.source}`
    }
  }

  return (
    <Dialog
      open
      onClose={isSaving ? undefined : onClose}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle sx={{ pr: 6 }}>
        Customize charts
        <IconButton
          aria-label="Close"
          onClick={onClose}
          disabled={isSaving}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Select and rearrange charts for <Chip icon={<PlayCircleOutlinedIcon/>} size="small" label={experiment} />.
      </Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <FormControl component="fieldset" variant="standard" fullWidth>
          <FormGroup sx={{ mt: 1 }}>
            {selectedDescriptors.map((descriptor) => (
              <Box
                key={descriptor.chart_key}
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData("text/plain", descriptor.chart_key);
                  setDraggedChartKey(descriptor.chart_key);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                  setDragOverChartKey(descriptor.chart_key);
                }}
                onDragLeave={() => {
                  if (dragOverChartKey === descriptor.chart_key) {
                    setDragOverChartKey(null);
                  }
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  handleDrop(descriptor.chart_key);
                }}
                onDragEnd={() => {
                  setDraggedChartKey(null);
                  setDragOverChartKey(null);
                }}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0.5,
                  borderRadius: 1,
                  backgroundColor: dragOverChartKey === descriptor.chart_key ? "action.hover" : "transparent",
                  opacity: draggedChartKey === descriptor.chart_key ? 0.6 : 1,
                  "&:hover": { backgroundColor: "action.hover" },
                }}
              >
                <Box
                  aria-hidden="true"
                  sx={{
                    width: 44,
                    height: 44,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: "grab",
                    color: "text.secondary",
                  }}
                >
                  <DragIndicatorIcon />
                </Box>
                <FormControlLabel
                  control={(
                    <Checkbox
                      checked
                      name={descriptor.chart_key}
                      onChange={handleChartChange}
                      slotProps={{ input: { "aria-label": descriptor.title } }}
                    />
                  )}
                  label={chartLabel(descriptor)}
                  sx={{ flexGrow: 1, minWidth: 0, mr: 1 }}
                />
              </Box>
            ))}
          </FormGroup>
          {selectedDescriptors.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ my: 2 }}>
              No charts selected.
            </Typography>
          )}
          {availableDescriptors.length > 0 && (
            <React.Fragment>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2">Available charts</Typography>
              <FormGroup sx={{ mt: 1 }}>
                {availableDescriptors.map((descriptor) => (
                  <CustomFormControlLabel
                    key={descriptor.chart_key}
                    control={(
                      <Checkbox
                        checked={false}
                        name={descriptor.chart_key}
                        onChange={handleChartChange}
                        slotProps={{ input: { "aria-label": descriptor.title } }}
                        sx={{ mb: sublabel(descriptor) ? 3 : 0 }}
                      />
                    )}
                    label={chartLabel(descriptor)}
                    sublabel={sublabel(descriptor)}
                  />
                ))}
              </FormGroup>
            </React.Fragment>
          )}
        </FormControl>
      </DialogContent>
      <DialogActions sx={{ justifyContent: "space-between" }}>
        <Button onClick={handleReset} disabled={isSaving}>
          Use defaults
        </Button>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button color="secondary" onClick={onClose} disabled={isSaving}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleSave} disabled={isSaving}>
            {isSaving && <CircularProgress size={16} sx={{ mr: 1 }} />}
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </Box>
      </DialogActions>
    </Dialog>
  );
}


export default function ChartPreferencesControl({
  chartPageLabel,
  chartPreferences,
  experiment,
}) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);

  const handleSave = async (chartKeys) => {
    await chartPreferences.save(chartKeys);
    setSnackbarOpen(true);
  };

  return (
    <React.Fragment>
        <span>
          <IconButton
            aria-label={`Customize ${chartPageLabel} charts for this experiment`}
            onClick={() => {
              setSnackbarOpen(false);
              setIsOpen(true);
            }}
            disabled={chartPreferences.isLoading || Boolean(chartPreferences.error)}
            sx={{ width: 44, height: 44 }}
          >
            {chartPreferences.isLoading
              ? <CircularProgress size={20} />
              : <SettingsIcon />}
          </IconButton>
        </span>
      {isOpen && (
        <ChartPreferencesDialog
          key={`${experiment}-${chartPageLabel}`}

          defaultChartKeys={chartPreferences.defaultChartKeys}
          descriptors={chartPreferences.descriptors}
          experiment={experiment}
          initialChartKeys={chartPreferences.selectedChartKeys}
          initialUseDefaults={chartPreferences.isUsingDefaults}
          onClose={() => setIsOpen(false)}
          onSave={handleSave}
        />
      )}
      <Snackbar
        open={snackbarOpen}
        message={`Chart selection saved.`}
        onClose={() => setSnackbarOpen(false)}
      />
    </React.Fragment>
  );
}
