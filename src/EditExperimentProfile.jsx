import React, { useState, useEffect } from 'react';
import yaml from "js-yaml";


import FormControl from '@mui/material/FormControl';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import SaveIcon from '@mui/icons-material/Save';
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import { Link } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import Snackbar from '@mui/material/Snackbar';
import { useSearchParams } from "react-router-dom";
import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import 'prismjs/components/prism-yaml'; // You can add more languages or change it
import {DisplayProfile} from "./components/DisplayProfile"

function addQuotesToBrackets(input) {
    return input.replace(/(\${0}){{(.*?)}}/g, (match, p1, p2, offset, string) => {
        if (string[offset - 1] !== '$') {
            return `"{{${p2}}}"`;
        }
        return match;
    });
}

function convertYamlToJson(yamlString){
  return yaml.load(addQuotesToBrackets(yamlString))
}

const EditExperimentProfilesContent = ({ initialCode, filename }) => {
  const [code, setCode] = useState(initialCode);
  const [parsedCode, setParsedCode] = useState(convertYamlToJson(initialCode));
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [isChanged, setIsChanged] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [isError, setIsError] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (initialCode !== code) {
      setCode(initialCode);
      setParsedCode(convertYamlToJson(initialCode));
    }
  }, [initialCode]);

  const onTextChange = newCode => {
    setCode(newCode);
    setIsChanged(true);
    try {
      setParsedCode(convertYamlToJson(newCode))
    } catch (error) {
      if (error.name === "YAMLException") {
        // do nothing?
      }
    }
  };


  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  const saveCurrentCode = () => {
    if (filename === "") {
      setIsError(true);
      setErrorMsg("Filename can't be blank");
      return;
    }

    setIsError(false);
    setIsChanged(false);
    fetch("/api/contrib/experiment_profiles", {
      method: "PATCH",
      body: JSON.stringify({ body: code, filename: filename + '.yaml' }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
      .then(res => {
        if (res.ok) {
          setOpenSnackbar(true);
          setSnackbarMsg(`Experiment profile ${filename}.yaml saved.`);
        } else {
          res.json().then(parsedJson => {
            setErrorMsg(parsedJson['msg']);
            setIsError(true);
          });
        }
      });
  };

  const displayedProfile = () => {
    return <DisplayProfile data={parsedCode} />;
  };


  return (
    <>
      <Grid container spacing={1}>

        <Grid item xs={12}>
          <div style={{ width: "100%", margin: "10px", display: "flex", justifyContent: "space-between" }}>
            <TextField
              label="Filename"
              value={filename + '.yaml'}
              disabled={true}
              style={{ width: "250px" }}
            />
          </div>
        </Grid>

        <Grid item xs={6}>
          <div style={{
            tabSize: "4ch",
            border: "1px solid #ccc",
            margin: "10px auto 10px auto",
            position: "relative",
            width: "98%",
            height: "350px",
            overflow: "auto",
            flex: 1
          }}>
          {(code !== null) && (code !== "") &&
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
          }
          </div>
        </Grid>

        <Grid item xs={6}>
          {code && displayedProfile()}
        </Grid>

        <Grid item xs={12}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div>
              <Button
                variant="contained"
                color="primary"
                style={{ marginLeft: "20px", textTransform: 'none' }}
                onClick={saveCurrentCode}
                endIcon={<SaveIcon />}
                disabled={!isChanged}
              >
                Save
              </Button>
              <p style={{ marginLeft: "20px" }}>{isError ? <Box color="error.main">{errorMsg}</Box> : ""}</p>
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


function ProfilesContainer(props){
  const [queryParams, setQueryParams] = useSearchParams();
  const [source, setSource] = React.useState('')
  const filename = queryParams.get("profile")

  React.useEffect(() => {
    fetch(`/api/contrib/experiment_profiles/${filename}`, {
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
          <EditExperimentProfilesContent initialCode={source} filename={filename.split(".")[0]}/>
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
          <Grid item md={12} xs={12}>
            <ProfilesContainer />
          </Grid>
        </Grid>
    )
}

export default EditProfile;
