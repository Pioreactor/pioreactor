import React from 'react';
import { styled } from '@mui/material/styles';
import Drawer from '@mui/material/Drawer';
import Badge from '@mui/material/Badge';
import Divider from '@mui/material/Divider';
import MenuIcon from '@mui/icons-material/Menu';
import MenuItemMUI from '@mui/material/MenuItem';
import IconButton from '@mui/material/IconButton';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import UpdateIcon from '@mui/icons-material/Update';
import Toolbar from '@mui/material/Toolbar';
import FormControl from '@mui/material/FormControl';
import Select from '@mui/material/Select';
import Tooltip from '@mui/material/Tooltip';
import ListSubheader from '@mui/material/ListSubheader';
import {AppBar, Typography, Button} from '@mui/material';
import PioreactorIcon from './PioreactorIcon';
import PioreactorsIcon from './PioreactorsIcon';
import LibraryAddOutlinedIcon from '@mui/icons-material/LibraryAddOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import InsertChartOutlinedIcon from '@mui/icons-material/InsertChartOutlined';
import ViewTimelineOutlinedIcon from '@mui/icons-material/ViewTimelineOutlined';
import ChatOutlinedIcon from '@mui/icons-material/ChatOutlined';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar, Menu, MenuItem, SubMenu} from "react-pro-sidebar";
import { useExperiment } from '../providers/ExperimentContext';
import ScienceOutlinedIcon from '@mui/icons-material/ScienceOutlined';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';


const drawerWidth = 230;

const DrawerStyled = styled(Drawer)(({ theme }) => ({
  width: drawerWidth,
  flexShrink: 0,
  [theme.breakpoints.up('sm')]: {
    width: drawerWidth,
  },
}));


const ConditionalTooltip = ({condition, title, children}) => {
  return (
    <>
      {condition ? (
        <Tooltip placement="top" title={title}>
          {children}
        </Tooltip>
      ) : (
        children
      )}
    </>
  );
};


const SelectableMenuItem = ({allExperiments, experiment, updateExperiment}) => {
  const navigate = useNavigate();
  const [selectOpen, setSelectOpen] = React.useState(false);
  const [activeExperiments, setActiveExperiments] = React.useState(new Set([]))

  React.useEffect(() => {
    async function getActiveExperiments() {
         await fetch("/api/experiments/assignment_count")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setActiveExperiments(new Set(data.map(item => item.experiment)))
        })
      }
    getActiveExperiments()
  }, [])

  const handleMenuItemClick = (e) => {
    e.stopPropagation()
    setSelectOpen(true);
  };

  const handleSelectClose = (e) => {
    e.stopPropagation()
    setSelectOpen(false);
  };


  function handleExperimentChange(e) {
    const currentPath = window.location.pathname.split('/')[1]; // Assumes the base path is at the first segment
    const allowedPaths = ['pioreactors', 'experiment-profiles', 'overview'];

    if (!allowedPaths.includes(currentPath)) {
      navigate('/overview');
    }

    if (e.target.value){
      updateExperiment(allExperiments.find(obj => obj.experiment === e.target.value));
    }

    setSelectOpen(false)
  }
  return (

    <ConditionalTooltip
      title={experiment}
      condition={experiment.length > 16}
    >
    <MenuItem onClick={handleMenuItemClick} icon={<ScienceOutlinedIcon />}>
      <FormControl variant="standard" fullWidth>
        <Select
          open={selectOpen}
          onClose={handleSelectClose}
          value={experiment}
          label="Experiment"
          onChange={handleExperimentChange}
          MenuProps={{ classes: { paper: { maxHeight: 400 } } }}
          sx={{
            '&:before': {
              borderColor: 'rgba(0, 0, 0, 0);',
            },
            '&:after': {
              borderColor: 'rgba(0, 0, 0, 0);',
            },
            '&:not(.Mui-disabled):hover::before': {
              borderColor: 'rgba(0, 0, 0, 0);',
            },
          }}
        >
          <MenuItemMUI value={null} component={Link} to="/start-new-experiment">
            <AddCircleOutlineIcon fontSize="15" sx={{ verticalAlign: 'middle', margin: '0px 3px' }} />
            New experiment
          </MenuItemMUI>
          <Divider />
          <ListSubheader>Active</ListSubheader>
          {allExperiments
            .filter((e) => activeExperiments.has(e.experiment))
            .map((e) => (
              <MenuItemMUI key={e.experiment} value={e.experiment}>
                {e.experiment}
              </MenuItemMUI>
            ))}
          <Divider />
          <ListSubheader>Inactive</ListSubheader>
          {allExperiments
            .filter((e) => !activeExperiments.has(e.experiment))
            .map((e) => (
              <MenuItemMUI key={e.experiment} value={e.experiment}>
                {e.experiment}
              </MenuItemMUI>
            ))}
        </Select>
      </FormControl>
    </MenuItem>
    </ConditionalTooltip>
  );
};



