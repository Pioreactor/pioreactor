import React, { useState } from 'react';

import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Alert from '@mui/material/Alert';
import CardContent from '@mui/material/CardContent';
import SaveIcon from '@mui/icons-material/Save';
import TextField from '@mui/material/TextField';
import { Link, useParams } from 'react-router';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import Snackbar from './components/Snackbar';
import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import 'prismjs/components/prism-yaml';
import {DisplayProfile, DisplayProfileError} from "./components/DisplayProfile"
import CapabilitiesPanel from './components/CapabilitiesPanel';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import IconButton from '@mui/material/IconButton';
import SearchIcon from '@mui/icons-material/Search';
import CloseIcon from '@mui/icons-material/Close';
import { convertYamlToProfilePreview } from "./utils/experimentProfilePreview";

const formatProfileSaveError = (payload) => {
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
};

export const EditExperimentProfilesContent = ({ initialCode, profileFilename }) => {
  const [code, setCode] = useState(initialCode);
  const [parsedCode, setParsedCode] = useState(() => convertYamlToProfilePreview(initialCode));
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [isChanged, setIsChanged] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [isError, setIsError] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const onTextChange = newCode => {
    setCode(newCode);
    setIsChanged(true);
    try {
      setParsedCode(convertYamlToProfilePreview(newCode));
    } catch (error) {
      //pass
    }
  };

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  const saveCurrentCode = () => {

    setIsError(false);
    fetch(`/api/experiment_profiles/${encodeURIComponent(profileFilename)}`, {
      method: "PATCH",
      body: JSON.stringify({ body: code }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(parsedJson => {
            throw new Error(formatProfileSaveError(parsedJson));
          });
        }
        setIsChanged(false);
        setOpenSnackbar(true);
        setSnackbarMsg(`Experiment profile ${profileFilename} saved.`);
      })
      .catch(err => {
        setIsError(true);
        setErrorMsg(err.message || 'Network error: failed to save profile');
        setIsChanged(true);
      });
  };

  const displayedProfile = () => {
    if (parsedCode.error) {
      return <DisplayProfileError error={parsedCode.error} />;
    } else {
      return <DisplayProfile data={parsedCode.data} comments={parsedCode.comments} />;
    }
  };

  return (
    <>
      <Grid container spacing={0}>

        <Grid size={12}>
          <div style={{ width: "100%", margin: "10px", display: "flex", justifyContent: "space-between" }}>
            <TextField
              label="Filename"
              value={profileFilename }
              disabled={true}
              style={{ width: "350px" }}
            />
          </div>
        </Grid>

        <Grid size={6}>
          <div style={{
            tabSize: "4ch",
            border: "1px solid #ccc",
            margin: "10px auto 10px auto",
            position: "relative",
            width: "98%",
            height: "350px",
            overflow: "auto",
            borderRadius: "4px",
            flex: 1
          }}>
          <Editor
            value={code}
            onValueChange={onTextChange}
            highlight={code => highlight(code, languages.yaml)}
            padding={10}
            style={{
              fontSize: "14px",
              fontFamily: 'monospace',
              backgroundColor: "hsla(0, 0%, 100%, .5)",
              borderRadius: "4px",
              minHeight: "100%"
            }}
          />
          </div>
        </Grid>

        <Grid size={6}>
          {code && displayedProfile()}
        </Grid>

        <Grid size={12}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div>
              <Button
                variant="contained"
                color="primary"
                style={{ marginLeft: "5px", textTransform: 'none' }}
                onClick={saveCurrentCode}
                endIcon={<SaveIcon />}
                disabled={!isChanged}
              >
                Save
              </Button>
              <Box sx={{ ml: 0.7, mt: 1 }}>{isError ? <Alert severity="error">{errorMsg}</Alert> : ""}</Box>
            </div>
          </div>
        </Grid>

      </Grid>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={openSnackbar}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={4000}
        key={"edit-profile-snackbar"}
      />
    </>
  );
};


function ProfilesContainer(){
  const {profileFilename} = useParams();
  const [source, setSource] = React.useState('')
  const [isLoadingSource, setIsLoadingSource] = React.useState(true)
  const [openCapabilities, setOpenCapabilities] = React.useState(false)

  React.useEffect(() => {
    let isActive = true;

    setIsLoadingSource(true);
    setSource('');

    fetch(`/api/experiment_profiles/${encodeURIComponent(profileFilename)}`, {
          method: "GET",
      }).then(res => {
        if (res.ok) {
          return res.text();
        }
        return '';
      }).then(text => {
        if (!isActive) {
          return;
        }
        setSource(text || '')
        setIsLoadingSource(false)
      }).catch(() => {
        if (!isActive) {
          return;
        }
        setSource('')
        setIsLoadingSource(false)
      })

    return () => {
      isActive = false;
    };
  }, [profileFilename])

  return(
    <React.Fragment>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2" sx={{ fontWeight: "bold" }}>
          Edit Experiment Profile
        </Typography>
        <Box>
          <Button sx={{ textTransform: 'none', mr: 1 }} variant="text" startIcon={<SearchIcon />} onClick={() => setOpenCapabilities(true)}>
            Search jobs and automations
          </Button>
          <Button to={`/experiment-profiles`} component={Link} sx={{ textTransform: 'none' }}>
            <ArrowBackIcon sx={{ verticalAlign: "middle", mr: 0.5 }} fontSize="small"/> Back
          </Button>
        </Box>
      </Box>
      <Card sx={{marginTop: "15px"}}>
        <CardContent sx={{padding: "10px"}}>
          {!isLoadingSource && (
            <EditExperimentProfilesContent
              key={profileFilename}
              initialCode={source}
              profileFilename={profileFilename}
            />
          )}
        </CardContent>
      </Card>
      <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about editing <a href="https://docs.pioreactor.com/user-guide/create-edit-experiment-profiles" target="_blank" rel="noopener noreferrer">experiment profile schemas</a>.</p>

      <Dialog
        open={openCapabilities}
        onClose={() => setOpenCapabilities(false)}
        fullWidth maxWidth="md"
        slotProps={{ paper: { sx: {
        minHeight: '80%',
        maxHeight: '80%',
      }}}}>
        <DialogTitle>
          Search jobs and automations
          <IconButton
            aria-label="close"
            onClick={() => setOpenCapabilities(false)}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
              color: (theme) => theme.palette.grey[500],
            }}
            size="large">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ height: '100%' }}>
          <CapabilitiesPanel />
        </DialogContent>
      </Dialog>
    </React.Fragment>
)}


function EditProfile(props) {

    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <ProfilesContainer />
        </Grid>
      </Grid>
    );
}

export default EditProfile;
