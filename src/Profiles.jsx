import React from "react";
import dayjs from "dayjs";

import FormControl from '@mui/material/FormControl';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Select from '@mui/material/Select';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Divider from '@mui/material/Divider';
import CardContent from '@mui/material/Card';
import {getConfig} from "./utilities"
import FormLabel from '@mui/material/FormLabel';
import MenuItem from '@mui/material/MenuItem';
import IconButton from '@mui/material/IconButton';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import {DisplayProfile} from "./components/DisplayProfile"
import DisplaySourceCode from "./components/DisplaySourceCode"
import CloseIcon from '@mui/icons-material/Close';
import CodeIcon from '@mui/icons-material/Code';
import AddIcon from '@mui/icons-material/Add';
import { Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import UnderlineSpan from "./components/UnderlineSpan";
import { RunningProfilesProvider, useRunningProfiles } from './providers/RunningProfilesContext';

import EditIcon from '@mui/icons-material/Edit';
import { Link, useNavigate, useParams } from 'react-router-dom';
import SelectButton from "./components/SelectButton";
import DeleteIcon from '@mui/icons-material/Delete';
import ViewTimelineOutlinedIcon from '@mui/icons-material/ViewTimelineOutlined';
import PlayDisabledIcon from '@mui/icons-material/PlayDisabled';
import { useConfirm } from 'material-ui-confirm';
import { MQTTProvider, useMQTT } from './providers/MQTTContext';
import { useExperiment } from './providers/ExperimentContext';
import ManageExperimentMenu from "./components/ManageExperimentMenu";
import StopIcon from '@mui/icons-material/Stop';
import CircularProgress from '@mui/material/CircularProgress';
import Chip from '@mui/material/Chip';


/**
 * 1) Child component that displays the experiment profile dropdown,
 *    the “Run profile” button, etc.
 */
function RunExperimentProfilesContent({
  experiment,
  experimentProfilesAvailable,
  selectedExperimentProfile,
  confirmed,
  setConfirmed,
  viewSource,
  setViewSource,
  source,
  setSource,
  dryRun,
  setDryRun
}) {
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { startProfile } = useRunningProfiles();

  const onSubmit = () => {
    setConfirmed(true);
    // The “selectedExperimentProfile” is the file key we pass to start
    startProfile(experimentProfilesAvailable[selectedExperimentProfile].fullpath, experiment, dryRun);
  };

  const onSelectExperimentProfileChange = (e) => {

    navigate(`/experiment-profiles/${e.target.value}`)

  };

  const deleteProfile = () => {
    confirm({
      title: `Are you sure you wish to delete this profile?`,
      description: "This action is permanent.",
      confirmationText: "Delete",
      confirmationButtonProps: { color: "primary" },
      cancellationButtonProps: { color: "secondary" },
    })
      .then(() => {
        fetch(`/api/contrib/experiment_profiles/${selectedExperimentProfile}`, {
          method: "DELETE",
        }).then(res => {
          if (res.ok) {
            navigate(0);
          }
        })
      })
      .catch(() => {});
  };

  const getSourceAndView = () => {
    // fetch the raw file content only if we are about to toggle into “view source”
    if (!viewSource) {
      fetch(`/api/contrib/experiment_profiles/${selectedExperimentProfile}`, {
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
  };

  return (
    <Grid container spacing={1}>
      <Grid item xs={6}>
        <Box sx={{ width: "100%", marginTop: 2,  display: "flex", justifyContent: "space-between" }}>
          <FormControl style={{ minWidth: "300px" }}>
            <FormLabel component="legend">Experiment profile</FormLabel>
            <Select
              labelId="profileSelect"
              variant="standard"
              value={selectedExperimentProfile}
              onChange={onSelectExperimentProfileChange}
              label="Experiment profile"
            >
              {Object.keys(experimentProfilesAvailable).map((file) => {
                const profile = experimentProfilesAvailable[file].profile;
                return (
                  <MenuItem key={file} value={file}>
                    {profile.experiment_profile_name}
                  </MenuItem>
                )
              })}
            </Select>
          </FormControl>
        </Box>
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
            style={{ textTransform: "none" }}
            to={`/experiment-profiles/${(selectedExperimentProfile || "")}/edit`}
            component={Link}
            disabled={ selectedExperimentProfile === ''}
          >
            <EditIcon fontSize="15" sx={{ verticalAlign: "middle", margin: "0px 3px" }}/>
            Edit
          </Button>
          <Button
            variant="text"
            size="small"
            color="primary"
            aria-label="view source code"
            disabled={selectedExperimentProfile === ""}
            onClick={getSourceAndView}
            style={{ textTransform: "none" }}
          >
            <CodeIcon fontSize="15" sx={{ verticalAlign: "middle", margin: "0px 3px" }}/>
            {viewSource ? "View preview" : "View source"}
          </Button>
          <Button
            variant="text"
            size="small"
            color="secondary"
            aria-label="delete profile"
            onClick={deleteProfile}
            style={{ marginRight: "5px", textTransform: "none" }}
            disabled={selectedExperimentProfile === ''}
          >
            <DeleteIcon fontSize="15" sx={{ verticalAlign: "middle", margin: "0px 3px" }}/>
            Delete
          </Button>
        </Grid>
      </Grid>

      <Grid item xs={12}>
        {selectedExperimentProfile !== "" && !viewSource &&
          <DisplayProfile data={experimentProfilesAvailable[selectedExperimentProfile].profile} />
        }
        {selectedExperimentProfile !== "" && viewSource &&
          <DisplaySourceCode sourceCode={source} />
        }
      </Grid>

      <Box sx={{ display: "flex", justifyContent: "flex-end", marginLeft: 1 }}>
        <SelectButton
          variant="contained"
          color="primary"
          value={dryRun ? "execute_dry_run" : "execute"}
          onClick={onSubmit}
          endIcon={dryRun ? <PlayDisabledIcon /> : <PlayArrowIcon />}
          disabled={confirmed}
          onChange={({ target: { value } }) =>
            setDryRun(value === "execute_dry_run")
          }
        >
          <MenuItem value={"execute"}>Run profile</MenuItem>
          <MenuItem value={"execute_dry_run"}>Dry-run profile</MenuItem>
        </SelectButton>
      </Box>
    </Grid>
  );
}


/**
 * 2) Simple container for the “Available profiles” card.
 *    (We keep it separate just to keep the layout organized.)
 */
function RunProfilesContainer(props) {
  const { experiment } = props; // from parent

  return (
    <React.Fragment>
      <Card>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="h6" component="h2">
            <Box fontWeight="fontWeightRegular">Available profiles</Box>
          </Typography>
          {/* Pass all relevant props through */}
          <RunExperimentProfilesContent {...props} experiment={experiment} />
        </CardContent>
      </Card>
    </React.Fragment>
  );
}


function RunningProfilesContainer() {
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { runningProfiles, loading, stopProfile } = useRunningProfiles();

  const onStop = (job_id) => {
    confirm({
      description: 'Stopping this profile early will stop executing new actions end all actions started by it.',
      title: 'Stop profile?',
      confirmationText: 'Stop profile',
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},
    })
      .then(() => stopProfile(job_id))
      .catch(() => {});
  };

  return (
    <React.Fragment>
      <Card>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="h6" component="h2">
            <Box fontWeight="fontWeightRegular">Profiles Running</Box>
          </Typography>
          {loading && (
            <Box sx={{ textAlign: "center", mt: 2 }}>
              <CircularProgress size={33}/>
            </Box>
          )}
          {!loading && runningProfiles.length === 0 && (
            <p>No profiles are currently running.</p>
          )}
          {!loading && runningProfiles.length > 0 && (
            <Table size="small" sx={{ mt: 0 }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ padding: "6px 0px" }}>Profile name</TableCell>
                  <TableCell align="right">Elapsed</TableCell>
                  <TableCell align="right"></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {runningProfiles.map((element) => (
                  <React.Fragment key={element.job_id}>
                    <TableRow>
                      <TableCell sx={{ padding: "6px 0px" }}>
                        <Chip
                          size="small"
                          icon={<ViewTimelineOutlinedIcon/>}
                          label={element.settings.experiment_profile_name}
                          sx={{maxWidth: "210px"}}
                          clickable
                          onClick={() => {
                            navigate(`/experiment-profiles/${element.settings.profile_filename}`);
                          }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        {dayjs().diff(dayjs(element.settings.start_time_utc), 'hour', true).toFixed(1)} h
                      </TableCell>
                      <TableCell align="right" sx={{ width: "100px", px: 0 }}>
                        <Button color="secondary" sx={{ textTransform: "none", p: 0 }} onClick={() => onStop(element.job_id)}>
                          Stop
                        </Button>
                      </TableCell>
                    </TableRow>
                  </React.Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </React.Fragment>
  );
}


function Profiles(props) {
  const { experimentMetadata } = useExperiment();
  const { profileFilename } = useParams();

  const [experimentProfilesAvailable, setExperimentProfilesAvailable] = React.useState({});
  const [selectedExperimentProfile, setSelectedExperimentProfile] = React.useState('');
  const [confirmed, setConfirmed] = React.useState(false);
  const [viewSource, setViewSource] = React.useState(false);
  const [source, setSource] = React.useState("Loading...");
  const [dryRun, setDryRun] = React.useState(false);

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  React.useEffect(() => {
    fetch("/api/contrib/experiment_profiles")
      .then(response => response.json())
      .then(profiles => {
        // shape: [ {file: "...", experimentProfile: {...}}, ... ]
        const profilesByKey = profiles.reduce(
          (acc, cur) => ({ ...acc, [cur.file]: {profile: cur.experimentProfile, fullpath: cur.fullpath, file: cur.file} }),
          {}
        );
        setExperimentProfilesAvailable(profilesByKey);

        if (profileFilename && (profileFilename in profilesByKey)){
          setSelectedExperimentProfile(profileFilename);
          setConfirmed(false)
        } else {
          const firstKey = Object.keys(profilesByKey)[0] ?? "";
          setSelectedExperimentProfile(firstKey);
          setConfirmed(false)
        }
      });
  }, [profileFilename]);

  return (
    <RunningProfilesProvider experiment={experimentMetadata.experiment}>
      <Grid container spacing={2}>
        <Grid item md={12} xs={12}>
          <Box>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
              <Typography variant="h5" component="h2">
                <Box fontWeight="fontWeightBold">
                  Experiment Profiles
                </Box>
              </Typography>
              <Box sx={{ display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap" }}>
                <Button
                  to={`/experiment-profiles/new`}
                  component={Link}
                  style={{ textTransform: 'none', marginRight: "0px", float: "right" }}
                  color="primary"
                >
                  <AddIcon fontSize="15" sx={{ verticalAlign: "middle", margin: "0px 3px" }}/>
                  Create new profile
                </Button>
                <Divider orientation="vertical" flexItem variant="middle" />
                <ManageExperimentMenu experiment={experimentMetadata.experiment}/>
              </Box>
            </Box>
            <Divider />
          </Box>
        </Grid>

        {/* Left side: For selecting a profile or running a new profile */}
        <Grid item md={8} xs={12}>
          <RunProfilesContainer
            experiment={experimentMetadata.experiment}
            // Pass all the “lifted” states + setters
            experimentProfilesAvailable={experimentProfilesAvailable}
            selectedExperimentProfile={selectedExperimentProfile}
            confirmed={confirmed}
            setConfirmed={setConfirmed}
            viewSource={viewSource}
            setViewSource={setViewSource}
            source={source}
            setSource={setSource}
            dryRun={dryRun}
            setDryRun={setDryRun}
          />
        </Grid>

        {/* Right side: The table of running profiles with clickable Chips */}
        <Grid item md={4} xs={12}>
          <RunningProfilesContainer />
        </Grid>

        <Grid item xs={12}>
          <p style={{ textAlign: "center", marginTop: "20px" }}>
            Learn more about{" "}
            <a href="https://docs.pioreactor.com/user-guide/experiment-profiles" target="_blank" rel="noopener noreferrer">
              experiment profiles
            </a>.
          </p>
        </Grid>
      </Grid>
    </RunningProfilesProvider>
  );
}

export {Profiles, RunningProfilesContainer};
