import React from "react";

import FormControl from '@mui/material/FormControl';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import { makeStyles } from '@mui/styles';
import Select from '@mui/material/Select';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {getConfig} from "./utilities"
import { Link } from 'react-router-dom';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import DisplayProfile from "./components/DisplayProfile"
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import CloseIcon from '@mui/icons-material/Close';


const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  formControl: {
    margin: theme.spacing(2),
  },
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "10px"
  },
  pos: {
    marginBottom: 0,
  },
  caption: {
    marginLeft: "30px",
    maxWidth: "650px"
  },
  headerMenu: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: "5px",
    [theme.breakpoints.down('lg')]:{
      flexFlow: "nowrap",
      flexDirection: "column",
    }
  },
  headerButtons: {display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}

}));


function ExperimentProfilesContent(props) {

  const [experimentProfilesAvailable, setExperimentProfilesAvailable] = React.useState([])
  const [selectedExperimentProfile, setSelectedExperimentProfile] = React.useState('')
  const [confirmed, setConfirmed] = React.useState(false)

  React.useEffect(() => {
    fetch("/api/experiment_profiles")
      .then(response => {
        return response.json();
      })
      .then(profiles => {
        const profilesByKey = profiles.reduce((acc, cur) => ({ ...acc, [cur.file]: cur.experimentProfile}), {})
        setExperimentProfilesAvailable(profilesByKey)
        setSelectedExperimentProfile(Object.keys(profilesByKey)[0])
      })
  }, [])

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

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

  const onStop = () => {
    fetch(`/api/stop/${props.config['cluster.topology']['leader_hostname']}/experiment_profile`,{
          method: "PATCH",
      })
  }

  const onSelectExperimentProfileChange = (e) =>
    setSelectedExperimentProfile(e.target.value)


  return (
      <Grid container spacing={1}>
        <Grid item xs={6}>
          <div style={{width: "100%", margin: "10px", display: "flex", justifyContent:"space-between"}}>
            <FormControl style={{minWidth: "300px"}}>
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
              </Select>
            </FormControl>
          </div>
        </Grid>
        <Grid item xs={6} />

        <Grid item xs={12}>
          {selectedExperimentProfile !== "" &&
            <DisplayProfile data={experimentProfilesAvailable[selectedExperimentProfile]} />
          }
        </Grid>
        <div style={{display: "flex", justifyContent: "flex-end"}}>
            <Button
              variant="contained"
              color="primary"
              style={{marginLeft: "20px"}}
              onClick={onSubmit}
              endIcon={ <PlayArrowIcon /> }
              disabled={(selectedExperimentProfile === "") || confirmed}
            >
                Execute
           </Button>
          <Button
            component={Link}
            target="_blank"
            rel="noopener noreferrer"
            to={`/api/experiment_profiles/${selectedExperimentProfile.split('/').pop()}`}
            variant="text"
            size="small"
            color="primary"
            aria-label="view source code"
            style={{marginLeft: "15px"}}
            disabled={selectedExperimentProfile === ""}
            endIcon={<OpenInNewIcon />}
          >
            View source
          </Button>
          <Button
            variant="text"
            color="secondary"
            style={{marginLeft: "20px"}}
            onClick={onStop}
            endIcon={ <CloseIcon /> }
          >
            Stop
         </Button>
        </div>
      </Grid>
  );
}

function ProfilesContainer(props){
  const classes = useStyles();

  return(
    <React.Fragment>
      <div>
        <div>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Experiment Profiles
            </Box>
          </Typography>
        </div>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <ExperimentProfilesContent config={props.config}/>
          <p style={{textAlign: "center", marginTop: "30px"}}><span role="img" aria-labelledby="Note">💡</span> Learn more about <a href="https://docs.pioreactor.com/user-guide/experiment-profiles" target="_blank" rel="noopener noreferrer">experiment profiles</a>.</p>
        </CardContent>
      </Card>
    </React.Fragment>
)}


function Profiles(props) {
    const [config, setConfig] = React.useState({})

    React.useEffect(() => {
      getConfig(setConfig)
    }, [])

    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <ProfilesContainer config={config}/>
          </Grid>
        </Grid>
    )
}

export default Profiles;
