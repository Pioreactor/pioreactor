import React from "react";

import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import { Typography } from "@mui/material";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Alert from "@mui/material/Alert";
import CardContent from "@mui/material/CardContent";
import SaveIcon from "@mui/icons-material/Save";
import TextField from "@mui/material/TextField";
import FormControl from "@mui/material/FormControl";
import InputAdornment from "@mui/material/InputAdornment";
import { Link, useLocation, useParams } from "react-router";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import Snackbar from "./components/Snackbar";
import Editor from "react-simple-code-editor";
import { highlight, languages } from "prismjs";
import "prismjs/components/prism-yaml";
import { DisplayProfile, DisplayProfileError } from "./components/DisplayProfile";
import CapabilitiesPanel from "./components/CapabilitiesPanel";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import IconButton from "@mui/material/IconButton";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import CircularProgress from "@mui/material/CircularProgress";
import { convertYamlToProfilePreview } from "./utils/experimentProfilePreview";


const textIcon = {verticalAlign: "middle", margin: "0px 3px"}

const DEFAULT_CODE = `experiment_profile_name:

version: "1.0"

metadata:
  author:
  description:
`;

const INITIAL_PROFILE_SAVE_STATE = {
  error: "",
  filename: "",
  code: "",
};

export function formatProfileSaveError(payload) {
  if (typeof payload === "string" && payload.trim()) {
    return payload.trim();
  }

  if (!payload || typeof payload !== "object") {
    return "Failed to save profile";
  }

  const messages = [];

  if (typeof payload.error === "string" && payload.error.trim()) {
    messages.push(payload.error.trim());
  }

  if (Array.isArray(payload.diagnostics) && payload.diagnostics.length > 0) {
    const diagnostic =
      payload.diagnostics.find((entry) => entry?.severity === "error") ?? payload.diagnostics[0];
    if (diagnostic && typeof diagnostic.message === "string" && diagnostic.message.trim()) {
      if (typeof diagnostic.path === "string" && diagnostic.path.trim()) {
        messages.push(`${diagnostic.message.trim()} (${diagnostic.path.trim()})`);
      } else {
        messages.push(diagnostic.message.trim());
      }
    }
  }

  if (typeof payload.cause === "string" && payload.cause.trim() && !messages.includes(payload.cause.trim())) {
    messages.push(payload.cause.trim());
  }

  return messages.join(" ") || "Failed to save profile";
}

async function parseErrorPayload(response) {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  return text.trim() || null;
}

