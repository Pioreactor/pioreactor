import React from 'react';
import { styled } from '@mui/material/styles';
import Drawer from '@mui/material/Drawer';
import Badge from '@mui/material/Badge';
import Divider from '@mui/material/Divider';
import MenuIcon from '@mui/icons-material/Menu';
import MenuItemMUI from '@mui/material/MenuItem';
import IconButton from '@mui/material/IconButton';
import DownloadIcon from '@mui/icons-material/Download';
import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined';
import UpdateIcon from '@mui/icons-material/Update';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import EmailOutlinedIcon from '@mui/icons-material/EmailOutlined';
import Toolbar from '@mui/material/Toolbar';
import FormControl from '@mui/material/FormControl';
import Select from '@mui/material/Select';
import Tooltip from '@mui/material/Tooltip';
import ListSubheader from '@mui/material/ListSubheader';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import MuiLink from '@mui/material/Link';
import {AppBar, Typography, Button} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import PioreactorIcon from './PioreactorIcon';
import PioreactorsIcon from './PioreactorsIcon';
//import Icon2x2Grid from './Icon2x2Grid';
import LibraryAddOutlinedIcon from '@mui/icons-material/LibraryAddOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import ViewTimelineOutlinedIcon from '@mui/icons-material/ViewTimelineOutlined';
import ChatOutlinedIcon from '@mui/icons-material/ChatOutlined';
import { Link, useLocation } from 'react-router';
import { Sidebar, Menu, MenuItem, SubMenu} from "react-pro-sidebar";
import { useExperiment } from '../providers/ExperimentContext';
import AddIcon from '@mui/icons-material/Add';
import TuneIcon from '@mui/icons-material/Tune';
import SubdirectoryArrowRightIcon from '@mui/icons-material/SubdirectoryArrowRight';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';
import whiteLogo from '../assets/white_colour.png';

const ExpIcon = PlayCircleOutlinedIcon

const drawerWidth = 230;

export function pathnameMatchesAnySubmenu(pathname, prefixes) {
  return prefixes.some((prefix) => pathname.startsWith(`/${prefix}`));
}

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
          <span>{children}</span>
        </Tooltip>
      ) : (
        children
      )}
    </>
  );
};

