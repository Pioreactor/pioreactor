import React from "react";
import dayjs from "dayjs";

import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import DialogCloseButton from "./DialogCloseButton";

function normalizeExperimentTagList(tags) {
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

export default function ExperimentMetadataDialog(props) {
  if (!props.open || !props.experiment) {
    return null;
  }
  return <ExperimentMetadataForm key={props.experiment.experiment} {...props} />;
}

function ExperimentMetadataForm({
  experiment,
  open,
  onClose,
  onSave,
  allTagOptions,
  isSaving,
  errorMessage,
}) {
  const [description, setDescription] = React.useState(experiment.description || "");
  const [tags, setTags] = React.useState(experiment.tags || []);
  const [tagInputValue, setTagInputValue] = React.useState("");
  const [startedAt, setStartedAt] = React.useState(
    () => dayjs(experiment.started_at).format("YYYY-MM-DDTHH:mm:ss"),
  );
  const [startTimeError, setStartTimeError] = React.useState("");

  const commitPendingTag = React.useCallback(() => {
    if (!tagInputValue.trim()) {
      return;
    }

    setTags((previousTags) => normalizeExperimentTagList([...previousTags, tagInputValue]));
    setTagInputValue("");
  }, [tagInputValue]);

  const handleTagsChange = (_event, nextTags) => {
    setTags(normalizeExperimentTagList(nextTags));
  };

  const handleSave = () => {
    if (isSaving) {
      return;
    }
    const startTime = new Date(startedAt);
    if (!startedAt || !Number.isFinite(startTime.getTime())) {
      setStartTimeError("Enter a valid start date and time.");
      return;
    }

    onSave({
      ...experiment,
      started_at: startedAt === dayjs(experiment.started_at).format("YYYY-MM-DDTHH:mm:ss")
        ? experiment.started_at
        : startTime.toISOString(),
      description,
      tags: normalizeExperimentTagList([...tags, tagInputValue]),
    });
  };

  return (
    <Dialog open={open} onClose={isSaving ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>
        Edit {experiment?.experiment || "experiment"}
        <DialogCloseButton onClick={onClose} disabled={isSaving} />
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: "flex-start" }}>
            <TextField
              label="Experiment start (local time)"
              type="datetime-local"
              required
              value={startedAt}
              disabled={isSaving}
              onChange={(event) => {
                setStartedAt(event.target.value);
                setStartTimeError("");
              }}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { step: "1" } }}
              error={Boolean(startTimeError)}
              helperText={startTimeError}
              fullWidth
            />
            <Button
              variant="text"
              size="small"
              onClick={() => {
                setStartedAt(dayjs().format("YYYY-MM-DDTHH:mm:ss"));
                setStartTimeError("");
              }}
              disabled={isSaving}
              sx={{ flexShrink: 0, minHeight: 44, alignSelf: { xs: "flex-end", sm: "center" } }}
            >
              Set to now
            </Button>
          </Stack>
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
        <Button color="secondary" onClick={onClose} disabled={isSaving}>
          Cancel
        </Button>
        <Button
          onClick={handleSave}
          variant="contained"
          disabled={isSaving}
        >
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
