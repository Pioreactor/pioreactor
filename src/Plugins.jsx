import { Hashicon } from "@emeraldpay/hashicon-react";
import React from "react";

import Grid from '@mui/material/Grid';
import { makeStyles } from '@mui/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
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
import Avatar from '@mui/material/Avatar';
import GetAppIcon from '@mui/icons-material/GetApp';
import CircularProgress from '@mui/material/CircularProgress';
import { Link } from 'react-router-dom';


const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "25px",
  },
  pos: {
    marginBottom: 0,
  },
  pluginList:{
    width: "92%",
    margin: "auto",
    marginBottom: "15px"
  },
  primaryActionButton:{
    marginLeft: "5px"
  },
  secondaryActionButton:{
    marginLeft: "15px"
  }
}));



function PageHeader(props) {
  return (
    <React.Fragment>
    <div>
      <div>
        <Typography variant="h5" component="h2">
          <Box fontWeight="fontWeightBold">
            Plugins
          </Box>
        </Typography>
      </div>
    </div>
    </React.Fragment>
  )
}



function ListAvailablePlugins({alreadyInstalledPluginsNames}){

  const classes = useStyles();
  const [availablePlugins, setAvailablePlugins] = React.useState([])
  const [snackbarOpen, setSnackbarOpen] = React.useState(false)
  const [snackbarMsg, setSnackbarMsg] = React.useState("")


  React.useEffect(() => {
    async function getData() {
         await fetch("https://raw.githubusercontent.com/Pioreactor/list-of-plugins/main/plugins.json")
        .then((response) => {
          return response.json();
        })
        .then((json) => {
          setAvailablePlugins(json)
        }).catch(e => {
          // no internet?
        })
      }
      getData()
  }, [])

  const installPlugin = (plugin_name) => () => {
      setSnackbarOpen(true);
      setSnackbarMsg(`Installing ${plugin_name} in the background...`);
      fetch('/api/install_plugin', {
        method: "POST",
        body: JSON.stringify({plugin_name: plugin_name}),
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
    <div className={classes.pluginList}>
     <List dense={true}>
        {availablePlugins
            .filter(plugin => (!alreadyInstalledPluginsNames.includes(plugin.name)))
            .map(plugin =>
          <ListItem key={plugin.name}>
            <ListItemAvatar>
              <Avatar variant="square" style={{backgroundColor:"#FFFFFF"}}>
                <Hashicon value={plugin.name} size={40} />
              </Avatar>
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

              <Button
                onClick={installPlugin(plugin.name)}
                variant="contained"
                size="small"
                aria-label="install"
                color="primary"
                endIcon={<GetAppIcon />}
                className={classes.primaryActionButton}
              >
                Install
              </Button>
              <Button
                component={Link}
                target="_blank"
                rel="noopener noreferrer"
                to={plugin.homepage}
                variant="text"
                size="small"
                color="primary"
                aria-label="view homepage"
                disabled={!plugin.homepage || (plugin.homepage === "Unknown")}
                endIcon={<OpenInNewIcon />}
                className={classes.secondaryActionButton}
              >
                View
              </Button>
              </ListItemSecondaryAction>

          </ListItem>,
        )}
      </List>
    </div>
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



function ListInstalledPlugins({installedPlugins}){
  const [snackbarOpen, setSnackbarOpen] = React.useState(false)
  const [snackbarMsg, setSnackbarMsg] = React.useState("")
  const classes = useStyles();

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  const uninstallPlugin = (plugin_name) => () => {
      setSnackbarOpen(true);
      setSnackbarMsg(`Uninstalling ${plugin_name} in the background...`);
      fetch('/api/uninstall_plugin', {
        method: "POST",
        body: JSON.stringify({plugin_name: plugin_name}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
  }
  if (installedPlugins.length > 0) {
    return (
      <React.Fragment>
      <div className={classes.pluginList}>
       <List dense={true}>
          {installedPlugins.map(plugin =>
            <ListItem key={plugin.name}>
              <ListItemAvatar>
                <Avatar variant="square" style={{backgroundColor:"#FFFFFF"}}>
                  <Hashicon value={plugin.name} size={42} />
                </Avatar>
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
                  color="primary"
                  aria-label="delete"
                  endIcon={<DeleteIcon />}
                  className={classes.primaryActionButton}
                >
                  Uninstall
                </Button>
                { !plugin.source.startsWith("plugins/") &&
                  <Button
                    component={Link}
                    target="_blank"
                    rel="noopener noreferrer"
                    to={plugin.homepage}
                    variant="text"
                    size="small"
                    color="primary"
                    aria-label="view homepage"
                    disabled={!plugin.homepage || (plugin.homepage === "Unknown")}
                    endIcon={<OpenInNewIcon />}
                    className={classes.secondaryActionButton}
                  >
                    View
                  </Button>
                }
                { plugin.source.startsWith("plugins/") &&
                  <Button
                    component={Link}
                    target="_blank"
                    rel="noopener noreferrer"
                    to={`/api/installed_plugins/${plugin.source.slice(8)}`}
                    variant="text"
                    size="small"
                    color="primary"
                    aria-label="view homepage"
                    endIcon={<OpenInNewIcon />}
                    className={classes.secondaryActionButton}
                  >
                    View
                  </Button>
                }
              </ListItemSecondaryAction>
            </ListItem>,
          )}
        </List>
      </div>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={7000}
        key="snackbar-installation"
      />
      </React.Fragment>
    )
  }
  else {
    return (
      <div style={{textAlign: "center", marginBottom: '50px', marginTop: "50px"}}>
        <Typography>
          <Box fontWeight="fontWeightRegular">
            No installed plugins. Try installing one below, or read more about <a href="https://docs.pioreactor.com/user-guide/using-community-plugins" target="_blank" rel="noopener noreferrer">Pioreactor plugins</a>.
          </Box>
        </Typography>
      </div>
  )}
}


function PluginContainer(){
  const classes = useStyles();

  const [installedPlugins, setInstalledPlugins] = React.useState([])
  const [isFetchComplete, setIsFetchComplete] = React.useState(false)

  React.useEffect(() => {
    async function getData() {
         await fetch("/api/installed_plugins")
        .then((response) => {
          return response.json();
        })
        .then((json) => {
          setIsFetchComplete(true)
          setInstalledPlugins(json)
        });
      }
      getData()
  }, [])


  return(
    <React.Fragment>
      <PageHeader/>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <p> Discover, install, and manage Pioreactor plugins created by the community. These plugins can provide new functionalities for your Pioreactor (additional hardware may be necessary), or new automations to control dosing, temperature and LED tasks.</p>

         <Typography variant="h6" component="h3">
          Installed plugins
         </Typography>

          {isFetchComplete && (
           <ListInstalledPlugins installedPlugins={installedPlugins}/>
          )}

          {!isFetchComplete && (
            <div style={{textAlign: "center", marginBottom: '50px', marginTop: "50px"}}>
              <CircularProgress size={33}/>
            </div>
          )}

         <Typography variant="h6" component="h3">
          Available plugins from the community
         </Typography>
          <ListAvailablePlugins alreadyInstalledPluginsNames={installedPlugins.map(plugin => plugin.name)}/>


          <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about Pioreactor <a href="https://docs.pioreactor.com/user-guide/using-community-plugins" target="_blank" rel="noopener noreferrer">plugins</a>.</p>

        </CardContent>
      </Card>
    </React.Fragment>
)}


function Plugins(props) {
    React.useEffect(() => {
    document.title = props.title;
  }, [props.title])
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <PluginContainer/>
          </Grid>
        </Grid>
    )
}


export default Plugins;
