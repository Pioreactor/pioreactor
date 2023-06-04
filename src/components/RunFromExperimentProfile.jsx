import React from "react";
import Grid from '@mui/material/Grid';
import FlareIcon from '@mui/icons-material/Flare';
import { Client, Message } from "paho-mqtt";
import clsx from 'clsx';
import {useState, useEffect} from "react";
import { makeStyles } from '@mui/styles';
import Button from "@mui/material/Button";
import TextField from '@mui/material/TextField';
import Divider from '@mui/material/Divider';
import PioreactorIcon from "./PioreactorIcon"
import { Link } from 'react-router-dom';
import EditIcon from '@mui/icons-material/Edit';
import {getRelabelMap} from "../utilities"
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import FormControl from '@mui/material/FormControl';
import MenuItem from '@mui/material/MenuItem';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import CheckIcon from '@mui/icons-material/Check';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';

const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  cardContent: {
    padding: "10px"
  },
  button: {
    marginRight: theme.spacing(1),
  },
  textField:{
    marginTop: theme.spacing(1),
    marginBottom: theme.spacing(1),
    width: "100%"
  },
  DisplayProfileCard: {
    marginTop: "20px",
    marginBottom: "20px",
    maxHeight: "360px",
    overflow: "auto",
    backgroundColor: "rgb(242,242,242)"
  },
  cardContent: {
    padding: "10px 20px 20px 20px"
  },
  indent: {
    textIdent: "15px"
  }
}));


const DisplayProfile = ({ data }) => {
  const classes = useStyles();
  return (
    <Card className={classes.DisplayProfileCard}>
      <CardContent className={classes.cardContent}>
        <Typography variant="h6">
          {data.experiment_profile_name}
        </Typography>
        <Typography variant="body2">
            <b>Author:</b> {data.metadata.author}
        </Typography>
        <Typography variant="body2">
            <b>Description:</b> {data.metadata.description}
        </Typography>
        <Typography variant="body2">
            <b>Aliases:</b>
        </Typography>
        {Object.keys(data.labels).map(worker => (
            <Typography key={worker} variant="body2" style={{ marginLeft: '2em' }}>
                {worker}: {data.labels[worker]}
            </Typography>
        ))}

        <Typography variant="body2">
            <b>Common:</b>
        </Typography>
        {data.common && Object.keys(data.common).map(job => (
            <>
              <Typography key={job} variant="body2" style={{ marginLeft: '2em' }}>
                  <b>Job</b>: {job}
              </Typography>
              {data.common[job].actions.map((action, index) => (
                  <>
                    <Typography key={`common-action-${index}`} variant="body2" style={{ marginLeft: '4em' }}>
                        <b>Action {index + 1}</b>: {action.type} after {action.hours_elapsed} hours
                    </Typography>
                      {Object.keys(action.options).map((option, index) => (
                      <Typography key={`common-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '8em' }}>
                        {option}: {action.options[option]}
                      </Typography>
                      ))}
                  </>
              ))}
            </>
        ))}

        {data.pioreactors && Object.keys(data.pioreactors).map(pioreactor => (
            <>
                <Typography key={pioreactor} variant="body2">
                    <b>Pioreactor</b>: {pioreactor}
                </Typography>
                {Object.keys(data.pioreactors[pioreactor].jobs).map(job => (
                    <>
                      <Typography key={`${pioreactor}-${job}`}  variant="body2" style={{ marginLeft: '2em' }}>
                          <b>Job</b>: {job}
                      </Typography>
                      {data.pioreactors[pioreactor].jobs[job].actions.map((action, index) => (
                          <>
                            <Typography key={`${pioreactor}-action-${index}`} variant="body2" style={{ marginLeft: '4em' }}>
                                <b>Action {index + 1}</b>: {action.type} after {action.hours_elapsed} hours
                            </Typography>
                              {Object.keys(action.options).map( (option, index) => (
                              <Typography key={`${pioreactor}-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '8em' }}>
                                {option}: {action.options[option]}
                              </Typography>
                              ))}
                          </>
                      ))}
                    </>
                ))}
            </>
        ))}
      </CardContent>
    </Card>
  );
};



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

        <Grid item xs={1}/>
        <Grid item xs={10}>
          <p> Experiment profiles are an optional ways to automatically start, end, and change acitivities for an experiment.</p>

          <p>Choose an experiment profile to run: </p>
          <Box sx={{ minWidth: 120 }}>
            <FormControl fullWidth>
              <InputLabel id="profileSelect" variant="standard">Experiment profile</InputLabel>
              <Select
                labelId="profileSelect"
                variant="standard"
                value={selectedExperimentProfile}
                onChange={onSelectExperimentProfileChange}
                label="Experiment profile"
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
        <Grid item xs={1}/>

        <Grid item xs={1}/>
        <Grid item xs={10}>
          {selectedExperimentProfile !== "" &&
            <DisplayProfile data={experimentProfilesAvailable[selectedExperimentProfile]} />
          }
        </Grid>
        <Grid item xs={1}/>

        <Grid item xs={12} lg={4}/>
        <Grid item xs={12} lg={8}>
          <div style={{display: "flex", justifyContent: "flex-end"}}>
            <Button
              variant="contained"
              color="primary"
              onClick={onSubmit}
              endIcon={confirmed ? <CheckIcon /> : <PlayArrowIcon /> }
              disabled={selectedExperimentProfile === ""}
            >
                 {confirmed ? "Executed!" : "Execute now"}
             </Button>
          </div>
        </Grid>

      </Grid>

    </div>
  );}


export default RunFromExperimentProfile;
