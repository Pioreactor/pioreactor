import clsx from 'clsx';

import React from "react";
import MarkdownView from 'react-showdown';

import Grid from '@mui/material/Grid';
import { makeStyles } from '@mui/styles';
import { styled } from '@mui/material/styles';
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
import FolderZipIcon from '@mui/icons-material/FolderZip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import CloseIcon from '@mui/icons-material/Close';

const VisuallyHiddenInput = styled('input')({
  clip: 'rect(0 0 0 0)',
  clipPath: 'inset(50%)',
  height: 1,
  overflow: 'hidden',
  position: 'absolute',
  bottom: 0,
  left: 0,
  whiteSpace: 'nowrap',
  width: 1,
});

const lostRed = "#DE3618"

const useStyles = makeStyles((theme) => ({
  lostRed: {
    color: lostRed
  },
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


function UploadArchiveAndConfirm(props) {
  const classes = useStyles()
  const [selectedFile, setSelectedFile] = React.useState(null);
  const [errorMsg, setErrorMsg] = React.useState(null);
  const handleClose = props.onClose

  const handleFileChange = (event) => {
    const file = event.target.files[0]

    if (/^release_\d{0,2}\.\d{0,2}\.\d{0,2}\w{0,6}\.zip$/.test(file.name)) {
      setSelectedFile(event.target.files[0]);
      setErrorMsg(null)
    }
    else {
      setErrorMsg("Not a valid release zip file. It should be a zip file, starting with `release_`.")
    }
  };

  const handleFileUpload = async () => {
    const formData = new FormData();
    formData.append('file', selectedFile);
    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        // Handle non-2xx responses here
        const errorData = await response.json();
        throw new Error(errorData.error || 'Upload failed with status ' + response.status);
      }

      const data = await response.json();
      return data.save_path;
    } catch (error) {
      setErrorMsg(error.message)
      return null;
    }
  };

  const handleUpdate = async (savePath) => {
    try {
      await fetch("/api/update_app_from_release_archive", {
        method: "POST",
        body: JSON.stringify({ release_archive_location: savePath }),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
      });
    } catch (error) {
      console.error(error);
    }
  };

  const handleUploadClick = async () => {
    const savePath = await handleFileUpload();

    if (savePath === null) {
      // Exit the function if there was a problem in handleFileUpload
      return;
    }

    await handleUpdate(savePath);
    handleClose();
    props.onSuccess()
  }



  return (
    <React.Fragment>
      <Dialog
        open={true}
        onClose={handleClose}
        aria-labelledby="alert-dialog-title"
        aria-describedby="alert-dialog-description"
      >
        <DialogTitle id="alert-dialog-title">
          {props.title}
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="alert-dialog-description">
            {props.description}
            <br/>
            <br/>
            <Button component="label" style={{textTransform: 'none'}}>Choose zip file <VisuallyHiddenInput onChange={handleFileChange} accept=".zip" type="file" /></Button>
            {selectedFile == null ? "" : selectedFile.name}
            <div style={{minHeight: "30px", alignItems: "center", display: "flex"}}>
              {errorMsg   ? <p><CloseIcon className={clsx(classes.textIcon, classes.lostRed)}/>{errorMsg}</p>           : <React.Fragment/>}
            </div>
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} color="secondary">Cancel</Button>
          <Button disabled={selectedFile == null} onClick={handleUploadClick}>Update</Button>
        </DialogActions>
      </Dialog>
    </React.Fragment>
  );
}


function UpdateSoftwareConfirmDialog(props) {
  const confirm = useConfirm();
  const [updating, setUpdating] = React.useState(false)
  const [openSnackbar, setOpenSnackbar] = React.useState(false)
  const [installOption, setInstallOption] = React.useState("latest")
  const [showArchiveConfirm, setShowArchiveConfirm] = React.useState(false);

  const updateVersion = () => {
    setOpenSnackbar(true)
    if (installOption === "development"){
      fetch("/api/update_app_to_develop", {method: "POST"})
    } else if (installOption === "latest") {
      fetch("/api/update_app", {method: "POST"})
    }
  }

  const handleClick = () => {
    if (installOption === "archive") {
      // Open the UploadArchiveAndConfirm dialog
      setShowArchiveConfirm(true);
    }
    else {
      confirm({
        description: getDescription(),
        title: getTitle(),
        confirmationText: "Update",
        confirmationButtonProps: {color: "primary"},
        cancellationButtonProps: {color: "secondary"}, //style: {textTransform: 'none'}
        }).then(() => {
          updateVersion();
          setUpdating(true)
        }
      )
    }
  };

  const getIcon = () =>{
    if ( installOption ==="development"){
      return <ScienceIcon/>
    }
    else if (installOption === "latest") {
      return <UpdateIcon/>
    }
    else if (installOption === "archive"){
      return <FolderZipIcon/>
    }
  }

  const getTitle = () => {
    if (installOption === "development"){
      return "Update to development build?"
    }
    else if (installOption === "latest") {
      return "Update to next release?"
    }
    else if (installOption === "archive"){
      return "Update from zip file?"
    }
  }

  const getDescription = () => {
    if (installOption === "development"){
      return "This requires an internet connection. To avoid possible data interruptions, we suggest updating between running experiments. We also recommend being on the latest release of software before doing this. Check you are on the latest software before updating."
    }
    else if (installOption === "latest") {
      return "This requires an internet connection. To avoid possible data interruptions, we suggest updating between running experiments."
    }
    else if (installOption === "archive"){
      return "You can update the Pioreactor software from our pre-built zip files. Choose the file below. To avoid possible data interruptions, we suggest updating between running experiments. "
    }
  }

  return (
    <React.Fragment>
      <SelectButton
        buttonStyle={{textTransform: 'none'}}
        value={installOption}
        onClick={handleClick}
        onChange={({ target: { value } }) =>
          setInstallOption(value)
        }
        disabled={updating}
        endIcon={getIcon()}
      >
        <MenuItem value={"latest"}>Update to next release</MenuItem>
        <MenuItem value={"development"}>Update to development</MenuItem>
        <MenuItem value={"archive"}>Update from zip file</MenuItem>
      </SelectButton>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        message="Updating in the background. This may take a few minutes. You may leave this page."
        autoHideDuration={20000}
        key="snackbar-update"
      />
      {showArchiveConfirm && (
        <UploadArchiveAndConfirm
          title={getTitle()}
          description={getDescription()}
          onSuccess={() => setOpenSnackbar(true)}
          onClose={() => setShowArchiveConfirm(false)}
        />
      )}
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
        })
        .catch(e => {
          console.log("No internet connection?")
        })
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
            <UpdateSoftwareConfirmDialog />
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
        }
        ).catch(e => {
          // no internet?
          setChangelog(`
Could not retrieve latest Changelog. Perhaps not connected to the internet.
 - You can find the latest changelog at this url: [https://github.com/pioreactor/pioreactor/master/CHANGELOG.md](https://github.com/pioreactor/pioreactor/master/CHANGELOG.md)
 - To update to the latest version of Pioreactor software, even without internet, see documentation here: [https://docs.pioreactor.com/user-guide/common-questions#im-using-a-local-access-point-but-id-like-to-install-plugins-update-software-etc](https://docs.pioreactor.com/user-guide/common-questions#im-using-a-local-access-point-but-id-like-to-install-plugins-update-software-etc).
          `)
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