export default function SideNavAndHeader() {
  const location = useLocation()

  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [version, setVersion] = React.useState(null)
  const [lap, setLAP] = React.useState(false)
  const [latestVersion, setLatestVersion] = React.useState(null)
  const {experimentMetadata, updateExperiment, allExperiments} = useExperiment()

  React.useEffect(() => {
    async function getLAP() {
       await fetch("/api/is_local_access_point_active")
      .then((response) => {
        return response.text();
      })
      .then((data) => {
        setLAP(data === "true")
      });
    }

    async function getCurrentApp() {
         await fetch("/unit_api/versions/app")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setVersion(data['version'])
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
    getLAP()
  }, [])

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  function isSelected(path) {
    return (location.pathname === path)
  }


  const list = () => (
    <Sidebar rootStyles={{height: "100%"}} width="230px" backgroundColor="white">
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1}}>

          <Menu
              style={{minWidth: "230px", width: "230px", height: "100%"}}
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
              <SelectableMenuItem
                experiment={experimentMetadata.experiment || ""}
                allExperiments={allExperiments}
                updateExperiment={updateExperiment}
                />

              <MenuItem
                icon={<DashboardOutlinedIcon/>}
                component={<Link to="/overview" className="link" />}
                active={(isSelected("/") || isSelected("/overview"))}
                >
                Overview
              </MenuItem>

              <SubMenu
                icon={<PioreactorIcon viewBox="-3 0 24 24"/>}
                component={<Link to="/pioreactors" className="link" />}
                active={isSelected("/pioreactors")}
                label="Pioreactors"
                >

              </SubMenu>

              <MenuItem
                icon={
                      <ViewTimelineOutlinedIcon/>
                  }
                component={<Link to="/experiment-profiles" className="link" />}
                active={isSelected("/experiment-profiles")}
                >
                Profiles
              </MenuItem>

            <Divider sx={{marginTop: "15px", marginBottom: "15px"}} />
          </Menu>
        </div>
        <div>
          <Menu
              style={{minWidth: "230px", width: "230px", height: "100%"}}
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
                  icon={<SettingsOutlinedIcon/> }
                  component={<Link to="/config" className="link" />}
                  active={isSelected("/config")}
                  >
                  Configuration

                </MenuItem>

                <MenuItem
                  icon={<PioreactorsIcon viewBox="0 0 18 19"/> }
                  component={<Link to="/inventory" className="link" />}
                  active={isSelected("/inventory")}
                  >
                  Inventory

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
           </Menu>
        </div>
      </div>
    </Sidebar>
  );
  return (
    <React.Fragment>
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
          <Toolbar variant="dense">
              <IconButton
                color="inherit"
                aria-label="open drawer"
                edge="start"
                onClick={handleDrawerToggle}
                sx={{mr: 2, display: { md: 'none', sm: 'block', xs: "block" }, root: {marginRight: (theme) => theme.spacing(2)}}}
                size="large">
                <MenuIcon />
              </IconButton>

              <Typography variant="h6"  sx={{ flexGrow: 1 }}>
                <Link color="inherit" underline="none" to="/" >
                  <img alt="pioreactor logo" src="/white_colour.png" style={{width: "120px", height: "29px"}}/> <
                /Link>
              </Typography>


              <div>
                { lap &&
                  <Button color="inherit" sx={{textTransform: "none"}}  component={Link}  to={{pathname: "/inventory"}}>
                    <div aria-label="LAP online" className="indicator-dot" style={{boxShadow: "0 0 2px #2FBB39, inset 0 0 12px  #2FBB39"}}/> LAP online
                  </Button>
                }
                <Button  target="_blank" rel="noopener noreferrer" href="https://forums.pioreactor.com" color="inherit" style={{textTransform: "none"}}>
                  <ChatOutlinedIcon style={{ fontSize: 18, verticalAlign: "middle", marginRight: 3 }}/>Forum
                </Button>
                <Button target="_blank" rel="noopener noreferrer" href="https://docs.pioreactor.com" color="inherit" style={{textTransform: "none"}}>
                  <HelpOutlineIcon style={{ fontSize: 18, verticalAlign: "middle", marginRight: 3 }}/>Help
                </Button>
              </div>
          </Toolbar>
        </AppBar>
      <DrawerStyled
        variant="temporary"
        anchor="left"
        open={mobileOpen}
        onClose={handleDrawerToggle}
        ModalProps={{
          keepMounted: true, // Better open performance on mobile.
        }}
        sx={{ display: { xs: 'block', sm: 'block' , md: "none"} }}
      >
        <div style={{minHeight: "60px"}}/>
        {list()}
      </DrawerStyled>
      <DrawerStyled
        variant="permanent"
        open
        sx={{ display: { xs: 'none', sm: 'none', md: "block" } }}
      >
        <Toolbar />
        {list()}
      </DrawerStyled>
    </React.Fragment>
  );
}
