import React from 'react';
import { makeStyles } from '@mui/styles';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Badge from '@mui/material/Badge';
import Divider from '@mui/material/Divider';
import MenuIcon from '@mui/icons-material/Menu';
import IconButton from '@mui/material/IconButton';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import FeedbackOutlinedIcon from '@mui/icons-material/FeedbackOutlined';
import TuneIcon from '@mui/icons-material/Tune';
import UpdateIcon from '@mui/icons-material/Update';
import Toolbar from '@mui/material/Toolbar';
import {AppBar, Typography, Link, Button} from '@mui/material';
import PioreactorIcon from './PioreactorIcon';
import LibraryAddOutlinedIcon from '@mui/icons-material/LibraryAddOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import InsertChartOutlinedIcon from '@mui/icons-material/InsertChartOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import Tooltip from '@mui/material/Tooltip';

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
  }
}));



export default function SideNavAndHeader() {
  const classes = useStyles();

  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [version, setVersion] = React.useState(null)
  const [latestVersion, setLatestVersion] = React.useState(null)

  React.useEffect(() => {
    async function getCurrentApp() {
         await fetch("/api/get_app_version")
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
        });
      }

      getCurrentApp()
      getLatestVersion()
  }, [])


  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  function isSelected(path) {
    return (window.location.pathname === path)
  }

  const helpNode = <React.Fragment>
                     Help <OpenInNewIcon style={{fontSize:"15px", verticalAlign: "middle"}}/>
                    </React.Fragment>

  const list = () => (
    <div className={classes.drawerContainer}>
      <List>

        <ListItemButton href="/overview" component="a"  key="overview" selected={isSelected("/") || isSelected("/overview")}>
          <ListItemIcon className={classes.listItemIcon}><DashboardOutlinedIcon color={(isSelected("/") || isSelected("/overview")) ? "primary" : "inherit"}/> </ListItemIcon>
          <ListItemText primaryTypographyProps={{color: isSelected("/") || isSelected("/overview") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Overview" />
        </ListItemButton>

        <ListItemButton href="/pioreactors"  component="a" key="pioreactors" selected={isSelected("/pioreactors")}>
          <ListItemIcon className={classes.listItemIcon}> <PioreactorIcon color={isSelected("/pioreactors") ? "primary" : "inherit"} viewBox="-3 0 24 24"/> </ListItemIcon>
          <ListItemText primaryTypographyProps={{color: isSelected("/pioreactors") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Pioreactors" />
        </ListItemButton>



        <ListItemButton  href="/config"  component="a" key="config" selected={isSelected("/config")}>
          <ListItemIcon className={classes.listItemIcon}> <SettingsOutlinedIcon color={isSelected("/config") ? "primary" : "inherit"}/> </ListItemIcon>
          <ListItemText primaryTypographyProps={{color: isSelected("/config") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Configuration" />
        </ListItemButton>

        <ListItemButton href="/export-data" component="a"  key="export_data" selected={isSelected("/export-data")}>
          <ListItemIcon className={classes.listItemIcon}><SaveAltIcon color={isSelected("/export-data") ? "primary" : "inherit"}/> </ListItemIcon>
          <ListItemText primaryTypographyProps={{color: isSelected("/export-data") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Export data" />
        </ListItemButton>

        <ListItemButton  href="/analysis" key="analysis" selected={isSelected("/analysis")} disabled>
          <ListItemIcon className={classes.listItemIcon}> <InsertChartOutlinedIcon color={isSelected("/analysis") ? "primary" : "inherit"}/> </ListItemIcon>
          <Tooltip title="Coming soon" placement="bottom-end">
            <ListItemText primaryTypographyProps={{color: isSelected("/analysis") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Analysis" />
          </Tooltip>
        </ListItemButton>

        <ListItemButton  href="/calibrations"  key="calibrations" selected={isSelected("/calibrations")} disabled={true} >
          <ListItemIcon className={classes.listItemIcon}> <TuneIcon color={isSelected("/calibrations") ? "primary" : "inherit"}/> </ListItemIcon>
          <Tooltip title="Coming soon" placement="bottom-end">
            <ListItemText primaryTypographyProps={{color: isSelected("/calibrations") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Calibrations" />
          </Tooltip>
        </ListItemButton>

        <Divider className={classes.divider} />

        <ListItemButton href="/plugins" component="a"  key="plugins" selected={isSelected("/plugins")}>
          <ListItemIcon className={classes.listItemIcon}><LibraryAddOutlinedIcon color={isSelected("/plugins") ? "primary" : "inherit"}/> </ListItemIcon>
          <ListItemText primaryTypographyProps={{color: isSelected("/plugins") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Plugins" />
        </ListItemButton>

        <ListItemButton href="/updates" component="a"  key="updates" selected={isSelected("/updates")}>
          <ListItemIcon className={classes.listItemIcon}>
            <Badge variant="dot" color="secondary" invisible={!((version) && (latestVersion) && (version !== latestVersion))}>
              <UpdateIcon color={isSelected("/updates") ? "primary" : "inherit"}/>
            </Badge>
          </ListItemIcon>
          <ListItemText primaryTypographyProps={{color: isSelected("/updates") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Updates"/>
        </ListItemButton>

        <ListItemButton target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com" component="a"  key="help">
          <ListItemIcon className={classes.listItemIcon}><HelpOutlineIcon/> </ListItemIcon>
          <ListItemText primary={helpNode} primaryTypographyProps={{color: "rgba(0, 0, 0, 0.87)"}}/>
        </ListItemButton>

        <ListItemButton href="/feedback" component="a"  key="feedback" selected={isSelected("/feedback")}>
          <ListItemIcon className={classes.listItemIcon}>
            <FeedbackOutlinedIcon color={isSelected("/feedback") ? "primary" : "inherit"}/>
          </ListItemIcon>
          <ListItemText primaryTypographyProps={{color: isSelected("/feedback") ? "primary" : "rgba(0, 0, 0, 0.87)"}} primary="Share feedback"/>
        </ListItemButton>

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
              <Link color="inherit" underline="none" href="/" className={classes.title}> <img alt="pioreactor logo" src="/white_colour.png" style={{width: "120px", height: "29px"}}/> </Link>
            </Typography>
            <Link color="inherit" underline="none" href="https://docs.pioreactor.com" target="_blank" rel="noopener noreferrer">
              <Button color="inherit" style={{textTransform: "none"}}>Help <HelpOutlineIcon style={{ fontSize: 18, verticalAlign: "middle", marginLeft: 5 }}/></Button>
            </Link>
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