async function saveNewExperimentProfile(code, filename) {
  const response = await fetch("/api/experiment_profiles", {
    method: "POST",
    body: JSON.stringify({ body: code, filename: `${filename}.yaml` }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });

  if (response.ok) {
    return;
  }

  const payload = await parseErrorPayload(response);
  throw new Error(formatProfileSaveError(payload));
}

async function saveExistingExperimentProfile(code, profileFilename) {
  const response = await fetch(`/api/experiment_profiles/${encodeURIComponent(profileFilename)}`, {
    method: "PATCH",
    body: JSON.stringify({ body: code }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });

  if (response.ok) {
    return;
  }

  const payload = await parseErrorPayload(response);
  throw new Error(formatProfileSaveError(payload));
}

export function ExperimentProfileEditorContent({
  initialCode,
  initialFilename,
  filenameEditable,
  onSave,
}) {
  const [code, setCode] = React.useState(initialCode);
  const [filename, setFilename] = React.useState(initialFilename);
  const [openSnackbar, setOpenSnackbar] = React.useState(false);
  const [snackbarMsg, setSnackbarMsg] = React.useState("");
  const [isChanged, setIsChanged] = React.useState(false);

  const parsedCode = React.useMemo(() => convertYamlToProfilePreview(code), [code]);

  const onTextChange = (newCode) => {
    setCode(newCode);
    setIsChanged(true);
  };

  const onFilenameChange = (event) => {
    setFilename(event.target.value.replace(/ |\/|\.|\\/g, "_"));
    setIsChanged(true);
  };

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  const [saveState, saveCurrentCode, saving] = React.useActionState(async (_previousState, payload) => {
    if (filenameEditable && payload.filename === "") {
      return {
        error: "Filename can't be blank.",
        filename: payload.filename,
        code: payload.code,
      };
    }

    try {
      await onSave(payload);
      setIsChanged(false);
      setOpenSnackbar(true);
      setSnackbarMsg(
        filenameEditable
          ? `Experiment profile ${payload.filename}.yaml saved.`
          : `Experiment profile ${initialFilename} saved.`,
      );
      return {
        error: "",
        filename: payload.filename,
        code: payload.code,
      };
    } catch (error) {
      setIsChanged(true);
      return {
        error: error.message || "Network error: failed to save profile",
        filename: payload.filename,
        code: payload.code,
      };
    }
  }, INITIAL_PROFILE_SAVE_STATE);

  const visibleSaveError =
    saveState.error && saveState.filename === filename && saveState.code === code
      ? saveState.error
      : "";

  return (
    <>
      <Grid container spacing={0}>
        <Grid size={12}>
          <Box sx={{ width: "100%", m: "10px", display: "flex", justifyContent: "space-between" }}>
            {filenameEditable ? (
              <FormControl>
                <TextField
                  label="Filename"
                  onChange={onFilenameChange}
                  required
                  value={filename}
                  sx={{ width: "320px" }}
                  slotProps={{
                    input: {
                      endAdornment: <InputAdornment position="end">.yaml</InputAdornment>,
                    },
                  }}
                />
              </FormControl>
            ) : (
              <TextField
                label="Filename"
                value={initialFilename}
                disabled={true}
                sx={{ width: "350px" }}
              />
            )}
          </Box>
        </Grid>

        <Grid size={6}>
          <Box
            sx={{
              tabSize: "4ch",
              border: "1px solid #ccc",
              m: "10px auto 10px auto",
              position: "relative",
              width: "98%",
              height: "350px",
              overflow: "auto",
              borderRadius: "4px",
              flex: 1,
            }}
          >
            <Editor
              value={code}
              onValueChange={onTextChange}
              highlight={(currentCode) => highlight(currentCode, languages.yaml)}
              padding={10}
              style={{
                fontSize: "14px",
                fontFamily: "monospace",
                backgroundColor: "hsla(0, 0%, 100%, .5)",
                borderRadius: "4px",
                minHeight: "100%",
              }}
            />
          </Box>
        </Grid>

        <Grid size={6}>
          {parsedCode.error ? (
            <DisplayProfileError error={parsedCode.error} />
          ) : (
            <DisplayProfile data={parsedCode.data} comments={parsedCode.comments} />
          )}
        </Grid>

        <Grid size={12}>
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <div>
              <Button
                variant="contained"
                color="primary"
                sx={{ ml: "5px", textTransform: "none" }}
                onClick={() => {
                  React.startTransition(() => {
                    saveCurrentCode({ code, filename });
                  });
                }}
                endIcon={<SaveIcon />}
                disabled={!isChanged || saving}
              >
                {saving ? "Saving..." : "Save"}
              </Button>
              <Box sx={{ ml: 0.7, mt: 1 }}>{visibleSaveError ? <Alert severity="error">{visibleSaveError}</Alert> : ""}</Box>
            </div>
          </Box>
        </Grid>
      </Grid>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={openSnackbar}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={4000}
        key={"experiment-profile-editor-snackbar"}
      />
    </>
  );
}

function getPageCopy(mode) {
  if (mode === "edit") {
    return {
      heading: "Edit Experiment Profile",
      docsSentence: "Learn more about editing",
    };
  }

  return {
    heading: "Create Experiment Profile",
    docsSentence: "Learn more about creating",
  };
}

export default function ExperimentProfileEditorPage({ mode, title }) {
  const location = useLocation();
  const { profileFilename } = useParams();
  const [openCapabilities, setOpenCapabilities] = React.useState(false);
  const [loadedCode, setLoadedCode] = React.useState("");
  const [loading, setLoading] = React.useState(mode === "edit");
  const [loadError, setLoadError] = React.useState("");

  const pageCopy = getPageCopy(mode);
  const createInitialCode = location.state?.initialCode ?? DEFAULT_CODE;
  const createInitialFilename = location.state?.initialFilename ?? "";
  const editorKey = mode === "edit" ? `edit:${profileFilename}` : `create:${location.key}`;

  React.useEffect(() => {
    document.title = title;
  }, [title]);

  React.useEffect(() => {
    if (mode !== "edit") {
      return;
    }

    const controller = new AbortController();

    setLoading(true);
    setLoadError("");
    setLoadedCode("");

    fetch(`/api/experiment_profiles/${encodeURIComponent(profileFilename)}`, {
      method: "GET",
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load profile source");
        }
        return response.text();
      })
      .then((text) => {
        setLoadedCode(text);
      })
      .catch((error) => {
        if (error.name === "AbortError") {
          return;
        }
        setLoadError(error.message || "Failed to load profile source");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [mode, profileFilename]);

  const handleSave = async ({ code, filename }) => {
    if (mode === "edit") {
      await saveExistingExperimentProfile(code, profileFilename);
      return;
    }

    await saveNewExperimentProfile(code, filename);
  };

  const initialCode = mode === "edit" ? loadedCode : createInitialCode;
  const initialFilename = mode === "edit" ? profileFilename : createInitialFilename;

  return (
    <Grid container spacing={2}>
      <Grid
        size={{
          md: 12,
          xs: 12,
        }}
      >
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2" sx={{ fontWeight: "bold" }}>
            {pageCopy.heading}
          </Typography>
          <Box>
            <Button sx={{ textTransform: "none", mr: 1 }} variant="text" onClick={() => setOpenCapabilities(true)}>
              <SearchIcon fontSize="small" sx={textIcon}/> Search jobs and automations
            </Button>
            <Button component={Link} to="/experiment-profiles" sx={{ textTransform: "none" }}>
              <ArrowBackIcon fontSize="small" sx={textIcon}/> Back
            </Button>
          </Box>
        </Box>

        <Card sx={{ mt: 2 }}>
          <CardContent sx={{ p: 2 }}>
            {loading && (
              <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
                <CircularProgress size={33} />
              </Box>
            )}
            {!loading && loadError && <Alert severity="error">{loadError}</Alert>}
            {!loading && !loadError && (
              <ExperimentProfileEditorContent
                key={editorKey}
                initialCode={initialCode}
                initialFilename={initialFilename}
                filenameEditable={mode !== "edit"}
                onSave={handleSave}
              />
            )}
          </CardContent>
        </Card>

        <Box component="p" sx={{ textAlign: "center", mt: "30px" }}>
          {pageCopy.docsSentence}{" "}
          <a href="https://docs.pioreactor.com/user-guide/create-edit-experiment-profiles" target="_blank" rel="noopener noreferrer">
            experiment profile schemas
          </a>
          .
        </Box>

        <Dialog
          open={openCapabilities}
          onClose={() => setOpenCapabilities(false)}
          fullWidth
          maxWidth="md"
          slotProps={{
            paper: {
              sx: {
                minHeight: "80%",
                maxHeight: "80%",
              },
            },
          }}
        >
          <DialogTitle>
            Search jobs and automations
            <IconButton
              aria-label="close"
              onClick={() => setOpenCapabilities(false)}
              sx={{
                position: "absolute",
                right: 8,
                top: 8,
                color: (theme) => theme.palette.grey[500],
              }}
              size="large"
            >
              <CloseIcon />
            </IconButton>
          </DialogTitle>
          <DialogContent sx={{ height: "100%" }}>
            <CapabilitiesPanel />
          </DialogContent>
        </Dialog>
      </Grid>
    </Grid>
  );
}
