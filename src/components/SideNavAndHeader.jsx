import React from 'react';
import { makeStyles } from '@mui/styles';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import ListItem from '@mui/material/ListItem';
import Badge from '@mui/material/Badge';
import Divider from '@mui/material/Divider';
import MenuIcon from '@mui/icons-material/Menu';
import IconButton from '@mui/material/IconButton';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import TuneIcon from '@mui/icons-material/Tune';
import UpdateIcon from '@mui/icons-material/Update';
import Toolbar from '@mui/material/Toolbar';
import {AppBar, Typography, Button} from '@mui/material';
import PioreactorIcon from './PioreactorIcon';
import LibraryAddOutlinedIcon from '@mui/icons-material/LibraryAddOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import InsertChartOutlinedIcon from '@mui/icons-material/InsertChartOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import Tooltip from '@mui/material/Tooltip';
import { Link, useLocation } from 'react-router-dom';
import clsx from 'clsx';


const drawerWidth = 212;

const useStyles = makeStyles((theme) => ({
  root: {
    display: 'flex',
  },
  drawer: {
    [theme.breakpoints.up('sm')]: {
      width: drawerWidth,
      flexShrink: 0,
    },
  },
  menuButton: {
    marginRight: theme.spacing(2),
  },
  drawerPaper: {
    width: drawerWidth,
  },
  title: {
    flexGrow: 1,
  },
  appBarRoot: {
    [theme.breakpoints.up('sm')]: {
      zIndex: theme.zIndex.drawer + 1
    }
  },
  listItemIcon: {
    minWidth: "40px"
  },
  divider: {
    marginTop: "15px",
    marginBottom: "15px",
  },
  outlined: {
    "&:hover": {
      backgroundColor: "rgba(83, 49, 202, 0.04)"
    },
  },
  outlinedActive: {
    "&:hover": {
      backgroundColor: "rgba(100, 100, 100, 0.04)"
    }
  }
}));



