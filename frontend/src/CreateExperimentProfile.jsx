import {useEffect, useState, Fragment } from 'react';
import yaml from "js-yaml";

import FormControl from '@mui/material/FormControl';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import SaveIcon from '@mui/icons-material/Save';
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import { Link, useLocation } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import Snackbar from '@mui/material/Snackbar';
import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import 'prismjs/components/prism-yaml'; // You can add more languages or change it
import {DisplayProfile, DisplayProfileError} from "./components/DisplayProfile"
import CapabilitiesPanel from './components/CapabilitiesPanel';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import SearchIcon from '@mui/icons-material/Search';

function addQuotesToBrackets(input) {
    return input.replace(/(\${0}){{(.*?)}}/g, (match, p1, p2, offset, string) => {
        if (string[offset - 1] !== '$') {
            return `"{{${p2}}}"`;
        }
        return match;
    });
}

function convertYamlToJson(yamlString){
  try{
    return yaml.load(addQuotesToBrackets(yamlString))
  } catch (error) {
    console.log(error)
    return {error: error.message}
  }
}

const EditExperimentProfilesContent = () => {
  const DEFAULT_CODE = `experiment_profile_name:

metadata:
  author:
  description:
`;
  const DEFAULT_FILENAME = "";

  const location = useLocation();
  const { initialCode: locInitialCode, initialFilename: locInitialFilename } = location.state || {};
  const startingCode = locInitialCode ?? DEFAULT_CODE;
  const startingFilename = locInitialFilename ?? DEFAULT_FILENAME;

  const [code, setCode] = useState(startingCode);
  const [filename, setFilename] = useState(startingFilename);
  const [parsedCode, setParsedCode] = useState(convertYamlToJson(startingCode));
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [isChanged, setIsChanged] = useState(false);
  const [isError, setIsError] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const onTextChange = newCode => {
    setCode(newCode);
    setIsChanged(true);
    try {
      setParsedCode(convertYamlToJson(newCode));
    } catch (error) {
      //pass
    }
  };

  const onFilenameChange = e => {
    setFilename(e.target.value.replace(/ |\/|\.|\\/g, "_"));
    setIsChanged(true);
  };

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  const saveCurrentCode = () => {
    if (filename === "") {
      setIsError(true);
      setErrorMsg("Filename can't be blank.");
      return;
    }

    setIsError(false);
    fetch("/api/contrib/experiment_profiles", {
      method: "POST",
      body: JSON.stringify({ body: code, filename: filename + '.yaml' }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(parsedJson => {
            throw new Error(parsedJson.error || 'Failed to save profile');
          });
        }
        setIsChanged(false);
        setOpenSnackbar(true);
        setSnackbarMsg(`Experiment profile ${filename}.yaml saved.`);
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
      return <DisplayProfile data={parsedCode} />;
    }
  };


  return (
    <>
      <Grid container spacing={0}>
        <Grid size={12}>
          <div style={{ width: "100%", margin: "10px", display: "flex", justifyContent: "space-between" }}>
            <FormControl>
              <TextField
                label="Filename"
                onChange={onFilenameChange}
                required
                value={filename}
                style={{ width: "320px" }}
                InputProps={{
                  endAdornment: <InputAdornment position="end">.yaml</InputAdornment>,
                }}
              />
            </FormControl>
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
              borderRadius: "3px",
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
              <p style={{ marginLeft: "10px" }}>{isError ? <Box color="error.main">{errorMsg}</Box> : ""}</p>
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
        key={"create-profile-snackbar"}
      />
    </>
  );
};

function ProfilesContainer(){
  const [openCapabilities, setOpenCapabilities] = useState(false)
  return(
    <>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2" sx={{ fontWeight: "bold" }}>
          Create Experiment Profile
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
      <Card sx={{mt: 2}}>
        <CardContent sx={{p: 2}}>
          <EditExperimentProfilesContent />

        </CardContent>
      </Card>

      <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about creating <a href="https://docs.pioreactor.com/user-guide/create-edit-experiment-profiles" target="_blank" rel="noopener noreferrer">experiment profile schemas</a>.</p>

      <Dialog open={openCapabilities} onClose={() => setOpenCapabilities(false)} fullWidth maxWidth="md"
      PaperProps={{ style: {
        minHeight: '80%',
        maxHeight: '80%',
      }}}> >
        <DialogTitle>Search jobs and automations</DialogTitle>
        <DialogContent sx={{ height: '100%' }}>
          <CapabilitiesPanel />
        </DialogContent>
      </Dialog>
    </>
)}


function CreateNewProfile(props) {

    useEffect(() => {
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

export default CreateNewProfile;
