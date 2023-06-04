import React from "react";
import Grid from '@mui/material/Grid';
import {useState, useEffect} from "react";
import { makeStyles } from '@mui/styles';
import Button from "@mui/material/Button";
import DisplayProfile from "./DisplayProfile"
import { Link } from 'react-router-dom';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import FormControl from '@mui/material/FormControl';
import MenuItem from '@mui/material/MenuItem';
import Box from '@mui/material/Box';
import CheckIcon from '@mui/icons-material/Check';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';

const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  button: {
    marginRight: theme.spacing(1),
  },
  textField:{
    marginTop: theme.spacing(1),
    marginBottom: theme.spacing(1),
    width: "100%"
  },
}));


function RunFromExperimentProfile(props){
  const classes = useStyles();
  const [experimentProfilesAvailable, setExperimentProfilesAvailable] = React.useState([])
  const [selectedExperimentProfile, setSelectedExperimentProfile] = React.useState('')
  const [confirmed, setConfirmed] = useState(false)

  useEffect(() => {
    fetch("/api/experiment_profiles")
      .then(response => {
        return response.json();
      })
      .then(profiles => {
        setExperimentProfilesAvailable(profiles.reduce((acc, cur) => ({ ...acc, [cur.file]: cur.experimentProfile}), {}))
      })
  }, [])


  const onSelectExperimentProfileChange = (e) =>
    setSelectedExperimentProfile(e.target.value)

  const onSubmit = () => {
    fetch(`/api/run/${props.config['cluster.topology']['leader_hostname']}/experiment_profile`,{
          method: "PATCH",
          body: JSON.stringify({args: ['execute', selectedExperimentProfile]}),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
      })
    setConfirmed(true)
  }

  return (
    <div className={classes.root}>

      <Grid container spacing={1}>

        <Grid item xs={12}>
          <p> Experiment profiles are an optional ways to automatically start, end, and change activities for an experiment. Choose an experiment profile to run: </p>
          <Box sx={{ minWidth: 120 }}>
            <FormControl fullWidth>
              <InputLabel id="profileSelect" variant="standard">Experiment profile (optional)</InputLabel>
              <Select
                labelId="profileSelect"
                variant="standard"
                value={selectedExperimentProfile}
                onChange={onSelectExperimentProfileChange}
                label="Experiment profile (optional)"
              >
                {Object.keys(experimentProfilesAvailable).map((file) => {
                  const profile = experimentProfilesAvailable[file]
                  return <MenuItem key={file} value={file}>{profile.experiment_profile_name} (from {file.split('/').pop()})</MenuItem>
                  }
                )}
                <MenuItem value=""><em>None</em></MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Grid>

        <Grid item xs={12}>
          {selectedExperimentProfile !== "" &&
            <DisplayProfile data={experimentProfilesAvailable[selectedExperimentProfile]} />
          }
        </Grid>

        <Grid item xs={12} lg={4}/>
        <Grid item xs={12} lg={8}>
          <div style={{display: "flex", justifyContent: "flex-end"}}>
            <Button
              component={Link}
              target="_blank"
              rel="noopener noreferrer"
              to={`/api/experiment_profiles/${selectedExperimentProfile.split('/').pop()}`}
              variant="text"
              size="small"
              color="primary"
              aria-label="view source code"
              style={{marginRight: "10px"}}
              disabled={selectedExperimentProfile === ""}
            >
              View source
            </Button>
            <Button
              variant="contained"
              color="primary"
              onClick={onSubmit}
              endIcon={confirmed ? <CheckIcon /> : <PlayArrowIcon /> }
              disabled={(selectedExperimentProfile === "") || confirmed}
            >
                 {confirmed ? "Executed" : "Execute"}
             </Button>
          </div>
        </Grid>

      </Grid>

    </div>
  );}


export default RunFromExperimentProfile;
