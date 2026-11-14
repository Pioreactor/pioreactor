import React, { useRef, useState } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import InputAdornment from "@mui/material/InputAdornment";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { experimentPathSegment } from "../utils/url";

const SAVE_ERROR = "Could not save label.";

// The Pioreactor card title; clicking it swaps it for an inline label field.
// Enter or leaving the field saves, Escape cancels, and an empty label removes it.
export default function UnitLabelEditor({ unit, experiment, label, onLabelChange, titleSx }) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [errorText, setErrorText] = useState("");
  const isCancellingRef = useRef(false);

  const startEditing = () => {
    isCancellingRef.current = false;
    setDraft(label || "");
    setErrorText("");
    setIsEditing(true);
  };

  const stopEditing = () => {
    setIsEditing(false);
    setErrorText("");
  };

  const save = async () => {
    if (isSaving || isCancellingRef.current) {
      return;
    }
    const nextLabel = draft.trim();
    if (nextLabel === (label || "")) {
      stopEditing();
      return;
    }

    setIsSaving(true);
    setErrorText("");
    try {
      const response = await fetch(`/api/experiments/${experimentPathSegment(experiment)}/unit_labels`, {
        method: "PUT",
        body: JSON.stringify({ unit, label: nextLabel }),
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.error || SAVE_ERROR);
      }
      onLabelChange(nextLabel);
      stopEditing();
    } catch (error) {
      setErrorText((error.message || SAVE_ERROR).replaceAll("`", ""));
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      save();
    } else if (event.key === "Escape") {
      event.preventDefault();
      isCancellingRef.current = true;
      stopEditing();
    }
  };

  if (isEditing) {
    return (
      <TextField
        variant="standard"
        autoFocus
        value={draft}
        placeholder={unit}
        disabled={isSaving}
        error={Boolean(errorText)}
        helperText={errorText || null}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={save}
        sx={{ mb: "7px", width: "20ch" }}
        slotProps={{
          htmlInput: {
            "aria-label": `Label for ${unit}`,
            style: { fontSize: 20, fontWeight: 500, padding: "0px" },
          },
          input: {
            endAdornment: isSaving ? (
              <InputAdornment position="end">
                <CircularProgress size={16} />
              </InputAdornment>
            ) : null,
          },
        }}
      />
    );
  }

  return (
    <Tooltip title={label ? "Edit label" : "Add label"} placement="top-start">
      <Typography
        component="button"
        type="button"
        onClick={startEditing}
        aria-label={`${label ? "Edit" : "Add"} label for ${unit}`}
        sx={{
          p: 0,
          border: 0,
          background: "none",
          fontFamily: "inherit",
          textAlign: "left",
          cursor: "text",
          mb: "7px",
          ...titleSx,
          "&:hover": { textDecoration: "underline dotted", textUnderlineOffset: "4px" },
          "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: "2px" },
        }}
      >
        {label || unit}
      </Typography>
    </Tooltip>
  );
}
