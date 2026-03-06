import React from "react";
import dayjs from "dayjs";

import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

export function normalizeExperimentTagList(tags) {
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

export default function ExperimentMetadataDialog({
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

    setTags((previousTags) => normalizeExperimentTagList([...previousTags, tagInputValue]));
    setTagInputValue("");
  }, [tagInputValue]);

  const handleTagsChange = (_event, nextTags) => {
    setTags(normalizeExperimentTagList(nextTags));
  };

  const handleSave = () => {
    if (!experiment) {
      return;
    }

    onSave({
      ...experiment,
      description,
      tags: normalizeExperimentTagList([...tags, tagInputValue]),
    });
  };

  return (
    <Dialog open={open} onClose={isSaving ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>
        Edit {experiment?.experiment || "experiment"}
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
