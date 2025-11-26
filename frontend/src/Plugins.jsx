import Avatar from "boring-avatars";
import React from "react";
import Divider from '@mui/material/Divider';

import Select from '@mui/material/Select';
import MenuItem from "@mui/material/MenuItem";
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';
import {Typography} from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import Snackbar from '@mui/material/Snackbar';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemAvatar from '@mui/material/ListItemAvatar';
import ListItemSecondaryAction from '@mui/material/ListItemSecondaryAction';
import ListItemText from '@mui/material/ListItemText';
import DeleteIcon from '@mui/icons-material/Delete';
import CircularProgress from '@mui/material/CircularProgress';
import { Link, useParams, useNavigate } from 'react-router';
import SelectButton from "./components/SelectButton";
import {checkTaskCallback} from "./utilities";

function PageHeader(props) {
  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2">
          <Box fontWeight="fontWeightBold">
            Plugins
          </Box>
        </Typography>
      </Box>
      <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />
    </Box>
  )
}



function ListSuggestedPlugins({selectedUnit, installedPlugins}){
  const [availablePlugins, setSuggestedPlugins] = React.useState([])
  const [snackbarOpen, setSnackbarOpen] = React.useState(false)
  const [snackbarMsg, setSnackbarMsg] = React.useState("")


  React.useEffect(() => {
    async function getData() {
         await fetch("https://raw.githubusercontent.com/Pioreactor/list-of-plugins/main/plugins.json")
        .then((response) => {
          return response.json();
        })
        .then((json) => {
          setSuggestedPlugins(json)
        }).catch(e => {
          // no internet?
        })
      }
      getData()
  }, [])

  const installPlugin = (name, plugin_name)  => {
      setSnackbarOpen(true);
      setSnackbarMsg(`Installing ${plugin_name} to ${name === '$broadcast' ? "all units" : name} in the background - this may take a minute...`);
      fetch(`/api/units/${name}/plugins/install`, {
        method: "POST",
        body: JSON.stringify({args: [plugin_name]}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
  }

  const handleSnackbarClose = (event, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }
  return (
    <React.Fragment>
      <Box sx={{m: "auto", mb: "15px", width: "92%"}}>
       <List>
          {availablePlugins
              .map((plugin, i) =>
            <ListItem key={plugin.name}>
              <ListItemAvatar>
                <Avatar name={plugin.name+"seed1"} size={40} colors={["#5332ca", "#856edb", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"]} variant="bauhaus"/>
              </ListItemAvatar>
              <ListItemText
                primary={plugin.name}
                primaryTypographyProps={{style: {fontSize: '0.95rem'}}}
                secondary={
                 <>
                  <Typography
                    sx={{ display: 'block', fontStyle: "italic"}}
                    component="span"
                    variant="body2"
                    color="text.primary"
                  >
                    {plugin.author}
                  </Typography>
                  <span>
                   {plugin.description}
                  </span>
                 </>
                }
                style={{maxWidth: "525px"}}
              />
              <ListItemSecondaryAction sx={{display: {xs: 'contents', md: 'block'}}}>

                <SelectButton
                  variant="contained"
                  color="primary"
                  aria-label="install"
                  value={selectedUnit}
                  onClick={(e) => installPlugin(e.target.value, plugin.name)}
                  //endIcon={<DownloadIcon />}
                  style={{textTransform: 'none'}}
                  sx={{ml: "3px"}}
                  disabled={installedPlugins.includes(plugin.name)}
                >
                  <MenuItem value={selectedUnit}>{installedPlugins.includes(plugin.name) ? `Installed on ${selectedUnit}` :  `Install on ${selectedUnit}` }</MenuItem>
                  <MenuItem value={"$broadcast"}>Install across cluster</MenuItem>
                </SelectButton>

                <Button
                  component={Link}
                  target="_blank"
                  rel="noopener noreferrer"
                  to={plugin.homepage}
                  variant="text"
                  style={{textTransform: 'none'}}
                  size="small"
                  color="primary"
                  aria-label="view homepage"
                  disabled={!plugin.homepage || (plugin.homepage === "Unknown")}
                  endIcon={<OpenInNewIcon />}
                  sx={{ml: "15px"}}
                >
                  View
                </Button>
                </ListItemSecondaryAction>

            </ListItem>,
          )}
        </List>
      </Box>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={10000}
        key="snackbar-available"
      />
    </React.Fragment>
  )
}



function ListInstalledPlugins({selectedUnit, installedPlugins}){
  const [snackbarOpen, setSnackbarOpen] = React.useState(false)
  const [snackbarMsg, setSnackbarMsg] = React.useState("")

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  const uninstallPlugin = (plugin_name) => () => {
    setSnackbarOpen(true);
    setSnackbarMsg(`Uninstalling ${plugin_name} in the background...`);
    fetch(`/api/units/${selectedUnit}/plugins/uninstall`, {
      method: "POST",
      body: JSON.stringify({args: [plugin_name]}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
  }
  if (installedPlugins.length > 0) {
    return (
      <React.Fragment>
        <Box sx={{m: "auto", mb: "15px", width: "92%"}}>
         <List >
            {installedPlugins.map(( plugin, i) =>
              <ListItem key={plugin.name}>
                <ListItemAvatar>
                    <Avatar name={plugin.name + "seed1"} size={40} colors={["#5332ca", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"]} variant="bauhaus"/>
                </ListItemAvatar>
                <ListItemText
                  primary={`${plugin.name} ${(plugin.version === "Unknown")  ? "" : "(" + plugin.version + ")"}`}
                  primaryTypographyProps={{style: {fontSize: '0.95rem'}}}
                  secondary={
                   <>
                    <Typography
                      sx={{ display: 'block', fontStyle: "italic" }}
                      component="span"
                      variant="body2"
                      color="text.primary"
                    >
                      {plugin.author || "unknown author"}
                    </Typography>
                    <span>{`${plugin.description === "Unknown" ? "No description provided." : plugin.description}`}</span>
                   </>
                  }
                  style={{maxWidth: "525px"}}
                />
                <ListItemSecondaryAction sx={{display: {xs: 'contents', md: 'block'}}}>
                  <Button
                    onClick={uninstallPlugin(plugin.source.startsWith("plugins/") ? plugin.source.slice(8, -3) : plugin.name)}
                    variant="text"
                    size="small"
                    color="secondary"
                    aria-label="delete"
                    style={{textTransform: 'none'}}
                    endIcon={<DeleteIcon />}
                    sx={{ml: "3px"}}
                  >
                    Uninstall
                  </Button>
                    <Button
                      component={Link}
                      target="_blank"
                      rel="noopener noreferrer"
                      to={plugin.homepage.replace(/^https?:\/\/127\.0\.0\.1(?::\d+)?/, '')} // this is a hack since the leader will produce a homepage with it's leader_address which is 127.0.0.1.
                      variant="text"
                      size="small"
                      color="primary"
                      aria-label="view homepage"
                      disabled={!plugin.homepage || (plugin.homepage === "Unknown")}
                      endIcon={<OpenInNewIcon />}
                      sx={{ml: "15px", textTransform: 'none'}}
                    >
                      View
                    </Button>
                </ListItemSecondaryAction>
              </ListItem>,
            )}
          </List>
        </Box>
        <Snackbar
          anchorOrigin={{vertical: "bottom", horizontal: "center"}}
          open={snackbarOpen}
          onClose={handleSnackbarClose}
          message={snackbarMsg}
          autoHideDuration={7000}
          key="snackbar-installation"
        />
      </React.Fragment>
    );
  }
  else {
    return (
      <Box sx={{textAlign: "center", marginBottom: '50px', marginTop: "50px"}}>
        <Typography variant="body2" component="p" color="textSecondary">
            No installed plugins. Try installing one below, or read more about <a href="https://docs.pioreactor.com/user-guide/using-community-plugins" target="_blank" rel="noopener noreferrer">Pioreactor plugins</a>.
        </Typography>
      </Box>
  )}
}


function PluginContainer(){

  const {pioreactorUnit} = useParams();
  const navigate = useNavigate();

  const [installedPlugins, setInstalledPlugins] = React.useState([])
  const [isFetchComplete, setIsFetchComplete] = React.useState(false)
  const [selectedUnit, setSelectedUnit] = React.useState(pioreactorUnit || "")
  const [units, setUnits] = React.useState([])

  React.useEffect(() => {
    // Recursive approach with an optional delay between retries

    async function getPluginsInstalled() {
      setIsFetchComplete(false)
      try {
        // Fetch installed plugins
        const response = await fetch(`/api/units/${selectedUnit}/plugins/installed`);
        const json = await response.json();

        if (!json.result_url_path){
          throw new Error("No result_url_path in response")
        }

        // Poll the backend at `json.result_url_path` until status is 200
        const result = await checkTaskCallback(json.result_url_path);

        // Once 200 is received and JSON is parsed, update state
        setIsFetchComplete(true);

        if (result['result'][selectedUnit]){
          setInstalledPlugins(result['result'][selectedUnit])
        } else {
          setInstalledPlugins([])
        }
      } catch (err) {
        console.error('Error getting plugins installed:', err);
      }
    }

    if (selectedUnit){
      getPluginsInstalled()
    }
  }, [selectedUnit])


  React.useEffect(() => {
    async function getUnits() {
         await fetch(`/api/units`)
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setUnits(data.map((unit) => unit.pioreactor_unit))
          setSelectedUnit(selectedUnit || data[0].pioreactor_unit)
        });
      }
      getUnits()
  }, [])

  const onSelectionChange = (e) => {
    setSelectedUnit(e.target.value)
    navigate(`/plugins/${e.target.value}`)
  }

  return(
    <React.Fragment>
      <Card>
        <CardContent sx={{p: 2}}>
          <p> Discover, install, and manage Pioreactor plugins created by the community. These plugins can provide new functionalities for your Pioreactor (additional hardware may be necessary), or new automations to control dosing, temperature and LED tasks.</p>

        <Typography variant="h6" component="h3">
          Installed plugins on

          <Select
            labelId="configSelect"
            variant="standard"
            value={selectedUnit}
            onChange={onSelectionChange}

            sx={{
              "& .MuiSelect-select": {
                paddingY: 0,
              },
              ml: 1,
              fontWeight: 500, // Matches the title font weight
              fontSize: "inherit", // Inherits the Typography's font size
              fontFamily: "inherit", // Inherits the Typography's font family
            }}
          >
            {units.map((unit) => (
              <MenuItem key={unit} value={unit}>{unit}</MenuItem>
            ))}
          </Select>


        </Typography>

          {isFetchComplete && (
           <ListInstalledPlugins  selectedUnit={selectedUnit} installedPlugins={installedPlugins}/>
          )}

          {!isFetchComplete && (
            <Box sx={{textAlign: "center", marginBottom: '50px', marginTop: "50px"}}>
              <CircularProgress size={33}/>
            </Box>
          )}

        <Typography variant="h6" component="h3">
          Suggested plugins from the community
        </Typography>

        <ListSuggestedPlugins selectedUnit={selectedUnit} installedPlugins={installedPlugins.map(p => p.name)}/>

        </CardContent>
      </Card>
        <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about Pioreactor <a href="https://docs.pioreactor.com/user-guide/using-community-plugins" target="_blank" rel="noopener noreferrer">plugins</a>.</p>
    </React.Fragment>
)}


function Plugins(props) {
    React.useEffect(() => {
    document.title = props.title;
  }, [props.title])
    return (
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <PageHeader/>
          <PluginContainer/>
        </Grid>
      </Grid>
    );
}


export default Plugins;
