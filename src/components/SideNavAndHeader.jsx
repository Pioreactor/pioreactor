import React from 'react';
import { makeStyles } from '@mui/styles';
import Drawer from '@mui/material/Drawer';
import Badge from '@mui/material/Badge';
import Divider from '@mui/material/Divider';
import MenuIcon from '@mui/icons-material/Menu';
import IconButton from '@mui/material/IconButton';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import UpdateIcon from '@mui/icons-material/Update';
import Toolbar from '@mui/material/Toolbar';
import {AppBar, Typography, Button} from '@mui/material';
import PioreactorIcon from './PioreactorIcon';
import LibraryAddOutlinedIcon from '@mui/icons-material/LibraryAddOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import InsertChartOutlinedIcon from '@mui/icons-material/InsertChartOutlined';
import ViewTimelineOutlinedIcon from '@mui/icons-material/ViewTimelineOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import ChatOutlinedIcon from '@mui/icons-material/ChatOutlined';
import { Link, useLocation } from 'react-router-dom';
import { Sidebar, Menu, MenuItem} from "react-pro-sidebar";

const drawerWidth = 230;

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

}));



export default function SideNavAndHeader() {
  const classes = useStyles();
  const location = useLocation()

  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [version, setVersion] = React.useState(null)
  const [latestVersion, setLatestVersion] = React.useState(null)

  React.useEffect(() => {
    async function getCurrentApp() {
         await fetch("/api/versions/app")
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
          setLatestVersion(data['tag_name'])
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


  const list = () => (
    <Sidebar width="230px" backgroundColor="white">
      <Menu
          style={{minWidth: "230px", width: "230px"}}
          renderExpandIcon={({level, active, disabled}) => null }
          menuItemStyles={{
            label:  {whiteSpace: "pre-wrap"},
            button: ({ level, active, disabled }) => {
              // only apply styles on first level elements of the tree
              if (level === 0)
                return {
                  color: disabled ? '#00000050' : (active ? '#5331ca' : 'inherit'),
                  backgroundColor: active ? '#5331ca14' : undefined,
                };
            },
            icon: ({level, active, disabled}) => {
              return {
                color: disabled ? '#00000050' : (active ? '#5331ca' : '#0000008a'),
              };
            }
          }}
        >
        <MenuItem
          icon={<DashboardOutlinedIcon/>}
          component={<Link to="/overview" className="link" />}
          active={(isSelected("/") || isSelected("/overview"))}
          >
          Overview
        </MenuItem>

        <MenuItem
          icon={<PioreactorIcon viewBox="-3 0 24 24"/>}
          component={<Link to="/pioreactors" className="link" />}
          active={isSelected("/pioreactors")}
          >
          Pioreactors
        </MenuItem>

        <MenuItem
          icon={<ViewTimelineOutlinedIcon/> }
          component={<Link to="/experiment-profiles" className="link" />}
          active={isSelected("/experiment-profiles")}
          >
          Profiles
        </MenuItem>


        <MenuItem
          icon={<SettingsOutlinedIcon/> }
          component={<Link to="/config" className="link" />}
          active={isSelected("/config")}
          >
          Configuration

        </MenuItem>

        <MenuItem
          icon={<SaveAltIcon/> }
          component={<Link to="/export-data" className="link" />}
          active={isSelected("/export-data")}
          >
          Export data
        </MenuItem>

        <MenuItem
          icon={<InsertChartOutlinedIcon/> }
          component={<Link to="/experiments" className="link" />}
          active={isSelected("/experiments")}
          >
          Past experiments
        </MenuItem>


        <Divider className={classes.divider} />

        <MenuItem
          icon={<LibraryAddOutlinedIcon/> }
          component={<Link to="/plugins" className="link" />}
          active={isSelected("/plugins")}
          >
          Plugins
        </MenuItem>

        <MenuItem
          icon={
            <Badge variant="dot" color="secondary" invisible={!((version) && (latestVersion) && (version !== latestVersion))}>
                <UpdateIcon/>
            </Badge>
            }
          component={<Link to="/updates" className="link" />}
          active={isSelected("/updates")}
          >
          Updates
        </MenuItem>


        <MenuItem
          icon={<HelpOutlineIcon/> }
          component={<Link target="_blank" rel="noopener noreferrer" to={{pathname: "https://docs.pioreactor.com"}}  className="link" />}
          suffix={<OpenInNewIcon style={{fontSize:"15px", verticalAlign: "middle"}}/>}
          >
          Help
        </MenuItem>


        <MenuItem
          icon={<ChatOutlinedIcon/> }
          component={<Link target="_blank" rel="noopener noreferrer" to={{pathname: "https://forum.pioreactor.com"}}  className="link" />}
          suffix={<OpenInNewIcon style={{fontSize:"15px", verticalAlign: "middle"}}/>}
          >
          Forums
        </MenuItem>


      </Menu>
    </Sidebar>
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
