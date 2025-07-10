import React, { useState, useEffect } from 'react';
import yaml from "js-yaml";


import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import SaveIcon from '@mui/icons-material/Save';
import TextField from '@mui/material/TextField';
import { Link, useParams } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import Snackbar from '@mui/material/Snackbar';
import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import 'prismjs/components/prism-yaml';
import {DisplayProfile, DisplayProfileError} from "./components/DisplayProfile"

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

const EditExperimentProfilesContent = ({ initialCode, profileFilename }) => {
  const [code, setCode] = useState("");
  const [parsedCode, setParsedCode] = useState({});
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [isChanged, setIsChanged] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [isError, setIsError] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (initialCode !== code) {
      setCode(initialCode);
      try {
        setParsedCode(convertYamlToJson(initialCode));
      } catch (error) {
        //pass
      }
    }
  }, [initialCode]);

  const onTextChange = newCode => {
    setCode(newCode);
    setIsChanged(true);
    try {
      setParsedCode(convertYamlToJson(newCode));
    } catch (error) {
      //pass
    }
  };

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  const saveCurrentCode = () => {

    setIsError(false);
    fetch("/api/contrib/experiment_profiles", {
      method: "PATCH",
      body: JSON.stringify({ body: code, filename: profileFilename }),
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
      return <DisplayProfile data={parsedCode} />;
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
        key={"edit-profile-snackbar"}
      />
    </>
  );
};


function ProfilesContainer(){
  const {profileFilename} = useParams();
  const [source, setSource] = React.useState('')

  React.useEffect(() => {
    fetch(`/api/contrib/experiment_profiles/${profileFilename}`, {
          method: "GET",
      }).then(res => {
        if (res.ok) {
          return res.text();
        }
      }).then(text => {
        setSource(text)
      })
  })

  return(
    <React.Fragment>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2" sx={{ fontWeight: "bold" }}>
          Edit Experiment Profile
        </Typography>
        <Button to={`/experiment-profiles`} component={Link} sx={{ textTransform: 'none' }}>
          <ArrowBackIcon sx={{ verticalAlign: "middle", mr: 0.5 }} fontSize="small"/> Back
        </Button>
      </Box>
      <Card sx={{marginTop: "15px"}}>
        <CardContent sx={{padding: "10px"}}>
          <EditExperimentProfilesContent initialCode={source} profileFilename={profileFilename}/>
          <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about editing <a href="https://docs.pioreactor.com/user-guide/create-edit-experiment-profiles" target="_blank" rel="noopener noreferrer">experiment profile schemas</a>.</p>
        </CardContent>
      </Card>
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