const SelectableMenuItem = ({experiment, availableExperiments, selectExperiment}) => {
  const [selectOpen, setSelectOpen] = React.useState(false);
  const [activeExperiments, setActiveExperiments] = React.useState(new Set([]))
  const [hasLoadedActiveExperiments, setHasLoadedActiveExperiments] = React.useState(false);

  const loadActiveExperiments = React.useCallback(async () => {
      if (hasLoadedActiveExperiments) {
        return;
      }

      try {
        const response = await fetch("/api/experiments/assignment_count");
        if (!response.ok) {
          setActiveExperiments(new Set([]));
          setHasLoadedActiveExperiments(true);
          return;
        }

        const data = await response.json();
        if (!Array.isArray(data)) {
          setActiveExperiments(new Set([]));
          setHasLoadedActiveExperiments(true);
          return;
        }

        setActiveExperiments(new Set(data.map(item => item.experiment)));
      } catch (error) {
        console.error("Failed to fetch active experiments:", error);
        setActiveExperiments(new Set([]));
      }
      finally {
        setHasLoadedActiveExperiments(true);
      }
  }, [hasLoadedActiveExperiments]);

  const handleMenuItemClick = (e) => {
    e.stopPropagation()
    void loadActiveExperiments();
    setSelectOpen(true);
  };

  const handleSelectClose = (e) => {
    e.stopPropagation()
    setSelectOpen(false);
  };


  function handleExperimentChange(e) {
    if (e.target.value){
      selectExperiment(e.target.value);
    }

    setSelectOpen(false)
  }
  const experimentsList = Array.isArray(availableExperiments) ? availableExperiments : [];
  const normalizedExperimentsList = experiment && !experimentsList.includes(experiment)
    ? [experiment, ...experimentsList]
    : experimentsList;
  const selectValue = experiment || "";

  return (

    <ConditionalTooltip
      title={experiment}
      condition={experiment && experiment.length > 14}
    >
    <MenuItem
      onClick={handleMenuItemClick}
      icon={<ExpIcon sx={{fontSize: "23px"}} /> }
    >
      <FormControl variant="standard" fullWidth>
        <Select
          open={selectOpen}
          onClose={handleSelectClose}
          value={selectValue}
          label="Experiment"
          onChange={handleExperimentChange}
          renderValue={(val) => {
            if (!val && experiment) return experiment;
            if (!val) return "Select experiment";
            return val;
          }}
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
            <AddIcon sx={{ verticalAlign: 'middle', margin: '0px 3px 0px 0px', fontSize: "21px"}} />
            New experiment
          </MenuItemMUI>
          <Divider />
          <ListSubheader>Active</ListSubheader>
          {normalizedExperimentsList
            .filter((e) => activeExperiments.has(e))
            .map((e) => (
              <MenuItemMUI key={e} value={e}>
                {e}
              </MenuItemMUI>
            ))}
          <Divider />
          <ListSubheader>Inactive</ListSubheader>
          {normalizedExperimentsList
            .filter((e) => !activeExperiments.has(e))
            .map((e) => (
              <MenuItemMUI key={e} value={e}>
                {e}
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
  const [helpDialogOpen, setHelpDialogOpen] = React.useState(false);
  const [version, setVersion] = React.useState(null)
  const [lap, setLAP] = React.useState(false)
  const [latestVersion, setLatestVersion] = React.useState(null)
  const {experimentMetadata, selectExperiment, allExperiments} = useExperiment()
  const allExperimentNames = Array.isArray(allExperiments) ? allExperiments.map((v) => v.experiment) : [];


  React.useEffect(() => {
    const lapTimerId = window.setTimeout(() => {
      fetch("/api/local_access_point")
        .then((response) => response.json())
        .then((data) => {
          setLAP(Boolean(data?.active))
        })
        .catch(() => {});
    }, 1000);

    const currentAppTimerId = window.setTimeout(() => {
      fetch("/unit_api/versions/app")
        .then((response) => response.json())
        .then((data) => {
          setVersion(data['version'])
        })
        .catch(() => {});
    }, 1750);

    const latestVersionTimerId = window.setTimeout(() => {
      // TODO: what happens when there is not internet connection?
      fetch("https://api.github.com/repos/pioreactor/pioreactor/releases/latest")
        .then((response) => response.json())
        .then((data) => {
          setLatestVersion(data['tag_name'])
        }).catch((_e) => {
          // no internet?
        });
    }, 2500);

    return () => {
      window.clearTimeout(lapTimerId);
      window.clearTimeout(currentAppTimerId);
      window.clearTimeout(latestVersionTimerId);
    };
  }, [])

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const openHelpDialog = () => {
    setHelpDialogOpen(true);
  };

  const closeHelpDialog = () => {
    setHelpDialogOpen(false);
  };

  function isSelected(path) {
    return (location.pathname.startsWith(path))
  }


  const list = () => (
    <Sidebar rootStyles={{height: "100%"}} width="230px" backgroundColor="white">
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1}}>

          <Menu
              transitionDuration={0}
              style={{minWidth: "230px", width: "230px", height: "100%"}}
              renderExpandIcon={() => null }
              menuItemStyles={{
                label:  {whiteSpace: "pre-wrap", fontSize: "16px"},
                button: ({ level, active, disabled }) => {
                  const sx = {
                    color: disabled ? '#00000050' : (active ? '#5331ca' : 'inherit'),
                    backgroundColor: active ? '#5331ca14' : undefined,
                    height: "43px",
                    fontWeight: active ? 500 : 400,
                  };
                  if (level === 1){
                    sx.paddingLeft = "27px"
                    sx.color = disabled ? '#00000050' : (active ? '#5331ca' : 'rgb(75, 75, 75)')
                    sx.fontWeight = active ? 500 : 400
                  }
                  return sx
                },
                icon: ({level, active, disabled}) => {
                  return {
                    color: disabled ? '#00000050' : (active ? '#5331ca' : 'rgba(0,0,0, 0.6)'),
                    marginRight: "8px",
                    minWidth: "30px",
                    width: "30px",
                    visibility: (( (level===1 && active) || level===0)  ? "visible" : "hidden")
                  };
                }
              }}
            >
              <SelectableMenuItem
                experiment={experimentMetadata.experiment || ""} // CAM: don't remove the ""
                availableExperiments={allExperimentNames}
                selectExperiment={selectExperiment}
                />

              <MenuItem
                icon={<DashboardOutlinedIcon sx={{fontSize: "23px"}}/>}
                component={<Link to="/overview" className="link" />}
                active={(location.pathname === "/" || isSelected("/overview"))}

                >
                Overview
              </MenuItem>

              <MenuItem
                icon={<PioreactorIcon  sx={{fontSize: "23px"}}/>}
                component={<Link to="/pioreactors" className="link" />}
                active={isSelected("/pioreactors")}
                >
                Pioreactors
              </MenuItem>

              <MenuItem
                component={<Link to="/logs" className="link" />}
                active={isSelected("/logs")}
                icon={<ListAltOutlinedIcon  sx={{fontSize: "23px"}}/>}
                >
                Event logs
              </MenuItem>

              <MenuItem
                icon={
                      <ViewTimelineOutlinedIcon  sx={{fontSize: "23px"}}/>
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
              transitionDuration={0}
              style={{minWidth: "230px", width: "230px", height: "100%"}}
              renderExpandIcon={() => null }
              menuItemStyles={{
                label:  {whiteSpace: "pre-wrap", fontSize: "16px"},
                button: ({ level, active, disabled }) => {
                  const sx = {
                    color: disabled ? '#00000050' : (active ? '#5331ca' : 'inherit'),
                    backgroundColor: active ? '#5331ca14' : undefined,
                    height: "43px",
                    fontWeight: active ? 500 : 400,
                  };
                  if (level === 1){
                    sx.paddingLeft = "27px"
                    sx.color = disabled ? '#00000050' : (active ? '#5331ca' : 'rgb(75, 75, 75)')
                    sx.fontWeight = active ? 500 : 400
                  }
                  return sx
                },
                icon: ({level, active, disabled}) => {
                  return {
                    color: disabled ? '#00000050' : (active ? '#5331ca' : 'rgba(0,0,0, 0.6)'),
                    marginRight: "8px",
                    minWidth: "30px",
                    width: "30px",
                    visibility: (( (level===1 && active) || level===0)  ? "visible" : "hidden")

                  };
                }
              }}
            >

                <MenuItem
                  icon={<SettingsOutlinedIcon sx={{fontSize: "23px"}}/> }
                  component={<Link to="/config" className="link" />}
                  active={isSelected("/config")}

                >
                  Configuration
                </MenuItem>

                <SubMenu label="Inventory"
                  open={pathnameMatchesAnySubmenu(location.pathname, ["inventory", "leader", "system-logs"])}
                  icon={<PioreactorsIcon sx={{fontSize: "23px"}} />}
                  component={<Link to="/inventory" className="link" />}
                  active={isSelected("/inventory")}

                >
                  <MenuItem
                    component={<Link to="/leader" className="link" />}
                    active={isSelected("/leader")}
                    icon={<SubdirectoryArrowRightIcon  sx={{fontSize: "23px"}}/>}
                    >
                    Leader
                  </MenuItem>
                  <MenuItem
                    component={<Link to="/system-logs" className="link" />}
                    active={isSelected("/system-logs")}
                    icon={<SubdirectoryArrowRightIcon  sx={{fontSize: "23px"}}/>}
                    >
                    System logs
                  </MenuItem>

                </SubMenu>

                <SubMenu  label="Calibrations"
                  open={
                    pathnameMatchesAnySubmenu(location.pathname, ["calibrations", "protocols", "estimators"]) ||
                    isSelected("/calibration-coverage")
                  }
                  icon={<TuneIcon sx={{fontSize: "23px"}}/> }
                  component={<Link to="/calibrations" className="link" />}
                  active={isSelected("/calibrations") || isSelected("/estimators") || isSelected("/protocols") || isSelected("/calibration-coverage")}

                  >
                  <MenuItem
                    component={<Link to="/protocols" className="link" />}
                    active={isSelected("/protocols")}
                    icon={<SubdirectoryArrowRightIcon  sx={{fontSize: "23px"}}/>}
                    >
                    Protocols
                  </MenuItem>
                  <MenuItem
                    component={<Link to="/estimators" className="link" />}
                    active={isSelected("/estimators")}
                    icon={<SubdirectoryArrowRightIcon  sx={{fontSize: "23px"}}/>}
                    >
                    Estimators
                  </MenuItem>
                </SubMenu>

                <MenuItem
                  icon={<PlayCircleOutlinedIcon sx={{fontSize: "23px"}}/> }
                  component={<Link to="/experiments" className="link" />}
                  active={isSelected("/experiments")}

                  >
                  Experiments
                </MenuItem>

                <MenuItem
                  icon={<DownloadIcon sx={{fontSize: "23px"}}/> }
                  component={<Link to="/export-data" className="link" />}
                  active={isSelected("/export-data")}

                  >
                  Export data
                </MenuItem>


                <MenuItem
                  icon={<LibraryAddOutlinedIcon sx={{fontSize: "23px"}}/> }
                  component={<Link to="/plugins" className="link" />}
                  active={isSelected("/plugins")}

                  >
                  Plugins
                </MenuItem>

                <MenuItem
                  icon={
                    <Badge variant="dot" color="secondary" invisible={!((version) && (latestVersion) && (version !== latestVersion))}>
                        <UpdateIcon sx={{fontSize: "23px"}}/>
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
                  <img alt="pioreactor logo" src={whiteLogo} style={{width: "120px", height: "29px"}}/>
                </Link>
              </Typography>


              <div>
                { lap &&
                  <Button color="inherit" sx={{textTransform: "none"}}  component={Link}  to={{pathname: "/inventory"}}>
                    <div aria-label="LAP online" className="indicator-dot" style={{boxShadow: "0 0 2px #2FBB39, inset 0 0 12px  #2FBB39"}}/> LAP online
                  </Button>
                }
                <Button onClick={openHelpDialog} color="inherit" style={{textTransform: "none"}}>
                  <HelpOutlineIcon style={{ fontSize: 18, verticalAlign: "middle", marginRight: 3 }}/>Help
                </Button>
              </div>
          </Toolbar>
        </AppBar>
      <Dialog open={helpDialogOpen} onClose={closeHelpDialog} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ pr: 6 }}>
          Help
          <IconButton
            aria-label="Close"
            onClick={closeHelpDialog}
            sx={{ position: "absolute", right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} divider={<Divider flexItem />} sx={{ pt: 1 }}>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <DescriptionOutlinedIcon fontSize="small" color="action" />
                <Typography variant="subtitle2">Documentation</Typography>
              </Stack>
              <Typography variant="body1">
                Looking for setup instructions, how-to guides, or reference material? Our documentation is available at{" "}
                <MuiLink href="https://docs.pioreactor.com/user-guide/introduction" target="_blank" rel="noopener noreferrer">
                  docs.pioreactor.com
                </MuiLink>
                .
              </Typography>
            </Stack>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <ChatOutlinedIcon fontSize="small" color="action" />
                <Typography variant="subtitle2">Community forum</Typography>
              </Stack>
              <Typography variant="body1">
                You can also visit our community forum to browse discussions, share ideas, and learn from other Pioreactor users at{" "}
                <MuiLink href="https://forum.pioreactor.com" target="_blank" rel="noopener noreferrer">
                  forum.pioreactor.com
                </MuiLink>
                .
              </Typography>
            </Stack>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <EmailOutlinedIcon fontSize="small" color="action" />
                <Typography variant="subtitle2">Email support</Typography>
              </Stack>
              <Typography variant="body1">
                If you have a question about your Pioreactor, run into an issue, or want direct help from our team, email us at{" "}
                <MuiLink href="mailto:support@pioreactor.com">
                  support@pioreactor.com
                </MuiLink>
                It's especially helpful if you can provide your software version, hardware version, and any screenshots in the email, too.
                .
              </Typography>
            </Stack>
          </Stack>
        </DialogContent>
      </Dialog>
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
