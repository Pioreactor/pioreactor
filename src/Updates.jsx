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
import MenuItem from '@mui/material/MenuItem';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { useConfirm } from 'material-ui-confirm';
import UnderlineSpan from "./components/UnderlineSpan";
import SelectButton from "./components/SelectButton";
import ScienceIcon from '@mui/icons-material/Science';

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
  const [installDev, setInstallDev] = React.useState(false)

  const updateVersion = () => {
    setOpenSnackbar(true)
    if (installDev){
      fetch("/api/update_app_to_develop", {method: "POST"})
    } else {
      fetch("/api/update_app", {method: "POST"})
    }
  }

  const handleClick = () => {
    confirm({
      description: 'To avoid possible data interruptions, we suggest updating between running experiments. ' + (installDev ? "We recommend being on the latest release of software before doing this. Confirm you are before updating." : ""),
      title: installDev ? "Update to development?" : "Update to next release?" ,
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
      <SelectButton
        buttonStyle={{textTransform: 'none'}}
        value={installDev ? "development" : "latest"}
        onClick={handleClick}
        onChange={({ target: { value } }) =>
          setInstallDev(value === "development")
        }
        disabled={updating}
        endIcon={installDev ? <ScienceIcon /> :  <UpdateIcon />}
      >
        <MenuItem value={"latest"}>Update to next release</MenuItem>
        <MenuItem value={"development"}>Update to development</MenuItem>
      </SelectButton>
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
  const [uiVersion, setUIVersion] = React.useState("")
  const [latestVersion, setLatestVersion] = React.useState("")

  React.useEffect(() => {
    async function getCurrentAppVersion() {
         await fetch("/api/versions/app")
        .then((response) => {
          return response.text();
        })
        .then((data) => {
          setVersion(data)
        });
      }

    async function getCurrentUIVersion() {
         await fetch("/api/versions/ui")
        .then((response) => {
          return response.text();
        })
        .then((data) => {
          setUIVersion(data)
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

      getCurrentUIVersion()
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
        <div>
          <div style={{float: "right", marginRight: "0px", marginLeft: "10px"}}>
            <UpdateToLatestConfirmDialog />
          </div>
          <Link color="inherit" underline="none" href={`https://github.com/Pioreactor/pioreactor/releases/tag/${latestVersion}`} target="_blank" rel="noopener noreferrer">
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
          <UnderlineSpan title={`App: ${version}\nUI:  ${uiVersion}`}> {version} </UnderlineSpan>
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
          setChangelog("Could not request latest Changelog. Missing internet connection?")
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

