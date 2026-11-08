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
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import ButtonBase from "@mui/material/ButtonBase";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SettingsIcon from '@mui/icons-material/SettingsOutlined';
import Snackbar from "./Snackbar";
import PluginChip from "./PluginChip";
import Chip from '@mui/material/Chip';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import DialogCloseButton from "./DialogCloseButton";
import UnitColorPicker from "./UnitColorPicker";
import useChartTheme from "../theme/useChartTheme";
import { createUnitColorMap } from "../utils/color";


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

function UnitColorsPanel({ units, relabelMap, unitColors, onChange }) {
  const chartTheme = useChartTheme();
  const [expandedUnit, setExpandedUnit] = React.useState(null);
  const resolvedColors = createUnitColorMap(units, unitColors);
  const displayName = (unit) => relabelMap?.[unit] || unit;

  if (units.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ my: 2 }}>
        No Pioreactors have been assigned to this experiment.
      </Typography>
    );
  }

  return units.map((unit) => {
    const isExpanded = unit === expandedUnit;
    const chosenColor = unitColors[unit] ?? null;
    const color = chartTheme.seriesColor(resolvedColors[unit]);
    return (
      <Box key={unit} sx={{ borderRadius: 1, backgroundColor: isExpanded ? "action.hover" : "transparent" }}>
        <ButtonBase
          disableRipple
          aria-expanded={isExpanded}
          onClick={() => setExpandedUnit(isExpanded ? null : unit)}
          sx={{
            width: "100%",
            justifyContent: "flex-start",
            gap: 1.5,
            px: 1,
            py: 1,
            borderRadius: 1,
            "&:hover": { backgroundColor: "action.hover" },
            "&.Mui-focusVisible": { outline: "2px solid", outlineColor: "primary.main" },
          }}
        >
          <Box
            sx={{
              width: 20,
              height: 20,
              flex: "none",
              borderRadius: "50%",
              backgroundColor: color,
              ...(chosenColor ? {} : { outline: "2px dashed", outlineColor: color, outlineOffset: "2px" }),
            }}
          />
          <Typography variant="body1" sx={{ flexGrow: 1, textAlign: "left" }}>
            {displayName(unit)}
            {relabelMap?.[unit] && (
              <Typography component="span" variant="body2" color="text.secondary"> ({unit})</Typography>
            )}
          </Typography>
          {isExpanded ? <ExpandLessIcon color="action" /> : <ExpandMoreIcon color="action" />}
        </ButtonBase>
        {isExpanded && (
          <Box sx={{ pl: 5, pb: 1.5 }}>
            <UnitColorPicker
              chosenColor={chosenColor}
              automaticColor={chosenColor ? null : resolvedColors[unit]}
              onChange={(nextColor) => {
                onChange(unit, nextColor);
                setExpandedUnit(null);
              }}
            />
          </Box>
        )}
      </Box>
    );
  });
}

function ChartPreferencesDialog({
  defaultChartKeys,
  descriptors,
  experiment,
  initialChartKeys,
  initialUseDefaults,
  initialUnitColors,
  onClose,
  onSave,
  relabelMap,
  units,
}) {
  const [tab, setTab] = React.useState(units ? "colors" : "charts");
  const [unitColors, setUnitColors] = React.useState(initialUnitColors ?? {});
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

  const handleUnitColorChange = (unit, color) => {
    setUnitColors((currentColors) => {
      const nextColors = { ...currentColors };
      if (color) {
        nextColors[unit] = color;
      } else {
        delete nextColors[unit];
      }
      return nextColors;
    });
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
      const chartKeys = useDefaults ? null : selectedChartKeys;
      await (units ? onSave(chartKeys, unitColors) : onSave(chartKeys));
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
      return <>Provided by <PluginChip name={descriptor.source} /></>
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
        <DialogCloseButton onClick={onClose} disabled={isSaving} />
      </DialogTitle>
      {units && (
        <Tabs value={tab} onChange={(_, nextTab) => setTab(nextTab)} sx={{ px: 3, borderBottom: 1, borderColor: "divider" }}>
          <Tab value="colors" label="Line colors" />
          <Tab value="charts" label="Charts" />
        </Tabs>
      )}
      <DialogContent sx={units ? { pt: 2 } : undefined}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {tab === "colors" ? (
          <React.Fragment>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Choose a line color for any Pioreactor in <Chip component="span" icon={<PlayCircleOutlinedIcon/>} size="small" label={experiment} />. Pioreactors left on Automatic use the next unused color.
            </Typography>
            <UnitColorsPanel
              units={units}
              relabelMap={relabelMap}
              unitColors={unitColors}
              onChange={handleUnitColorChange}
            />
          </React.Fragment>
        ) : (
          <React.Fragment>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Select and rearrange charts for <Chip component="span" icon={<PlayCircleOutlinedIcon/>} size="small" label={experiment} />.
          </Typography>
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
                    <CustomFormControlLabel
                      control={(
                        <Checkbox
                          checked
                          name={descriptor.chart_key}
                          onChange={handleChartChange}
                          slotProps={{ input: { "aria-label": descriptor.title } }}
                        />
                      )}
                      label={chartLabel(descriptor)}
                      sublabel={sublabel(descriptor)}
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
          </React.Fragment>
        )}
      </DialogContent>
      <DialogActions sx={{ justifyContent: "space-between" }}>
        {tab === "colors" ? (
          <Button onClick={() => setUnitColors({})} disabled={isSaving}>
            Reset all to automatic
          </Button>
        ) : (
          <Button onClick={handleReset} disabled={isSaving}>
            Use defaults
          </Button>
        )}
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


// Pass units (sorted unit names) to offer the Line colors tab.
export default function ChartPreferencesControl({
  chartPageLabel,
  chartPreferences,
  experiment,
  relabelMap,
  units,
}) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);

  const handleSave = async (...preferences) => {
    await chartPreferences.save(...preferences);
    setSnackbarOpen(true);
  };

  return (
    <React.Fragment>
        {/* The gear sits at the right end of the chart controls row. */}
        <Box component="span" sx={{ ml: "auto" }}>
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
        </Box>
      {isOpen && (
        <ChartPreferencesDialog
          key={`${experiment}-${chartPageLabel}`}

          defaultChartKeys={chartPreferences.defaultChartKeys}
          descriptors={chartPreferences.descriptors}
          experiment={experiment}
          initialChartKeys={chartPreferences.selectedChartKeys}
          initialUseDefaults={chartPreferences.isUsingDefaults}
          initialUnitColors={chartPreferences.unitColors}
          onClose={() => setIsOpen(false)}
          onSave={handleSave}
          relabelMap={relabelMap}
          units={units}
        />
      )}
      <Snackbar
        open={snackbarOpen}
        message="Chart settings saved."
        onClose={() => setSnackbarOpen(false)}
      />
    </React.Fragment>
  );
}
