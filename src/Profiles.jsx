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
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import DisplayProfile from "./components/DisplayProfile"
import DisplaySourceCode from "./components/DisplaySourceCode"
import CloseIcon from '@mui/icons-material/Close';
import CodeIcon from '@mui/icons-material/Code';
import {runPioreactorJob} from "./utilities"
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import { Link } from 'react-router-dom';
import SelectButton from "./components/SelectButton";
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined';
import PlayCircleFilledIcon from '@mui/icons-material/PlayCircleFilled';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';

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
  headerButtons: {display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"},
  textIcon: {
    verticalAlign: "middle",
    margin: "0px 3px"
  },
}));


function ExperimentProfilesContent(props) {
  const classes = useStyles();

  const [experimentProfilesAvailable, setExperimentProfilesAvailable] = React.useState([])
  const [selectedExperimentProfile, setSelectedExperimentProfile] = React.useState('')
  const [confirmed, setConfirmed] = React.useState(false)
  const [viewSource, setViewSource] = React.useState(false)
  const [source, setSource] = React.useState("")
  const [dryRun, setDryRun] = React.useState(false)

  React.useEffect(() => {
    fetch("/api/contrib/experiment_profiles")
      .then(response => {
        return response.json();
      })
      .then(profiles => {
        const profilesByKey = profiles.reduce((acc, cur) => ({ ...acc, [cur.file]: cur.experimentProfile}), {})
        setExperimentProfilesAvailable(profilesByKey)
        setSelectedExperimentProfile(Object.keys(profilesByKey)[0] ?? "")
      })
  }, [])

  const onSubmit = () => runPioreactorJob(props.config['cluster.topology']?.leader_hostname, 'experiment_profile', ['execute', selectedExperimentProfile], dryRun ? {'dry-run': null} : {}, () => setConfirmed(true))


  const onStop = () => {
    fetch(`/api/stop/${props.config['cluster.topology']?.leader_hostname}/experiment_profile`,{
          method: "PATCH",
      })
  }

  const onSelectExperimentProfileChange = (e) => {
    setSelectedExperimentProfile(e.target.value)
    setViewSource(false)
  }

  const getSourceAndView = (e) => {
    if (!viewSource){
      fetch(`/api/contrib/experiment_profiles/${selectedExperimentProfile.split('/').pop()}`, {
            method: "GET",
        }).then(res => {
          if (res.ok) {
            return res.text();
          }
        }).then(text => {
          setSource(text)
        })
    }
    setViewSource(!viewSource)
  }


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
        <Grid item xs={3} />
        <Grid container xs={3} direction="column" alignItems="flex-end">
          <Grid item xs={6} />
          <Grid item xs={6} >
            <Button
              variant="text"
              size="small"
              color="primary"
              aria-label="edit source code"
              onClick={getSourceAndView}
              style={{marginRight: "10px", textTransform: "none"}}
              to={`/edit-experiment-profile?profile=${selectedExperimentProfile.split("/").pop()}`}
              component={Link}
            >
              <EditIcon fontSize="15" classes={{root: classes.textIcon}} /> Edit
            </Button>
            <Button
              variant="text"
              size="small"
              color="primary"
              aria-label="view source code"
              disabled={selectedExperimentProfile === ""}
              onClick={getSourceAndView}
              style={{marginRight: "10px", textTransform: "none"}}
            >
              <CodeIcon fontSize="15" classes={{root: classes.textIcon}} /> {viewSource ? "View description": "View source"}
            </Button>
          </Grid>

        </Grid>

        <Grid item xs={12}>
          {selectedExperimentProfile !== "" && !viewSource &&
            <DisplayProfile data={experimentProfilesAvailable[selectedExperimentProfile]} />
          }
          {selectedExperimentProfile !== "" && viewSource &&
            <DisplaySourceCode sourceCode={source}/>
          }
        </Grid>
        <div style={{display: "flex", justifyContent: "flex-end", marginLeft: "20px"}}>
            <SelectButton
              variant="contained"
              color="primary"
              value={dryRun ? "execute_dry_run" : "execute"}
              onClick={onSubmit}
              endIcon={ dryRun ? <PlayCircleOutlineIcon />  : <PlayArrowIcon />}
              disabled={(selectedExperimentProfile === "") || confirmed}
              onChange={({ target: { value } }) =>
                setDryRun(value === "execute_dry_run")
              }
            >
              <MenuItem value={"execute"}>Execute</MenuItem>
              <MenuItem value={"execute_dry_run"}>Execute dry-run</MenuItem>
           </SelectButton>
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
        <div className={classes.headerMenu}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Experiment Profiles
            </Box>
          </Typography>
          <div className={classes.headerButtons}>
            <Button to={`/create-experiment-profile`} component={Link} style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary">
              <AddIcon fontSize="15" classes={{root: classes.textIcon}}/> Create new profle
            </Button>
          </div>
        </div>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <ExperimentProfilesContent config={props.config}/>
          <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/experiment-profiles" target="_blank" rel="noopener noreferrer">experiment profiles</a>.</p>
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
