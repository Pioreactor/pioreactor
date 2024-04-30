import React from "react";
import moment from "moment";

import FormControl from '@mui/material/FormControl';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import { makeStyles } from '@mui/styles';
import Select from '@mui/material/Select';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Divider from '@mui/material/Divider';
import CardContent from '@mui/material/Card';
import {getConfig} from "./utilities"
import FormLabel from '@mui/material/FormLabel';
import MenuItem from '@mui/material/MenuItem';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import DisplayProfile from "./components/DisplayProfile"
import DisplaySourceCode from "./components/DisplaySourceCode"
import CloseIcon from '@mui/icons-material/Close';
import CodeIcon from '@mui/icons-material/Code';
import AddIcon from '@mui/icons-material/Add';
import Badge from '@mui/material/Badge';

import EditIcon from '@mui/icons-material/Edit';
import { Link, useNavigate } from 'react-router-dom';
import SelectButton from "./components/SelectButton";
import DeleteIcon from '@mui/icons-material/Delete';
import ViewTimelineOutlinedIcon from '@mui/icons-material/ViewTimelineOutlined';
import PlayDisabledIcon from '@mui/icons-material/PlayDisabled';
import { useConfirm } from 'material-ui-confirm';
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';
import ManageExperimentMenu from "./components/ManageExperimentMenu";
import {runPioreactorJob} from "./utilities"


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


function ExperimentProfilesContent({experiment, config, setRunningProfileName, setStartTime, runningProfileName}) {
  const classes = useStyles();
  const confirm = useConfirm();
  const navigate = useNavigate()

  const [experimentProfilesAvailable, setExperimentProfilesAvailable] = React.useState([])
  const [selectedExperimentProfile, setSelectedExperimentProfile] = React.useState('')
  const [confirmed, setConfirmed] = React.useState(false)
  const [viewSource, setViewSource] = React.useState(false)
  const [source, setSource] = React.useState("Loading...")
  const [dryRun, setDryRun] = React.useState(false)
  const [isProfileActive, setIsProfileActive] = React.useState(false)
  const {client, subscribeToTopic } = useMQTT();


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


  React.useEffect(() => {
    if (experiment && client){
      subscribeToTopic(`pioreactor/+/${experiment}/experiment_profile/+`, onMessage, "ExperimentProfilesContent")
    }

  },[experiment, client])


  const onMessage = (topic, message, packet) => {
    const payload = message.toString()
    const setting = topic.toString().split("/")[4]
    if ((setting === "$state") && (payload === "ready")){
      setIsProfileActive(true)
    }
    else if ((setting === "$state") && (payload === "disconnected")){
      setIsProfileActive(false)
      setConfirmed(false)
    }
    else if(setting === "experiment_profile_name") {
      if (payload === ""){
        setRunningProfileName(null)
      }
      else {
        setRunningProfileName(payload)
        const filename = Object.keys(experimentProfilesAvailable).find(k => experimentProfilesAvailable[k].experiment_profile_name === payload);
        setSelectedExperimentProfile(filename || "")
      }
    }
    else if(setting === "start_time_utc") {
      setStartTime(payload === "" ? null : payload)
    }
  }

  const onSubmit = () => runPioreactorJob(config['cluster.topology']?.leader_hostname, '$experiment' , 'experiment_profile', ['execute', selectedExperimentProfile, experiment], (dryRun ? {'dry-run': null} : {}), () => setConfirmed(true))

  const onStop = () => {
    confirm({
      description: 'Stopping this profile early will stop executing new actions end all actions started by it.',
      title: `Stop profile?`,
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
    }).then(() => {
      const topic = `pioreactor/${config['cluster.topology']?.leader_hostname}/${experiment}/experiment_profile/$state/set`
      client.publish(topic, "disconnected")
      setIsProfileActive(false)
    })

  }

  const onSelectExperimentProfileChange = (e) => {
    setSelectedExperimentProfile(e.target.value)
    setViewSource(false)
  }

  const deleteProfile = () => {
    confirm({
      title: `Are you sure you wish to delete this profile?`,
      description: "This action is permanent.",
      confirmationText: "Delete",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"}, //style: {textTransform: 'none'}
      }).then(() => {
        fetch(`/api/contrib/experiment_profiles/${selectedExperimentProfile.split('/').pop()}`, {
              method: "DELETE",
          }).then(res => {
              if (res.ok) {
                navigate(0);
              }
          })
      }
    )
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
              <FormLabel component="legend">Experiment profile</FormLabel>
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
        <Grid item xs={2} />
        <Grid container item xs={4} direction="column" alignItems="flex-end">
          <Grid item xs={4} />
          <Grid item xs={8} >
            <Button
              variant="text"
              size="small"
              color="primary"
              aria-label="edit source code"
              style={{textTransform: "none"}}
              to={`/edit-experiment-profile?profile=${(selectedExperimentProfile || "").split("/").pop()}`}
              component={Link}
              disabled={ selectedExperimentProfile === ''}
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
              style={{textTransform: "none"}}
            >
              <CodeIcon fontSize="15" classes={{root: classes.textIcon}} /> {viewSource ? "View description": "View source"}
            </Button>
            <Button
              variant="text"
              size="small"
              color="secondary"
              aria-label="delete profile"
              onClick={deleteProfile}
              style={{marginRight: "10px", textTransform: "none"}}
              disabled={selectedExperimentProfile === ''}

            >
              <DeleteIcon fontSize="15" classes={{root: classes.textIcon}} /> Delete
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
              endIcon={dryRun ? <PlayDisabledIcon />  : <PlayArrowIcon />}
              style={{}}
              disabled={confirmed || (isProfileActive)}
              onChange={({target: { value } }) =>
                setDryRun(value === "execute_dry_run")
              }
            >
              <MenuItem value={"execute"}>Run profile</MenuItem>
              <MenuItem value={"execute_dry_run"}>Dry-run profile</MenuItem>
           </SelectButton>
          <Button
            variant="text"
            color="secondary"
            style={{marginLeft: "20px",textTransform: 'none'}}
            onClick={onStop}
            endIcon={ <CloseIcon /> }
            disabled={!isProfileActive}
          >
            Stop early
         </Button>
        </div>
      </Grid>
  );
}