export default function SideNavAndHeader() {
  const classes = useStyles();
  const location = useLocation()

  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [version, setVersion] = React.useState(null)
  const [latestVersion, setLatestVersion] = React.useState(null)

  React.useEffect(() => {
    async function getCurrentApp() {
         await fetch("/api/app_version")
        .then((response) => {
          return response.text();
        })
        .then((data) => {
          setVersion(data)
        });
      }

    async function getLatestVersion() {
         // TODO: what happens when there is not internet connection?
         await fetch("https://api.github.com/repos/pioreactor/pioreactor/releases/latest")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setLatestVersion(data['name'])
        }).catch(e => {
          // no internet?
        });
      }

      getCurrentApp()
      getLatestVersion()
  }, [])


  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  function isSelected(path) {
    return (location.pathname === path)
  }

  const helpNode = <React.Fragment>
                     Help <OpenInNewIcon style={{fontSize:"15px", verticalAlign: "middle"}}/>
                    </React.Fragment>

  const list = () => (
    <div>
      <List>
        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: !(isSelected("/") || isSelected("/overview"))})} component={Link} to="/"  key="overview" selected={isSelected("/") || isSelected("/overview")}>
            <ListItemIcon className={classes.listItemIcon}><DashboardOutlinedIcon color={(isSelected("/") || isSelected("/overview")) ? "primary" : "inherit"}/> </ListItemIcon>
            <ListItemText primaryTypographyProps={{color: isSelected("/") || isSelected("/overview") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Overview" />
          </ListItemButton>
        </ListItem>

        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: !isSelected("/pioreactors") })} component={Link} to="/pioreactors" key="pioreactors" selected={isSelected("/pioreactors")}>
            <ListItemIcon className={classes.listItemIcon}> <PioreactorIcon color={isSelected("/pioreactors") ? "primary" : "inherit"} viewBox="-3 0 24 24"/> </ListItemIcon>
            <ListItemText primaryTypographyProps={{color: isSelected("/pioreactors") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Pioreactors" />
          </ListItemButton>
        </ListItem>


        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: !isSelected("/config") })} component={Link} to="/config" key="config" selected={isSelected("/config")}>
            <ListItemIcon className={classes.listItemIcon}> <SettingsOutlinedIcon color={isSelected("/config") ? "primary" : "inherit"}/> </ListItemIcon>
            <ListItemText primaryTypographyProps={{color: isSelected("/config") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Configuration" />
          </ListItemButton>
        </ListItem>

        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: !isSelected("/export-data") })} component={Link} to="/export-data"  key="export-data" selected={isSelected("/export-data")}>
            <ListItemIcon className={classes.listItemIcon}><SaveAltIcon color={isSelected("/export-data") ? "primary" : "inherit"}/> </ListItemIcon>
            <ListItemText primaryTypographyProps={{color: isSelected("/export-data") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Export data" />
          </ListItemButton>
        </ListItem>

        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]:!isSelected("/analysis") })} selected={isSelected("/analysis")} disabled>
            <ListItemIcon className={classes.listItemIcon}> <InsertChartOutlinedIcon color={isSelected("/analysis") ? "primary" : "inherit"}/> </ListItemIcon>
            <Tooltip title="Coming soon" placement="bottom-end">
              <ListItemText primaryTypographyProps={{color: isSelected("/analysis") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Analysis" />
            </Tooltip>
          </ListItemButton>
        </ListItem>

        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: !isSelected("/calibrations") })} selected={isSelected("/calibrations")} disabled={true} >
            <ListItemIcon className={classes.listItemIcon}> <TuneIcon color={isSelected("/calibrations") ? "primary" : "inherit"}/> </ListItemIcon>
            <Tooltip title="Not available in UI yet" placement="bottom-end">
              <ListItemText primaryTypographyProps={{color: isSelected("/calibrations") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Calibrations" />
            </Tooltip>
          </ListItemButton>
        </ListItem>

        <Divider className={classes.divider} />

        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: !isSelected("/plugins") })} component={Link} to="/plugins"  key="plugins" selected={isSelected("/plugins")}>
            <ListItemIcon className={classes.listItemIcon}><LibraryAddOutlinedIcon color={isSelected("/plugins") ? "primary" : "inherit"}/> </ListItemIcon>
            <ListItemText primaryTypographyProps={{color: isSelected("/plugins") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Plugins" />
          </ListItemButton>
        </ListItem>

        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: !isSelected("/updates") })} component={Link} to="/updates"  key="updates" selected={isSelected("/updates")}>
            <ListItemIcon className={classes.listItemIcon}>
              <Badge variant="dot" color="secondary" invisible={!((version) && (latestVersion) && (version !== latestVersion))}>
                <UpdateIcon color={isSelected("/updates") ? "primary" : "inherit"}/>
              </Badge>
            </ListItemIcon>
            <ListItemText primaryTypographyProps={{color: isSelected("/updates") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Updates"/>
          </ListItemButton>
        </ListItem>

        <ListItem disablePadding>
          <ListItemButton className={clsx({[classes.outlined]: true })} target="_blank" rel="noopener noreferrer" component={Link} to={{pathname: "https://docs.pioreactor.com"}}  key="help">
            <ListItemIcon className={classes.listItemIcon}><HelpOutlineIcon/> </ListItemIcon>
            <ListItemText primary={helpNode} primaryTypographyProps={{color: "rgba(0, 0, 0, 0.87)"}}/>
          </ListItemButton>
        </ListItem>


      </List>
    </div>
  );

  return (
    <React.Fragment>
      <div className={classes.appBarRoot}>
        <AppBar position="fixed" >
          <Toolbar variant="dense">

            <IconButton
              color="inherit"
              aria-label="open drawer"
              edge="start"
              onClick={handleDrawerToggle}
              classes={{root: classes.menuButton}}
              sx={{ display: { xs: 'block', sm: 'none' } }}
              size="large">
              <MenuIcon />
            </IconButton>


            <Typography variant="h6" className={classes.title}>
              <Link color="inherit" underline="none" to="/" className={classes.title}>
                <img alt="pioreactor logo" src="/white_colour.png" style={{width: "120px", height: "29px"}}/> <
              /Link>
            </Typography>
            <Button component={Link} target="_blank" rel="noopener noreferrer" to={{pathname: "https://docs.pioreactor.com"}} color="inherit" style={{textTransform: "none"}}>
              Help <HelpOutlineIcon style={{ fontSize: 18, verticalAlign: "middle", marginLeft: 5 }}/>
            </Button>
          </Toolbar>
        </AppBar>
      </div>
      <Drawer
        variant="temporary"
        anchor="left"
        open={mobileOpen}
        onClose={handleDrawerToggle}
        classes={{
          paper: classes.drawerPaper,
        }}
        ModalProps={{
          keepMounted: true, // Better open performance on mobile.
        }}
        sx={{ display: { xs: 'block', sm: 'none' } }}
      >
        {list()}
      </Drawer>
      <Drawer
        classes={{
          paper: classes.drawerPaper,
        }}
        variant="permanent"
        open
        className={classes.drawer}
        sx={{ display: { xs: 'none', sm: 'block' } }}
      >
        <Toolbar />
        {list()}
      </Drawer>
    </React.Fragment>
  );
}
