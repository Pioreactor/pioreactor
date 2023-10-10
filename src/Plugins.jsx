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
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import CloseIcon from '@mui/icons-material/Close';
import TextField from '@mui/material/TextField';
import IconButton from '@mui/material/IconButton';


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
  },
  textField: {
    marginTop: "15px",
    maxWidth: "180px",
  },
  textFieldWide: {
    marginTop: "15px",
    width: "320px",
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
}));


function InstallByNameDialog(props){

  const classes = useStyles();

  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const [snackbarOpen, setSnackbarOpen] = React.useState(false)
  const [snackbarMsg, setSnackbarMsg] = React.useState("")


  const handleClickOpen = () => {
    setOpen(true);
  };


  const handleClose = () => {
    setOpen(false);
  };

  const handleTextChange = evt => {
    setText(evt.target.value)
  }

  const handleSnackbarClose = (event, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false)
  }

  const onSubmit = () => {
    setSnackbarOpen(true);
    setSnackbarMsg(`Installing ${text} in the background...`);
    fetch('/api/install_plugin', {
      method: "POST",
      body: JSON.stringify({plugin_name: text}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    setOpen(false);
  }

  return (
    <React.Fragment>

    <Button style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary" onClick={handleClickOpen}>
      <GetAppIcon fontSize="15" classes={{root: classes.textIcon}}/> Install plugin by name
    </Button>
    <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title">
      <DialogTitle>
        Install plugin by name
        <IconButton
          aria-label="close"
          onClick={handleClose}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[500],
          }}
          size="large">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <div>
          <TextField
            size="small"
            id="plugin-name"
            label="Plugin name"
            variant="outlined"
            className={classes.textFieldWide}
            onChange={handleTextChange}
            value={text}
          />
        </div>

        <Button
          variant="contained"
          color="primary"
          style={{marginTop: "20px"}}
          onClick={onSubmit}
          type="submit"
          endIcon={<GetAppIcon />}
        >
          Install
        </Button>
      </DialogContent>
    </Dialog>
    <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={snackbarOpen}
      onClose={handleSnackbarClose}
      message={snackbarMsg}
      autoHideDuration={10000}
      key="snackbar-available"
    />
    </React.Fragment>
)}



function PageHeader(props) {
  const classes = useStyles();
  return (
    <div>
      <div className={classes.headerMenu}>
        <Typography variant="h5" component="h2">
          <Box fontWeight="fontWeightBold">
            Plugins
          </Box>
        </Typography>
        <div className={classes.headerButtons}>
          <InstallByNameDialog />
        </div>
      </div>
    </div>
  )
}



function ListSuggestedPlugins({alreadyInstalledPluginsNames}){

  const classes = useStyles();
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
          Suggested plugins from the community
         </Typography>
          <ListSuggestedPlugins alreadyInstalledPluginsNames={installedPlugins.map(plugin => plugin.name)}/>


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
            <PageHeader/>
            <PluginContainer/>
          </Grid>
        </Grid>
    )
}


export default Plugins;
