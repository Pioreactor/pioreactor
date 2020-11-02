import React from 'react'
import {AppBar, Toolbar, Typography} from '@material-ui/core';
import {makeStyles} from '@material-ui/styles';
import Button from '@material-ui/core/Button';
import SwipeableTemporaryDrawer from './Drawer'

const useStyles = makeStyles(() => ({
    logo: {
    },
}));


const Header = () => {
    const classes = useStyles();
    return (
    <AppBar position="static">
        <Toolbar variant="dense">
          <SwipeableTemporaryDrawer />
          <Typography className={classes.logo}>
            Morbidostat
          </Typography>
        </Toolbar>
      </AppBar>
    )
}

export default Header;
