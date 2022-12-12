import React from "react";
import MarkdownView from 'react-showdown';

import Grid from '@mui/material/Grid';
import { makeStyles } from '@mui/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';
import {Typography} from '@mui/material';
import Snackbar from '@mui/material/Snackbar';
import Link from '@mui/material/Link';
import UpdateIcon from '@mui/icons-material/Update';
import Divider from '@mui/material/Divider';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { useConfirm } from 'material-ui-confirm';
import LoadingButton from '@mui/lab/LoadingButton';

const useStyles = makeStyles((theme) => ({
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "10px"
  },
  pos: {
    marginBottom: 0,
  },
  textIcon: {
    fontSize: 15,
    verticalAlign: "middle",
    margin: "0px 3px"
  },
}));


function UpdateToLatestConfirmDialog(props) {
  const confirm = useConfirm();
  const [updating, setUpdating] = React.useState(false)
  const [openSnackbar, setOpenSnackbar] = React.useState(false)

  const updateVersion = () => {
    setOpenSnackbar(true)
    fetch("/api/update_app", {method: "POST"})
  }

  const handleClick = () => {
    confirm({
      description: 'Updating will not stop or change currently running activities or experiments.',
      title: "Update to latest release?",
      confirmationText: "Update now",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},

      }).then(() => {
        updateVersion();
        setUpdating(true)
      }
    )
  };

  return (
    <React.Fragment>
      <LoadingButton
        onClick={handleClick}
        style={{textTransform: 'none', float: "right", marginRight: "0px", marginLeft: "10px"}}
        color="primary"
        variant="contained"
        endIcon={<UpdateIcon/>}
        disabled={!props.isAvailable}
        loading={updating}
        loadingPosition="end"
        >
          Update to latest release
      </LoadingButton>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        message="Updating in the background - you may leave this page"
        autoHideDuration={20000}
        key="snackbar-update"
      />
    </React.Fragment>
  );
}


function PageHeader(props) {
  const classes = useStyles();
  const [version, setVersion] = React.useState("")
  const [latestVersion, setLatestVersion] = React.useState("")

  React.useEffect(() => {
    async function getCurrentAppVersion() {
         await fetch("/api/get_app_version")
        .then((response) => {
          return response.text();
        })
        .then((data) => {
          setVersion(data)
        });
      }

    async function getLatestAppVersion() {
         await fetch("https://api.github.com/repos/pioreactor/pioreactor/releases/latest")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setLatestVersion(data['tag_name'])
        });
      }

      getCurrentAppVersion()
      getLatestAppVersion()
  }, [])

  return (
    <div>
      <div style={{display: "flex", justifyContent: "space-between", marginBottom: "5px"}}>
        <Typography variant="h5" component="h1">
          <Box fontWeight="fontWeightBold">
            Updates
          </Box>
        </Typography>
        <div >
          <UpdateToLatestConfirmDialog isAvailable={(version !== "") && (latestVersion !== "") && (version !== latestVersion) } />
          <Link color="inherit" underline="none" href="https://github.com/Pioreactor/pioreactor/releases" target="_blank" rel="noopener noreferrer">
            <Button style={{textTransform: 'none', float: "right", marginRight: "0px"}} color="primary">
              <OpenInNewIcon fontSize="15" classes={{root: classes.textIcon}}/> View latest release
            </Button>
          </Link>
        </div>
      </div>
      <Divider/>
      <Typography variant="subtitle2">

        <Box fontWeight="fontWeightBold" style={{margin: "10px 2px 10px 2px", display:"inline-block"}}>
          <SystemUpdateAltIcon style={{ fontSize: 14, verticalAlign: "-1px" }}/> Version installed:
        </Box>
        <Box fontWeight="fontWeightRegular" style={{marginRight: "20px", display:"inline-block"}}>
          {version}
        </Box>

        <Box fontWeight="fontWeightBold" style={{margin: "10px 2px 10px 2px", display:"inline-block"}}>
            <UpdateIcon style={{ fontSize: 14, verticalAlign: "-1px" }}/>
          Latest version available:
        </Box>
        <Box fontWeight="fontWeightRegular" style={{marginRight: "20px", display:"inline-block"}}>
          {latestVersion}
        </Box>

      </Typography>
    </div>
  )
}



function ChangelogContainer(){
  const classes = useStyles();

  const [changelog, setChangelog] = React.useState("")

  React.useEffect(() => {
    async function getData() {
         await fetch("https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md")
        .then((response) => {
          return response.text();
        })
        .then((data) => {
          setChangelog(data)
        }).catch(e => {
          // no internet?
          setChangelog("Could not find changelog. Are you connected to the internet?")
        })
      }
      getData()
  }, [])


  return(
    <React.Fragment>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
        <Typography variant="h6" component="h6">
            Change log
        </Typography>
          <MarkdownView
            markdown={changelog}
          />
        </CardContent>
      </Card>
    </React.Fragment>
)}


function Updates(props) {
    React.useEffect(() => {
    document.title = props.title;
  }, [props.title])
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <PageHeader/>
            <ChangelogContainer/>
          </Grid>
        </Grid>
    )
}

export default Updates;

