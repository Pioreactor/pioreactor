import React from "react";
import dayjs from "dayjs";

import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import { styled } from "@mui/material/styles";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import PlayCircleOutlinedIcon from "@mui/icons-material/PlayCircleOutlined";
import { useConfirm } from "material-ui-confirm";
import { useSnackbar } from "notistack";
import { Link, useNavigate } from "react-router";

import { useExperiment } from "./providers/ExperimentContext";

const TAGS_TO_SHOW = 6;

const StyledTableCell = styled(TableCell)(() => ({
  padding: "6px 6px 6px 10px",
  whiteSpace: "normal",
}));

const TableRowStyled = styled(TableRow)(() => ({
  "&:nth-of-type(odd)": {
    backgroundColor: "#F7F7F7",
  },
  "&:nth-of-type(even)": {
    backgroundColor: "white",
  },
}));

function normalizeTagList(tags) {
  const normalizedTags = [];
  const seenTags = new Set();

  for (const rawTag of tags) {
    if (typeof rawTag !== "string") {
      continue;
    }

    const tag = rawTag.trim();
    if (!tag) {
      continue;
    }

    const normalizedTag = tag.toLowerCase();
    if (seenTags.has(normalizedTag)) {
      continue;
    }

    normalizedTags.push(tag);
    seenTags.add(normalizedTag);
  }

  return normalizedTags;
}

