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
import Snackbar from './components/Snackbar';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemAvatar from '@mui/material/ListItemAvatar';
import ListItemSecondaryAction from '@mui/material/ListItemSecondaryAction';
import ListItemText from '@mui/material/ListItemText';
import DeleteIcon from '@mui/icons-material/Delete';
import CircularProgress from '@mui/material/CircularProgress';
import { Link, useParams, useNavigate } from 'react-router';
import SelectButton from "./components/SelectButton";
import {fetchTaskResult} from "./utils/tasks";

function PageHeader() {
  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2">
          <Box sx={{ fontWeight: "fontWeightBold" }}>
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
  const [isSuggestedPluginsLoading, setIsSuggestedPluginsLoading] = React.useState(true)
  const [suggestedPluginsFetchError, setSuggestedPluginsFetchError] = React.useState("")
  const [suggestedPluginsRefreshCounter, setSuggestedPluginsRefreshCounter] = React.useState(0)


  React.useEffect(() => {
    let isActive = true

    async function getData() {
      setIsSuggestedPluginsLoading(true)
      setSuggestedPluginsFetchError("")

      try {
        const response = await fetch("https://raw.githubusercontent.com/Pioreactor/list-of-plugins/main/plugins.json")

        if (!response.ok) {
          throw new Error(`Unable to load community plugins (HTTP ${response.status}).`)
        }

        const payload = await response.json();
        const suggestedPlugins = Array.isArray(payload) ? payload : []

        if (!isActive) {
          return
        }

        setSuggestedPlugins(suggestedPlugins)
      } catch (e) {
        if (!isActive) {
          return
        }

        setSuggestedPlugins([])
        setSuggestedPluginsFetchError(
          e instanceof Error ? e.message : "Unable to load community plugins."
        )
      } finally {
        if (isActive) {
          setIsSuggestedPluginsLoading(false)
        }
      }
    }

    getData()

    return () => {
      isActive = false
    }
  }, [suggestedPluginsRefreshCounter])

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

  const handleSnackbarClose = (_event, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  const refreshSuggestedPlugins = () => {
    setSuggestedPluginsRefreshCounter((counter) => counter + 1)
  }

  return (
    <React.Fragment>
      <Box sx={{m: "auto", mb: "15px", width: "92%"}}>
        {isSuggestedPluginsLoading && (
          <Box sx={{textAlign: "center", marginBottom: '24px', marginTop: "24px"}}>
            <CircularProgress size={24}/>
          </Box>
        )}

        {!isSuggestedPluginsLoading && suggestedPluginsFetchError && (
          <Box sx={{textAlign: "center", marginBottom: '24px', marginTop: "24px"}}>
            <Typography variant="body2" component="p" color="error">
              {suggestedPluginsFetchError}
            </Typography>
            <Button variant="text" onClick={refreshSuggestedPlugins} sx={{mt: 1, textTransform: 'none'}}>
              Retry
            </Button>
          </Box>
        )}

        {!isSuggestedPluginsLoading && !suggestedPluginsFetchError && availablePlugins.length === 0 && (
          <Box sx={{textAlign: "center", marginBottom: '24px', marginTop: "24px"}}>
            <Typography variant="body2" component="p" color="textSecondary">
              No suggested plugins available right now.
            </Typography>
          </Box>
        )}

        {!isSuggestedPluginsLoading && !suggestedPluginsFetchError && availablePlugins.length > 0 && (
          <List>
            {availablePlugins
                .map((plugin) => {
                  return (
              <ListItem key={plugin.name}>
                <ListItemAvatar>
                  <Avatar name={plugin.name+"seed1"} size={40} colors={["#5332ca", "#856edb", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"]} variant="bauhaus"/>
                </ListItemAvatar>
                <ListItemText
                  primary={plugin.name}
                  slotProps={{ primary: { style: { fontSize: '0.95rem' } } }}
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

              </ListItem>
                  )
                })}
          </List>
        )}
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

  const handleSnackbarClose = (_event, reason) => {
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
            {installedPlugins.map((plugin) =>
              {
                const homepage =
                  typeof plugin.homepage === "string"
                    ? plugin.homepage.replace(/^https?:\/\/127\.0\.0\.1(?::\d+)?/, "")
                    : "";

                return (
              <ListItem key={plugin.name}>
                <ListItemAvatar>
                    <Avatar name={plugin.name + "seed1"} size={40} colors={["#5332ca", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"]} variant="bauhaus"/>
                </ListItemAvatar>
                <ListItemText
                  primary={`${plugin.name} ${(plugin.version === "Unknown")  ? "" : "(" + plugin.version + ")"}`}
                  slotProps={{ primary: { style: { fontSize: '0.95rem' } } }}
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
                      to={homepage} // this is a hack since the leader will produce a homepage with it's leader_address which is 127.0.0.1.
                      variant="text"
                      size="small"
                      color="primary"
                      aria-label="view homepage"
                      disabled={!homepage || (homepage === "Unknown")}
                      endIcon={<OpenInNewIcon />}
                      sx={{ml: "15px", textTransform: 'none'}}
                    >
                      View
                    </Button>
                </ListItemSecondaryAction>
              </ListItem>
                )
              })}
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
  const [installedPluginsFetchError, setInstalledPluginsFetchError] = React.useState("")
  const [unitsFetchError, setUnitsFetchError] = React.useState("")
  const [pluginsRefreshCounter, setPluginsRefreshCounter] = React.useState(0)
  const latestPluginsRequestId = React.useRef(0)
  const displayedSelectedUnit = units.includes(selectedUnit) ? selectedUnit : ""

  React.useEffect(() => {
    if (!selectedUnit) {
      setInstalledPlugins([])
      setInstalledPluginsFetchError("")
      setIsFetchComplete(true)
      return
    }

    let isActive = true
    const requestId = ++latestPluginsRequestId.current

    async function getPluginsInstalled() {
      setIsFetchComplete(false)
      setInstalledPluginsFetchError("")

      try {
        // Fetch installed plugins
        const result = await fetchTaskResult(`/api/units/${selectedUnit}/plugins/installed`);
        const unitPlugins = result?.result?.[selectedUnit]

        if (!isActive || requestId !== latestPluginsRequestId.current) {
          return
        }

        if (unitPlugins == null) {
          throw new Error("Could not reach this Pioreactor.")
        }

        if (!Array.isArray(unitPlugins)) {
          throw new Error("Installed plugins payload is not a list.")
        }

        setInstalledPlugins(unitPlugins)
      } catch (err) {
        if (!isActive || requestId !== latestPluginsRequestId.current) {
          return
        }
        console.error('Error getting plugins installed:', err);
        setInstalledPlugins([])
        setInstalledPluginsFetchError(err instanceof Error ? err.message : "Failed to load installed plugins.")
      } finally {
        if (isActive && requestId === latestPluginsRequestId.current) {
          setIsFetchComplete(true)
        }
      }
    }

    getPluginsInstalled()

    return () => {
      isActive = false
    }
  }, [selectedUnit, pluginsRefreshCounter])


  React.useEffect(() => {
    let isActive = true

    async function getUnits() {
      setUnitsFetchError("")

      try {
        const response = await fetch(`/api/units`)

        if (!response.ok) {
          throw new Error(`Unable to load units (HTTP ${response.status}).`)
        }

        const data = await response.json();
        const nextUnits = Array.isArray(data) ? data.map((unit) => unit.pioreactor_unit) : []

        if (!isActive) {
          return
        }

        setUnits(nextUnits)

        if (nextUnits.length === 0) {
          setSelectedUnit("")
          setInstalledPlugins([])
          setIsFetchComplete(true)
          setUnitsFetchError("No units are available.")
          return
        }

        setSelectedUnit((current) => {
          if (current && nextUnits.includes(current)) {
            return current
          }

          if (pioreactorUnit && nextUnits.includes(pioreactorUnit)) {
            return pioreactorUnit
          }

          return nextUnits[0]
        })
      } catch (err) {
        if (!isActive) {
          return
        }

        console.error('Error getting units:', err)
        setUnits([])
        setSelectedUnit("")
        setInstalledPlugins([])
        setIsFetchComplete(true)
        setUnitsFetchError(err instanceof Error ? err.message : "Failed to load units.")
      }
    }

    getUnits()

    return () => {
      isActive = false
    }
  }, [pioreactorUnit])

  const refreshInstalledPlugins = () => {
    setPluginsRefreshCounter((counter) => counter + 1)
  }

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
            value={displayedSelectedUnit}
            onChange={onSelectionChange}
            disabled={units.length === 0}
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

          {!isFetchComplete && selectedUnit && (
            <Box sx={{textAlign: "center", marginBottom: '50px', marginTop: "50px"}}>
              <CircularProgress size={33}/>
            </Box>
          )}

          {unitsFetchError && (
            <Box sx={{textAlign: "center", marginBottom: '24px', marginTop: "16px"}}>
              <Typography variant="body2" component="p" color="textSecondary">
                {unitsFetchError}
              </Typography>
            </Box>
          )}

          {!unitsFetchError && isFetchComplete && installedPluginsFetchError && (
            <Box sx={{textAlign: "center", marginBottom: '24px', marginTop: "16px"}}>
              <Typography variant="body2" component="p" color="error">
                {installedPluginsFetchError}
              </Typography>
              <Button variant="text" onClick={refreshInstalledPlugins} sx={{mt: 1, textTransform: 'none'}}>
                Retry
              </Button>
            </Box>
          )}

          {!unitsFetchError && isFetchComplete && !installedPluginsFetchError && (
           <ListInstalledPlugins  selectedUnit={selectedUnit} installedPlugins={installedPlugins}/>
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