function ProfilesContainer({experiment, config}){
  const classes = useStyles();
  const [runningProfileName, setRunningProfileName] = React.useState(null)
  const [startTime, setStartTime] = React.useState(null)

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
            <Divider orientation="vertical" flexItem variant="middle"/>
            <ManageExperimentMenu experiment={experiment}/>
          </div>
        </div>
        <Divider/>
        <div style={{margin: "10px 2px 10px 2px", display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
          <Typography variant="subtitle2" style={{flexGrow: 1}}>
            <div style={{display:"inline"}}>
              <Box fontWeight="fontWeightBold" style={{display:"inline-block"}}>
                  <ViewTimelineOutlinedIcon style={{ fontSize: 12, verticalAlign: "-1px" }}/>
                 Profile running:&nbsp;
              </Box>
              <Box fontWeight="fontWeightRegular" style={{marginRight: "1%", display:"inline-block"}}>
                {runningProfileName || "None"}
              </Box>

              <Box fontWeight="fontWeightBold" style={{display:"inline-block"}}>
                <CalendarTodayIcon style={{ fontSize: 12, verticalAlign: "-1px" }}/> Profile started at:&nbsp;
              </Box>
              <Box fontWeight="fontWeightRegular" style={{marginRight: "1%", display:"inline-block"}}>
                {(startTime && moment(startTime).format("dddd, MMMM D, h:mm a")) || "-"}
              </Box>
            </div>

          </Typography>
        </div>

      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <ExperimentProfilesContent experiment={experiment} config={config} setStartTime={setStartTime} setRunningProfileName={setRunningProfileName} runningProfileName={runningProfileName}/>
          <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/experiment-profiles" target="_blank" rel="noopener noreferrer">experiment profiles</a>.</p>
        </CardContent>
      </Card>
    </React.Fragment>
)}


function Profiles(props) {
    const [config, setConfig] = React.useState({})
    const {experimentMetadata} = useExperiment()

    React.useEffect(() => {
      getConfig(setConfig)
    }, [])

    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
      <MQTTProvider name="profiles" config={config} experiment={experimentMetadata.experiment}>
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <ProfilesContainer experiment={experimentMetadata.experiment} config={config}/>
          </Grid>
        </Grid>
      </MQTTProvider>
    )
}

export default Profiles;