function ExperimentMetadataDialog({
  experiment,
  open,
  onClose,
  onSave,
  allTagOptions,
  isSaving,
  errorMessage,
}) {
  const [description, setDescription] = React.useState("");
  const [tags, setTags] = React.useState([]);
  const [tagInputValue, setTagInputValue] = React.useState("");

  React.useEffect(() => {
    if (!open || !experiment) {
      return;
    }

    setDescription(experiment.description || "");
    setTags(Array.isArray(experiment.tags) ? experiment.tags : []);
    setTagInputValue("");
  }, [open, experiment]);

  const commitPendingTag = React.useCallback(() => {
    if (!tagInputValue.trim()) {
      return;
    }

    setTags((previousTags) => normalizeTagList([...previousTags, tagInputValue]));
    setTagInputValue("");
  }, [tagInputValue]);

  const handleTagsChange = (_event, nextTags) => {
    setTags(normalizeTagList(nextTags));
  };

  const handleSave = () => {
    if (!experiment) {
      return;
    }

    onSave({
      ...experiment,
      description,
      tags: normalizeTagList([...tags, tagInputValue]),
    });
  };

  return (
    <Dialog open={open} onClose={isSaving ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{experiment?.experiment || "Edit experiment"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Created {experiment?.created_at ? dayjs(experiment.created_at).format("D MMMM YYYY, h:mm a") : "Unknown"}
          </Typography>
          <TextField
            label="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            multiline
            minRows={3}
            fullWidth
          />
          <Autocomplete
            multiple
            freeSolo
            options={allTagOptions}
            value={tags}
            inputValue={tagInputValue}
            onChange={handleTagsChange}
            onInputChange={(_event, nextValue, reason) => {
              if (reason === "reset") {
                return;
              }
              setTagInputValue(nextValue);
            }}
            filterSelectedOptions
            renderInput={(params) => (
              <TextField
                {...params}
                label="Tags"
                placeholder="Add a tag"
                helperText="Press Enter or comma to add a tag."
                onKeyDown={(event) => {
                  if ((event.key === "Enter" || event.key === ",") && tagInputValue.trim()) {
                    event.preventDefault();
                    commitPendingTag();
                  }
                }}
              />
            )}
          />
          {errorMessage && <Alert severity="error">{errorMessage}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={isSaving} sx={{ textTransform: "none" }}>
          Cancel
        </Button>
        <Button
          onClick={handleSave}
          variant="contained"
          disabled={isSaving}
          sx={{ textTransform: "none" }}
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ExperimentActionsMenu({
  experiment,
  disabled,
  onEdit,
  onExport,
  onEnd,
  onDelete,
}) {
  const [anchorEl, setAnchorEl] = React.useState(null);
  const menuOpen = Boolean(anchorEl);

  const handleClose = () => {
    setAnchorEl(null);
  };

  return (
    <React.Fragment>
      <IconButton
        size="small"
        onClick={(event) => setAnchorEl(event.currentTarget)}
        disabled={disabled}
        aria-label={`More actions for ${experiment.experiment}`}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu anchorEl={anchorEl} open={menuOpen} onClose={handleClose}>
        <MenuItem
          onClick={() => {
            handleClose();
            onEdit();
          }}
        >
          Edit
        </MenuItem>
        <MenuItem
          onClick={() => {
            handleClose();
            onExport();
          }}
        >
          Export data
        </MenuItem>
        {experiment.worker_count > 0 && (
          <MenuItem
            onClick={() => {
              handleClose();
              onEnd();
            }}
          >
            End experiment
          </MenuItem>
        )}
        <MenuItem
          onClick={() => {
            handleClose();
            onDelete();
          }}
          sx={{ color: "secondary.main" }}
        >
          Delete experiment
        </MenuItem>
      </Menu>
    </React.Fragment>
  );
}

function ExperimentsContainer(props) {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { enqueueSnackbar } = useSnackbar();
  const { allExperiments, experimentMetadata, selectExperiment, updateExperiment, setAllExperiments } = useExperiment();
  const [experiments, setExperiments] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [selectedTags, setSelectedTags] = React.useState([]);
  const [editingExperiment, setEditingExperiment] = React.useState(null);
  const [isSavingDialog, setIsSavingDialog] = React.useState(false);
  const [dialogError, setDialogError] = React.useState("");
  const [busyExperimentName, setBusyExperimentName] = React.useState("");

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  const refreshExperiments = React.useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const response = await fetch("/api/experiments");
      if (!response.ok) {
        throw new Error(`Failed to load experiments (${response.status})`);
      }

      const data = await response.json();
      setExperiments(data);
      setAllExperiments(data);
    } catch (error) {
      console.error("Failed to fetch experiments:", error);
      setLoadError("Unable to load experiments right now.");
    } finally {
      setLoading(false);
    }
  }, [setAllExperiments]);

  React.useEffect(() => {
    if (Array.isArray(allExperiments) && allExperiments.length > 0) {
      setExperiments(allExperiments);
      setLoading(false);
    }
  }, [allExperiments]);

  React.useEffect(() => {
    refreshExperiments();
  }, [refreshExperiments]);

  const allTagOptions = React.useMemo(() => {
    return [...new Set(experiments.flatMap((experiment) => experiment.tags || []))].sort((left, right) =>
      left.localeCompare(right),
    );
  }, [experiments]);

  const filteredExperiments = React.useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return experiments.filter((experiment) => {
      const isActive = experiment.worker_count > 0;
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && isActive) ||
        (statusFilter === "inactive" && !isActive);
      if (!matchesStatus) {
        return false;
      }

      const tags = Array.isArray(experiment.tags) ? experiment.tags : [];
      const matchesTags =
        selectedTags.length === 0 ||
        selectedTags.every((tag) => tags.some((experimentTag) => experimentTag.toLowerCase() === tag.toLowerCase()));
      if (!matchesTags) {
        return false;
      }

      if (!normalizedSearch) {
        return true;
      }

      return [experiment.experiment, experiment.description || "", ...tags]
        .join(" ")
        .toLowerCase()
        .includes(normalizedSearch);
    });
  }, [experiments, search, selectedTags, statusFilter]);

  const handleDialogSave = async (updatedExperiment) => {
    setIsSavingDialog(true);
    setDialogError("");

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
      setExperiments((previousExperiments) =>
        previousExperiments.map((experiment) =>
          experiment.experiment === savedExperiment.experiment ? savedExperiment : experiment,
        ),
      );
      updateExperiment(savedExperiment);
      setDialogError("");
      setIsSavingDialog(false);
      setEditingExperiment(null);
    } catch (error) {
      console.error("Failed to save experiment metadata:", error);
      setDialogError(error.message || "Failed to update experiment metadata.");
      setIsSavingDialog(false);
    }
  };

  const handleEndExperiment = async (experiment) => {
    await confirm({
      description:
        "This will stop any running activities in assigned Pioreactors, and unassign all Pioreactors from this experiment. Do you wish to continue?",
      title: "End experiment?",
      confirmationText: "Confirm",
      confirmationButtonProps: { color: "primary", sx: { textTransform: "none" } },
      cancellationButtonProps: { color: "secondary", sx: { textTransform: "none" } },
    });

    setBusyExperimentName(experiment.experiment);

    try {
      const response = await fetch(`/api/experiments/${encodeURIComponent(experiment.experiment)}/workers`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`Failed to end ${experiment.experiment}.`);
      }

      await refreshExperiments();
      enqueueSnackbar(`Ended ${experiment.experiment}.`, { variant: "success" });
    } finally {
      setBusyExperimentName("");
    }
  };

  const handleDeleteExperiment = async (experiment) => {
    await confirm({
      description:
        "This will permanently delete experiment data, stop Pioreactor activity, and unassign Pioreactors. Do you wish to continue?",
      title: "Delete experiment?",
      confirmationText: "Confirm",
      confirmationButtonProps: { color: "primary", sx: { textTransform: "none" } },
      cancellationButtonProps: { color: "secondary", sx: { textTransform: "none" } },
    });

    setBusyExperimentName(experiment.experiment);

    try {
      const response = await fetch(`/api/experiments/${encodeURIComponent(experiment.experiment)}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`Failed to delete ${experiment.experiment}.`);
      }

      const responseAfterDelete = await fetch("/api/experiments");
      const nextExperiments = responseAfterDelete.ok ? await responseAfterDelete.json() : [];
      setExperiments(nextExperiments);
      setAllExperiments(nextExperiments);

      if (experimentMetadata.experiment === experiment.experiment && nextExperiments.length > 0) {
        updateExperiment(nextExperiments[0], true);
      }

      enqueueSnackbar(`Deleted ${experiment.experiment}.`, { variant: "success" });
    } finally {
      setBusyExperimentName("");
    }
  };

  return (
    <React.Fragment>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 2, gap: 2, flexWrap: "wrap" }}>
        <Typography variant="h5" component="h1">
          <Box fontWeight="fontWeightBold">Experiments</Box>
        </Typography>
        <Button
          variant="text"
          component={Link}
          to="/start-new-experiment"
          sx={{ textTransform: "none" }}
        >
          <AddIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/> New experiment
        </Button>
      </Box>

      <Card sx={{ mb: 2 }}>
        {loading && <LinearProgress />}
        <Box sx={{ p: 2 }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} useFlexGap flexWrap="wrap">
            <TextField
              size="small"
              label="Search experiments"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              sx={{ minWidth: { xs: "100%", md: 260 } }}
            />
            <ToggleButtonGroup
              size="small"
              exclusive
              value={statusFilter}
              onChange={(_event, nextValue) => {
                if (nextValue) {
                  setStatusFilter(nextValue);
                }
              }}
            >
              <ToggleButton value="all" sx={{ textTransform: "none" }}>
                all
              </ToggleButton>
              <ToggleButton value="active" sx={{ textTransform: "none" }}>
                active
              </ToggleButton>
              <ToggleButton value="inactive" sx={{ textTransform: "none" }}>
                inactive
              </ToggleButton>
            </ToggleButtonGroup>
            <Autocomplete
              multiple
              size="small"
              options={allTagOptions}
              value={selectedTags}
              onChange={(_event, nextValue) => setSelectedTags(nextValue)}
              filterSelectedOptions
              sx={{ minWidth: { xs: "100%", md: 280 }, flexGrow: 1 }}
              renderInput={(params) => <TextField {...params} label="Filter by tags" />}
            />
          </Stack>
        </Box>
      </Card>

      {loadError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {loadError}
        </Alert>
      )}

      <Card>
        <TableContainer sx={{ width: "100%", overflowY: "auto", overflowX: "auto" }}>
          <Table size="small" aria-label="experiments table">
            <TableHead>
              <TableRow>
                <StyledTableCell sx={{ backgroundColor: "white" }}>Experiment</StyledTableCell>
                <StyledTableCell sx={{ backgroundColor: "white", whiteSpace: "nowrap" }}>Created at</StyledTableCell>
                <StyledTableCell sx={{ backgroundColor: "white" }}>Status</StyledTableCell>
                <StyledTableCell sx={{ backgroundColor: "white" }} align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredExperiments.map((experiment) => {
                const isBusy = busyExperimentName === experiment.experiment;
                const visibleTags = (experiment.tags || []).slice(0, TAGS_TO_SHOW);
                const remainingTagCount = Math.max((experiment.tags || []).length - visibleTags.length, 0);

                return (
                  <TableRowStyled key={experiment.experiment} hover>
                    <StyledTableCell sx={{ width: "65%" }}>
                      <Stack spacing={0.75}>
                        <Box>
                          <Chip
                            icon={<PlayCircleOutlinedIcon />}
                            size="small"
                            sx={{ mb: "2px" }}
                            label={experiment.experiment}
                            clickable
                            component={Link}
                            to="/overview"
                            onClick={() => selectExperiment(experiment.experiment)}
                            data-experiment-name={experiment.experiment}
                          />
                        </Box>
                        <Typography
                          variant="body2"
                          color={experiment.description ? "text.primary" : "text.secondary"}
                          sx={{
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {experiment.description || "No description"}
                        </Typography>
                        <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                          {visibleTags.map((tag) => (
                            <Chip key={`${experiment.experiment}-${tag}`} label={tag} size="small" variant="outlined" />
                          ))}
                          {remainingTagCount > 0 && (
                            <Chip label={`+${remainingTagCount}`} size="small" variant="outlined" />
                          )}
                        </Stack>
                      </Stack>
                    </StyledTableCell>
                    <StyledTableCell sx={{ whiteSpace: "nowrap", verticalAlign: "top" }}>
                      {dayjs(experiment.created_at).format("D MMMM YYYY, h:mm a")}
                    </StyledTableCell>
                    <StyledTableCell sx={{ verticalAlign: "top" }}>
                      <Chip
                        label={experiment.worker_count > 0 ? "Active" : "Inactive"}
                        size="small"
                        variant="outlined"
                        color={experiment.worker_count > 0 ? "primary" : "default"}
                      />
                    </StyledTableCell>
                    <StyledTableCell align="right" sx={{ whiteSpace: "nowrap", verticalAlign: "top" }}>
                      <ExperimentActionsMenu
                        experiment={experiment}
                        disabled={isBusy}
                        onEdit={() => {
                          setDialogError("");
                          setEditingExperiment(experiment);
                        }}
                        onExport={() => navigate(`/export-data?experiment=${encodeURIComponent(experiment.experiment)}`)}
                        onEnd={() => handleEndExperiment(experiment).catch(() => {})}
                        onDelete={() => handleDeleteExperiment(experiment).catch(() => {})}
                      />
                    </StyledTableCell>
                  </TableRowStyled>
                );
              })}
              {!loading && filteredExperiments.length === 0 && (
                <TableRow>
                  <StyledTableCell colSpan={4}>
                    <Box sx={{ py: 4, textAlign: "center" }}>
                      <Typography variant="body1">No experiments match the current filters.</Typography>
                    </Box>
                  </StyledTableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      <ExperimentMetadataDialog
        experiment={editingExperiment}
        open={Boolean(editingExperiment)}
        onClose={() => {
          if (!isSavingDialog) {
            setDialogError("");
            setEditingExperiment(null);
          }
        }}
        onSave={handleDialogSave}
        allTagOptions={allTagOptions}
        isSaving={isSavingDialog}
        errorMessage={dialogError}
      />
    </React.Fragment>
  );
}

function Experiments(props) {
  return (
    <Grid container spacing={2}>
      <Grid
        size={{
          md: 12,
          xs: 12,
        }}
      >
        <ExperimentsContainer title={props.title} />
      </Grid>
    </Grid>
  );
}

export default Experiments;
