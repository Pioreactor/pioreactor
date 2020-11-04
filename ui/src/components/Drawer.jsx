import React from 'react';
import { makeStyles } from '@material-ui/core/styles';
import SwipeableDrawer from '@material-ui/core/SwipeableDrawer';
import List from '@material-ui/core/List';
import {Typography} from '@material-ui/core';
import ListItem from '@material-ui/core/ListItem';
import ListItemIcon from '@material-ui/core/ListItemIcon';
import ListItemText from '@material-ui/core/ListItemText';
import MenuIcon from '@material-ui/icons/Menu';
import IconButton from '@material-ui/core/IconButton';
import EditIcon from '@material-ui/icons/Edit';
import AddIcon from '@material-ui/icons/Add';
import SaveAltIcon from '@material-ui/icons/SaveAlt';
import SettingsIcon from '@material-ui/icons/Settings';
import DashboardIcon from '@material-ui/icons/Dashboard';
import { BrowserRouter as Router, Switch, Route, Link } from "react-router-dom";


import DialogTitle from '@material-ui/core/DialogTitle';
import Dialog from '@material-ui/core/Dialog';


const useStyles = makeStyles({
  list: {
    width: 250,
  },
  fullList: {
    width: 'auto',
  },
});

export default function Drawer() {
  const classes = useStyles();
  const [isOpen, setIsOpen] = React.useState(false);

  function determineBG(path) {
    return (window.location.pathname === path) ? "rgba(237, 238, 239, 1)" : null
  }



  const toggleDrawer = (open) => (event) => {
    if (event && event.type === 'keydown' && (event.key === 'Tab' || event.key === 'Shift')) {
      return;
    }
    setIsOpen(open);
  };

  const list = () => (
    <div
      role="presentation"
      onClick={toggleDrawer(false)}
      onKeyDown={toggleDrawer(false)}
    >
      <Typography style={{textAlign: "center", paddingTop: "15px"}} className={classes.logo}>
        Morbidostat
      </Typography>
      <List>

        <ListItem href="/" component="a" button key={"dashboard"} style={{backgroundColor: determineBG("/")}}>
          <ListItemIcon><DashboardIcon /> </ListItemIcon>
          <ListItemText primary={"Dashboard"} />
        </ListItem>

        <ListItem href="/download-data" component="a" button key={"download_data"} style={{backgroundColor: determineBG("/download-data")}}>
          <ListItemIcon><SaveAltIcon /> </ListItemIcon>
          <ListItemText primary={"Download experiment data"} />
        </ListItem>

        <ListItem button href="/calibrate"  component="a" key={"calibrate"} style={{backgroundColor: determineBG("/calibrate")}}>
          <ListItemIcon> <SettingsIcon /> </ListItemIcon>
          <ListItemText primary={"Calibrate unit"} />
        </ListItem>
        <ListItem button href="/start-new-experiment"  component="a" key={"start_new_experiment"} style={{backgroundColor: determineBG("/start-new-experiment")}}>
          <ListItemIcon> <AddIcon /> </ListItemIcon>
          <ListItemText primary={"Start new experiment"} />
        </ListItem>
        <ListItem button href="/edit-config"  component="a" key={"edit_config"} style={{backgroundColor: determineBG("/edit-config")}}>
          <ListItemIcon> <EditIcon /> </ListItemIcon>
          <ListItemText primary={"Edit config.ini"} />
        </ListItem>
      </List>
    </div>
  );

  return (
    <div>
      <React.Fragment key={"left"}>
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          onClick={toggleDrawer(true)}
        >
          <MenuIcon />
        </IconButton>

        <SwipeableDrawer
          anchor={"left"}
          open={isOpen}
          onClose={toggleDrawer(false)}
          onOpen={toggleDrawer(true)}
        >
          {list()}
        </SwipeableDrawer>
      </React.Fragment>
    </div>
  );
}
