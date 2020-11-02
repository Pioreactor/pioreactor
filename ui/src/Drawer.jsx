import React from 'react';
import clsx from 'clsx';
import { makeStyles } from '@material-ui/core/styles';
import SwipeableDrawer from '@material-ui/core/SwipeableDrawer';
import Button from '@material-ui/core/Button';
import List from '@material-ui/core/List';
import Divider from '@material-ui/core/Divider';
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

const useStyles = makeStyles({
  list: {
    width: 250,
  },
  fullList: {
    width: 'auto',
  },
});

export default function SwipeableTemporaryDrawer() {
  const classes = useStyles();
  const [isOpen, setIsOpen] = React.useState(false);

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
        <ListItem button key={"download_data"}>
          <ListItemIcon><SaveAltIcon /> </ListItemIcon>
          <ListItemText primary={"Download experiment data"} />
        </ListItem>
        <ListItem button key={"calibrate"}>
          <ListItemIcon> <SettingsIcon /> </ListItemIcon>
          <ListItemText primary={"Calibrate unit"} />
        </ListItem>
        <ListItem button key={"start_new_experiment"}>
          <ListItemIcon> <AddIcon /> </ListItemIcon>
          <ListItemText primary={"Start new experiment"} />
        </ListItem>
        <ListItem button key={"edit_config"}>
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
